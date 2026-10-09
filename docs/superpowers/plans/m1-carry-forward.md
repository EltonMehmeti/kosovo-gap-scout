# M1 → M2 carry-forward

Review findings deliberately deferred during M1 (subagent-driven development, 2026-10-09).
Each was judged non-blocking for the first live runs. Pick these up when planning M2.

## Watch during the first live week (Foundation, from 2026-10-10)

- **Search-capped research task counts as complete.** When a research task hits its per-task
  web-search cap, `_apply_outcome` still treats it as complete. A map-sector or hunt-models
  sector can be marked mapped or hunted with a thin digest, a deep-dive can store a partial
  test plan and set the monthly `deep-dive-done` flag, and a founder flag can be cleared.
  - **Symptom:** "search cap" in the brief.
  - **Workaround:** `scout add-task` to re-queue.
  - **M2 fix:** decide whether a capped task is requeued or failed, and leave it out of the
    success side effects.
- **Live checks never run by implementers:**
  - the Play Store chart HTML regex (`collection/topselling_free` returned 0 ids offline);
  - the tool_runner mirrored history (raw `message.content` vs `to_param()`).
  - **Action:** run `uv run pytest -m network` by hand once.
- **Cost estimates are rough.** Re-tune the research step, Strategist and Critic estimates from
  the first days of `costs` rows.
- **Verification needs real data.** Without `GOOGLE_PLACES_API_KEY`, every presence check is
  degraded and nothing can verify. Verification also needs proven models whose market URLs
  cover at least 2 countries, at least 1 of them nearby. Confirm the research workers record
  these URLs before the Verification phase starts on 2026-11-16.

- **Truncated tasks look done in the brief.** A task cut off by `max_tokens` still shows
  "done" in the brief. It is correctly not applied, for example the sector is not marked
  mapped. Show "cut short" instead. Seen live on 2026-10-09 before the cap was raised to 16000.

## Strategy / verification

- When the Critic raises a new `needs_field_check` question on the day a gap verifies, the
  question is dropped. It should block verification or at least be queued.
- `apply` writes assessments for gap ids that were not sent to the Strategist. Filter them to
  the ids that were sent.
- A verified gap is not demoted when its score falls below 60, and a verified gap has no score
  floor.
- With `critic_ok=False`, only the total score is capped, not each component.
- Strategist fresh-only gating must widen once M2 starts editing gaps.

## Director / accounting

- A run's `spent_eur` is the day total, not the amount spent by that run.
- `days_run` double-counts reruns on the same day.
- Planner task-mix caps are only per plan.
- Extractor calls carry no `task_id`, so their cost rows are not linked to a task.
- A budget-stopped task is marked done. By design, it is re-planned the next day.
- The quiet-day "failed" count misses tasks that errored and were left queued.
- `web_fetch` `max_uses` is per request, not per task.

## Sources / KB

- Source health flags are not implemented (spec, M2).
- Default httpx clients are never closed. This is not a real leak in CPython.
- `upsert_fact` hashes the claim text, so reworded facts duplicate, for example in weekly
  chart-diff consumer needs.
- `upsert_fact` keeps the max confidence and never downgrades it.
- `has_presence_check` ignores `expires_at`.
- `search_facts` drops the filter when given an unknown sector, and its ilike pattern is not
  escaped.
- Places transport and JSON errors escape as non-`PlacesError`.

## CLI / tests

- `run --phase bogus` shows a traceback, and a negative `--budget` is not checked.
- `field-check answer` makes 3 separate commits.
- Missing tests:
  - functional unique indexes;
  - month-boundary money and quota bounds;
  - the CLI `brief` / `chart-diff` / `unflag` commands;
  - `load_state` against a real DB.
- Style:
  - `rubric.py` uses a file-level `# ruff: noqa: E501`;
  - a NaN confidence clamps to 1.0;
  - money rounding uses `ROUND_HALF_EVEN`.
