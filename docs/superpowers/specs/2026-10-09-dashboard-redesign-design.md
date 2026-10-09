# Dashboard redesign: design

**Status:** approved in conversation on 2026-10-09; awaiting review of this written spec.

**Builds on:**
- The dashboard (M2 B11), plan `docs/superpowers/plans/2026-10-09-kosovo-gap-scout-dashboard.md`.
- It is live at https://scout-dashboard-bmoz.onrender.com.

## Goal

The founder should understand every page at a glance. The redesign uses:
- a modern "clean SaaS" look (neutral grays, one indigo accent, light and dark modes);
- plain-language labels;
- the next action shown first.

It is used on laptop and phone equally.

This is a visual and information-architecture redesign only. It adds no new founder actions and
does not change scout behaviour.

## Decisions (from the conversation)

- **Device:** both. A left sidebar on wide screens becomes a bottom tab bar on phones (< 768px).
- **Style:** clean SaaS:
  - Inter font;
  - neutral grays and an indigo accent (`#4f46e5` light / `#818cf8` dark);
  - crisp cards with 12px radius and subtle shadows;
  - light and dark themes that follow `prefers-color-scheme`.
- **Build approach:** a hand-written design system with no build step:
  - one stylesheet at `scout/web/static/app.css`;
  - one small script at `scout/web/static/app.js`;
  - Inter woff2 files under `scout/web/static/fonts/`;
  - an SVG icon sprite at `scout/web/static/icons.svg`, with Lucide icons (ISC licence).

  There is no Tailwind, no CDN and no Node toolchain. The Render build command is unchanged.
- **Structure:** five sections replace the eight flat tabs. Every existing URL and form stays.

  | Section | Icon | Pages (tabs inside the section) |
  |---|---|---|
  | Home | `home` | `/` |
  | Gaps | `lightbulb` | `/gaps` (Board), `/field-checks` (Field checks); `/gaps/{id}` detail |
  | Activity | `activity` | `/pipeline` (Pipeline), `/journal` (Journal) |
  | Knowledge | `book-open` | `/knowledge`, `/knowledge/sectors/{slug}`, `/knowledge/digests/{key}` |
  | Settings | `settings` | `/settings` (General), `/costs` (Budget & costs) |

## Understandability rules (every page)

1. **Page header.** Each page has a title and a one-sentence plain explanation, for example:
   "Gaps — business ideas the scout found that may be missing in Kosovo."
2. **Plain labels.** Internal words map to plain labels in one module, `scout/web/ui.py`. Each
   label has a tone (colour) and a tooltip sentence.

   Gap status:

   | Internal | Label | Tone |
   |---|---|---|
   | candidate | New idea | blue |
   | verifying | Being checked | amber |
   | verified | Confirmed gap | green |
   | parked | On hold | gray |
   | killed | Rejected | red |

   Task status:

   | Internal | Label | Tone |
   |---|---|---|
   | queued | Waiting | gray |
   | running | Running | blue |
   | done | Done | green |
   | failed | Failed | red |

   Run status:

   | Internal | Label | Tone |
   |---|---|---|
   | running | Running | blue |
   | done / completed | Finished | green |
   | failed | Failed | red |
   | stopped | Stopped | amber |

   Use whatever statuses the models actually have. Unknown values fall back to the raw value
   with a gray tone.

   Task profiles also get plain names, for example:

   | Profile | Plain name |
   |---|---|
   | map-sector | Map a sector |
   | hunt-models | Find proven models |
   | verify-gap | Check a gap |
   | culture | Culture research |
   | news-scan | News scan |
   | deep-dive | Deep dive |

   Phases get a label and a one-line meaning:

   | Phase | Label | Meaning |
   |---|---|---|
   | foundation | Foundation | "building the knowledge base, ~€3/day" |
   | verification | Verification | "checking the best gaps against real data" |
   | maintenance | Maintenance | "light daily watch" |
3. **Scores** show as a 0–100 bar plus a band word:

   | Score | Band |
   |---|---|
   | ≥ 75 | strong |
   | 60–74 | promising |
   | 40–59 | weak |
   | < 40 | poor |
   | None | "not scored yet" |

   Confidence shows as a percent.
4. **Buttons say what they do:**

   | Old | New |
   |---|---|
   | Verify | Check this again |
   | Unverify | Cancel check |
   | Finalist | Make finalist |
   | Unfinalist | Remove finalist |
   | Park | Put on hold |
   | Kill | Reject |
   | Reopen | Reopen |

   Reject asks for confirmation (`data-confirm`, handled by app.js, with a native `confirm()`
   fallback).
5. **Empty states** explain why something is empty and what happens next. Each has an icon,
   one sentence and an optional link.
6. **Flash messages** (`?msg=` / `?err=`, unchanged on the server) render as a toast. A toast
   auto-hides after 5 seconds; an error toast stays until dismissed. Without JS they render
   inline.
