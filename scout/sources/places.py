"""Google Places API (New) text search, restricted to the Pro SKU fields (5,000 free calls/mo)."""

from __future__ import annotations

import httpx

from scout.sources.types import PlaceHit, PlacesResult

PLACES_URL = "https://places.googleapis.com/v1/places:searchText"
PRO_FIELD_MASK = (
    "places.id,places.displayName,places.formattedAddress,places.primaryType,"
    "places.types,places.businessStatus,places.location"
)


class PlacesError(RuntimeError):
    pass


class PlacesClient:
    def __init__(
        self, api_key: str, http: httpx.Client | None = None, timeout: float = 20.0
    ) -> None:
        self.api_key = api_key
        self.http = http or httpx.Client(timeout=timeout)

    def _post(self, body: dict) -> httpx.Response:
        return self.http.post(
            PLACES_URL,
            json=body,
            headers={
                "X-Goog-Api-Key": self.api_key,
                "X-Goog-FieldMask": PRO_FIELD_MASK,
                "Content-Type": "application/json",
            },
        )

    def text_search(
        self,
        query: str,
        *,
        region_code: str | None = "XK",
        language: str = "sq",
        page_size: int = 20,
    ) -> PlacesResult:
        body = {"textQuery": query, "languageCode": language, "pageSize": page_size}
        if region_code:
            body["regionCode"] = region_code
        r = self._post(body)
        if r.status_code == 400 and region_code and "region" in r.text.lower():
            # Spec B19 #1: if XK is not an accepted region code, anchor the query textually instead.
            body = {"textQuery": f"{query} Kosovo", "languageCode": language, "pageSize": page_size}
            r = self._post(body)
        if r.status_code >= 400:
            raise PlacesError(f"places {r.status_code}: {r.text[:300]}")
        places = r.json().get("places", [])
        hits = [
            PlaceHit(
                place_id=p.get("id", ""),
                name=(p.get("displayName") or {}).get("text", ""),
                address=p.get("formattedAddress", ""),
                primary_type=p.get("primaryType"),
                business_status=p.get("businessStatus"),
                lat=(p.get("location") or {}).get("latitude"),
                lng=(p.get("location") or {}).get("longitude"),
            )
            for p in places
        ]
        return PlacesResult(count=len(hits), places=hits)
