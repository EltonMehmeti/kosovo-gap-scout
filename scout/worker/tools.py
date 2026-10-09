"""Custom tools the research worker can call. Each tool is a thin closure over a testable *_impl."""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal

from anthropic import beta_tool
from sqlalchemy.orm import Session

from scout.db import repo
from scout.db.repo import CostRecord, FactIn
from scout.sources import apple, play, social
from scout.sources.apify import ADS_ACTOR, INSTAGRAM_ACTOR, ApifyClient, ad_library_url
from scout.sources.askdata import AskDataClient
from scout.sources.crawl import (
    ALLOWED_DOMAINS,
    CrawlClient,
    CrawlRefused,
    allowed_domain,
    source_for,
)
from scout.sources.places import PlacesClient
from scout.worker import social_guard

FACT_ENTITY_TYPES = (
    "sector",
    "business",
    "proven_model",
    "gap",
    "culture",
    "stat",
    "news",
    "presence_check",
    "demand_test",
    "payment_path",
    "social",
    "ad_signal",
)
PRESENCE_LEVELS = (
    "absent",
    "exists-but-poor",
    "prishtina-only",
    "offline-only",
    "instagram-only",
    "decent",
    "unknown",
)
DIGEST_PREFIXES = ("sector:", "culture:", "country")
# Presence-check provenance (spec B8, review I4): the fact that lifts the rubric's absence/confidence cap may
# only be written by a verify-gap task, for its own gap, after real searches ran in that same task. Below
# these minimums (one Places search per city, one app-store search) the verdict is stored as "unknown".
PRESENCE_CHECK_PROFILE = "verify-gap"
PRESENCE_CHECK_TTL_DAYS = 60
MIN_PLACES_SEARCHES = 7
MIN_APP_STORE_SEARCHES = 1
DEGRADED_CHECK_MAX_CONFIDENCE = 0.5
KB_RESULT_LIMIT = 2000
SOURCE_RESULT_LIMIT = 1200
DIGEST_CHAR_LIMIT = 5000  # ≈ 1,200 tokens (spec B13)

TOOL_NAMES = (
    "kb_search",
    "kb_record_fact",
    "kb_record_business",
    "kb_record_proven_model",
    "kb_propose_gap",
    "kb_write_digest",
    "places_search",
    "app_store_search",
    "askdata_list",
    "askdata_table",
    "askdata_fetch",
)
SOCIAL_TOOL_NAMES = ("instagram_search", "ad_library_search")
CRAWL_TOOL_NAMES = ("kosovo_site_crawl",)
MAX_INSTAGRAM_ACCOUNTS = 30
MAX_ADS = 50
SWEEP_MAX_ADS = 300
SWEEP_RESULT_LIMIT = 12000
MAX_CRAWL_PAGES = 20


@dataclass
class ToolContext:
    session: Session
    guard: object  # BudgetGuard or test fake: spent/remaining/can_afford/check/record/day
    now: datetime
    run_id: int | None
    task_id: int | None
    places: PlacesClient | None
    askdata: AskDataClient
    apple_search: Callable = apple.search_apps
    play_search: Callable = play.search_apps
    places_monthly_quota: int = 4500
    events: list[dict] = field(default_factory=list)
    profile: str | None = None  # the task's profile name (provenance for presence checks)
    payload: dict = field(default_factory=dict)  # the task's payload (gap_id for verify-gap)
    places_searches: int = 0  # Places searches that actually returned in this task
    app_store_searches: int = 0  # app-store searches that actually returned in this task
    touched_gap_ids: set[int] = field(default_factory=set)  # gaps proposed/updated or written about
    search_note: str | None = (
        None  # set by the worker when the task's web-search allowance is used up
    )
    apify: ApifyClient | None = None
    crawler: CrawlClient | None = None
    apify_monthly_usd: Decimal = Decimal("4.50")
    social_calls: dict[str, int] = field(default_factory=dict)
    social_ok: int = 0
    crawl_pages: int = 0


def _clip(text: str, limit: int) -> str:
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _or_none(value: str, width: int | None = None) -> str | None:
    value = value.strip()
    if width is not None:
        value = value[:width]
    return value or None


def _fit(value: str, width: int) -> str:
    """Trim a model-supplied string to its column width (a too-long value would abort the transaction)."""
    return value.strip()[:width]