7. **Dates** show as human strings: "today", "yesterday", "Oct 7". The ISO date is the tooltip.
8. **Money** always shows as €0.00.

## Layout

- **Wide screens (≥ 768px):**
  - The left sidebar is 240px wide. From top to bottom it holds:
    - the logo mark and "Gap Scout";
    - the five sections (icon and label), each with an optional count badge;
    - a phase pill and a Log out button at the bottom.
  - The content column is at most 1100px wide.
- **Phone (< 768px):**
  - A top bar shows the logo and the page title.
  - A fixed bottom tab bar shows the five icons with short labels and badges.
  - Content has a 16px gutter, and there is no horizontal page scroll.
- **Section tabs** (Board / Field checks, Pipeline / Journal, General / Budget & costs) are a
  segmented control under the page header. They are plain links.
- **Nav badges** are computed once per page render by `page()`:

  | Section | Badge |
  |---|---|
  | Home | 1 when the latest brief is unread |
  | Gaps | number of open field checks |
  | Activity | number of failed tasks |

  A count of 0 hides the badge.
- **Login and error pages** use the same look in a centred card, without the nav.

## Pages

### Home (`/`)
- **Header:** "Good morning/afternoon/evening" (Kosovo local time), with the date.
- **"Needs you" card.** It lists only actionable items, each with one button:
  - "New brief for {date}" → Read (scrolls to the brief) and Mark read;
  - "{n} field check(s) to answer" → Answer (/field-checks);
  - "{n} failed task(s)" → Review (/pipeline).

  If there is nothing to act on, it shows "All clear ✓ — nothing needs you right now".
- **Stat tiles** (4; 2×2 on phone):

  | Tile | Shows | Note |
  |---|---|---|
  | Spent today | €x of €cap | progress bar; cap = `founder.effective_cap` |
  | This month | €x | |
  | Open gaps | count of New idea + Being checked + Confirmed | links to /gaps |
  | Next run | "Tomorrow 07:00" or "Today 07:00" | daily cron is 06:00 UTC, shown in Kosovo time |

- **Last run line:** status chip, date, tasks done/failed, cost. It links to /pipeline.
- **Brief:** a readable article card (max 70ch, comfortable line height) with the `md` filter,
  or an empty state.

### Gaps: Board (`/gaps`)
- **Wide screens:** a board with the columns New idea, Being checked, Confirmed gap and On hold.
  Each column header has a count. Rejected is a collapsed section below the board.
- **Phone:** the columns become a segmented filter (`?status=`, server-side; the default is the
  first non-empty column).
- **Gap card:**
  - title (a link) and sector;
  - score bar;
  - ★ Finalist chip, "Check requested" chip and critic-flag chip, when they apply;
  - "updated {human date}".

  Card actions sit in a compact overflow row: Check this again, Make finalist, Put on hold,
  Reject and Reopen, as each applies.
- **Empty board:** "No gaps yet — the scout proposes gaps after it maps sectors and finds proven
  models."

### Gap detail (`/gaps/{id}`)
- **Header:** title, status chip, sector, finalist and flag chips, and an action bar.
- **Cards:**
  - **Summary** (description / pitch fields as they exist).
  - **"Why it might work"**: the proven model's name, where it works, and links (existing
    http/https guard).
  - **Scores:** the total bar plus the latest assessment's component scores as small bars, each
    with its rubric name, and confidence %.
  - **"Critic's concerns"**: the critic JSON rendered as a readable list (key → value). Raw JSON
    sits in a collapsed details element.
  - **Field checks** for this gap: question, why, and the answer or "waiting for your answer".
  - **History:** the latest 5 assessments as a timeline.

### Gaps: Field checks (`/field-checks`)
- Each open check is a card with:
  - the question in bold;
  - "Why it matters";
  - the linked gap;
  - the due date;
  - a textarea and an "Save answer" button.
- Answered checks are listed below, collapsed.
- **Empty state:** "No questions for you right now."

### Activity: Pipeline (`/pipeline`)
- **Summary strip:** Waiting n, Running n, Failed n.
- **Lists:**
  - Failed first, each with its error in a collapsible block and a Retry button;
  - then Waiting, by priority;
  - then Running.

  Each row shows the plain profile name, its target (sector name or gap title) and a human date.
- **"Add a task" card:** a profile select with the plain names, a sector select, a gap id, a
  theme, a priority (with the help text "0–100, higher runs sooner") and a "Queue task" button.
- **"Recent runs":** a timeline showing date, run status chip, planned/done/failed and cost.
  Each run's result summary is collapsed.

### Activity: Journal (`/journal`)
- A dated timeline. Founder-only entries (null `run_id`) get a "You" chip; run entries get
  "Scout · run #n". Markdown is rendered.

### Knowledge (`/knowledge`, sector, digest)
- A search box at the top for facts. Results are cards showing the claim, source link (guarded),
  confidence % and a human date.
- **Sector cards:**
  - name;
  - priority;
  - Mapped / Hunted chips, or "not mapped yet";
  - a link to the sector page.
