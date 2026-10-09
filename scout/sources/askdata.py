"""Kosovo Agency of Statistics (ASK) PxWeb API v1 client — free, official numbers."""

from __future__ import annotations

import json
from dataclasses import dataclass
from urllib.parse import quote

import httpx

DEFAULT_BASE_URL = "https://askdata.rks-gov.net/api/v1/en/ASKdata"
USER_AGENT = "kosovo-gap-scout/0.1 (+research; contact via GitHub)"


@dataclass
class PxItem:
    id: str
    text: str
    kind: str  # "l" = folder, "t" = table


@dataclass
class PxVariable:
    code: str
    text: str
    values: list[str]
    value_texts: list[str]


@dataclass
class PxTable:
    title: str
    variables: list[PxVariable]


@dataclass
class PxData:
    columns: list[str]
    rows: list[dict]  # each {"key": [...], "values": [...]}


def _json(response: httpx.Response):
    response.raise_for_status()
    return json.loads(response.text.lstrip("﻿"))  # PxWeb prefixes JSON with a BOM


class AskDataClient:
    def __init__(
        self,
        http: httpx.Client | None = None,
        base_url: str = DEFAULT_BASE_URL,
        timeout: float = 30.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.http = http or httpx.Client(timeout=timeout, headers={"User-Agent": USER_AGENT})

    def _url(self, path: str) -> str:
        segments = [quote(s, safe="") for s in path.split("/") if s != ""]
        if not segments:
            return self.base_url + "/"
        return "/".join([self.base_url, *segments])

    def list(self, path: str = "") -> list[PxItem]:
        items = _json(self.http.get(self._url(path)))
        return [PxItem(id=i["id"], text=i.get("text", ""), kind=i.get("type", "")) for i in items]

    def metadata(self, path: str) -> PxTable:
        d = _json(self.http.get(self._url(path)))
        return PxTable(
            title=d.get("title", ""),
            variables=[
                PxVariable(
                    code=v["code"],
                    text=v.get("text", ""),
                    values=list(v.get("values", [])),
                    value_texts=list(v.get("valueTexts", [])),
                )
                for v in d.get("variables", [])
            ],
        )

    def fetch(self, path: str, selections: dict[str, list[str]]) -> PxData:
        query = [
            {"code": code, "selection": {"filter": "item", "values": list(values)}}
            for code, values in selections.items()
        ]
        d = _json(
            self.http.post(self._url(path), json={"query": query, "response": {"format": "json"}})
        )
        return PxData(
            columns=[c.get("text", c.get("code", "")) for c in d.get("columns", [])],
            rows=list(d.get("data", [])),
        )
