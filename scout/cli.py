"""Command-line entry points: `scout <command>`."""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

import typer
from rich.console import Console
from rich.table import Table

from scout.config import Settings, get_settings
from scout.db import repo
from scout.db.base import make_engine, make_session_factory
from scout.db.models import FieldCheck
from scout.db.repo import FactIn
from scout.director.planner import PHASES
from scout.director.run import run_once
from scout.seeds import seed_all
from scout.worker.profiles import PROFILES

app = typer.Typer(help="Kosovo Gap Scout", no_args_is_help=True)
field_check_app = typer.Typer(help="Founder field checks")
app.add_typer(field_check_app, name="field-check")
console = Console()


def session_factory(settings: Settings):
    return make_session_factory(make_engine(settings.database_url))


def _local_today(settings: Settings) -> date:
    """Kosovo local calendar date (settings.timezone), never the UTC date."""
    return datetime.now(UTC).astimezone(ZoneInfo(settings.timezone)).date()


@app.command("init-db")
def init_db() -> None:
    """Apply database migrations (alembic upgrade head)."""
    from alembic.config import Config

    from alembic import command

    command.upgrade(Config("alembic.ini"), "head")
    console.print("database at head")


@app.command()
def seed() -> None:
    """Insert sectors, culture themes, sources and the starting country digest."""
    with session_factory(get_settings())() as s:
        console.print(seed_all(s))