- **Digests:** a list with key and updated date.
- **Digest page:** rendered view, with an "Edit" toggle that reveals the textarea form (no JS
  fallback: the form shows below in a details element).

### Settings: General (`/settings`)
- **Phase card:** the current phase label and meaning, and a select with the meanings to switch.
- **Sector priorities card:** a table with a number input and Save per row.
- **"Your lists" card:**
  - Finalists, each with a Remove button;
  - Flagged gaps, each with a "Cancel check" button.

### Settings: Budget & costs (`/costs`)
- **Today's cap card:**
  - effective cap and where it comes from (your cap for today / phase cap / daily budget);
  - input and Save;
  - Clear;
  - the existing help text about runs started today.
- **Spend:** today, this month, and the last 14 days as a simple CSS bar chart. There is no
  chart library.
- **Cost table** by component/model, as it is today, restyled.

## Technical design

- **Static files:** `app.mount("/static", StaticFiles(directory=…/static), name="static")`.
  - The auth middleware treats a path starting with `/static/` as open, so the login page is
    styled.
  - Responses get `Cache-Control: public, max-age=86400`.
  - Asset URLs carry `?v={{ ASSET_VERSION }}`, a hash of the app.css + app.js contents computed
    at import, for cache busting.
- **`scout/web/ui.py`** (pure functions, unit-tested), registered as Jinja globals and filters
  in `deps.py`:
  - `status_label`, `task_label`, `run_label`, `profile_label` and `phase_info`, each returning
    `(label, tone, tooltip)` or a similar small dataclass;
  - `score_band(score) -> (word, tone)`;
  - `human_date(d, today)`;
  - `greeting(now_local)`;
  - `next_run_local(now_utc, tz) -> datetime`.
- **`templates/_ui.html`:** Jinja macros used by every page:
  - `page_header(title, subtitle, actions)`;
  - `tabs(items, active)`;
  - `chip(label, tone, title)`;
  - `status_chip(status)`;
  - `score_bar(score)`;
  - `stat_tile(label, value, sub, href, progress)`;
  - `empty_state(icon, text, href, link_text)`;
  - `icon(name)`;
  - `gap_actions(g, finalists, flagged, next)`, which replaces `_gap_actions.html`;
  - `confirm_button(...)`.
- **`base.html`:**
  - sidebar and bottom-bar markup driven by `SECTIONS` (replaces `NAV`), with the active section
    chosen by path prefix;
  - the toast region;
  - the `<link>` to app.css and the deferred `<script>` for app.js;
  - the existing `<meta name="referrer" content="no-referrer">`.
- **`page()`** adds `nav_badges` (a dict from section to count). It uses the request's existing
  DB session when the route passes one (`session=` kwarg). Otherwise it opens a short-lived
  session from `request.app.state.session_factory`. Errors computing badges degrade to no
  badges and never fail the page.
- **app.js:**
  - toasts: read `[data-toast]` and auto-hide them;
  - `data-confirm` on forms;
  - phone filter tabs need no JS (server-side `?status=`);
  - the digest edit toggle;
  - keyboard shortcuts: `g h`, `g g`, `g a`, `g k` and `g s` navigate, and `/` focuses the
    search box on Knowledge;
  - about 100 lines, with no framework.
- **CSP:** unchanged (`img-src 'self' data:`). No inline event handlers remain; the existing
  inline `onsubmit` moves to `data-confirm`.
- **Accessibility:**
  - visible focus rings;
  - `aria-current="page"` on active nav;
  - chips are not colour-only (they carry text);
  - 44px minimum tap targets on phone;
  - contrast ≥ 4.5:1 in both themes;
  - the sidebar is a `<nav aria-label="Main">`.

## Testing

- All existing route and behaviour tests keep passing. Where a test asserts on old visible
  wording (e.g. "Killed", button text, the `new-brief` class), the plan updates the assertion to
  the new wording in the same task.
- **New unit tests** for `ui.py`:
  - labels and unknown-value fallback;
  - score bands at the boundaries 39/40/59/60/74/75/None;
  - `human_date` for today, yesterday and older;
  - `next_run_local` before and after 06:00 UTC, and across DST.
- **New page tests:**
  - **Home "Needs you":** an unread brief, open checks and a failed task each produce their
    row, and none produces "All clear".
  - **Nav badges** appear with counts and are hidden at 0.
  - **Static:** `/static/app.css` returns 200 without login, with a cache header. A non-static
    path is still protected, e.g. `/staticx`.
  - **Board:** the plain labels appear, Rejected is collapsed, and `?status=` filters on phone.
  - **Empty states:** each list page shows its empty sentence on an empty DB.
  - **No inline event handlers:** a test greps the rendered pages for `onsubmit=` and
    `onclick=`.
- Manual check after deploy: both themes, phone width 375px, keyboard navigation.

## Out of scope

- New founder actions.
- A JS framework.
- Charts beyond CSS bars.
- The Ask page (M2b).
- Real-time updates.
