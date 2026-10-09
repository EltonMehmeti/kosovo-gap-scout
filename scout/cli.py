"""Command-line entry points: `scout <command>`."""

from __future__ import annotations

import signal
from datetime import UTC, date, datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

import typer
from rich.console import Console
from rich.table import Table

from scout import founder
from scout.config import Settings, get_settings
from scout.db import repo
from scout.db.base import make_engine, make_session_factory
from scout.director.run import run_once
from scout.founder import FounderError
from scout.seeds import seed_all

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


def sigterm_to_exit(signum, frame) -> None:
    """SIGTERM (Render stopping the job) becomes SystemExit(143), so run_once's `except BaseException`
    closes the run row as failed and releases its task instead of leaving them `running`."""
    raise SystemExit(143)


def install_sigterm_handler():
    """Install sigterm_to_exit; returns the previous handler so the caller can restore it."""
    return signal.signal(signal.SIGTERM, sigterm_to_exit)


@app.command()
def run(
    budget: float | None = typer.Option(None, help="Override today's cap in EUR"),
    phase: str | None = typer.Option(None, help="foundation | verification | maintenance"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Plan only; run nothing"),
) -> None:
    """Run today's cycle: plan → research → judge → brief."""
    settings = get_settings()
    previous = install_sigterm_handler()
    try:
        summary = run_once(
            settings,
            today=None,
            budget_override=Decimal(str(budget)) if budget is not None else None,
            phase_override=phase,
            dry_run=dry_run,
        )
    finally:
        signal.signal(signal.SIGTERM, previous)
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
    settings = get_settings()
    with session_factory(settings)() as s:
        try:
            t = founder.add_task(
                s,
                profile,
                today=_local_today(settings),
                sector=sector,
                gap_id=gap_id,
                theme=theme,
                priority=priority,
            )
        except FounderError as e:
            raise typer.BadParameter(str(e)) from None
        console.print(f"queued task #{t.id} {profile} {t.payload}")


@field_check_app.command("answer")
def field_check_answer(check_id: int, answer: str) -> None:
    """Record the founder's answer as a high-confidence fact and re-queue verification of the gap."""
    settings = get_settings()
    with session_factory(settings)() as s:
        try:
            fc = founder.answer_field_check(
                s, check_id, answer, today=_local_today(settings), now=datetime.now(UTC)
            )
        except FounderError as e:
            raise typer.BadParameter(str(e)) from None
        console.print(
            f"answered #{check_id}; verify-gap queued" if fc.gap_id else f"answered #{check_id}"
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
    settings = get_settings()
    with session_factory(settings)() as s:
        try:
            ids = founder.flag_gap(s, gap_id, today=_local_today(settings), unflag=unflag)
        except FounderError as e:
            raise typer.BadParameter(str(e)) from None
        console.print(f"flagged gaps: {ids}")


@app.command("set-phase")
def set_phase(phase: str) -> None:
    """Switch phase: foundation | verification | maintenance."""
    settings = get_settings()
    with session_factory(settings)() as s:
        try:
            founder.set_phase(s, phase, today=_local_today(settings))
        except FounderError as e:
            raise typer.BadParameter(str(e)) from None
        console.print(f"phase = {phase}")


@app.command("set-cap")
def set_cap(eur: str = typer.Argument("", help="EUR for today; empty clears")) -> None:
    """Set (or clear) today's spend cap; the next run uses it instead of the phase cap."""
    settings = get_settings()
    with session_factory(settings)() as s:
        try:
            value = founder.set_today_cap(s, eur, today=_local_today(settings))
        except FounderError as e:
            raise typer.BadParameter(str(e)) from None
        console.print(f"today's cap = €{value}" if value is not None else "today's cap cleared")
