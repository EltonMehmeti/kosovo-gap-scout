"""The Director: plan the day, run tasks one at a time, judge, write, remember. Exits when done."""

from __future__ import annotations

import json
import sys
import traceback
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

import anthropic

from scout.budget.guard import BudgetExceeded, BudgetGuard
from scout.config import Settings
from scout.db import repo
from scout.db.base import make_engine, make_session_factory
from scout.director.planner import CHART_DIFF_EST, PHASE_RULES, _key, load_state, plan_tasks
from scout.editor.brief import write_brief
from scout.extract.extractor import Extractor
from scout.llm.gateway import LLM, LLMError
from scout.sources import apple, play
from scout.sources.askdata import AskDataClient
from scout.sources.places import PlacesClient
from scout.strategy.schemas import DirectorReview
from scout.strategy.strategist import Strategist
from scout.worker.chart_diff import classify_and_record, run_chart_diff
from scout.worker.profiles import PROFILES, build_brief, build_system, journal_markdown
from scout.worker.research import ResearchWorker
from scout.worker.tools import ToolContext

REVIEW_EST = Decimal("0.10")
REVIEW_SYSTEM = (
    "You review the day's research plan for Kosovo Gap Scout. You may DROP tasks that duplicate "
    "recent work (see the journal) or REORDER them so the most decision-relevant run first. You may "
    "not add tasks. Keep every task unless you have a concrete reason."
)


@dataclass
class RunSummary:
    run_id: int
    day: date
    phase: str
    planned: int
    done: int
    failed: int
    spent_eur: Decimal
    brief_md: str
    stopped_reason: str


def review_plan(llm: LLM, tasks: list, *, journal_md: str) -> tuple[list, list[str]]:
    """Opus may drop or reorder (never add). Returns (kept tasks in order, notes for the journal)."""
    payload = {
        "tasks": [
            {
                "id": t.id,
                "profile": t.profile,
                "payload": t.payload,
                "priority": t.priority,
                "est_cost_eur": str(t.est_cost_eur),
            }
            for t in tasks
        ],
        "journal": journal_md,
    }
    res = llm.parse(
        model="claude-opus-5-5",
        output_format=DirectorReview,
        system=REVIEW_SYSTEM,
        user=json.dumps(payload, sort_keys=True, ensure_ascii=False),
        max_tokens=1024,
        effort="medium",
        est_eur=REVIEW_EST,
    )
    review: DirectorReview = res.parsed
    by_id = {t.id: t for t in tasks}
    notes: list[str] = []
    dropped_ids = set()
    for d in review.dropped:
        t = by_id.get(d.task_id)
        if t is None:
            continue
        dropped_ids.add(t.id)
        t.status = "skipped"
        t.error = f"director: {d.reason}"[:4000]
        _, target = _key(t.profile, t.payload or {})
        notes.append(f"dropped {t.profile} {target}: {d.reason}".replace("  ", " "))
    kept = [by_id[i] for i in review.keep_task_ids_in_order if i in by_id and i not in dropped_ids]
    kept += [
        t for t in tasks if t.id not in dropped_ids and t not in kept
    ]  # never lose a task silently
    for rank, t in enumerate(kept):
        t.priority = 100 - rank
    llm.guard.session.commit()
    if review.note.strip():
        notes.append(review.note.strip())
    return kept, notes


def _local_today(now: datetime, tz: str) -> date:
    return now.astimezone(ZoneInfo(tz)).date()


def _gaps_md(session, sector_slug: str | None, gap_id: int | None, now: datetime) -> str:
    if gap_id is not None:
        gap = repo.get_gap(session, gap_id)
        if gap is None:
            return ""
        facts = repo.search_facts(session, gap.title, limit=12, now=now)
        head = (
            f"- #{gap.id} {gap.title}: status {gap.status}, score {gap.score_total}, confidence "
            f"{gap.confidence:.2f}, presence {gap.presence_level}\n  hypothesis: {gap.hypothesis_md[:500]}\n"
            f"  why not yet: {gap.why_not_yet_md[:300]}"
        )
        return head + "\n" + "\n".join(f"- [{f.confidence:.2f}] {f.claim}" for f in facts)
    gaps = repo.list_gaps(
        session,
        statuses=["candidate", "verifying", "verified"],
        sector_slugs=[sector_slug] if sector_slug else None,
    )[:12]
    return "\n".join(
        f"- #{g.id} {g.title}: {g.status}, score {g.score_total}, presence {g.presence_level}"
        for g in gaps
    )


