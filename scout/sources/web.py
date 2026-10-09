"""Anthropic server tools (run on Anthropic's side; priced per search + tokens).

Basic versions on purpose: the `_20260209` dynamic-filtering versions run searches from a code sandbox,
where the model mis-called the tool ("invalid tool input") and re-ran queries while debugging its own
code, burning the per-task `max_uses` allowance on duplicates (live run 2026-10-09). The basic versions
make one direct call per search, so `max_uses` counts real queries.
"""

from __future__ import annotations


def web_tools(max_searches: int = 12, max_fetches: int = 8) -> list[dict]:
    return [
        {"type": "web_search_20250305", "name": "web_search", "max_uses": max_searches},
        {"type": "web_fetch_20250910", "name": "web_fetch", "max_uses": max_fetches},
    ]
