# Kosovo Gap Scout — Design Spec and Six-Month Venture Plan

**Date:** 2026-10-09 · **Founder:** Elton · **Status:** design confirmed in conversation; written in one pass on the founder's instruction ("write the plan without stopping").
**Companion:** `docs/superpowers/plans/2026-10-09-kosovo-gap-scout-m1-engine.md` (implementation plan for Milestone 1).

## 0. The one-paragraph version

A platform, running every morning on Render with Elton's own Claude API key, that keeps a living model of Kosovo — its sectors, businesses, people, culture, prices, complaints, app charts, ads — and hunts for **business models proven in nearby or European markets that are missing or badly served in Kosovo**. It remembers everything it learns (Neon Postgres), spends a hard-capped few euros a day, asks the founder at most five real-world questions a week, and keeps a ranked, evidence-backed list of gaps with the confidence it has in each. The venture goal is not "build a platform"; it is **by 2027-04-09 be running a real business in a verified Kosovo gap**. The platform is the instrument; the gates in Part A are the point.

---

# Part A — The venture plan

## A1. Objective and definition of success

| Horizon | Outcome | Measured by |
|---|---|---|
| 2026-11-15 (Gate 1) | The scout has mapped Kosovo and produced ≥ 10 gap candidates scoring ≥ 60/100 | `gaps` table, scorecard |
| 2026-12-13 (Gate 2) | ≥ 3 gaps **verified** (presence check done, confidence ≥ 0.7, test plan written); founder picks 2 to test | `gaps.status = verified` |
| 2027-01-10 (Gate 3) | One gap passes a real demand test with strangers' money or time (benchmarks in A6) | landing-page / ads metrics |
| 2027-02-21 (Gate 4a) | Thinnest sellable product live; ≥ 10 real users active weekly; business registered at ARBK at first revenue | product analytics, ARBK certificate |
| 2027-04-09 (Gate 4) | **≥ €500 MRR or ≥ 100 paying customers** (or ≥ 1,000 weekly actives if ad-supported) | bank/payment records |

If a gate fails, the rule is to go back one phase with the scout's next-best candidate, not to stall. The platform's cost of carrying on is small (A7); the founder's time is the scarce thing.

## A2. Founder profile and constraints (from the interview)

- Goal: a real, scalable company — not a side income.
- Time: 5–10 h/week next to a full-time job (Cardo AI). Practical shape: 10 min every morning, one 3–4 h block on Saturday, 30–60 min on Sunday.
- Domains: AI tools and agents first; open to anything that is software-only.
- Budget: €500–2,000 over six months. Platform ≤ ~€300 of it; the rest buys demand tests and the MVP.
- Customers: consumers (B2C). Market: Kosovo first; every idea must be able to grow to Albanian speakers everywhere (Albania, North Macedonia, the diaspora in DE/CH/AT/IT/UK/US).
- Reach: no audience today; comfortable buying attention with ads and SEO.
- Delivery: a web dashboard (mobile-first), read in the morning, acted on at the weekend.
- Standing exclusions (assumed, unconfirmed): nothing overlapping Cardo AI's business (asset-based-finance / securitisation software, B2B fintech); nothing requiring a financial, health or gambling licence; nothing needing physical inventory.
- Standing rules: public, logged-out data only; businesses, not people; the project runs on Elton's own API key and accounts, never Cardo's.

## A3. What counts as a gap

A **gap** is a *(proven model, Kosovo sector)* pair where:

1. the model is proven — it has worked commercially in at least one nearby market (AL, MK, ME, BA, RS, HR, SI count triple) or several EU/US markets;
2. Kosovo's presence level is *absent*, *exists-but-poor*, *Prishtina-only* or *offline-only* (B8 defines these);
3. there is a demand signal in Kosovo (complaints, searches, Facebook-group workarounds, diaspora requests, neighbour-market usage);
4. the founder can test it for ≤ €2,000 and build it part-time; and
5. the "why hasn't anyone done it" answer is not a structural blocker (regulation, payments, logistics, too-small market).

### A3.1 Scoring rubric (0–100)

| Component | Points | How it is scored |
|---|---|---|
| Proof elsewhere | 0–25 | Each nearby-market example counts ×3, each EU/US example ×1; evidence must cite a live business with a URL. 25 = thriving in ≥ 2 nearby markets. |
| Kosovo absence | 0–25 | Capped by presence level: absent 25 · exists-but-poor 18 · Prishtina-only 12 · offline-only 10 · decent 0 · unknown 12. **Without a recorded presence check (B8) the cap is 12 and confidence ≤ 0.5.** |
| Demand signal | 0–20 | Direct evidence from Kosovo (Albanian-language complaints, group posts, search interest, waiting lists, ad spend by adjacent players). |
| Founder fit | 0–15 | Software-only, AI-leverage, buildable in Saturdays, no licence; B2C with an Albanian-speaking growth path. |
| Why-not-yet risk | 0–15 | Scored as a penalty 0–15 and awarded as 15 − penalty. Structural blockers (payments, law, logistics, market size) score high penalties. |

**Hard filters** (fail → total 0, status `killed`): regulated finance/health/gambling; physical inventory or fleet; overlap with Cardo AI; > €2,000 to test; needs the founder full-time before revenue.

**Confidence** (0–1) is tracked separately from the score. High score + low confidence does not go up the list — it generates a field check for the founder (A5, B12).

### A3.2 Illustrative candidates to seed the hunt (all *unverified*; the scout's first job is to verify or kill them)

Transit and parking apps (the SkopjeBus pattern seen live in the MK chart diff) · second-hand fashion marketplace (Vinted-style, present in HR/RS) · dentist and clinic booking for Kosovo's dental-tourism trade · tutoring and Matura-prep marketplaces · home-services booking (cleaners, repairs) · student and long-term rental platforms with verified listings · wedding-industry marketplace (vendors, venues, dresses) · diaspora-to-family services (gifting, local errands, property care) · pet services · event ticketing beyond the big festivals · utility-bill and bureaucracy helpers (e-Kosova navigation) · car-service booking · local farm-box subscriptions.

## A4. Six-month calendar

Dates are Kosovo local (Europe/Belgrade in tzdata). Phase lengths respect 5–10 h/week.

