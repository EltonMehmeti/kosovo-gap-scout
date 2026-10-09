from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class ChartEntry:
    rank: int
    app_key: str
    name: str
    publisher: str
    genres: tuple[str, ...]
    url: str


@dataclass(frozen=True)
class AppHit:
    store: str  # "apple" | "play"
    app_key: str
    name: str
    publisher: str
    url: str


@dataclass(frozen=True)
class PlaceHit:
    place_id: str
    name: str
    address: str
    primary_type: str | None
    business_status: str | None
    lat: float | None
    lng: float | None


@dataclass
class PlacesResult:
    count: int
    places: list[PlaceHit] = field(default_factory=list)