# column widths from scout/db/models.py
W_NAME, W_KIND, W_CITY, W_TITLE, W_ENTITY_KEY, W_PM_SLUG, W_DIGEST_KEY = (
    200,
    20,
    80,
    200,
    160,
    120,
    120,
)
BUSINESS_KINDS = ("local", "foreign", "nearby")
_KIND_ALIASES = {"neighbour": "nearby", "neighbor": "nearby", "regional": "nearby"}


def _business_kind(raw: str) -> str | None:
    """Normalise the model's kind: first word, lower-case, aliases mapped; None when unrecognised."""
    word = re.split(r"[^a-z]+", (raw or "local").strip().lower(), maxsplit=1)[0] or "local"
    word = _KIND_ALIASES.get(word, word)
    return word if word in BUSINESS_KINDS else None


def _unknown_sector(ctx: ToolContext, sector: str) -> str | None:
    """Error text when a non-empty sector slug is not one of the seeded sectors (a typo must not
    create a new sector that the planner would then pay to map); None when it is fine."""
    slug = sector.strip()
    if not slug or repo.get_sector(ctx.session, slug) is not None:
        return None
    valid = ", ".join(s.slug for s in repo.list_sectors(ctx.session))
    return f"error: unknown sector {slug!r}; use one of: {valid}"


# ---------- knowledge base ----------


def kb_search_impl(ctx: ToolContext, query: str, sector: str = "") -> str:
    if err := _unknown_sector(ctx, sector):
        return err
    sector_slug = _or_none(sector)
    lines: list[str] = []
    if sector_slug:
        digest = repo.get_digest(ctx.session, f"sector:{sector_slug}")
        if digest:
            lines.append("DIGEST:\n" + digest[:800])
    facts = repo.search_facts(ctx.session, query, sector_slug=sector_slug, limit=15, now=ctx.now)
    for f in facts:
        line = f"- [{f.confidence:.2f}] {f.claim} ({f.source_name}; {f.observed_at.date().isoformat()})"
        if f.source_url:
            line += f" <{f.source_url}>"
        lines.append(line)
    return _clip("\n".join(lines) or "no facts yet", KB_RESULT_LIMIT)


def kb_record_fact_impl(
    ctx: ToolContext,
    claim: str,
    entity_type: str,
    entity_key: str,
    confidence: float,
    source_url: str = "",
    sector: str = "",
    ttl_days: int = 90,
    value_json: str = "",
) -> str:
    if entity_type not in FACT_ENTITY_TYPES:
        return f"error: entity_type must be one of {', '.join(FACT_ENTITY_TYPES)}"
    if not claim.strip():
        return "error: claim is empty"
    if err := _unknown_sector(ctx, sector):
        return err
    value = None
    if value_json.strip():
        try:
            value = json.loads(value_json)
        except json.JSONDecodeError:
            value = {"raw": value_json[:500]}
    if not isinstance(value, dict | None):
        value = {"raw": value}
    confidence = min(max(float(confidence), 0.0), 1.0)
    if entity_type == "presence_check":
        checked = _presence_check(ctx, entity_key.strip(), value, confidence)
        if isinstance(checked, str):
            return checked
        value, confidence = checked
        ttl_days = PRESENCE_CHECK_TTL_DAYS
    fact = repo.upsert_fact(
        ctx.session,
        FactIn(
            claim=claim,
            entity_type=entity_type,
            entity_key=_fit(entity_key, W_ENTITY_KEY),
            confidence=confidence,
            source_url=_or_none(source_url),
            sector_slug=_or_none(sector),
            value=value,
            ttl_days=max(1, min(int(ttl_days), 365)),
        ),
        run_id=ctx.run_id,
        observed_at=ctx.now,
    )
    key = fact.entity_key
    if key.startswith("gap:") and key[4:].isdigit():
        ctx.touched_gap_ids.add(int(key[4:]))
    return f"fact #{fact.id} saved (confidence {fact.confidence:.2f}, expires {fact.expires_at.date()})"