| Phase | Dates | Platform state | Founder work | Gate (pass = proceed) |
|---|---|---|---|---|
| **0 · Setup** | Fri 2026-10-09 → Sun 2026-10-18 | Build **M1 engine** (two Saturdays), deploy cron, seed sectors + culture, first live runs at €1/day | Create API key, Neon DB, Render services, Google Places key; read employment contract clauses (side work, IP, non-compete); run `scout run` twice by hand | Engine runs unattended 3 days in a row; costs recorded match the console |
| **1 · Foundation** | Mon 10-19 → Sun 11-15 (4 wks) | Daily cap **€3**; profiles: map-sector ×2, hunt-models ×2, culture ×1 (weeks 1–2), news-scan, chart-diff (Mon), deep-dive (Sun). **M2** (dashboard + Tier B social/ads) built on Saturdays 10-24 and 10-31 | 10 min/day brief; Sunday ≤ 5 field checks; Saturday build | **Gate 1:** ≥ 20 sectors mapped, ≥ 10 gaps ≥ 60, ≥ 3 Sunday field-check rounds done |
| **2 · Verification** | Mon 11-16 → Sun 12-13 (4 wks) | Daily cap **€1.5**; verify-gap ×2/day on the top 10, news-scan, chart-diff; Critic runs on every changed gap; **M3** (Batches, pushes, scorecard charts) optional | Pick finalists, visit 2–3 businesses in person (Tier D), talk to 10 potential users | **Gate 2:** ≥ 3 gaps verified (confidence ≥ 0.7, presence check ≤ 30 days old, test plan); founder chooses 2 |
| **3 · Demand tests** | Mon 12-14 → Sun 2027-01-10 (4 wks) | Cap **€0.8**; maintenance mode (news-scan, chart-diff weekly, verify on demand) | Two landing pages in Albanian, €75–150 Meta/TikTok ads each, Instagram DM outreach; weekly read-out | **Gate 3:** one idea hits an A6 benchmark |
| **4 · MVP** | Mon 01-11 → Sun 02-21 (6 wks) | Cap €0.8; `Ask` page used as research assistant for the build | Build the thinnest sellable version; register at ARBK on first euro; open business bank account | **Gate 4a:** ≥ 10 real users active weekly, ≥ 1 paying |
| **5 · Launch** | Mon 02-22 → Fri 04-09 (7 wks) | Cap €0.8; scout keeps watching competitors and complaints | Paid acquisition, referral loop, weekly iteration | **Gate 4:** ≥ €500 MRR or ≥ 100 paying (or ≥ 1,000 WAU if ad-supported) |

Holiday caveat: 12-20 → 01-10 the diaspora is in Kosovo and local attention shifts; demand-test numbers in that window need a second week in January before a go/no-go.

## A5. Weekly rhythm (what the founder actually does)

- **Every morning (10 min):** read the brief. React to at most three things: kill, park, or "verify this". The dashboard buttons write directly to `gaps.status`.
- **Saturday (3–4 h):** Phase 0–1: build the next milestone with Claude Code. Phase 2: field visits and user conversations. Phase 3+: build and ship.
- **Sunday (30–60 min):** answer the ≤ 5 field checks the scout queued (each ≤ 3 min: "Is there a dentist-booking app in Prizren you know of?", "Would your cousin pay €5/month for X?"). Read the Sunday deep-dive memo.
- **Monthly (1 h):** check real spend against A7; review the scorecard; re-weight sector priorities in Settings.

## A6. Demand-test playbook (Phase 3)

For each of the two finalists:

