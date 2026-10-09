# Social eyes: Design (Milestone 2, part 2)

**Status:** approved in chat on 2026-10-09; this document records it.
**Replaces:** the Tier B section of M2 in `2026-10-09-kosovo-gap-scout-design.md` (Apify Instagram, Facebook Pages, Meta Ad Library, TikTok, Google Maps). It also brings forward the M4 crawler work, using Crawl4AI instead of Crawlee.

## 1. Goal

The scout must see Kosovo's social-media economy without the founder paying anything extra. Many Kosovo businesses exist only as an Instagram page, with no website and no Google Maps entry. Today the scout cannot see them, so it can call a gap "missing in Kosovo" when it is in fact served informally.

For each promising idea, the scout answers three questions:
1. **Does it exist?** Are there Instagram shops, Facebook pages or TikTok sellers offering it in Kosovo?
2. **Is anyone paying to sell it?** Are there Meta ads aimed at Kosovo, from local or foreign sellers?
3. **Are people asking for it?** How many comments ask about price, delivery or where to buy?

The answers feed the existing presence check and the "Demand signals /20" part of the score.

## 2. Constraints

- **€0 a month extra.**
  - Apify free plan: about $5 of monthly credit and no card on file. Apify blocks new runs when the credit is used up and does not charge overage.
  - Crawl4AI is open source (Apache-2.0) and runs inside the scout.
  - GitHub Actions is free for this public repo.
  - Claude web search is paid from the scout's existing daily budget, and that cap does not change.
