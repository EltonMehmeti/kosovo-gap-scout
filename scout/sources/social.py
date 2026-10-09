"""Turn raw Apify items into privacy-safe scout records: public business accounts only, comments reduced
to counts, ads with a local/foreign guess."""

from __future__ import annotations

import re
from collections.abc import Iterable
from datetime import UTC, date, datetime
from urllib.parse import urlparse

MAX_SHOPS = 30
LONG_RUNNING_DAYS = 30
QUESTION_PATTERNS = {
    "price": re.compile(
        r"sa\s*kushton|sa\s*[eë]sht[eë]|[cç]mimi|qmimi|\bprice\b|how much|\bcost", re.I
    ),
    "delivery": re.compile(r"d[eë]rg|posta|transport|delivery|\bship|a\s*vjen\s*n[eë]", re.I),
    "where": re.compile(
        r"ku\s*gjendeni|ku\s*jeni|ku\s*mund|lokacion|adres|where (can|do|are)", re.I
    ),
}
KOSOVO_LOCAL = re.compile(
    r"\+383|\b04[3-9][\s-]?\d{3}|prishtin|prizren|\bpej[eë]\b|gjakov|mitrovic|ferizaj|gjilan", re.I
)
FOREIGN_HINTS = re.compile(r"\+355|\+389|\+381|\+382|\+387|\+49|\+41|\+43|\+90|\btiran", re.I)
FOREIGN_TLDS = (".al", ".mk", ".rs", ".me", ".ba", ".hr", ".si", ".de", ".ch", ".at", ".tr")


def _first(d: dict, *keys):
    for k in keys:
        v = d.get(k)
        if v not in (None, ""):
            return v
    return None


def _dict(v) -> dict:
    return v if isinstance(v, dict) else {}


def _list(v) -> list:
    return v if isinstance(v, list) else []


def _date(v) -> date | None:
    if isinstance(v, int | float) and not isinstance(v, bool) and v > 0:
        return datetime.fromtimestamp(v, tz=UTC).date()
    if isinstance(v, str) and len(v) >= 10:
        try:
            return date.fromisoformat(v[:10])
        except ValueError:
            return None
    return None


def _count(v) -> int:
    if isinstance(v, bool):
        return 0
    if isinstance(v, int | float):
        return int(v)
    if isinstance(v, str):
        s = v.strip().lower().replace(",", "")
        scale = {"k": 1_000, "m": 1_000_000}.get(s[-1:], 1)
        try:
            return int(float(s[:-1] if scale > 1 else s) * scale)
        except ValueError:
            return 0
    return 0


def _str(v) -> str | None:
    return v if isinstance(v, str) and v else None


def question_counts(texts: Iterable[str]) -> dict[str, int]:
    counts = dict.fromkeys(QUESTION_PATTERNS, 0)
    for text in texts:
        for kind, pattern in QUESTION_PATTERNS.items():
            if isinstance(text, str) and pattern.search(text):
                counts[kind] += 1
    return counts


def instagram_summary(items: list[dict]) -> dict:
    shops: list[dict] = []
    texts: list[str] = []
    for it in _list(items):
        it = _dict(it)
        username = it.get("username")
        is_business = it.get("isBusinessAccount") or it.get("businessCategoryName")
        if not username or it.get("private") or not is_business:
            continue
        posts = [_dict(p) for p in _list(it.get("latestPosts"))]
        dates = [d for d in (_date(p.get("timestamp")) for p in posts) if d]
        for p in posts:
            texts += [_dict(c).get("text") or "" for c in _list(p.get("latestComments"))]
        shops.append(
            {
                "username": str(username),
                "name": str(it.get("fullName") or ""),
                "followers": _count(it.get("followersCount")),
                "category": _str(it.get("businessCategoryName")),
                "last_post": max(dates).isoformat() if dates else None,
                "url": _str(it.get("url")) or f"https://www.instagram.com/{username}/",
            }
        )
        if len(shops) >= MAX_SHOPS:
            break
    return {"shops": shops, "questions": question_counts(texts)}


def is_foreign(text: str, link_url: str | None) -> bool | None:
    host = (urlparse(link_url or "").hostname or "").lower()
    if host.endswith(FOREIGN_TLDS) or FOREIGN_HINTS.search(text or ""):
        return True
    if host.endswith(".rks") or KOSOVO_LOCAL.search(text or ""):
        return False
    return None


def ads_summary(items: list[dict], *, today: date) -> dict:
    ads: list[dict] = []
    for it in _list(items):
        it = _dict(it)
        archive_id = _first(it, "adArchiveID", "adArchiveId", "ad_archive_id")
        if archive_id is None:
            continue
        snap = _dict(it.get("snapshot"))
        text = str(_first(_dict(snap.get("body")), "text") or "")
        link = _str(_first(snap, "linkUrl", "link_url"))
        active = bool(_first(it, "isActive", "is_active"))
        first = _date(_first(it, "startDate", "start_date", "startDateFormatted"))
        end = _date(_first(it, "endDate", "end_date", "endDateFormatted"))
        last = today if active else end
        platforms = _first(it, "publisherPlatform", "publisher_platform") or []
        ads.append(
            {
                "ad_archive_id": str(archive_id),
                "page_name": str(_first(it, "pageName", "page_name") or ""),
                "page_url": _str(_first(snap, "pageProfileUri", "page_profile_uri")),
                "ad_text": text[:2000],
                "platforms": [str(p).lower() for p in _list(platforms)],
                "first_seen": first.isoformat() if first else None,
                "last_seen": last.isoformat() if last else None,
                "is_active": active,
                "is_foreign": is_foreign(text, link),
                "link_url": link,
                "long_running": bool(
                    active and first and (today - first).days >= LONG_RUNNING_DAYS
                ),
            }
        )
    return {
        "ads": ads,
        "count": len(ads),
        "foreign": sum(1 for a in ads if a["is_foreign"]),
        "long_running": sum(1 for a in ads if a["long_running"]),
    }
