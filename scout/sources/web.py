"""Anthropic server tools (run on Anthropic's side; priced per search + tokens)."""

from __future__ import annotations


def web_tools(max_searches: int = 12, max_fetches: int = 8) -> list[dict]:
    return [
        {"type": "web_search_20260209", "name": "web_search", "max_uses": max_searches},
        {"type": "web_fetch_20260209", "name": "web_fetch", "max_uses": max_fetches},
    ]