def _presence_check(
    ctx: ToolContext, entity_key: str, value: dict | None, confidence: float
) -> tuple[dict, float] | str:
    """Validate a presence_check write; return (value, confidence) to store, or the error text."""
    if ctx.profile != PRESENCE_CHECK_PROFILE:
        return (
            "error: presence_check facts are written only by verify-gap tasks; record what you "
            "found as entity_type 'gap' or 'business' instead"
        )
    gap_id = ctx.payload.get("gap_id")
    if entity_key != f"gap:{gap_id}":
        return f"error: this task may only record the presence check for 'gap:{gap_id}'"
    if ctx.places_searches + ctx.app_store_searches == 0:
        return "error: run places_search and app_store_search first (presence-check protocol)"
    value = dict(value or {})
    claimed = value.get("verdict")
    verdict = claimed if claimed in PRESENCE_LEVELS else "unknown"
    value["protocol"] = {
        "places_searches": ctx.places_searches,
        "app_store_searches": ctx.app_store_searches,
    }
    if ctx.places_searches < MIN_PLACES_SEARCHES or ctx.app_store_searches < MIN_APP_STORE_SEARCHES:
        value["degraded"] = True
        value["claimed_verdict"] = claimed
        verdict = "unknown"
        confidence = min(confidence, DEGRADED_CHECK_MAX_CONFIDENCE)
    if ctx.apify is not None and social_guard.qualifies(ctx) and ctx.social_ok == 0:
        value["social"] = "partial"
        confidence = min(confidence, DEGRADED_CHECK_MAX_CONFIDENCE)
    value["verdict"] = verdict
    return value, confidence


def kb_record_business_impl(
    ctx: ToolContext,
    name: str,
    sector: str,
    kind: str = "local",
    city: str = "",
    instagram: str = "",
    website: str = "",
    facebook: str = "",
    note: str = "",
) -> str:
    if not name.strip() or not sector.strip():
        return "error: name and sector are required"
    norm_kind = _business_kind(kind)
    if norm_kind is None:
        return f"error: kind must be one of {', '.join(BUSINESS_KINDS)} (got {kind!r})"
    if err := _unknown_sector(ctx, sector):
        return err
    channels = {
        k: v.strip()
        for k, v in (("instagram", instagram), ("website", website), ("facebook", facebook))
        if v.strip()
    }
    b = repo.upsert_business(
        ctx.session,
        name=_fit(name, W_NAME),
        sector_slug=sector.strip(),
        kind=norm_kind,
        city=_or_none(city, W_CITY),
        channels=channels,
        note=_or_none(note),
        seen_at=ctx.now,
    )
    return f"business #{b.id} saved ({b.name}, {b.city or 'city unknown'})"


def kb_record_proven_model_impl(
    ctx: ToolContext,
    slug: str,
    name: str,
    sector: str,
    description: str,
    markets_json: str,
    business_model: str = "",
    source_urls_json: str = "",
) -> str:
    try:
        markets = json.loads(markets_json) if markets_json.strip() else []
        source_urls = json.loads(source_urls_json) if source_urls_json.strip() else []
    except json.JSONDecodeError as e:
        return f"error: invalid JSON ({e.msg})"
    if not isinstance(markets, list) or not all(
        isinstance(m, dict) and m.get("country") for m in markets
    ):
        return 'error: markets_json must be a list of {"country": "HR", "example": "...", "url": "..."}'
    if not sector.strip():
        return "error: sector is required"
    if err := _unknown_sector(ctx, sector):
        return err
    pm = repo.upsert_proven_model(
        ctx.session,
        slug=repo.slugify(slug)[:W_PM_SLUG].strip("-"),
        name=_fit(name, W_NAME),
        sector_slug=sector.strip(),
        description=description,
        markets=markets,
        business_model=_or_none(business_model),
        source_urls=[str(u) for u in source_urls],
    )
    return f"proven model '{pm.slug}' saved (markets: {len(pm.markets)}, nearby markets: {pm.nearby_count})"


def kb_propose_gap_impl(
    ctx: ToolContext,
    title: str,
    sector: str,
    hypothesis: str,
    presence_level: str = "unknown",
    proven_model_slug: str = "",
    why_not_yet: str = "",
) -> str:
    if presence_level not in PRESENCE_LEVELS:
        return f"error: presence_level must be one of {', '.join(PRESENCE_LEVELS)}"
    if not title.strip() or not sector.strip():
        return "error: title and sector are required"
    if err := _unknown_sector(ctx, sector):
        return err
    gap, created = repo.propose_gap(
        ctx.session,
        title=_fit(title, W_TITLE),
        sector_slug=sector.strip(),
        proven_model_slug=_or_none(proven_model_slug, W_PM_SLUG),
        hypothesis_md=hypothesis,
        presence_level=presence_level,
        why_not_yet_md=why_not_yet,
        run_id=ctx.run_id,
    )
    ctx.touched_gap_ids.add(gap.id)
    return (
        f"gap #{gap.id} {'(new)' if created else '(existing)'}: {gap.title} [status {gap.status}]"
    )


