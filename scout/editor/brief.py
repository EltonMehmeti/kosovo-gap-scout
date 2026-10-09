"""Deterministic Markdown brief with one optional Sonnet paragraph. Quiet days cost nothing."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import date, datetime
from decimal import Decimal

import anthropic

from scout.budget.guard import BudgetExceeded
from scout.db import repo
from scout.llm.gateway import LLM, LLMError

NARRATIVE_SYSTEM = (
    "You write the two-sentence opening of a daily brief for a founder in Kosovo who is looking "
    "for a business gap. Plain, specific, no hype, no bullet points. Mention the most important "
    "change and what the founder should do today, if anything."
)


@dataclass
class BriefInputs:
    run: object
    today: date
    changes: list
    fresh_facts: list
    field_checks: list
    tasks: list
    chart_errors: list[str]
    spent_today: Decimal
    spent_mtd: Decimal
    cap: Decimal
    places_calls: int
    gap_titles: dict[int, str] = field(default_factory=dict)


def collect_inputs(
    session, run, *, today: date, now: datetime, changes: list, chart_report=None
) -> BriefInputs:
    facts = [
        f
        for f in repo.fresh_facts_since(session, run.started_at, now=now, min_confidence=0.6)
        if f.source_name != "seed"
    ]
    checks = repo.open_field_checks(session)[:5]
    titles = {}
    for fc in checks:
        gap = repo.get_gap(session, fc.gap_id) if fc.gap_id else None
        titles[fc.id] = gap.title if gap else "(general)"
    return BriefInputs(
        run=run,
        today=today,
        changes=list(changes),
        fresh_facts=facts,
        field_checks=checks,
        tasks=repo.tasks_for_run(session, run.id),
        chart_errors=list(chart_report.errors) if chart_report else [],
        spent_today=repo.spent_on(session, today),
        spent_mtd=repo.spent_between(session, today.replace(day=1), today),
        cap=Decimal(run.budget_cap_eur),
        places_calls=repo.places_calls_in_month(session, today),
        gap_titles=titles,
    )


def is_quiet(inputs: BriefInputs) -> bool:
    return not inputs.changes and not inputs.fresh_facts


def _money(x: Decimal) -> str:
    return f"€{Decimal(x).quantize(Decimal('0.01'))}"


def render_brief(inputs: BriefInputs, narrative: str = "") -> str:
    n_tasks = len(inputs.tasks)
    if is_quiet(inputs):
        return f"Quiet day — {n_tasks} tasks, {_money(inputs.spent_today)}, nothing moved."
    top = sorted(inputs.changes, key=lambda c: -c.new_score)
    headline = (
        f"# {inputs.today.isoformat()} — {top[0].title}: {top[0].new_status} ({top[0].new_score}/100)"
        if top
        else f"# {inputs.today.isoformat()} — {len(inputs.fresh_facts)} new facts, no gap moved"
    )
    lines = [headline, ""]
    if narrative:
        lines += [narrative.strip(), ""]
    lines.append("## What changed")
    lines += [
        f"- **{c.title}** — {c.old_status} → {c.new_status}, score {c.old_score} → {c.new_score}, "
        f"confidence {c.confidence:.2f}. {c.why}"
        for c in top
    ] or ["- nothing"]
    lines += ["", "## Field checks for you"]
    lines += [
        f"- [{fc.id}] {fc.question} — _{fc.why}_ (gap: {inputs.gap_titles.get(fc.id, '')}; due {fc.due})"
        for fc in inputs.field_checks
    ] or ["- none open"]
    lines += ["", "## What the scout did"]
    for t in inputs.tasks:
        p = t.payload or {}
        target = p.get("sector") or p.get("gap_title") or p.get("theme") or ""
        lines.append(
            f"- {t.profile} {target} — {t.status}, {_money(t.actual_cost_eur or Decimal(0))}"
            + (f" — {t.error[:80]}" if t.error else "")
        )
    lines += ["", "## What it learned"]
    for f in inputs.fresh_facts[:5]:
        src = f" <{f.source_url}>" if f.source_url else f" ({f.source_name})"
        lines.append(f"- [{f.confidence:.2f}] {f.claim}{src}")
    failed = [t for t in inputs.tasks if t.status == "failed"]
    lines += [
        "",
        "## Source health",
        f"- tasks failed: {len(failed)}; chart errors: {len(inputs.chart_errors)}; "
        f"Places calls this month: {inputs.places_calls}/4500",
    ]
    lines += [f"- {e}" for e in inputs.chart_errors[:5]]
    lines += [
        "",
        "## Spend",
        f"- today {_money(inputs.spent_today)} (cap {_money(inputs.cap)}); "
        f"month to date {_money(inputs.spent_mtd)}",
    ]
    return "\n".join(lines).strip()


def write_brief(
    session, llm: LLM, run, *, today: date, now: datetime, changes: list, chart_report=None
) -> str:
    inputs = collect_inputs(
        session, run, today=today, now=now, changes=changes, chart_report=chart_report
    )
    narrative = ""
    if not is_quiet(inputs):
        summary = render_brief(inputs)[:6000]
        try:
            narrative = llm.create_text(
                model="claude-sonnet-5-5",
                system=NARRATIVE_SYSTEM,
                user=summary,
                max_tokens=300,
                effort="low",
                est_eur=Decimal("0.03"),
            ).text
        except (LLMError, BudgetExceeded, anthropic.APIError):
            narrative = ""
        inputs = replace(
            inputs,
            spent_today=repo.spent_on(session, today),
            spent_mtd=repo.spent_between(session, today.replace(day=1), today),
        )
    md = render_brief(inputs, narrative)
    repo.save_brief(session, run_id=run.id, day=today, markdown=md)
    return md