1. **Promise page** in Albanian (and English variant for diaspora), one screen, one call to action; built in an afternoon (static site on Render). Collect: email/phone, city, one qualifying question.
2. **Traffic:** Meta ads (Facebook + Instagram placements, Kosovo geo, interests from the gap's demand facts), TikTok if the audience is under 30; €75–150 per idea over 10–14 days; two creatives per idea, Albanian copy written with the scout's culture digest at hand.
3. **Direct outreach:** 30 Instagram DMs/day to people visibly looking for the thing (the Tier B hashtag/place scrapes give the list of public business pages, not individuals — outreach to individuals is manual and consensual only).
4. **Benchmarks (any one passes):** cost per lead < €1.50 **and** ≥ 50 sign-ups; or ≥ 5 pre-orders/deposits (even €5); or ≥ 20 two-way conversations where a stranger describes the problem unprompted.
5. **Kill rule:** < 15 sign-ups after €75 and 7 days with two creatives tried → stop, move to the next candidate.

Everything measured goes back into the scout as `facts` with confidence 0.95 (entity_type `demand_test`), so the ranking reflects reality.

## A7. Money plan

| Item | Phase 0 | Phase 1 | Phase 2 | Phases 3–5 | Total (≈) |
|---|---|---|---|---|---|
| Claude models + web search (daily caps) | €10 | ≤ €84 (cap €3 × 28) | ≤ €42 | ≤ €70 (€0.8 × 86 d) | **≤ €206** |
| Apify Starter (Tier B; ~$19/mo, 2 months) | — | €18 | €18 | pay-as-you-go | €36 |
| Render (cron ≈ €1–3/mo; web service from M2 ≈ €7/mo) | €1 | €8 | €8 | €24 | €41 |
| Neon Postgres (free tier) · Google Places (free tiers) | €0 | €0 | €0 | €0 | €0 |
| Domain(s) | — | — | €12 | — | €12 |
| **Platform total** | | | | | **≈ €295** |
| Demand tests (ads, 2 ideas) | | | | €200–300 | €200–300 |
| MVP tooling (email, hosting, payments setup) | | | | €50–100 | €50–100 |
| **Six-month total** | | | | | **≈ €550–700** |

Prices are from the claude-api skill and vendor pages read on 2026-10-09; the Costs page shows actuals from `response.usage` and actor run stats, so drift is visible within a day.

## A8. Risks and mitigations

| Risk | Why it matters here | Mitigation built into the plan |
|---|---|---|
| Market is small (≈ 1.6 M people, lower income) | Many proven models need density Kosovo lacks | Nearby-market weighting ×3 (if it works in Skopje or Tirana it can work in Prishtina); Albanian-speaker growth path is a scoring requirement |
| Payments: Stripe is not in Kosovo; PayPal is limited; cash-on-delivery dominates | Blocks subscriptions and marketplaces | Treated as a *why-not-yet* penalty, not a filter; verify-gap must record the payment path (local bank gateway, merchant-of-record such as Paddle, COD, in-app stores) before `verified` |
| Scraper fragility (Meta/TikTok) | Social data is the most Kosovo-specific signal | Tier B pay-per-result actors instead of self-hosted logged-in scrapers; every source has a health flag and the brief says when a source is degraded |
| The model "hallucinates absence" | A confident "there is no X in Kosovo" is the single most expensive error | Rubric caps absence at 12 and confidence at 0.5 until a presence check (7 cities, 5 channels) is recorded; Critic attacks every top-3 claim |
| Founder time | 5–10 h/week disappears into platform tinkering | Milestones are small; Phase 3 onwards the platform is in maintenance mode; gates force decisions |
| Legal/ToS | Scraping Meta properties; Kosovo Law 06/L-082 (GDPR-aligned) | Public, logged-out, business entities only; no account cookies ever; TTL and deletion; Meta v. Bright Data (N.D. Cal., Jan 2024) found logged-off public scraping outside ToS breach, but it is not binding in Kosovo — keep to business pages and ads |
| Employment contract | Side-work, IP, non-compete clauses | Read before Phase 1; nothing overlapping Cardo AI; own hardware, own accounts, own time |
| Analysis paralysis | A ranked list that never ends | Gate 2 forces a choice of two; the kill rule in A6 is mechanical |
| Seasonality | Summer diaspora return, weddings, winter holidays distort signals | Culture digest carries a calendar; Strategist is told the date and season |

## A9. Legal, employment and ethics guardrails

- **Data:** only public pages; only legal entities and public business accounts; natural persons' data is not stored (reviewer names in Places results are discarded; Instagram comments are not collected). Facts carry `expires_at`; raw payloads are not retained beyond extraction.
- **Platforms:** no logins, no cookies, no CAPTCHA solving. Tier C crawlers obey `robots.txt`, identify themselves, and rate-limit to one request per 2–5 s per host.
- **Kosovo law:** Law 06/L-082 on Protection of Personal Data applies to natural persons — the design avoids them. Business registration at ARBK (online via e-Kosova) at first revenue; VAT registration threshold and company form (B.I. vs SH.P.K.) to confirm with an accountant in Phase 4.
- **Employment:** check Cardo AI contract for side-work/IP/non-compete; keep the project on personal accounts and hardware; never use Cardo's Anthropic account.
- **Ethics of demand tests:** promise pages say "coming soon / join the waitlist" truthfully; deposits are refundable.

## A10. Decision rules

- A gap moves to **verified** only with: presence check ≤ 30 days old; ≥ 2 proof-elsewhere citations (≥ 1 nearby); payment path recorded; Critic verdict `proceed` or `needs_field_check` answered; confidence ≥ 0.7.
- A gap is **parked** when confidence < 0.4 after two verify-gap runs and one field check, or when a why-not-yet penalty ≥ 12 is confirmed.
- A gap is **killed** by a hard filter, by the founder, or by a Critic `kill` the founder accepts.
- The founder chooses finalists; the scout recommends. Buttons on the dashboard are the only way status changes by hand, and every change is journaled.


---

# Part B — The platform design

## B1. Architecture

```
            Render cron 06:00 UTC (daily)                       Render web service (M2)
 ┌────────────────────────────────────────────────┐    ┌──────────────────────────────┐
 │ DIRECTOR  plan → enqueue → run → assess → brief │    │ DASHBOARD  FastAPI + HTMX    │
 │   budget guard wraps every paid call            │    │  Today · Gaps · Field checks │
 └───────┬───────────────┬──────────────┬──────────┘    │  Pipeline · Knowledge · Ask  │
         │               │              │               │  Journal · Costs · Settings  │
         ▼               ▼              ▼               └──────────────┬───────────────┘
 ┌──────────────┐ ┌──────────────┐ ┌────────────────┐                  │
 │ RESEARCH     │ │ EXTRACTOR    │ │ STRATEGIST +   │                  │
 │ WORKER       │ │ Haiku 5.5    │ │ CRITIC         │                  │
 │ Sonnet 5.5   │ │ structured   │ │ Opus 5.5       │                  │
 │ tool runner  │ │ outputs      │ │ structured out │                  │
 └──────┬───────┘ └──────┬───────┘ └───────┬────────┘                  │
        │ tools          │                 │                           │
        ▼                ▼                 ▼                           ▼
 ┌──────────────────────────────────────────────────────────────────────────────┐
 │ KNOWLEDGE BASE  Neon Postgres: facts (TTL, hash) · digests · sectors ·        │
 │ businesses · proven_models · gaps · assessments · field_checks · tasks queue  │
 │ · runs · costs · journal · scorecard · app_chart_snapshots · ads · briefs     │
 └──────────────────────────────────────────────────────────────────────────────┘
        ▲                ▲                 ▲
 ┌──────┴────────────────┴─────────────────┴────────────────────────────────────┐
 │ SOURCE LAYER "Kosovo Eyes"                                                   │
 │ A official/free: ASKdata PxWeb · Google Places (Pro) · Apple RSS charts ·     │
 │   Google Play (gl=XK) · Claude web_search/web_fetch (Albanian-first)         │
 │ B pay-per-result (Apify): Instagram · Facebook Pages · Meta Ad Library ·      │
 │   TikTok · Google Maps fallback                                              │
 │ C self-hosted crawlers (Crawlee/Playwright): Merrjep · Gjirafa50 · KosovaJob │
 │   · Telegrafi/Koha/Kallxo/Prishtina Insight · ARBK                           │
 │ D the founder: ≤ 5 field checks on Sundays, answered in the dashboard        │
 └──────────────────────────────────────────────────────────────────────────────┘
```

Two Render services (cron + web), one Neon database, no Redis, no message broker: the task queue is a Postgres table claimed with `SELECT … FOR UPDATE SKIP LOCKED`.

## B2. The daily run

1. **Start.** `scout run` starts a `runs` row with the phase and the daily cap. The budget guard reads today's spend (sum of `costs.cost_eur` for today's local date) and refuses the run if the cap is already spent.
2. **Plan.** The deterministic planner (B9) reads the state (sectors by status, gaps by status/score/confidence, culture themes seeded, last chart-diff, open field checks) and produces the day's task list with estimated costs. If ≥ 3 tasks are planned, one capped Opus review call (≤ €0.10) may drop or reorder them; its reasons go in the journal.
3. **Run.** The worker claims tasks one at a time (highest priority first). Before each task — and before each model iteration inside a task — the guard checks `spent + estimate ≤ cap`. Tasks run sequentially so the second task reads the prompt cache the first one wrote.
4. **Assess.** For sectors whose facts or gaps changed today, the Strategist (Opus) scores gaps against the rubric and proposes field checks; the Critic (Opus) attacks the top three. At most two Opus calls per run.
5. **Brief.** The Editor writes the brief if anything changed; otherwise a one-line "quiet day" entry. No model call on quiet days.
6. **Remember.** Journal entry (did / learned / tomorrow), scorecard snapshot, `runs` row closed with spend and counts. The next run reads the last three journal entries, so the scout knows what it did yesterday.
7. **Stop conditions.** Budget exhausted, queue empty, or 50 minutes elapsed (Render cron safety). Unfinished tasks stay queued for tomorrow.