def _task_est(task) -> Decimal:
    if task.profile == "chart-diff":
        return CHART_DIFF_EST
    profile = PROFILES.get(task.profile)
    return profile.est_cost_eur if profile is not None else Decimal("0")


def run_once(
    settings: Settings,
    *,
    today: date | None = None,
    now: datetime | None = None,
    budget_override: Decimal | None = None,
    phase_override: str | None = None,
    dry_run: bool = False,
    client=None,
    session_factory=None,
    places: PlacesClient | None = None,
    askdata: AskDataClient | None = None,
    apple_fetch=apple.fetch_top_free,
    play_fetch=play.fetch_top_free,
    runner_factory=None,
    clock=None,
    worker_id: str = "director",
) -> RunSummary:
    clock = clock or (
        lambda: datetime.now(UTC)
    )  # the only wall-clock read; tests inject a fixed one
    now = now or clock()
    today = today or _local_today(now, settings.timezone)
    session_factory = session_factory or make_session_factory(make_engine(settings.database_url))
    client = client or anthropic.Anthropic(api_key=settings.anthropic_api_key)
    askdata = askdata or AskDataClient()
    if places is None and settings.google_places_api_key:
        places = PlacesClient(settings.google_places_api_key)
    session = session_factory()
    run_id: int | None = None
    progress: dict = {"task_id": None, "done": 0, "failed": 0}
    try:
        phase = (
            phase_override
            or (repo.get_setting(session, "phase") or {}).get("value")
            or settings.phase
        )
        if phase not in PHASE_RULES:
            raise ValueError(f"unknown phase {phase!r}")
        cap = (
            Decimal(budget_override)
            if budget_override is not None
            else min(PHASE_RULES[phase]["cap"], Decimal(settings.daily_budget_eur))
        )
        run = repo.start_run(session, day=today, phase=phase, budget_cap_eur=cap, started_at=now)
        run_id = run.id
        return _run_body(
            settings,
            session,
            run,
            today=today,
            now=now,
            phase=phase,
            cap=cap,
            dry_run=dry_run,
            client=client,
            places=places,
            askdata=askdata,
            apple_fetch=apple_fetch,
            play_fetch=play_fetch,
            runner_factory=runner_factory,
            clock=clock,
            worker_id=worker_id,
            progress=progress,
        )
    except BaseException as exc:
        if run_id is not None:
            _close_failed(session, session_factory, run_id, exc, clock(), progress)
        raise
    finally:
        session.close()


def _close_failed(
    session, session_factory, run_id: int, exc: BaseException, at: datetime, progress: dict
) -> None:
    """Never leave a run 'running': release its claimed task and mark it failed (fresh session if needed)."""
    tail = "".join(traceback.format_exception(exc))[-1500:]
    summary = f"failed: {type(exc).__name__}: {exc}\n{tail}"[:4000]
    errors: list[str] = []
    for use_fresh in (False, True):
        s = None
        try:
            s = session_factory() if use_fresh else session
            s.rollback()
            if progress.get("task_id") is not None:
                task = s.get(repo.Task, progress["task_id"])
                if task is not None and task.status == "running":
                    repo.release_task(s, task, give_back_attempt=True)
            row = s.get(repo.Run, run_id)
            if row is not None:
                try:  # best effort: do not understate the row
                    row.spent_eur = repo.spent_on(s, row.day)
                except Exception:  # noqa: BLE001
                    s.rollback()
                repo.finish_run(
                    s,
                    row,
                    spent_eur=row.spent_eur,
                    tasks_done=progress.get("done", 0),
                    tasks_failed=progress.get("failed", 0),
                    summary_md=summary,
                    finished_at=at,
                    status="failed",
                )
            return
        except Exception as cleanup_exc:  # noqa: BLE001 — the original exception is what gets raised
            errors.append(f"{type(cleanup_exc).__name__}: {cleanup_exc}")
        finally:
            if use_fresh and s is not None:
                s.close()
    print(f"scout: could not close failed run {run_id}: {'; '.join(errors)}", file=sys.stderr)