@app.command()
def run(
    budget: float | None = typer.Option(None, help="Override today's cap in EUR"),
    phase: str | None = typer.Option(None, help="foundation | verification | maintenance"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Plan only; run nothing"),
) -> None:
    """Run today's cycle: plan → research → judge → brief."""
    settings = get_settings()
    summary = run_once(
        settings,
        today=None,
        budget_override=Decimal(str(budget)) if budget is not None else None,
        phase_override=phase,
        dry_run=dry_run,
    )
    console.print(
        f"run #{summary.run_id} {summary.day} phase={summary.phase} planned={summary.planned} "
        f"done={summary.done} failed={summary.failed} spent=€{summary.spent_eur} "
        f"({summary.stopped_reason})"
    )
    console.print(summary.brief_md)


@app.command()
def brief() -> None:
    """Print the latest brief."""
    with session_factory(get_settings())() as s:
        b = repo.latest_brief(s)
        console.print(b.markdown if b else "no brief yet")


@app.command()
def status() -> None:
    """Show spend, queue, top gaps and open field checks."""
    settings = get_settings()
    with session_factory(settings)() as s:
        today = _local_today(settings)
        last = repo.last_run(s)
        console.print(
            f"last run: {last.day if last else '-'} status={last.status if last else '-'}; "
            f"spent today €{repo.spent_on(s, today)}; "
            f"month €{repo.spent_between(s, today.replace(day=1), today)}; "
            f"queued: {len(repo.queued_tasks(s))}"
        )
        table = Table("id", "gap", "status", "score", "conf", "presence")
        statuses = ["candidate", "verifying", "verified", "parked"]
        for g in repo.list_gaps(s, statuses=statuses)[:10]:
            table.add_row(
                str(g.id),
                g.title,
                g.status,
                str(g.score_total),
                f"{g.confidence:.2f}",
                g.presence_level,
            )
        console.print(table)
        for fc in repo.open_field_checks(s):
            console.print(f"field check #{fc.id}: {fc.question}")


@app.command("add-task")
def add_task(
    profile: str,
    sector: str | None = typer.Option(None),
    gap_id: int | None = typer.Option(None),
    theme: str | None = typer.Option(None),
    priority: int = typer.Option(70),
) -> None:
    """Queue a task for the next run."""
    if profile not in PROFILES and profile != "chart-diff":
        raise typer.BadParameter(f"profile must be one of {', '.join([*PROFILES, 'chart-diff'])}")
    with session_factory(get_settings())() as s:
        payload: dict = {}
        if sector:
            sec = repo.get_sector(s, sector)
            if sec is None:
                raise typer.BadParameter(f"unknown sector {sector}")
            payload = {"sector": sec.slug, "sector_name": sec.name_en}
        if gap_id is not None:
            gap = repo.get_gap(s, gap_id)
            if gap is None:
                raise typer.BadParameter(f"unknown gap {gap_id}")
            sec = next((x for x in repo.list_sectors(s) if x.id == gap.sector_id), None)
            payload = {"gap_id": gap.id, "gap_title": gap.title, "sector": sec.slug if sec else ""}
        if theme:
            payload = {"theme": theme, "theme_name": theme.replace("-", " ")}
        est = PROFILES[profile].est_cost_eur if profile in PROFILES else Decimal("0.05")
        t = repo.enqueue_task(
            s, profile=profile, payload=payload, priority=priority, est_cost_eur=est
        )
        console.print(f"queued task #{t.id} {profile} {payload}")


@field_check_app.command("answer")
def field_check_answer(check_id: int, answer: str) -> None:
    """Record the founder's answer as a high-confidence fact and re-queue verification of the gap."""
    with session_factory(get_settings())() as s:
        fc = s.get(FieldCheck, check_id)
        if fc is None or fc.status != "open":
            raise typer.BadParameter(f"no open field check #{check_id}")
        now = datetime.now(UTC)
        gap = repo.get_gap(s, fc.gap_id) if fc.gap_id else None
        sec = next((x for x in repo.list_sectors(s) if gap and x.id == gap.sector_id), None)
        repo.upsert_fact(
            s,
            FactIn(
                claim=f"Founder field check — Q: {fc.question} A: {answer}",
                entity_type="gap",
                entity_key=f"gap:{fc.gap_id}" if fc.gap_id else "general",
                confidence=0.95,
                sector_slug=sec.slug if sec else None,
                ttl_days=180,
                source_name="founder",
            ),
            run_id=None,
            observed_at=now,
        )
        repo.answer_field_check(s, fc, answer=answer, answered_at=now)
        if gap is not None:
            repo.enqueue_task(
                s,
                profile="verify-gap",
                priority=90,
                est_cost_eur=PROFILES["verify-gap"].est_cost_eur,
                payload={
                    "gap_id": gap.id,
                    "gap_title": gap.title,
                    "sector": sec.slug if sec else "",
                },
            )
        console.print(
            f"answered #{check_id}; verify-gap queued" if gap else f"answered #{check_id}"
        )


@app.command("chart-diff")
def chart_diff_cmd() -> None:
    """Run the app-chart diff now and print the leads (no model call)."""
    from scout.worker.chart_diff import run_chart_diff

    settings = get_settings()
    with session_factory(settings)() as s:
        report = run_chart_diff(s, _local_today(settings))
        for lead in report.leads:
            console.print(
                f"{lead.store} {lead.app_key} {lead.name} — {','.join(lead.countries)} "
                f"(best rank {lead.best_rank})"
            )
        console.print(f"snapshots {report.snapshots_saved}; errors {report.errors}")


@app.command("flag-gap")
def flag_gap(gap_id: int, unflag: bool = typer.Option(False, "--unflag")) -> None:
    """Ask for one re-verification of a gap ("verify this"): one flagged gap per day is verified first, in
    every phase, and the flag clears when that verify-gap completes. --unflag withdraws the request."""
    with session_factory(get_settings())() as s:
        if repo.get_gap(s, gap_id) is None:
            raise typer.BadParameter(f"unknown gap {gap_id}")
        flagged = list(repo.get_setting(s, "flagged_gaps", []) or [])
        flagged = [g for g in flagged if g != gap_id] if unflag else sorted(set(flagged) | {gap_id})
        repo.set_setting(s, "flagged_gaps", flagged)
        console.print(f"flagged gaps: {flagged}")


@app.command("set-phase")
def set_phase(phase: str) -> None:
    """Switch phase: foundation | verification | maintenance."""
    if phase not in PHASES:
        raise typer.BadParameter(f"phase must be one of {', '.join(PHASES)}")
    with session_factory(get_settings())() as s:
        repo.set_setting(s, "phase", {"value": phase})
        console.print(f"phase = {phase}")