def kb_write_digest_impl(ctx: ToolContext, key: str, title: str, body_md: str) -> str:
    key = _fit(key, W_DIGEST_KEY)
    if not (key == "country" or key.startswith(("sector:", "culture:"))):
        return f"error: key must be 'country', 'sector:<slug>' or 'culture:<theme>' (got {key!r})"
    if key.startswith("sector:") and (err := _unknown_sector(ctx, key.removeprefix("sector:"))):
        return err
    body = body_md.strip()[:DIGEST_CHAR_LIMIT]
    repo.set_digest(ctx.session, key, _fit(title, W_TITLE) or key, body, now=ctx.now)
    return f"digest {key} saved ({len(body)} chars; limit {DIGEST_CHAR_LIMIT})"


# ---------- Tier A sources ----------


def places_search_impl(ctx: ToolContext, query: str, city: str = "", language: str = "sq") -> str:
    if ctx.places is None:
        return "places_search unavailable (no GOOGLE_PLACES_API_KEY configured) — use web_search instead"
    if repo.places_calls_in_month(ctx.session, ctx.guard.day) >= ctx.places_monthly_quota:
        return "places_search quota exhausted for this month — use web_search instead"
    if not ctx.guard.can_afford(Decimal("0")):
        return "budget exhausted — stop researching and write your summary"
    q = f"{query.strip()} {city.strip()}".strip()
    try:
        result = ctx.places.text_search(q, language=language or "sq")
        ctx.places_searches += 1
    finally:  # a failed request may still have been billed
        ctx.guard.record(
            CostRecord("places", "google", None, {"calls": 1}, Decimal("0"), task_id=ctx.task_id)
        )
    lines = [f"{result.count} places for {q!r}"]
    lines += [
        f"- {p.name} | {p.address} | {p.primary_type or '-'} | {p.business_status or '-'}"
        for p in result.places[:15]
    ]
    return _clip("\n".join(lines), SOURCE_RESULT_LIMIT)


def app_store_search_impl(ctx: ToolContext, term: str, store: str = "both") -> str:
    lines: list[str] = []
    if store in ("apple", "both"):
        try:
            hits = ctx.apple_search(term, country="xk", limit=8)
            ctx.app_store_searches += 1
            lines.append(f"apple: {len(hits)} results")
            lines += [f"- [apple] {h.name} — {h.publisher} <{h.url}>" for h in hits]
        except Exception as e:  # noqa: BLE001 — a dead source must not kill the task
            lines.append(f"apple: error {type(e).__name__}")
    if store in ("play", "both"):
        try:
            hits = ctx.play_search(term, country="xk", lang="sq", limit=8)
            ctx.app_store_searches += 1
            lines.append(f"play: {len(hits)} results")
            lines += [f"- [play] {h.name} — {h.publisher} <{h.url}>" for h in hits]
        except Exception as e:  # noqa: BLE001
            lines.append(f"play: error {type(e).__name__}")
    return _clip(
        "\n".join(lines) or "error: store must be apple, play or both", SOURCE_RESULT_LIMIT
    )


def askdata_list_impl(ctx: ToolContext, path: str = "") -> str:
    items = ctx.askdata.list(path)
    lines = [
        f"- {'[folder]' if i.kind == 'l' else '[table]'} {i.id} — {i.text}" for i in items[:60]
    ]
    return _clip("\n".join(lines) or "empty folder", SOURCE_RESULT_LIMIT)


def askdata_table_impl(ctx: ToolContext, path: str) -> str:
    t = ctx.askdata.metadata(path)
    lines = [f"table: {t.title}"]
    for v in t.variables:
        sample = ", ".join(
            f"{c}={txt}" for c, txt in zip(v.values[:12], v.value_texts[:12], strict=False)
        )
        lines.append(f"- {v.code} ({v.text}; {len(v.values)} values): {sample}")
    return _clip("\n".join(lines), SOURCE_RESULT_LIMIT)


