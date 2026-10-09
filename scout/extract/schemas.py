"""Pydantic schemas for structured extraction. Rules: extra='forbid', Literal enums, no numeric constraints."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict

AppCategory = Literal[
    "mobility",
    "food-delivery",
    "marketplace",
    "fintech-payments",
    "health",
    "education",
    "home-services",
    "media-entertainment",
    "social",
    "utilities-government",
    "shopping",
    "travel",
    "jobs",
    "other",
]


class AppClassification(BaseModel):
    model_config = ConfigDict(extra="forbid")
    app_key: str
    category: AppCategory
    consumer_need: str
    kosovo_relevance: Literal["high", "medium", "low"]
    sector_slug: str
    is_global_brand: bool
    note: str


class AppClassificationBatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    items: list[AppClassification]