## B3. Source Layer — "Kosovo Eyes"

Rules for every source: public and logged-out only; no account cookies ever; business entities, not people; each source has a TTL (how long its facts stay fresh), a € cost per call recorded in `costs`, a health flag, and a milestone when it ships.

| Tier | Source | What it gives the scout | Cost | TTL | Ships |
|---|---|---|---|---|---|
| A | **ASKdata PxWeb API** `https://askdata.rks-gov.net/api/v1/en/ASKdata/` (26 folders incl. Population, Prices, ICT, Household budget survey, Labour market, Tourism, Structural business statistics) | Official statistics: population by municipality, household spending, ICT use, wages, business register counts | €0 | 180 d | M1 |
| A | **Google Places API (New) Text Search**, Pro field mask only (`places.id, displayName, formattedAddress, primaryType, types, businessStatus, location`) — 5,000 free calls/month | Presence checks: how many businesses of type X exist in each of 7 cities; names and types | €0 under quota (guard caps at 4,500/mo); Enterprise mask (ratings) only for finalists | 60 d | M1 |
| A | **Apple top-charts RSS** `https://rss.marketingtools.apple.com/api/v2/{xk,al,mk,me,ba,rs,hr,si}/apps/top-free/25/apps.json` | What consumers in Kosovo and neighbours install; chart diff reveals category gaps (verified live: xk chart has APTV, Wolt, GjirafaMall, Vala jone; mk has SkopjeBus) | €0 | 7 d | M1 |
| A | **Google Play storefront** `https://play.google.com/store/apps/collection/topselling_free?gl=XK&hl=en` (+ `google-play-scraper` search with `country="xk"`) | Same for Android (≈ 85 %+ of Kosovo phones) | €0 | 7 d | M1 |
| A | **Claude web_search / web_fetch** (`web_search_20250305`, `web_fetch_20250910` — basic versions, see scout/sources/web.py; `max_uses` per task) | Albanian-first queries ("a ka … në Kosovë", "aplikacion për …", "ku mund të …"), then English; news, forums, company sites, neighbour markets | ≈ $0.01 per search + tokens | per fact | M1 |
| A | **iTunes Search API** `https://itunes.apple.com/search?term=…&country=xk&entity=software` | App presence check by keyword | €0 | 30 d | M1 |
| B | **Apify — Instagram** (official `apify/instagram-scraper` hashtag/place/profile modes) | Who sells what in Kosovo (the economy lives on Instagram): business profiles per hashtag/place, post counts, follower counts | ≈ $2.3–2.7 / 1k results | 30 d | M2 |
| B | **Apify — Facebook Pages posts** | Local businesses' pages, posting frequency, offers | ≈ $2–5 / 1k | 30 d | M2 |
| B | **Apify — Meta Ad Library** (commercial ads, country XK) | **Who is paying to acquire Kosovo customers, for what** — the strongest demand signal available | ≈ $3 / 1k ads | 14 d | M2 |
| B | **Apify — TikTok** | Under-30 trends and creators selling services | ≈ $1.7–2 / 1k | 14 d | M2 |
| B | **Apify — Google Maps** | Fallback when Places quota is spent or ratings are needed in bulk | ≈ $1.5 / 1k | 60 d | M2 |
| C | **Crawlee (Python) / Playwright crawlers**: Merrjep (classifieds: what people buy/sell second-hand), Gjirafa50 (e-commerce prices), KosovaJob (what skills are hired → which services are growing), Telegrafi / Koha / Kallxo / Prishtina Insight (news), ARBK (business registry, JS app) | Prices, volumes, launches, complaints, registrations | Render compute only | 7–30 d | M4 |
| D | **The founder** | Ground truth: "I checked, there are two such shops in Prizren", "my aunt pays €X for this" | time (≤ 15 min/week) | 180 d | M1 (CLI) / M2 (UI) |

Open-source self-hosted scrapers for Instagram/Facebook/TikTok (instaloader, facebook-scraper and the like) were evaluated and rejected for 2026: they require logged-in sessions, break monthly and risk account bans. Apify's pay-per-result actors cost cents at this volume and keep the project on the right side of the logged-out rule. The `sources` table stores actor IDs and prices so they can be swapped without code changes.

## B4. Knowledge base schema (Neon Postgres)

All times UTC; money as `NUMERIC(12,6)` EUR; JSON as `JSONB`.