def _run_body(
    settings,
    session,
    run,
    *,
    today,
    now,
    phase,
    cap,
    dry_run,
    client,
    places,
    askdata,
    apple_fetch,
    play_fetch,
    runner_factory,
    clock,
    worker_id,
    progress,
) -> RunSummary:
    guard = BudgetGuard(session, day=today, daily_cap_eur=cap, run_id=run.id)
    llm = LLM(client, guard, Decimal(settings.usd_to_eur))
    deadline = now + timedelta(minutes=settings.run_max_minutes)
    journal_md = journal_markdown(repo.latest_journal(session, limit=3))
    notes: list[str] = []
    planned: list = []
    done = failed = 0
    chart_report = None
    stopped_reason = "queue empty"
    exhausted = guard.spent() >= cap

    if dry_run:  # a dry run never writes beyond its own runs row, even on a capped day
        earlier_runs = [r.id for r in repo.runs_on_day(session, today) if r.id != run.id]
        state = load_state(session, today=today, now=now, cap=cap, run_ids_today=earlier_runs)
        queued = repo.queued_tasks(session)
        keys = {_key(t.profile, t.payload or {}) for t in queued}
        extra = [p for p in plan_tasks(state, phase) if _key(p.profile, p.payload) not in keys]
        lines = [
            f"- {t.profile} {t.payload} (priority {t.priority}, est €{t.est_cost_eur})"
            for t in [*queued, *extra]
        ]
        repo.finish_run(
            session,
            run,
            spent_eur=Decimal("0"),
            tasks_done=0,
            tasks_failed=0,
            summary_md="dry run\n" + "\n".join(lines),
            finished_at=clock(),
            status="dry-run",
        )
        return RunSummary(
            run.id, today, phase, len(lines), 0, 0, Decimal("0"), "\n".join(lines), "dry run"
        )
    elif exhausted:  # spec B2.1: refuse the work if the cap is already spent; still brief and close
        stopped_reason = "budget"
    else:
        stale_cut = now - timedelta(minutes=settings.run_max_minutes)
        released = repo.release_stale_tasks(session, claimed_before=stale_cut)
        if released:
            notes.append(f"released {released} stale running task(s)")
        # 1. plan
        earlier_runs = [r.id for r in repo.runs_on_day(session, today) if r.id != run.id]
        state = load_state(session, today=today, now=now, cap=cap, run_ids_today=earlier_runs)
        queued_before = repo.queued_tasks(session)
        for t in queued_before:  # tasks added by hand or by field-check answers join today's run
            t.run_id = run.id
        session.commit()
        new_tasks = []
        existing_keys = {_key(t.profile, t.payload or {}) for t in queued_before}
        for p in plan_tasks(state, phase):
            if _key(p.profile, p.payload) in existing_keys:
                continue
            new_tasks.append(
                repo.enqueue_task(
                    session,
                    profile=p.profile,
                    payload=p.payload,
                    priority=p.priority,
                    est_cost_eur=p.est_cost_eur,
                    run_id=run.id,
                )
            )
        planned = queued_before + new_tasks
        if settings.director_review and len(planned) >= 3 and guard.can_afford(REVIEW_EST):
            try:
                planned, review_notes = review_plan(llm, planned, journal_md=journal_md)
                notes += review_notes
            except (LLMError, BudgetExceeded, anthropic.APIError) as e:
                notes.append(f"director review skipped: {type(e).__name__}")

        # 2. execute
        system = build_system(session)
        worker = ResearchWorker(client, llm, guard, system, runner_factory=runner_factory)
        extractor = Extractor(llm)
        while True:
            if clock() >= deadline:
                stopped_reason = "time limit"
                break
            queue = repo.queued_tasks(session)
            if not queue:
                break
            if not guard.can_afford(_task_est(queue[0])):  # check BEFORE claiming; it stays queued
                stopped_reason = "budget"
                break
            task = repo.claim_next_task(session, worker_id, now=clock())
            if task is None:
                break
            progress["task_id"] = task.id
            outcome = None
            try:  # the work itself (the only part whose failure may requeue a task)
                if task.profile == "chart-diff":
                    spent_before = guard.spent()
                    chart_report = run_chart_diff(
                        session, today, apple_fetch=apple_fetch, play_fetch=play_fetch
                    )
                    n = classify_and_record(
                        session, extractor, chart_report, now=clock(), run_id=run.id
                    )
                    result_md = (
                        f"snapshots {chart_report.snapshots_saved}; leads {len(chart_report.leads)}; "
                        f"facts {n}; new in Kosovo: {', '.join(chart_report.new_in_kosovo) or 'none'}"
                    )
                    cost = guard.spent() - spent_before
                else:
                    profile = PROFILES[task.profile]
                    payload = dict(task.payload or {})
                    sector = payload.get("sector")
                    digest = repo.get_digest(session, f"sector:{sector}") if sector else None
                    if task.profile == "culture":
                        digest = repo.get_digest(session, f"culture:{payload.get('theme')}")
                    if task.profile in ("verify-gap", "deep-dive") and payload.get("gap_id"):
                        gap = repo.get_gap(session, int(payload["gap_id"]))
                        if gap is not None:
                            payload.setdefault("hypothesis", gap.hypothesis_md)
                            payload.setdefault("presence_level", gap.presence_level)
                    brief = build_brief(
                        profile,
                        payload,
                        today,
                        journal_md=journal_md,
                        sector_digest=digest or "",
                        gaps_md=_gaps_md(session, sector, payload.get("gap_id"), clock()),
                    )
                    ctx = ToolContext(
                        session=session,
                        guard=guard,
                        now=clock(),
                        run_id=run.id,
                        task_id=task.id,
                        places=places,
                        askdata=askdata,
                    )
                    outcome = worker.run(task.id, profile, brief, ctx)
                    result_md, cost = outcome.summary_md, outcome.cost_eur
            except BudgetExceeded:
                session.rollback()
                repo.release_task(
                    session, task, give_back_attempt=True
                )  # stays queued for tomorrow
                progress["task_id"] = None
                stopped_reason = "budget"
                break
            except Exception as e:  # noqa: BLE001 — one bad task must not end the day
                session.rollback()
                repo.fail_task(
                    session,
                    task,
                    error=f"{type(e).__name__}: {e}\n{traceback.format_exc()[-1500:]}",
                    now=clock(),
                    requeue=True,
                )
                progress["task_id"] = None
                if task.status == "failed":
                    failed += 1
                    progress["failed"] = failed
                continue
            try:  # post-processing of paid work: never requeue (would repay for the research)
                repo.finish_task(
                    session, task, result_md=result_md, actual_cost_eur=cost, now=clock()
                )
                if outcome is not None:
                    _apply_outcome(session, task, outcome, today=today, now=clock())
            except Exception as e:  # noqa: BLE001
                session.rollback()
                session.refresh(task)
                notes.append(
                    f"post-processing {task.profile} failed: {type(e).__name__}: {e}"[:300]
                )
                if task.status == "running":
                    repo.fail_task(
                        session, task, error=f"post-processing: {e}", now=clock(), requeue=False
                    )
            progress["task_id"] = None
            if task.status == "failed":
                failed += 1
            else:
                done += 1
            progress["done"], progress["failed"] = done, failed
            if outcome is not None and outcome.budget_stopped:
                stopped_reason = "budget"
                break

    # 3. judge (only when this run produced new facts)
    changes = []
    strategist = Strategist(llm, session)
    fresh = repo.fresh_facts_since(session, run.started_at, now=clock())
    if fresh:
        try:
            inputs = strategist.collect_inputs(
                since=run.started_at - timedelta(hours=1), now=clock()
            )
            if inputs.gaps or inputs.facts:
                output = strategist.assess(inputs, today)
                critic = strategist.critique(output, inputs, today)
                applied = strategist.apply(output, critic, now=clock(), run_id=run.id)
                changes = applied.changes
                notes.append(
                    f"strategist: {output.headline}; new gaps {applied.new_gaps}; "
                    f"field checks {applied.field_checks_added}"
                )
        except (LLMError, BudgetExceeded, anthropic.APIError) as e:
            notes.append(f"strategy skipped: {type(e).__name__}: {str(e)[:120]}")

    # 4. write and remember
    brief_md = write_brief(
        session, llm, run, today=today, now=clock(), changes=changes, chart_report=chart_report
    )
    spent = guard.spent()  # after the brief so its narrative cost is included
    tasks = repo.tasks_for_run(session, run.id)
    did = (
        "; ".join(
            f"{t.profile} {(t.payload or {}).get('sector') or (t.payload or {}).get('gap_title') or (t.payload or {}).get('theme') or ''} ({t.status})"
            for t in tasks
        )
        or "nothing"
    )
    learned = "\n".join(f"- {f.claim[:160]}" for f in fresh[:8]) or "- nothing new"
    unmapped = [s.slug for s in repo.list_sectors(session) if s.status == "unmapped"][:3]
    tomorrow = (
        f"next sectors: {', '.join(unmapped) or 'all mapped'}; open field checks: "
        f"{len(repo.open_field_checks(session))}; " + "; ".join(notes)
    )
    repo.write_journal(
        session, run_id=run.id, day=today, did_md=did, learned_md=learned, tomorrow_md=tomorrow
    )
    gaps = repo.list_gaps(session)
    by_status: dict[str, int] = {}
    for g in gaps:
        by_status[g.status] = by_status.get(g.status, 0) + 1
    top10 = [g.confidence for g in gaps[:10]]
    all_facts = session.query(repo.Fact).count()
    fresh_total = session.query(repo.Fact).filter(repo.Fact.expires_at > clock()).count()
    first = today.replace(day=1)
    metrics = {
        "sectors_mapped": sum(1 for s in repo.list_sectors(session) if s.status != "unmapped"),
        "proven_models": session.query(repo.ProvenModel).count(),
        "gaps_by_status": by_status,
        "avg_confidence_top10": round(sum(top10) / len(top10), 3) if top10 else 0,
        "facts_fresh_ratio": round(fresh_total / all_facts, 3) if all_facts else 0,
        "spend_mtd": str(repo.spent_between(session, first, today)),
        "searches_mtd": sum(
            int((c.units or {}).get("web_search_requests", 0))
            for c in session.query(repo.Cost).filter(repo.Cost.day >= first)
        ),
        "field_checks_open": len(repo.open_field_checks(session)),
        "field_checks_answered": session.query(repo.FieldCheck)
        .filter_by(status="answered")
        .count(),
        "days_run": session.query(repo.Run.day).filter(repo.Run.status == "done").distinct().count()
        + 1,
    }
    repo.save_scorecard(session, day=today, metrics=metrics)
    repo.finish_run(
        session,
        run,
        spent_eur=spent,
        tasks_done=done,
        tasks_failed=failed,
        summary_md=brief_md[:4000],
        finished_at=clock(),
        status="done",
    )
    return RunSummary(
        run.id, today, phase, len(planned), done, failed, spent, brief_md, stopped_reason
    )


def _apply_outcome(session, task, outcome, *, today, now) -> None:
    payload = task.payload or {}
    sector = payload.get("sector")
    complete = not outcome.budget_stopped and not outcome.truncated
    if complete and task.profile == "map-sector" and sector:
        repo.set_sector_status(session, sector, "mapped", now=now)
    if complete and task.profile == "hunt-models" and sector:
        repo.set_sector_status(session, sector, "hunted", now=now)
    if complete and task.profile == "deep-dive" and payload.get("gap_id"):
        repo.set_gap_test_plan(session, int(payload["gap_id"]), outcome.summary_md)
        repo.set_setting(session, f"deep-dive-done:{today.replace(day=1).isoformat()}", True)
    if task.profile == "verify-gap" and payload.get("gap_id"):
        for line in outcome.summary_md.splitlines():
            if line.lower().startswith("field-check:") and len(repo.open_field_checks(session)) < 5:
                repo.add_field_check(
                    session,
                    gap_id=int(payload["gap_id"]),
                    question=line.split(":", 1)[1].strip(),
                    why="verify-gap was ambiguous",
                    due=today + timedelta(days=7),
                )
