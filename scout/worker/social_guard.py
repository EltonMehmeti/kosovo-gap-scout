"""Code-enforced limits on paid social calls (spec §4): the score gate, one call per tool per task, the
monthly Apify credit cap, and a cache that serves repeat queries free."""

from __future__ import annotations

from collections.abc import Callable
from datetime import date, timedelta
from decimal import Decimal

import httpx

from scout.db import repo
from scout.db.repo import CostRecord
from scout.sources.apify import ActorResult, ApifyError

SCORE_GATE = 60
ADS_SWEEP_PROFILE = "ads-sweep"
CACHE_DAYS = {"instagram": 30, "ads": 14}
TOOL_FOR = {"instagram": "instagram_search", "ads": "ad_library_search"}
SOURCE_NAME = {"instagram": "apify-instagram", "ads": "meta-ad-library"}
QUERY_KEY_CHARS = 300


def query_key(query: str, max_items: int) -> str:
    return f"{' '.join(query.lower().split())[:QUERY_KEY_CHARS]}|{max_items}"


def qualifies(ctx) -> bool:
    gap_id = (ctx.payload or {}).get("gap_id")
    if ctx.profile != "verify-gap" or gap_id is None:
        return False
    gap = repo.get_gap(ctx.session, int(gap_id))
    flagged = int(gap_id) in (repo.get_setting(ctx.session, "flagged_gaps", []) or [])
    return gap is not None and ((gap.score_total or 0) >= SCORE_GATE or flagged)


def resume_text(day: date) -> str:
    next_month = (day.replace(day=28) + timedelta(days=4)).replace(day=1)
    return f"Social credit used up for {day:%B} — paid social checks resume {next_month:%b} 1."


def credit_used_up(session, day: date, cap_usd: Decimal) -> bool:
    return repo.apify_usd_in_month(session, day) >= Decimal(cap_usd)


def _gate(ctx, source: str) -> str | None:
    if ctx.profile == ADS_SWEEP_PROFILE:
        if source == "ads":
            return None
        return "error: the weekly ads sweep may only call ad_library_search"
    if qualifies(ctx):
        return None
    return (
        "paid social checks run only while checking a gap that scores 60 or more (or that the "
        "founder flagged) — use web_search with site:instagram.com instead"
    )


def _record(ctx, source: str, cost_usd: Decimal, items: int) -> None:
    ctx.guard.record(
        CostRecord(
            "apify",
            "apify",
            source,
            {"usd": str(cost_usd), "items": items, "calls": 1},
            Decimal("0"),
            task_id=ctx.task_id,
        )
    )


def paid_call(
    ctx,
    source: str,
    query: str,
    *,
    max_items: int,
    run: Callable[[int], ActorResult],
    normalise: Callable[[list[dict]], dict],
) -> dict | str:
    """The normalised result, or the text to show the model when the call may not or did not run."""
    if refusal := _gate(ctx, source):
        return refusal
    key = query_key(query, max_items)
    cached = (
        None
        if ctx.profile == ADS_SWEEP_PROFILE
        else repo.get_social_cache(
            ctx.session, source, key, now=ctx.now, max_age_days=CACHE_DAYS[source]
        )
    )
    if cached is not None:
        ctx.social_ok += 1
        return cached.items
    if ctx.social_calls.get(source, 0) >= 1:
        return f"error: one {TOOL_FOR[source]} per task — work with the result you already have"
    if credit_used_up(ctx.session, ctx.guard.day, ctx.apify_monthly_usd):
        return f"social source unavailable: {resume_text(ctx.guard.day)}"
    ctx.social_calls[source] = ctx.social_calls.get(source, 0) + 1
    try:
        result = run(max_items)
    except ApifyError as e:
        _record(ctx, source, e.cost_usd, 0)
        repo.mark_source(ctx.session, SOURCE_NAME[source], ok=False, now=ctx.now)
        return f"social source unavailable: {e}"
    except httpx.HTTPError as e:
        _record(ctx, source, Decimal("0"), 0)
        repo.mark_source(ctx.session, SOURCE_NAME[source], ok=False, now=ctx.now)
        return f"social source unavailable: {type(e).__name__}"
    items = result.items[:max_items]
    _record(ctx, source, result.cost_usd, len(items))
    repo.mark_source(ctx.session, SOURCE_NAME[source], ok=True, now=ctx.now)
    summary = normalise(items)
    repo.put_social_cache(ctx.session, source, key, summary, cost_usd=result.cost_usd, now=ctx.now)
    ctx.social_ok += 1
    return summary
