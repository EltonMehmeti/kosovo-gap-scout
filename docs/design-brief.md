# Design brief: Kosovo Gap Scout dashboard

Paste this whole file into Claude Design. The repo is public: https://github.com/EltonMehmeti/kosovo-gap-scout. The live dashboard is https://scout-dashboard-bmoz.onrender.com (it needs the dashboard token to log in).

## 1. What the product is

A daily AI scout looks for **business gaps in Kosovo**: consumer (B2C) business models that already work abroad, ideally in nearby Balkan countries, but don't exist in Kosovo yet. The dashboard is the **only interface** for **one person, the founder**. They have 5–10 hours a week, a day job, and are not a designer or an engineer.

Every morning the scout runs by itself. It maps sectors, finds proven foreign models, proposes gaps, checks them against real data, scores them, and writes a daily brief. The founder opens the dashboard to:
1. Read the brief.
2. Answer questions only a local can answer (field checks).
3. Decide which gaps to pursue, hold or reject.
4. Retry failed tasks and watch the budget.

**The most important design goal: the founder must understand every screen at a glance, with no learning curve.** Plain words, no jargon, and it is always obvious what to do next. The current design failed at this ("I don't like the design"), so please design it from scratch.

Users and devices: one user, used about equally on **desktop and phone**.

## 2. What it must NOT become

- No marketing page, no multi-user features, no accounts, no dark patterns.
- It must stay **server-rendered HTML** (FastAPI + Jinja2) with **one CSS file and one small vanilla JS file**.
  - No React, no build step, no CDN, no external fonts or images.
  - Everything is served from `/static/`.
  - Self-hosted Inter font and a Lucide icon sprite (`icons.svg`) already exist there; replacing them is fine.
- The content security policy only allows `img-src 'self' data:`. No inline scripts or inline event handlers.
- Light and dark mode via `prefers-color-scheme`. Visible focus rings. Tap targets of at least 44px on phones.

## 3. Pages and what each one does

Five sections, shown in a sidebar on desktop and a bottom tab bar on phones. Some sections have sub-tabs.

| Section | URL | Purpose |
|---|---|---|
| **Home** | `/` | "Needs you" list (unread brief, open field checks, failed tasks), four numbers (spent today vs limit, spent this month, open gaps, next run), last-run line, and the latest brief rendered as Markdown. |
| **Gaps** → Board | `/gaps` | Kanban of gaps by status. On phones, one column at a time with a filter pill bar. A collapsed "Rejected" list sits below. |
| Gaps → detail | `/gaps/{id}` | Summary, why it might work (proven foreign model and source links), critic's concerns, score breakdown (5 parts), field-check Q&A, assessment history, and action buttons. |
| Gaps → Field checks | `/field-checks` | Questions the scout asks the founder, each with a text box for an answer. Answered ones are listed below. |
| **Activity** → Pipeline | `/pipeline` | Counts (waiting, running, failed), failed tasks with Retry and the error, queued tasks, an "Add a task" form, and recent runs. |
| Activity → Journal | `/journal` | Timeline of daily entries from the scout and from the founder: what happened, what was learned, what's next. |
| **Knowledge** | `/knowledge` | Fact search, sector cards, other notes. |
| Knowledge → sector | `/knowledge/sectors/{slug}` | Digest, gaps, businesses in Kosovo, proven models abroad. |
| Knowledge → digest | `/knowledge/digests/{key}` | Markdown note with an Edit form. |
| **Settings** → General | `/settings` | Phase switch, sector priorities, the founder's finalist and "check requested" lists, and a read-only environment list. |
| Settings → Budget & costs | `/costs` | Today's limit (and a way to set or clear it), a 14-day spend chart, cost per model this month, and data-source health. |
| Login | `/login` | A token field. |
| Error | any | A friendly message and a link back. |

Pages that are forms (field-check answers, add task, set cap, phase switch, priorities, digest edit) post to existing URLs. **All URLs, form fields and HTTP methods stay exactly as they are.** The design is free to change the layout, components and wording.