def askdata_fetch_impl(ctx: ToolContext, path: str, selections_json: str) -> str:
    try:
        selections = json.loads(selections_json)
    except json.JSONDecodeError as e:
        return f'error: selections_json must be JSON like {{"Year": ["2024"]}} ({e.msg})'
    if not isinstance(selections, dict):
        return "error: selections_json must be a JSON object of variable code -> list of values"
    data = ctx.askdata.fetch(path, {k: [str(x) for x in v] for k, v in selections.items()})
    lines = [" | ".join(data.columns)]
    lines += [
        " | ".join([*map(str, r.get("key", [])), *map(str, r.get("values", []))])
        for r in data.rows[:40]
    ]
    return _clip("\n".join(lines), SOURCE_RESULT_LIMIT)


# ---------- social and Kosovo sites ----------


def instagram_search_impl(ctx: ToolContext, query: str) -> str:
    if ctx.apify is None:
        return "instagram_search unavailable (no APIFY_TOKEN configured) — use web_search instead"
    query = query.strip()
    if not query:
        return "error: query is empty"
    actor_input = {
        "search": query,
        "searchType": "user",
        "searchLimit": MAX_INSTAGRAM_ACCOUNTS,
        "resultsType": "details",
        "resultsLimit": MAX_INSTAGRAM_ACCOUNTS,
    }
    out = social_guard.paid_call(
        ctx,
        "instagram",
        query,
        max_items=MAX_INSTAGRAM_ACCOUNTS,
        run=lambda n: ctx.apify.run(INSTAGRAM_ACTOR, actor_input, max_items=n),
        normalise=social.instagram_summary,
    )
    if isinstance(out, str):
        return out
    shops, q = out["shops"], out["questions"]
    gap_id = ctx.payload.get("gap_id")
    if gap_id is not None:
        repo.upsert_fact(
            ctx.session,
            FactIn(
                claim=f"Instagram search {query[:100]!r}: {len(shops)} business accounts in results",
                entity_type="social",
                entity_key=f"gap:{gap_id}",
                confidence=0.7,
                sector_slug=_or_none(ctx.payload.get("sector") or ""),
                value={"query": query, **out},
                ttl_days=30,
                source_name="apify-instagram",
            ),
            run_id=ctx.run_id,
            observed_at=ctx.now,
        )
        ctx.touched_gap_ids.add(int(gap_id))
    lines = [
        f"{len(shops)} Instagram business accounts for {query!r}",
        f"comment questions: price {q['price']}, delivery {q['delivery']}, where to buy {q['where']}",
    ]
    lines += [
        f"- @{s['username']} {s['name']} | {s['followers']} followers | {s['category'] or '-'} | "
        f"last post {s['last_post'] or '-'}"
        for s in shops
    ]
    return _clip("\n".join(lines), SOURCE_RESULT_LIMIT)


def ad_library_search_impl(ctx: ToolContext, query: str = "") -> str:
    if ctx.apify is None:
        return "ad_library_search unavailable (no APIFY_TOKEN configured) — use web_search instead"
    sweep = ctx.profile == social_guard.ADS_SWEEP_PROFILE
    query = query.strip()
    if not query and not sweep:
        return "error: query is empty"
    limit = SWEEP_MAX_ADS if sweep else MAX_ADS
    actor_input = {
        "startUrls": [{"url": ad_library_url(query)}],
        "resultsLimit": limit,
        "isDetailsPerAd": False,
    }
    out = social_guard.paid_call(
        ctx,
        "ads",
        query,
        max_items=limit,
        run=lambda n: ctx.apify.run(ADS_ACTOR, actor_input, max_items=n),
        normalise=lambda items: social.ads_summary(items, today=ctx.guard.day),
    )
    if isinstance(out, str):
        return out
    ads = out["ads"]
    gap_id = ctx.payload.get("gap_id")
    sector = _or_none(ctx.payload.get("sector") or "")
    repo.upsert_ads(
        ctx.session,
        ads,
        gap_id=int(gap_id) if gap_id is not None else None,
        sector_slug=sector,
        now=ctx.now,
    )
    head = (
        f"{out['count']} Meta ads shown in Kosovo for {query[:100] or 'all advertisers'!r}: "
        f"{out['foreign']} foreign sellers, {out['long_running']} running 30+ days"
    )
    if gap_id is not None and not sweep:
        repo.upsert_fact(
            ctx.session,
            FactIn(
                claim=head,
                entity_type="ad_signal",
                entity_key=f"gap:{gap_id}",
                confidence=0.7,
                sector_slug=sector,
                value={k: out[k] for k in ("count", "foreign", "long_running")} | {"query": query},
                ttl_days=14,
                source_name="meta-ad-library",
            ),
            run_id=ctx.run_id,
            observed_at=ctx.now,
        )
        ctx.touched_gap_ids.add(int(gap_id))

    def origin(a: dict) -> str:
        return {True: "foreign", False: "local"}.get(a["is_foreign"], "?")

    lines = [head]
    if sweep:
        by_page: dict[str, list[dict]] = {}
        for a in ads:
            by_page.setdefault(a["page_name"] or "?", []).append(a)
        lines += [
            f"- {page} | {len(group)} ads | {origin(group[0])} | "
            f"{sum(1 for a in group if a['long_running'])} running 30+ days | "
            f"{group[0]['ad_text'][:80]}"
            for page, group in sorted(by_page.items(), key=lambda kv: -len(kv[1]))
        ]
    else:
        lines += [
            f"- {a['page_name']} | {origin(a)} | since {a['first_seen'] or '?'} | "
            f"{a['ad_text'][:100]}"
            for a in ads
        ]
    return _clip("\n".join(lines), SWEEP_RESULT_LIMIT if sweep else SOURCE_RESULT_LIMIT)


