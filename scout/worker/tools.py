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
from scout.sources import apple, play
from scout.sources.askdata import AskDataClient
from scout.sources.places import PlacesClient

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
)
PRESENCE_LEVELS = (
    "absent",
    "exists-but-poor",
    "prishtina-only",
    "offline-only",
    "decent",
    "unknown",
)
DIGEST_PREFIXES = ("sector:", "culture:", "country")
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


# ---------- knowledge base ----------


def kb_search_impl(ctx: ToolContext, query: str, sector: str = "") -> str:
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
    value = None
    if value_json.strip():
        try:
            value = json.loads(value_json)
        except json.JSONDecodeError:
            value = {"raw": value_json[:500]}
    fact = repo.upsert_fact(
        ctx.session,
        FactIn(
            claim=claim,
            entity_type=entity_type,
            entity_key=_fit(entity_key, W_ENTITY_KEY),
            confidence=min(max(float(confidence), 0.0), 1.0),
            source_url=_or_none(source_url),
            sector_slug=_or_none(sector),
            value=value,
            ttl_days=max(1, min(int(ttl_days), 365)),
        ),
        run_id=ctx.run_id,
        observed_at=ctx.now,
    )
    return f"fact #{fact.id} saved (confidence {fact.confidence:.2f}, expires {fact.expires_at.date()})"


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
    return (
        f"gap #{gap.id} {'(new)' if created else '(existing)'}: {gap.title} [status {gap.status}]"
    )


def kb_write_digest_impl(ctx: ToolContext, key: str, title: str, body_md: str) -> str:
    key = _fit(key, W_DIGEST_KEY)
    if not (key == "country" or key.startswith(("sector:", "culture:"))):
        return f"error: key must be 'country', 'sector:<slug>' or 'culture:<theme>' (got {key!r})"
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
            lines.append(f"apple: {len(hits)} results")
            lines += [f"- [apple] {h.name} — {h.publisher} <{h.url}>" for h in hits]
        except Exception as e:  # noqa: BLE001 — a dead source must not kill the task
            lines.append(f"apple: error {type(e).__name__}")
    if store in ("play", "both"):
        try:
            hits = ctx.play_search(term, country="xk", lang="sq", limit=8)
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
            presence_level: absent, exists-but-poor, prishtina-only, offline-only, decent or unknown — say
                "unknown" unless you ran a presence check.
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

    return [
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