| Table | Purpose | Key columns |
|---|---|---|
| `sources` | registry of Kosovo Eyes | `id, tier, name, kind, base_url, ttl_hours, cost_per_call_eur, enabled, config, last_ok_at, failure_count` |
| `digests` | maintained prose the models read (country, culture themes, sectors) | `key PK` (`country`, `culture:<theme>`, `sector:<slug>`), `title, body_md, updated_at, token_estimate` |
| `sectors` | the taxonomy | `id, slug UNIQUE, name_en, name_sq, status` (`unmapped/mapped/hunted/parked`), `presence_level, priority, last_mapped_at, last_hunted_at` |
| `businesses` | legal entities / public business accounts | `id, sector_id, name, kind` (`local/foreign/neighbour`), `city, channels` (JSON: instagram, facebook, website, apple_id, play_id), `note, first_seen, last_seen, UNIQUE(sector_id, lower(name))` |
| `proven_models` | models that work elsewhere | `id, slug UNIQUE, name, sector_id, description, markets` (JSON list of `{country, example, url, since, scale}`), `business_model, source_urls, nearby_count, updated_at` |
| `gaps` | the ranked list | `id, title, sector_id, proven_model_id, hypothesis_md, presence_level, why_not_yet_md, test_plan_md, score_total, score_components, confidence, status` (`candidate/scored/verifying/verified/testing/building/parked/killed`), `created_at, updated_at, last_assessed_run_id, UNIQUE(sector_id, lower(title))` |
| `gap_assessments` | history of Strategist/Critic output | `id, gap_id, run_id, model, strategist, critic, score_total, confidence, created_at` |
| `field_checks` | Tier D questions | `id, gap_id, question, why, status` (`open/answered/skipped`), `answer, due, created_at, answered_at` |
| `facts` | atomic evidence | `id, hash UNIQUE, entity_type, entity_key, sector_id, claim, value, confidence, source_name, source_url, observed_at, expires_at, run_id` |
| `tasks` | the queue | `id, profile, payload, status` (`queued/running/done/failed/skipped`), `priority, est_cost_eur, actual_cost_eur, attempts, error, result_md, run_id, locked_by, created_at, started_at, finished_at` |
| `runs` | one per day | `id, day, phase, budget_cap_eur, spent_eur, tasks_done, tasks_failed, status, summary_md, started_at, finished_at` |
| `costs` | the ledger | `id, day, run_id, task_id, kind` (`llm/search/places/apify/other`), `provider, model, units, cost_eur, request_id, created_at` |
| `journal` | continuity | `id, run_id, day, did_md, learned_md, tomorrow_md, created_at` |
| `scorecard` | daily metrics snapshot | `id, day UNIQUE, metrics` |
| `app_chart_snapshots` | chart history | `id, store` (`apple/play`), `country, chart, rank, app_key, app_name, captured_on, UNIQUE(store,country,chart,app_key,captured_on)` |
| `ads` (M2) | Meta Ad Library results | `id, page_name, page_url, country, ad_text, platforms, first_seen, last_seen, sector_guess, raw` |
| `briefs` | what the founder reads | `id, run_id, day, markdown, created_at` |
| `settings` | runtime knobs | `key PK, value` |

Fact freshness: `expires_at = observed_at + ttl`; expired facts are excluded from searches and digests but kept for history. Re-observing the same claim (same `hash` of `entity_type|entity_key|normalised claim`) refreshes `observed_at` and takes the higher confidence rather than duplicating.

## B5. Research Worker and task profiles

One class, `ResearchWorker`, drives the SDK tool runner (`client.beta.messages.tool_runner`) on **Sonnet 5.5** with the server tools `web_search_20260209` and `web_fetch_20260209` (dynamic filtering keeps search results small) plus custom tools over the knowledge base and Tier A sources:

`kb_search`, `kb_record_fact`, `kb_record_business`, `kb_record_proven_model`, `kb_propose_gap`, `places_search`, `app_store_search`, `askdata_list`, `askdata_table`, `askdata_fetch`.

The tool set is identical for every profile (so the tools+system prefix caches across tasks); the profile is expressed in the first user message (the *brief*). `pause_turn` is handled by restarting the runner with the mirrored history (the Python runner does not auto-resume); each yielded message's `usage` is priced and recorded before the next iteration, and the loop stops early when the remaining budget cannot pay for another iteration.

| Profile | Purpose | Model | `max_uses` search/fetch | Max iterations | Est. € | Cadence |
|---|---|---|---|---|---|---|
| `map-sector` | Build/refresh a sector digest: local players, prices, channels, presence level, complaints (Albanian search), 5–10 facts, 0–3 proven-model leads | Sonnet 5.5 | 12 / 8 | 14 | 0.35 | Phase 1: 2/day |
| `hunt-models` | For a mapped sector find models proven nearby and in the EU; record `proven_models` with market evidence; propose gap candidates | Sonnet 5.5 | 12 / 8 | 14 | 0.35 | Phase 1: 2/day |
| `verify-gap` | Run the presence-check protocol (B8), record payment path and why-not-yet evidence, update presence level and confidence, propose a field check if ambiguous | Sonnet 5.5 | 10 / 6 | 14 | 0.40 | Phase 1: 1/day · Phase 2: 2/day |
| `culture` | Write/refresh one culture-theme digest (Appendix B) from statistics, press, and Albanian sources | Sonnet 5.5 | 10 / 8 | 12 | 0.30 | Phase 0–1: 1/day until seeded; monthly refresh |
| `news-scan` | Last 48 h in Kosovo: launches, funding, closures, regulation, viral complaints → facts and flags | Sonnet 5.5 | 4 / 4 | 6 | 0.10 | daily |
| `chart-diff` | Snapshot Apple/Play top-free for xk + 7 neighbours; apps popular in ≥ 2 neighbours and absent from Kosovo become leads; Haiku classifies them | deterministic + Haiku | — | — | 0.05 | Mondays (and on demand) |
| `deep-dive` | Full memo on the current top gap: market size for Kosovo and Albanian speakers, unit economics, GTM, risks, two-week test plan | Opus 5.5 | 8 / 6 | 10 | 0.80 | Sundays |

Each brief ends with the same contract: *persist everything with the kb_* tools, then write a ≤ 150-word summary with "leads:" lines*. The summary is stored in `tasks.result_md` and feeds the journal.

## B6. Extractor

`Extractor.extract(schema, instructions, text)` wraps `client.messages.parse` with **Haiku 5.5** (`output_config.effort = "low"`, prompts ≤ 100k tokens) and a Pydantic schema (all objects `additionalProperties: false`, no numeric constraints, `Literal` enums). M1 uses it for app-chart lead classification (`AppClassification`). M2 adds `BusinessProfile` (Instagram/Facebook pages), `AdSignal` (Ad Library), `ListingStats` (Merrjep/Gjirafa50). When daily extraction volume exceeds ~200 documents (Tier B/C), M3 moves the same calls to the Message Batches API at 50 % cost — the extraction step is single-shot, so it batches cleanly; the Director then runs in two stages (submit at 06:00, collect at 06:45).