def kosovo_site_crawl_impl(ctx: ToolContext, url: str) -> str:
    if ctx.crawler is None:
        return "kosovo_site_crawl unavailable (Crawl4AI is not installed) — use web_fetch instead"
    domain = allowed_domain(url)
    if domain is None:
        return f"error: only these sites can be crawled: {', '.join(ALLOWED_DOMAINS)}"
    if ctx.crawl_pages >= MAX_CRAWL_PAGES:
        return f"crawl limit reached for this task ({MAX_CRAWL_PAGES} pages) — use what you have"
    ctx.crawl_pages += 1
    source = source_for(domain)
    try:
        text = ctx.crawler.fetch(url)
    except CrawlRefused as e:
        repo.mark_source(ctx.session, source, ok=False, now=ctx.now)
        return f"page skipped: {e}"
    except Exception as e:  # noqa: BLE001 — a dead site must not kill the task
        repo.mark_source(ctx.session, source, ok=False, now=ctx.now)
        return f"page skipped: {type(e).__name__}"
    repo.mark_source(ctx.session, source, ok=True, now=ctx.now)
    return _clip(text.strip() or "(empty page)", SOURCE_RESULT_LIMIT)


# ---------- tool objects ----------


def _run(ctx: ToolContext, tool_name: str, fn: Callable, /, **kwargs) -> str:
    """Run one tool. Positional-only head: a tool argument called `name` can never collide."""
    try:
        out = fn(ctx, **kwargs)
    except Exception as e:  # noqa: BLE001 — tool errors go back to the model as text
        # A failed statement aborts the Postgres transaction; roll back so the next cost record,
        # tool call or task write runs on a usable session (otherwise: PendingRollbackError).
        if ctx.session is not None:
            ctx.session.rollback()
        out = f"error: {type(e).__name__}: {str(e)[:300]}"
    if ctx.search_note:
        out = f"{out}\n\n[scout] {ctx.search_note}"
    ctx.events.append({"tool": tool_name, "chars": len(out), "error": out.startswith("error:")})
    return out