- **Public, logged-out data only. Businesses only, never individuals.**
- **Targeted (founder's choice, option A).**
  - Paid social calls are made only while checking ideas that score 60 or more.
  - One broad Meta Ad Library sweep of Kosovo runs each week.
  - There is no broad weekly Instagram discovery.
- **No paid Facebook Pages or TikTok scrapers.** Those platforms are covered by web search only.
- **Fail soft.** Without an `APIFY_TOKEN`, or with the credit used up, the scout works as it does today.

## 3. Architecture

The approach is new tools inside the existing research worker (approach 1 in the chat). The agent chooses hashtags and search words because it knows Albanian and the idea. Code-enforced limits stop overspending.

### 3.1 New components

| Unit | File | Responsibility |
|---|---|---|
| Apify client | `scout/sources/apify.py` | Runs an Apify actor synchronously with a timeout, returns its dataset items and the run's real cost (USD) from the run stats. It has no knowledge of the scout. |
| Social normalisers | `scout/sources/social.py` | Turns raw actor items into scout records. Drops non-business Instagram profiles. Reduces comments to counts of price, delivery and where-to-buy questions. Classes ad advertisers as local or foreign. Pure functions. |
| Crawl client | `scout/sources/crawl.py` | Wraps Crawl4AI. Accepts URLs only from an allowlist of Kosovo domains, obeys robots.txt, waits 2 s between pages, returns Markdown capped at `SOURCE_RESULT_LIMIT`. |
| Social guard | `scout/worker/social_guard.py` | Decides whether a paid call may run. Checks the score gate, the per-task call limits and the monthly credit cap, and serves cached results. Pure logic over the repo. |
| Tools | `scout/worker/tools.py` | New tools `instagram_search`, `ad_library_search` and `kosovo_site_crawl`, built as thin closures over testable `*_impl` functions like the existing tools. |
| Profile | `scout/worker/profiles.py` | `verify-gap` gains the social step in its brief. A new `ads-sweep` profile handles the weekly sweep. |
| Planner | `scout/director/planner.py` | Queues one `ads-sweep` task each Monday when an Apify token is set. |

### 3.2 Apify actors

Use Apify's official actors:
- **Instagram:** `apify/instagram-scraper`, in hashtag or place mode, for public posts and profiles.
- **Meta Ad Library:** `apify/facebook-ads-scraper`, run against the public Ad Library with country `XK`.

Confirm both actor IDs and their input fields at implementation time, and record them as constants. If an actor is renamed or needs a paid plan, the tool reports "social source unavailable" (see §5).

### 3.3 Data model (one Alembic migration)

**New table `ads`:**

| Column | Content |
|---|---|
| `id` | primary key |
| `ad_archive_id` | unique |
| `page_name`, `page_url` | the advertiser |
| `ad_text` | the ad copy |
| `platforms` | JSON |
| `first_seen`, `last_seen` | dates |
| `is_foreign` | bool or null |
| `sector_slug` | nullable |
| `gap_id` | nullable |
| `fetched_at` | when the scout pulled it |
| `raw` | JSON, already stripped of personal data |

**New table `social_cache`:**

| Column | Content |
|---|---|
| `id` | primary key |
| `source` | `instagram` or `ads` |
| `query_key` | normalised query |
| `items` | JSON |
| `cost_usd` | what the call cost |
| `fetched_at` | when it ran |

`(source, query_key)` is unique. Rows expire after 30 days for Instagram and 14 days for ads.

**Presence level:** add `instagram-only`. In the UI it is labelled "Only on Instagram (informal)".

**Fact types:** add `social` and `ad_signal` to `FACT_ENTITY_TYPES`.

**Costs:** every Apify call writes `CostRecord(kind="apify", provider="apify", units={"usd": …, "items": …})`, converting USD to EUR with `usd_to_eur`. The cost is recorded even when a run fails partway.

### 3.4 How the agent searches (the social step in `verify-gap`)

1. **Free scouting.** Run `web_search` with `site:instagram.com`, `site:facebook.com` and `site:tiktok.com` queries for the idea, in Albanian and English, with Kosovo city names. This finds the hashtags, page names and words local sellers use.
2. **One `instagram_search`** for the best hashtag or place found.
3. **One `ad_library_search`** with the words a seller would put in an ad.
4. **Free `kosovo_site_crawl`** calls as needed, for example Merrjep listings and prices, or KosovaJob ads.
5. **Record and assess.**
   - Write the findings with `kb_record_fact` (types `social` and `ad_signal`) and `kb_record_business` (Instagram shops).
   - Set the presence check. Use `instagram-only` when sellers exist only as informal Instagram pages.
   - Ads (especially long-running ones and foreign sellers shipping into Kosovo) and question counts are demand evidence.

### 3.5 Weekly `ads-sweep` (Mondays)

- **Pull:** one Ad Library pull for country `XK`, at most 300 ads, using broad consumer categories chosen by the agent.
- **Store:** ads are upserted into `ads`.
- **Analyse:** the agent groups ads by sector and flags long-running ads and foreign sellers.
- **Record:**
  - `ad_signal` facts per sector;
  - candidate gaps through `kb_propose_gap` when foreign sellers serve Kosovo with no local equivalent.
- **Cost:** Sonnet, estimated €0.20, from the normal daily budget.

## 4. Limits (enforced in code; the agent cannot override them)

| Limit | Value |
|---|---|
| Paid social calls allowed for | a `verify-gap` task whose gap has `score_total` ≥ 60 when the task starts, or that the founder flagged with "Check this again". The `ads-sweep` task is exempt from the score gate. |
| Paid calls per task | 1 `instagram_search` + 1 `ad_library_search` (`ads-sweep`: 1 `ad_library_search`) |
| Results per call | ≤ 30 Instagram profiles, ≤ 50 ads (sweep: ≤ 300) |
| Actor run timeout | 120 s |
| Monthly Apify spend | stops at `SCOUT_APIFY_MONTHLY_USD` (default 4.50). The month starts on the 1st in Europe/Belgrade. |
| Cache | the same `(source, query_key)` within its expiry returns the stored items at no cost, and the hit does not count toward the per-task limit |
| Crawl | allowlisted domains only, ≤ 20 pages per task, 1 page every 2 s, robots.txt obeyed |

Initial crawl allowlist (a constant, easy to extend):
- `merrjep.com`
- `gjirafa50.com`
- `kosovajob.com`
- `telegrafi.com`
- `koha.net`
- `kallxo.com`
- `prishtinainsight.com`
- `arbk.rks-gov.net`

## 5. Privacy and failure handling

**Privacy (enforced in `social.py`, and tested):**
- **Instagram profiles:** keep only those the actor marks as business or professional accounts. All others are dropped before storage.
- **Comments:** keep only counts by question type. Never store commenter usernames or comment text.
- **Ads:** keep the advertiser page and the ad content only.

**Failures:**
- **Apify error, timeout, actor unavailable or credit cap reached.**
  - The tool returns `"social source unavailable: <reason>"` and the agent carries on with the free steps.
  - If a gap qualified for paid social calls but none returned a result, `_presence_check` stores the check as partial. It keeps the agent's verdict, adds `"social": "partial"` to the value and caps confidence at `DEGRADED_CHECK_MAX_CONFIDENCE`. This differs from a Places/App Store shortfall, which still resets the verdict to `unknown`. Gaps below the score gate are not partial; they simply had no paid social step.
  - When this month's Apify spend has reached the cap, the daily brief adds one line, for example: "Social credit used up for October — paid social checks resume Nov 1."
- **No `APIFY_TOKEN`.** The two paid tools are not offered and `ads-sweep` is not queued.
- **Crawl blocked or robots.txt disallows.** The page is skipped, `sources.failure_count` is incremented, and it appears in data-source health on the Budget & costs page.
- **Source health.** Every Apify and crawl call updates `sources.last_ok_at` or `sources.failure_count`. The rows used are:
  - `apify-instagram` and `meta-ad-library`, already seeded with `enabled=False`, which are enabled when a token is set;
  - `merrjep` and `kosovajob`, already seeded, for those two domains;
  - one new seeded row `kosovo-sites` (tier C, kind `web`) for the other allowlisted domains.

## 6. Dashboard

- **Gap detail.** A "Social" block lists:
  - Instagram shops found (name, followers, last post date);
  - ads (advertiser, local or foreign, running since);
  - comment-question counts.
- **Budget & costs.** A "Social credit" line: "$X.XX of $4.50 used this month".
- **Labels.** `ui.py` maps `instagram-only` to "Only on Instagram (informal)".

## 7. Configuration and deployment

**Settings:**
- `apify_token` already exists.
- Add `apify_monthly_usd: Decimal = 4.50`, read from `SCOUT_APIFY_MONTHLY_USD`.

**Dependencies:**
- Add `crawl4ai`.
- The Apify client uses `httpx` directly against the Apify REST API (`run-sync-get-dataset-items`), so no new SDK is needed.

**`scout-daily.yml` changes:**
- Install Crawl4AI's Chromium, cached between runs.
- Pass `APIFY_TOKEN` and `SCOUT_APIFY_MONTHLY_USD`.

**Founder steps:**
- Create a free Apify account (email only, no card).
- The token is added as the GitHub secret `APIFY_TOKEN`.

**Database:** run `scout init-db` locally against Neon after the merge.

## 8. Testing

- **Unit tests, with no network.** Fake Apify and crawl clients replay stored sample payloads.
  - Normalisers:
    - non-business profiles are dropped;
    - comments become counts with no names or text;
    - advertisers are classed as local or foreign.
  - Guard:
    - a score below 60 is refused;
    - a second paid call in a task is refused;
    - the monthly cap is hit and resets on the 1st;
    - a cache hit is free and not counted;
    - a failed run still records its cost.
  - Crawl:
    - a non-allowlisted domain is refused;
    - robots.txt is obeyed;
    - the page cap holds;
    - pages are paced, using an injected clock.
  - Tools: failures produce the unavailable message, a partial presence check and the brief line. With no token, the paid tools are absent.
  - Planner: `ads-sweep` is queued on Mondays only, and only with a token.
- **DB tests.** The migration applies, `ads` upserts on `ad_archive_id`, and `social_cache` expiry works.
- **Web tests.**
  - The gap page shows the Social block.
  - The costs page shows the social-credit line.
  - The new presence label renders.
- **Live tests** (marked `network`, run by hand). One Instagram hashtag call, one Ad Library call and one crawl of an allowlisted page.

## 9. Out of scope

- Paid Facebook Pages, TikTok and Google Maps scrapers.
- The Ask page.
- Message Batches and the two-stage director (M3).
- Broad weekly Instagram discovery.
- Logged-in scraping of any kind.
