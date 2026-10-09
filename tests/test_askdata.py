import json

import httpx
import pytest

from scout.sources.askdata import DEFAULT_BASE_URL, AskDataClient


def _client(handler):
    return AskDataClient(http=httpx.Client(transport=httpx.MockTransport(handler)))


def test_list_root_parses_folders_and_tables():
    def handler(request):
        assert str(request.url) == DEFAULT_BASE_URL + "/"
        return httpx.Response(
            200,
            json=[
                {"id": "Population", "type": "l", "text": "Population"},
                {"id": "tbl01.px", "type": "t", "text": "Pop by municipality"},
            ],
        )

    items = _client(handler).list()
    assert [(i.id, i.kind) for i in items] == [("Population", "l"), ("tbl01.px", "t")]


def test_path_segments_are_url_encoded_including_trailing_space():
    seen = {}

    def handler(request):
        seen["url"] = str(request.url)
        return httpx.Response(200, json=[])

    _client(handler).list("Labour market /Wages")
    assert seen["url"] == DEFAULT_BASE_URL + "/Labour%20market%20/Wages"


def test_metadata_and_fetch_strip_bom_and_post_query():
    def handler(request):
        if request.method == "GET":
            return httpx.Response(
                200,
                json={
                    "title": "Population by year",
                    "variables": [
                        {
                            "code": "Year",
                            "text": "Year",
                            "values": ["2023", "2024"],
                            "valueTexts": ["2023", "2024"],
                        }
                    ],
                },
            )
        body = json.loads(request.content)
        assert body["query"] == [
            {"code": "Year", "selection": {"filter": "item", "values": ["2024"]}}
        ]
        assert body["response"] == {"format": "json"}
        payload = {
            "columns": [{"code": "Year", "text": "Year"}, {"code": "Pop", "text": "Population"}],
            "data": [{"key": ["2024"], "values": ["1586659"]}],
        }
        return httpx.Response(200, content=("﻿" + json.dumps(payload)).encode("utf-8"))

    c = _client(handler)
    meta = c.metadata("Population/tbl01.px")
    assert meta.title == "Population by year" and meta.variables[0].values == ["2023", "2024"]
    data = c.fetch("Population/tbl01.px", {"Year": ["2024"]})
    assert data.columns == ["Year", "Population"] and data.rows[0]["values"] == ["1586659"]


def test_http_error_raises():
    def handler(request):
        return httpx.Response(500, text="boom")

    with pytest.raises(httpx.HTTPStatusError):
        _client(handler).list()


@pytest.mark.network
def test_live_root_lists_population_folder():
    ids = [i.id for i in AskDataClient().list()]
    assert "Population" in ids