def build_tools(ctx: ToolContext) -> list:
    @beta_tool
    def kb_search(query: str, sector: str = "") -> str:
        """Search the scout's own knowledge base (saved facts and the sector digest). Call this FIRST,
        before any web search, so you build on what is already known.

        Args:
            query: Keywords in Albanian or English, e.g. "dentist booking Prishtina".
            sector: Optional sector slug to narrow the search, e.g. "health-booking".
        """
        return _run(ctx, "kb_search", kb_search_impl, query=query, sector=sector)

    @beta_tool
    def kb_record_fact(
        claim: str,
        entity_type: str,
        entity_key: str,
        confidence: float,
        source_url: str = "",
        sector: str = "",
        ttl_days: int = 90,
        value_json: str = "",
    ) -> str:
        """Save one verifiable fact about Kosovo or a nearby market. One claim per call, with its source.

        Args:
            claim: One sentence stating the fact, with numbers and dates where possible.
            entity_type: One of sector, business, proven_model, gap, culture, stat, news, presence_check,
                demand_test, payment_path.
            entity_key: Slug of the thing the fact is about, e.g. "health-booking", "gap:12", "wolt".
            confidence: 0.0–1.0; official statistics 0.9, reputable press 0.7, a single forum post 0.3.
            source_url: Where you saw it.
            sector: Sector slug the fact belongs to, if any.
            ttl_days: How long it stays fresh (prices 30, statistics 180, culture 365).
            value_json: Optional JSON with structured values, e.g. {"count": 3, "cities": ["Prizren"]}.
        """
        return _run(
            ctx,
            "kb_record_fact",
            kb_record_fact_impl,
            claim=claim,
            entity_type=entity_type,
            entity_key=entity_key,
            confidence=confidence,
            source_url=source_url,
            sector=sector,
            ttl_days=ttl_days,
            value_json=value_json,
        )

    @beta_tool
    def kb_record_business(
        name: str,
        sector: str,
        kind: str = "local",
        city: str = "",
        instagram: str = "",
        website: str = "",
        facebook: str = "",
        note: str = "",
    ) -> str:
        """Record a business active in Kosovo (or a nearby market) in a sector — only businesses, never people.

        Args:
            name: Trading name as written on its site or profile.
            sector: Sector slug.
            kind: local, foreign (operating in Kosovo), or nearby (operating only in AL/MK/ME/BA/RS/HR/SI).
            city: Main city, e.g. "Prishtinë".
            instagram: Instagram handle without @.
            website: Website URL.
            facebook: Facebook page URL.
            note: One line: what it offers, prices, how it takes payment.
        """
        return _run(
            ctx,
            "kb_record_business",
            kb_record_business_impl,
            name=name,
            sector=sector,
            kind=kind,
            city=city,
            instagram=instagram,
            website=website,
            facebook=facebook,
            note=note,
        )

    @beta_tool
    def kb_record_proven_model(
        slug: str,
        name: str,
        sector: str,
        description: str,
        markets_json: str,
        business_model: str = "",
        source_urls_json: str = "",
    ) -> str:
        """Record a business model that works somewhere else, with the markets where it is proven.

        Args:
            slug: Short id, e.g. "pet-sitting-marketplace".
            name: Human name.
            sector: Sector slug.
            description: Two or three sentences: what it is, who pays, why it works.
            markets_json: JSON list of {"country": "HR", "example": "Pawshake", "url": "https://..."}; use
                ISO-2 codes; nearby markets AL MK ME BA RS HR SI count three times in scoring.
            business_model: How it makes money (commission, subscription, ads, lead fees).
            source_urls_json: JSON list of URLs backing the evidence.
        """
        return _run(
            ctx,
            "kb_record_proven_model",
            kb_record_proven_model_impl,
            slug=slug,
            name=name,
            sector=sector,
            description=description,
            markets_json=markets_json,
            business_model=business_model,
            source_urls_json=source_urls_json,
        )

    @beta_tool
    def kb_propose_gap(
        title: str,
        sector: str,
        hypothesis: str,
        presence_level: str = "unknown",
        proven_model_slug: str = "",
        why_not_yet: str = "",
    ) -> str:
        """Propose a gap: a proven model that seems missing or weak in Kosovo. Duplicates are merged by title.

        Args:
            title: Short name, e.g. "Pet sitting marketplace".
            sector: Sector slug.
            hypothesis: Who in Kosovo would pay, for what, and the evidence so far.
            presence_level: absent, exists-but-poor, prishtina-only, offline-only, instagram-only, decent
                or unknown — say "unknown" unless you ran a presence check.
            proven_model_slug: Slug of the proven model it copies, if recorded.
            why_not_yet: The best reason nobody has done it (payments, trust, size, regulation, logistics).
        """
        return _run(
            ctx,
            "kb_propose_gap",
            kb_propose_gap_impl,
            title=title,
            sector=sector,
            hypothesis=hypothesis,
            presence_level=presence_level,
            proven_model_slug=proven_model_slug,
            why_not_yet=why_not_yet,
        )

    @beta_tool
    def kb_write_digest(key: str, title: str, body_md: str) -> str:
        """Write or replace a long-term digest the scout re-reads every day. Keep it under 5,000 characters,
        factual, with the most decision-relevant points first.

        Args:
            key: "sector:<slug>", "culture:<theme>" or "country".
            title: Digest title.
            body_md: Markdown body.
        """
        return _run(
            ctx, "kb_write_digest", kb_write_digest_impl, key=key, title=title, body_md=body_md
        )

    @beta_tool
    def places_search(query: str, city: str = "", language: str = "sq") -> str:
        """Google Places text search for real businesses in a Kosovo city (free quota, use for presence checks).

        Args:
            query: Service in Albanian or English, e.g. "veteriner" or "dog groomer".
            city: One of Prishtinë, Prizren, Pejë, Gjakovë, Mitrovicë, Ferizaj, Gjilan.
            language: "sq" or "en".
        """
        return _run(
            ctx, "places_search", places_search_impl, query=query, city=city, language=language
        )

    @beta_tool
    def app_store_search(term: str, store: str = "both") -> str:
        """Search the Kosovo App Store and Google Play storefronts for apps matching a keyword.

        Args:
            term: Keyword, e.g. "taxi", "dentist", "parking".
            store: apple, play or both.
        """
        return _run(ctx, "app_store_search", app_store_search_impl, term=term, store=store)

    @beta_tool
    def askdata_list(path: str = "") -> str:
        """List folders and tables of Kosovo's official statistics (ASKdata). Start with an empty path.

        Args:
            path: Folder path such as "Population" or "Household budget survey".
        """
        return _run(ctx, "askdata_list", askdata_list_impl, path=path)

    @beta_tool
    def askdata_table(path: str) -> str:
        """Show the variables and values of one ASKdata table so you can build a query.

        Args:
            path: Table path ending in .px, e.g. "Population/tbl01.px".
        """
        return _run(ctx, "askdata_table", askdata_table_impl, path=path)

    @beta_tool
    def askdata_fetch(path: str, selections_json: str) -> str:
        """Fetch numbers from one ASKdata table.

        Args:
            path: Table path ending in .px.
            selections_json: JSON object mapping variable code to the list of values, e.g.
                {"Year": ["2024"], "Municipality": ["Prizren"]}. Keep selections small.
        """
        return _run(
            ctx, "askdata_fetch", askdata_fetch_impl, path=path, selections_json=selections_json
        )

    @beta_tool
    def instagram_search(query: str) -> str:
        """Find Instagram business accounts in Kosovo by keyword (paid; one call per task; only while
        checking a gap that scores 60+). Returns public business accounts with followers and last post
        date, plus counts of comments asking about price, delivery or where to buy.

        Args:
            query: The word local sellers use, found first with web_search site:instagram.com, e.g.
                "torta prishtine" or "lule ferizaj".
        """
        return _run(ctx, "instagram_search", instagram_search_impl, query=query)

    @beta_tool
    def ad_library_search(query: str = "") -> str:
        """Search the public Meta Ad Library for ads shown in Kosovo (paid; one call per task). Shows who
        pays to sell this, whether the seller is local or foreign, and how long each ad has run.

        Args:
            query: Words a seller would put in the ad, in Albanian, e.g. "dërgesa falas torta". Leave
                empty only in the weekly ads sweep.
        """
        return _run(ctx, "ad_library_search", ad_library_search_impl, query=query)

    @beta_tool
    def kosovo_site_crawl(url: str) -> str:
        """Read one page of an allowlisted Kosovo site as Markdown (free; up to 20 pages per task):
        merrjep.com, gjirafa50.com, kosovajob.com, telegrafi.com, koha.net, kallxo.com,
        prishtinainsight.com, arbk.rks-gov.net. Use it for listings, prices and job ads.

        Args:
            url: Full https URL on one of those sites, e.g. a Merrjep search results page.
        """
        return _run(ctx, "kosovo_site_crawl", kosovo_site_crawl_impl, url=url)

    tools = [
        kb_search,
        kb_record_fact,
        kb_record_business,
        kb_record_proven_model,
        kb_propose_gap,
        kb_write_digest,
        places_search,
        app_store_search,
        askdata_list,
        askdata_table,
        askdata_fetch,
    ]
    if ctx.apify is not None:
        tools += [instagram_search, ad_library_search]
    if ctx.crawler is not None:
        tools.append(kosovo_site_crawl)
    return tools