## 4. The data behind the screens (so the design uses real states)

**Gap.** Fields: title, status, optional sector, a 0–100 score (or none yet), five score parts, a confidence percentage, a "how present is this in Kosovo" level, optional critic flag, and finalist or "check requested" marks.
- Statuses: `candidate` → shown as "New idea"; `verifying` → "Being checked"; `verified` → "Confirmed gap"; `parked` → "On hold"; `killed` → "Rejected".
- Score parts and maximums: Proven elsewhere /25, Missing in Kosovo /25, Demand signals /20, Fits you /15, Low risk /15.
- Score bands: 75+ strong (green), 60+ promising (blue), 40+ weak (amber), below 40 poor (red), none "not scored yet" (gray).
- Presence levels: "Not in Kosovo", "Exists but poor", "Only in Prishtina", "Offline only", "Already done well", "Not checked yet".
- Critic flags: "Critic says reject" and "Strategist says reject" (the scout puts these gaps on hold for the founder to decide).
- Founder actions on a gap: Check this again / Cancel check, Make or Remove finalist, Put on hold, Reject (asks for confirmation), Reopen.

**Task.** Statuses: Waiting, Running, Done, Failed, Skipped. Plain task names: Map a sector, Find proven models, Check a gap, Culture research, News scan, Deep dive, App chart comparison. A task has a target (sector, gap or theme), a priority of 0–100, an estimated cost, an optional error message and an optional Markdown result.

**Run** (one per day). Statuses: Running, Finished, Failed, Stopped, "Plan only" (dry run). It has a date, a phase, task counts, spend against its cap, and a Markdown summary.

**Phases** (the scout's mode; the founder can switch):
- Foundation: build the knowledge base, about €3/day.
- Verification: check the best gaps against real data, about €1.50/day.
- Maintenance: light daily watch, about €0.80/day.

**Money and time.** Amounts show as `€0.42` (and `<€0.01` for tiny ones). Dates are human: "today", "yesterday", "Oct 7", with the exact ISO date on hover. The scout runs once a day at 07:00 Kosovo time in winter, 08:00 in summer. Kosovo is on Europe/Belgrade time.

**Content that comes from AI.** Brief, summaries, digests and journal entries are Markdown, so the design needs good prose styling (headings, lists, tables, blockquotes). Critic output is odd-shaped JSON, shown as key/value rows with a "Raw data" fallback.

## 5. Behaviours worth designing deliberately

- **Feedback after actions:** a short green toast after a successful action ("Added to finalists"). A red error toast stays until dismissed.
- **Sidebar badges:** counts for Home (unread brief), Gaps (open field checks) and Activity (failed tasks). They hide at zero.
- **Empty states with a next step:** "No gaps yet", "No questions for you right now", "Nothing waiting", "No runs yet", "No sectors yet", "All clear ✓ — nothing needs you right now."
- **Keyboard (optional):** `g` then `h/g/a/k/s` jumps between sections, and `/` focuses search.
- **Wide content:** long titles and error text must wrap, and tables must scroll sideways on phones.

## 6. Where to look in the repo

- Templates: `scout/web/templates/` (`base.html` is the shell; `_ui.html` and `_gaps.html` are shared macros).
- Styles and script: `scout/web/static/app.css` and `app.js`.
- Plain-word labels and tones: `scout/web/ui.py`. Keep wording changes there; templates should not print raw database values.
- Page logic (what data each page receives): `scout/web/pages/*.py`.
- Original design spec: `docs/superpowers/specs/2026-10-09-dashboard-redesign-design.md`.
- Tests that pin down required text and behaviour: `tests/test_web_*.py`.

## 7. What to hand back

A design the founder can understand immediately, delivered as the HTML/CSS/JS above for the screens in section 3. Include mobile and desktop for Home, Gaps board, Gap detail, Pipeline, and Budget & costs. Keep every state in section 4 visually distinct, without relying on color alone (always include text).
