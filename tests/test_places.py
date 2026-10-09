import json

import httpx
import pytest

from scout.sources.places import PRO_FIELD_MASK, PlacesClient, PlacesError

RESPONSE = {
    "places": [
        {
            "id": "ChIJ1",
            "displayName": {"text": "Klinika Dentare Smile", "languageCode": "sq"},
            "formattedAddress": "Rr. Agim Ramadani, Prishtinë",
            "primaryType": "dentist",
            "types": ["dentist", "health"],
            "businessStatus": "OPERATIONAL",
            "location": {"latitude": 42.66, "longitude": 21.16},
        }
    ]
}


def test_text_search_sends_pro_mask_and_parses():
    def handler(request):
        assert request.headers["X-Goog-Api-Key"] == "k"
        assert request.headers["X-Goog-FieldMask"] == PRO_FIELD_MASK
        body = json.loads(request.content)
        assert body == {
            "textQuery": "dentist Prishtinë",
            "languageCode": "sq",
            "pageSize": 20,
            "regionCode": "XK",
        }
        return httpx.Response(200, json=RESPONSE)

    res = PlacesClient("k", http=httpx.Client(transport=httpx.MockTransport(handler))).text_search(
        "dentist Prishtinë"
    )
    assert res.count == 1
    p = res.places[0]
    assert (p.name, p.primary_type, p.business_status, p.lat) == (
        "Klinika Dentare Smile",
        "dentist",
        "OPERATIONAL",
        42.66,
    )


def test_empty_result_and_errors():
    def handler(request):
        body = json.loads(request.content)
        if body["textQuery"] == "nothing":
            return httpx.Response(200, json={})
        return httpx.Response(403, json={"error": {"message": "API key not valid"}})

    c = PlacesClient("k", http=httpx.Client(transport=httpx.MockTransport(handler)))
    assert c.text_search("nothing").count == 0
    with pytest.raises(PlacesError):
        c.text_search("boom")


def test_region_code_rejected_falls_back_to_kosovo_in_query():
    bodies = []

    def handler(request):
        body = json.loads(request.content)
        bodies.append(body)
        if "regionCode" in body:
            return httpx.Response(
                400, json={"error": {"message": "Invalid value at 'region_code'"}}
            )
        return httpx.Response(200, json=RESPONSE)

    res = PlacesClient("k", http=httpx.Client(transport=httpx.MockTransport(handler))).text_search(
        "dentist"
    )
    assert res.count == 1
    assert bodies[1]["textQuery"] == "dentist Kosovo" and "regionCode" not in bodies[1]