## B7. Strategist and Critic

Two **Opus 5.5** calls per run at most, both with structured outputs, both only when inputs changed:

- **Strategist** input: the country digest, the changed sectors' digests, fresh facts (sorted, deduplicated, ≤ 25k tokens), current gaps in those sectors with their last assessment, and the rubric text. Output `StrategistOutput`: per gap the component scores, presence level, confidence, hard-filter result, reasoning, a proposed field check, recommended status; plus new gap ideas. Python recomputes the total from the components with the caps in A3.1 — the model proposes, the rubric decides.
- **Critic** input: the Strategist's top three plus the same facts. It is told to find the strongest objection, the Kosovo-specific killer (payments, trust, logistics, informality, market size, a hidden incumbent), to adjust the risk penalty and confidence, and to return `proceed / needs_field_check / park / kill`.
- **Apply:** gaps and `gap_assessments` are written; field checks are queued (max 5 open at a time; oldest first); `killed` requires either a hard filter or founder confirmation (Critic `kill` sets status `parked` with a flag the dashboard shows as "Critic says kill").

## B8. Presence-check protocol (the anti-hallucination rule)

A gap's absence score and confidence are capped until a `presence_check` fact exists (≤ 60 days old) produced by this protocol:

1. **Places:** text search for the service in each of Prishtinë, Prizren, Pejë, Gjakovë, Mitrovicë, Ferizaj, Gjilan — in Albanian and English (14 calls, Pro mask).
2. **App stores:** iTunes Search (`country=xk`) and Google Play search (`country="xk"`, `lang="sq"`) for the service keywords.
3. **Web:** three Albanian queries (`"<service> në Kosovë"`, `"<service> Prishtinë"`, `"aplikacion <service>"`) and one English.
4. **Social (M2):** Instagram hashtag/place scrape and Meta Ad Library (country XK) for the category.
5. **Verdict:** absent (nothing found in any channel) · exists-but-poor (found, but ≤ 2 players, weak reviews/activity, or only social-media presence) · Prishtina-only · offline-only (businesses exist, no digital product) · decent (≥ 3 active players with digital products) · unknown (sources degraded) → field check.

The verdict, counts per city and channel, and the URLs are stored as one `presence_check` fact (`value` JSON) on the gap, and as `businesses` rows for every player found.

## B9. Director: planner, budget guard, phases

**Phase table**

| Phase (setting) | Daily cap | Task mix per day |
|---|---|---|
| `foundation` | €3.00 | map-sector ≤ 2 · hunt-models ≤ 2 · verify-gap ≤ 1 · culture ≤ 1 (until seeded) · news-scan 1 · chart-diff on Mondays · deep-dive on Sundays |
| `verification` | €1.50 | verify-gap ≤ 2 (top gaps by score with stale/low confidence) · news-scan 1 · chart-diff Mondays · deep-dive Sundays |
| `maintenance` | €0.80 | news-scan 1 · chart-diff Mondays · verify-gap only when the founder flags a gap · deep-dive first Sunday of the month |

**Planner** (pure function, unit-tested): orders sectors by `priority` then staleness; never plans the same profile+sector twice in a day; respects open-field-check limits; plans nothing when the cap is already spent. **Director review:** when ≥ 3 tasks are planned, one Opus call with `DirectorReview` schema may *drop or reorder* (never add) tasks, with reasons journaled; capped at €0.10 and skipped if the cap is tight.

**Budget guard:** `check(est)` raises `BudgetExceeded` if `spent_today + est > cap`; `record(cost)` writes a `costs` row keyed by the run's local date, with units (`input_tokens, output_tokens, cache_write_tokens, cache_read_tokens, web_search_requests, results`) and the request id. Prices live in one table (`pricing.py`) with USD → EUR conversion from settings. The guard wraps every Claude call, every Places call (counts toward the monthly quota), and every Apify run (actor stats). CLI `scout run --budget 1.00` overrides the cap for a day.

## B10. Editor and the brief

Deterministic Markdown plus one optional Sonnet 5.5 paragraph (effort `low`, ≈ €0.03) for the narrative. Sections, in order: headline (one line), **what changed** (new/moved gaps with score, confidence, status, one-line why), **field checks for you** (≤ 5, each with a reason), **what the scout did** (tasks, sectors), **what it learned** (top five fresh facts with sources), **source health**, **spend** (today, month-to-date, cap). Skip rule: no changed gaps and no fresh facts with confidence ≥ 0.6 → single line "Quiet day — N tasks, €X, nothing moved" and no model call.

## B11. Dashboard (M2) — FastAPI + Jinja2 + HTMX, mobile-first, single user

| Page | Shows | Actions |
|---|---|---|
| Today | latest brief | mark read; jump to gaps |
| Gaps | board by status; score, confidence, presence, last assessed | **Verify / Park / Kill / Choose as finalist** buttons (write status + journal) |
| Field checks | open questions, due Sunday | answer form → fact (confidence 0.95, `source_name = founder`) → re-queue verify-gap |
| Pipeline | today's tasks, queue, runs, failures | retry task; add task (profile + sector) |
| Knowledge | sectors with digests; fact search; businesses; proven models | edit digest (journaled) |
| Journal | did/learned/tomorrow per day | — |
| Costs | per day/kind/model; month-to-date vs cap; source health | set cap for today |
| Ask | chat over the knowledge base (Sonnet 5.5 with the kb_* tools, read-only, ≤ €0.20/question) | — |
| Settings | phase, caps, sector priorities, finalists | — |

Auth: `DASHBOARD_TOKEN` env; login page sets an HttpOnly cookie; every route checks it. HTTPS by Render.

## B12. Field-check loop (Tier D)

The Strategist proposes; the planner keeps ≤ 5 open; the dashboard (M2) or `scout field-check answer <id> "<text>"` (M1) records the answer as a fact with confidence 0.95, closes the check, and queues a `verify-gap` for that gap at priority 90. Questions are written to be answerable in ≤ 3 minutes from the founder's own knowledge or a phone call; the Strategist is told the founder's cities and network (Prishtina-based, family in other municipalities — edited in Settings).

