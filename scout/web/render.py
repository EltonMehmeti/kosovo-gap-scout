"""Safe Markdown for model-written text: raw HTML is escaped, and markdown-it drops javascript: links."""

from __future__ import annotations

from markdown_it import MarkdownIt
from markupsafe import Markup

_md = MarkdownIt("commonmark", {"html": False}).enable("table")


def md(text: str | None) -> Markup:
    return Markup(_md.render(text or ""))