## B13. Memory and continuity (how it knows what it did yesterday)

- **Journal:** each run writes *did / learned / tomorrow*; the next run's planner and every worker brief include the last three entries (≤ 1,500 tokens).
- **Digests:** the country digest, culture digests and sector digests are the long-term memory the models read; the worker updates them through `kb_*` tools and the Editor keeps them ≤ ~1,200 tokens each by asking the worker to rewrite when they grow.
- **Facts with TTL:** stale knowledge expires; re-observation refreshes.
- **Scorecard:** daily metrics (`sectors_mapped, proven_models, gaps_by_status, avg_confidence_top10, facts_fresh_ratio, spend_mtd, searches_mtd, field_checks_open, field_checks_answered, days_run`) make progress against gates visible.
- **Assessment history:** every Strategist/Critic output is kept, so score drift is explainable.

## B14. Model routing and cost model

| Step | Model | Effort | Why |
|---|---|---|---|
| Research worker (all web profiles) | `claude-sonnet-5-5` | medium | Supports `_20260209` web tools with dynamic filtering; $2/$10 per MTok |
| Deep-dive | `claude-opus-5-5` | high | One memo a week deserves the best model |
| Extractor | `claude-haiku-5-5` | low | $0.10/$0.50 per MTok; structured outputs; ≤ 100k prompts |
| Strategist, Critic, Director review | `claude-opus-5-5` | medium (Critic high) | Judgement calls; ≤ 3 calls/day |
| Editor narrative | `claude-sonnet-5-5` | low | Small, optional |
| Ask (M2) | `claude-sonnet-5-5` | medium | Interactive, capped |

Unit prices (USD per MTok, 2026-10-09): Opus 5.5 in 4 / out 20 / cache write 5 / cache read 0.20; Sonnet 5.5 2 / 10 / 2.5 / 0.20; Haiku 5.5 0.10 / 0.50 / 0.125 / 0.01; web search $10 per 1,000 searches; web fetch free beyond tokens. A typical Foundation day: 6 worker tasks ≈ €1.60 (searches ≈ €0.60, Sonnet tokens ≈ €1.00 with caching), Strategist + Critic ≈ €0.50, Haiku + Editor ≈ €0.05, Apify ≈ €0.50 (M2) → ≈ €2.65 against the €3 cap.

## B15. Prompt-caching and token discipline

- System prompts are **frozen within a day**: static rules block + digest block, with `cache_control: {"type": "ephemeral"}` on the last system block; the date, the task brief and the last journal entries go in the first user message. No timestamps, UUIDs or unsorted JSON before the breakpoint (`json.dumps(..., sort_keys=True)` everywhere).
- Same `tools` list, same order, same model for all worker tasks in a run; tasks run sequentially so later tasks read the cache written by the first.
- Each profile sets `max_uses` on `web_search` and `web_fetch`, and `max_iterations` on the runner. Tool results from `kb_search` are truncated to 2,000 characters; Places and app-store results to 1,200.
- The integration test for the worker asserts `usage.cache_read_input_tokens > 0` on the second task of a run; a regression here shows up on the Costs page as `cache_read_tokens = 0`.
- Opus 5.5 always thinks; depth is controlled with `output_config.effort` only. Forced `tool_choice` is never used (400 on 5.5 models); briefs state which tools to use.

## B16. Tech stack, repo layout, deployment

Python 3.12 · `uv` · `anthropic>=1,<2` (built on `httpx2`; our own HTTP uses `httpx`) · `pydantic` 2 + `pydantic-settings` · SQLAlchemy 2 + Alembic + `psycopg[binary]` 3 · `typer` CLI · `google-play-scraper` · `pytest` · `ruff`. M2 adds `fastapi`, `jinja2`, `uvicorn`, `markdown-it-py`, `apify-client`. M4 adds `crawlee[playwright]>=1.7`.

```
scout/
  config.py            Settings (env), normalize_db_url
  cli.py               typer app: init-db, seed, run, brief, status, add-task, field-check, chart-diff
  seeds.py             sector taxonomy, culture themes, source registry
  db/ base.py models.py repo.py
  budget/ pricing.py guard.py
  llm/ gateway.py
  sources/ types.py askdata.py apple.py play.py places.py web.py
  worker/ tools.py profiles.py research.py chart_diff.py
  extract/ schemas.py extractor.py
  strategy/ schemas.py rubric.py strategist.py
  editor/ brief.py
  director/ planner.py run.py
alembic/ (migrations)   tests/   render.yaml   pyproject.toml   .env.example
```

Deployment: Render **cron job** `scout-daily` (`schedule: "0 6 * * *"`, `startCommand: uv run scout run`), Render **web service** `scout-dashboard` (M2), Neon Postgres (free tier; a `test` branch for the test suite). Secrets as Render environment variables: `ANTHROPIC_API_KEY`, `DATABASE_URL`, `GOOGLE_PLACES_API_KEY`, `APIFY_TOKEN` (M2), `DASHBOARD_TOKEN` (M2), `SCOUT_PHASE`, `SCOUT_DAILY_BUDGET_EUR`.

## B17. Milestones

| Milestone | Scope | Built | Running by |
|---|---|---|---|
| **M1 — Engine** (this plan) | schema, budget guard, Tier A sources, worker with all web profiles, chart-diff, extractor, Strategist + Critic, Editor, Director, CLI, Render cron | Sat 10-10, Sat 10-17 | 10-18 |
| **M2 — Eyes and dashboard** | FastAPI/HTMX dashboard (Today, Gaps, Field checks, Pipeline, Knowledge, Journal, Costs, Ask, Settings), Apify Tier B (Instagram, Facebook Pages, Meta Ad Library, TikTok), `ads` table, verify-gap step 4 | Sat 10-24, Sat 10-31 | 11-01 |
| **M3 — Scale and polish** | Message Batches for extraction, two-stage director, brief push (email/Telegram), scorecard charts, Director review tuning, digest compaction | Sat 11-07 (optional 11-14) | 11-15 |
| **M4 — Crawlers** | Crawlee/Playwright Tier C: Merrjep, Gjirafa50, KosovaJob, news sites, ARBK; `ListingStats` extraction | Phase 2 Saturdays as needed | 12-13 |

## B18. Testing strategy

- Unit tests with no network and no database for: pricing, rubric, planner, brief rendering, prompt builders, source parsers (`httpx.MockTransport`), worker loop (fake runner), strategist apply (fake LLM).
- Database tests against `TEST_DATABASE_URL` (Neon branch or local Postgres via Docker) for repo functions and the queue's `SKIP LOCKED` behaviour.
- One end-to-end `run_once` test with fakes (no network) proving the daily lifecycle writes run, tasks, costs, journal, brief.
- `@pytest.mark.network` smoke tests (skipped by default) for the live endpoints and for cache-hit verification; run by hand before deploying.

## B19. Unverified assumptions (to confirm during Phase 0)

1. Google Places accepts `regionCode: "XK"`; fallback: omit it and keep "Kosovo" in the query.
2. The Play Store collection page HTML contains `/store/apps/details?id=` anchors without JavaScript; fallback: Playwright in M4, meanwhile Apple-only chart diff.
3. `client.beta.messages.tool_runner` accepts `system=`, `max_iterations=` and `output_config=` like `beta.messages.create` (documented in the SDK helpers; verify on first run).
4. Apify Starter price (~$19/month) and actor prices as researched on 2026-10-09.
5. The founder's employment contract permits side projects; nothing here overlaps Cardo AI.
6. Kosovo company form and VAT threshold — confirm with an accountant in Phase 4.

---

## Appendix A — Sector taxonomy (seed, priority 1 = first)

| Pri | slug | Sector (en / sq) |
|---|---|---|
| 1 | `home-services` | Home services booking — cleaners, repairs, movers / Shërbime për shtëpi |
| 1 | `health-booking` | Clinic, dentist, lab appointment booking (dental tourism) / Rezervime shëndetësore |
| 1 | `tutoring-education` | Tutoring, Matura prep, language learning / Mësim privat dhe edukim |
| 1 | `mobility-transit` | Transit, parking, ride-hailing, car-sharing / Transport urban |
| 1 | `secondhand-marketplaces` | Second-hand fashion, electronics, kids' goods / Tregu i dorës së dytë |
| 1 | `rentals-housing` | Long-term and student rentals, roommates / Qira dhe banim |
| 1 | `diaspora-services` | Services the diaspora buys for family at home / Shërbime për diasporën |
| 1 | `weddings-events` | Wedding and event vendors, ticketing / Dasma dhe evente |
| 2 | `food-grocery-delivery` | Food, grocery, pharmacy delivery / Dërgesa ushqimi |
| 2 | `beauty-wellness` | Salon, barber, spa booking / Bukuri dhe mirëqenie |
| 2 | `fitness-sports` | Gyms, classes, pitch booking / Fitnes dhe sport |
| 2 | `pets` | Pet services and supplies / Kafshë shtëpiake |
| 2 | `car-services` | Car wash, service, parts, inspection booking / Shërbime për vetura |
| 2 | `parenting-kids` | Childcare, activities, school logistics / Prindërim dhe fëmijë |
| 2 | `bureaucracy-helpers` | e-Kosova navigation, documents, appointments / Ndihmë burokratike |
| 2 | `local-travel` | Domestic tourism: Rugova, Brezovica, Prizren, guides / Turizëm vendor |
| 3 | `utilities-household-finance` | Bills (KEDS, water), household budgeting (non-regulated) / Fatura dhe buxhet |
| 3 | `jobs-gigs` | Gig work and local hiring for consumers / Punë me orar |
| 3 | `agri-to-consumer` | Farm boxes, local produce subscriptions / Nga ferma te konsumatori |
| 3 | `entertainment-media` | Streaming, gaming communities, local creators / Argëtim |
| 3 | `legal-consumer` | Consumer legal help, contracts, disputes / Ndihmë juridike |
| 3 | `instagram-seller-tools` | Tools for Kosovo's Instagram micro-sellers (B2C-adjacent, watch only) / Mjete për shitës në Instagram |
| 3 | `elderly-care` | Care coordination for parents of diaspora children / Kujdes për të moshuarit |
| 3 | `language-ai-consumer` | Albanian-language AI assistants for consumers / Asistentë AI në shqip |

## Appendix B — Culture themes (seed for the `culture` profile)

`payments-and-trust` (cash, cards, COD, bank apps, who trusts whom online) · `diaspora-and-remittances` (who sends what, when they visit, what they buy for family) · `family-and-housing` (multi-generation households, home ownership, building) · `youth-and-work` (unemployment, emigration, side hustles, English) · `language-and-media` (Albanian/Serbian/English, Telegrafi/Koha/Kallxo, TikTok vs Facebook by age) · `cities-and-mobility` (Prishtina vs the rest, cars, buses, parking) · `calendar-and-seasons` (Bajram, Christmas/New Year, Nov 28, Feb 17, summer diaspora, wedding season) · `shopping-habits` (Instagram shops, malls, Gjirafa50, Merrjep, imports from Turkey/China) · `bureaucracy-and-state` (e-Kosova, ARBK, municipal services, what is slow) · `health-and-education` (private clinics, dental tourism, private schools, tutoring culture).

## Appendix C — Nearby-market watchlist

Albania (Tirana), North Macedonia (Skopje — Albanian-speaking west), Montenegro, Bosnia, Serbia, Croatia, Slovenia: chart diffs weekly; `hunt-models` queries name these first. Secondary: Turkey (cultural and trade ties), Germany/Switzerland (diaspora behaviour).

## Appendix D — Endpoints verified on 2026-10-09

- `https://rss.marketingtools.apple.com/api/v2/xk/apps/top-free/25/apps.json` → 200, JSON `feed.results[]` (`name, artistName, id, genres[], url`); also `mk`, `al`.
- `https://play.google.com/store/apps?gl=XK&hl=en` and `/store/apps/collection/topselling_free?gl=XK&hl=en` → 200; Kosovo listed in Play supported locations.
- `https://askdata.rks-gov.net/api/v1/en/ASKdata/` → JSON list of 26 folders (ids include `"Population"`, `"Prices"`, `"ICT"`, `"Household budget survey"`, `"Labour market "` with a trailing space, `"Tourism and hotels"`, `"Structural business statistics"`).
- `arbk.rks-gov.net` → JavaScript application (needs Playwright, M4).
