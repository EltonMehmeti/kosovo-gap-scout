"""Starting knowledge: the sector taxonomy, culture themes, source registry and a cautious country digest."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from scout.db import repo
from scout.db.models import Source

# (slug, name_en, name_sq, priority) — spec Appendix A
SECTORS: list[tuple[str, str, str, int]] = [
    ("home-services", "Home services (cleaning, repairs, handymen)", "Shërbime për shtëpi", 1),
    ("health-booking", "Health and dental booking", "Rezervime shëndetësore", 1),
    ("tutoring-education", "Tutoring, Matura prep, courses", "Mësim privat dhe kurse", 1),
    ("mobility-transit", "Transit, parking, intercity transport", "Transport dhe parkim", 1),
    (
        "secondhand-marketplaces",
        "Second-hand marketplaces (fashion, kids, electronics)",
        "Tregje të dorës së dytë",
        1,
    ),
    ("rentals-housing", "Long-term rentals and housing services", "Qira dhe banim", 1),
    ("diaspora-services", "Diaspora-to-family services", "Shërbime për diasporën", 1),
    ("weddings-events", "Weddings and events marketplace", "Dasma dhe evente", 1),
    ("food-grocery-delivery", "Food, grocery and meal-plan delivery", "Ushqim dhe dërgesa", 2),
    ("beauty-wellness", "Beauty and wellness booking", "Bukuri dhe mirëqenie", 2),
    ("fitness-sports", "Fitness, sports and courts", "Fitnes dhe sport", 2),
    ("pets", "Pets (vets, sitting, supplies)", "Kafshë shtëpiake", 2),
    ("car-services", "Car services (repairs, inspection, parts)", "Shërbime për vetura", 2),
    ("parenting-kids", "Parenting, childcare and kids' activities", "Prindër dhe fëmijë", 2),
    ("bureaucracy-helpers", "Bureaucracy and e-Kosova helpers", "Ndihmë për burokraci", 2),
    ("local-travel", "Local travel, weekends, mountains", "Udhëtime lokale", 2),
    (
        "utilities-household-finance",
        "Utilities, bills and household money tools",
        "Fatura dhe financa familjare",
        3,
    ),
    ("jobs-gigs", "Jobs, gigs and freelancing", "Punë dhe angazhime", 3),
    ("agri-to-consumer", "Farm-to-consumer food", "Nga fshati te konsumatori", 3),
    ("entertainment-media", "Entertainment, tickets, media", "Argëtim dhe media", 3),
    ("legal-consumer", "Consumer legal and notary help", "Ndihmë juridike", 3),
    ("instagram-seller-tools", "Tools for Instagram sellers", "Vegla për shitës në Instagram", 3),
    ("elderly-care", "Elderly care and remote family care", "Kujdes për të moshuarit", 3),
    ("language-ai-consumer", "Albanian-language AI consumer tools", "Vegla AI në shqip", 3),
]

# (slug, name) — spec Appendix B
CULTURE_THEMES: list[tuple[str, str]] = [
    ("payments-and-trust", "Payments and trust"),
    ("diaspora-and-remittances", "Diaspora and remittances"),
    ("family-and-housing", "Family and housing"),
    ("youth-and-work", "Youth and work"),
    ("language-and-media", "Language and media"),
    ("cities-and-mobility", "Cities and mobility"),
    ("calendar-and-seasons", "Calendar and seasons"),
    ("shopping-habits", "Shopping habits"),
    ("bureaucracy-and-state", "Bureaucracy and the state"),
    ("health-and-education", "Health and education"),
]

SOURCES: list[dict] = [
    {
        "tier": "A",
        "name": "askdata",
        "kind": "stats",
        "base_url": "https://askdata.rks-gov.net/api/v1/en/ASKdata/",
        "ttl_hours": 24 * 180,
        "cost_per_call_eur": Decimal("0"),
    },
    {
        "tier": "A",
        "name": "google-places",
        "kind": "places",
        "base_url": "https://places.googleapis.com/v1/places:searchText",
        "ttl_hours": 24 * 30,
        "cost_per_call_eur": Decimal("0"),
        "config": {"monthly_quota": 4500},
    },
    {
        "tier": "A",
        "name": "apple-rss",
        "kind": "app-chart",
        "base_url": "https://rss.marketingtools.apple.com/api/v2/",
        "ttl_hours": 24 * 7,
        "cost_per_call_eur": Decimal("0"),
    },
    {
        "tier": "A",
        "name": "google-play",
        "kind": "app-chart",
        "base_url": "https://play.google.com/store/apps/",
        "ttl_hours": 24 * 7,
        "cost_per_call_eur": Decimal("0"),
    },
    {
        "tier": "A",
        "name": "itunes-search",
        "kind": "app-search",
        "base_url": "https://itunes.apple.com/search",
        "ttl_hours": 24 * 30,
        "cost_per_call_eur": Decimal("0"),
    },
    {
        "tier": "A",
        "name": "claude-web-search",
        "kind": "web",
        "base_url": None,
        "ttl_hours": 24 * 30,
        "cost_per_call_eur": Decimal("0.0092"),
    },
    {
        "tier": "B",
        "name": "apify-instagram",
        "kind": "social",
        "base_url": "https://api.apify.com/",
        "ttl_hours": 24 * 14,
        "cost_per_call_eur": Decimal("0.002"),
        "enabled": False,
    },
    {
        "tier": "B",
        "name": "meta-ad-library",
        "kind": "ads",
        "base_url": "https://www.facebook.com/ads/library/",
        "ttl_hours": 24 * 7,
        "cost_per_call_eur": Decimal("0.002"),
        "enabled": False,
    },
    {
        "tier": "C",
        "name": "merrjep",
        "kind": "classifieds",
        "base_url": "https://www.merrjep.com/",
        "ttl_hours": 24 * 7,
        "cost_per_call_eur": Decimal("0"),
        "enabled": False,
    },
    {
        "tier": "C",
        "name": "kosovajob",
        "kind": "jobs",
        "base_url": "https://kosovajob.com/",
        "ttl_hours": 24 * 7,
        "cost_per_call_eur": Decimal("0"),
        "enabled": False,
    },
    {
        "tier": "D",
        "name": "founder",
        "kind": "field",
        "base_url": None,
        "ttl_hours": 24 * 365,
        "cost_per_call_eur": Decimal("0"),
    },
]

COUNTRY_DIGEST_SEED = """# Kosovo — starting picture (seed; every number below must be verified and sourced by the scout)

- People: ≈ 1.6 million residents (2024 census, provisional), one of Europe's youngest populations (median age ≈ 30).
  Albanian-speaking majority; Serbian-speaking communities mainly in the north and in enclaves; official languages
  Albanian and Serbian.
- Cities: Prishtinë (capital, ≈ 200k+ in the municipality), Prizren, Pejë, Gjakovë, Mitrovicë, Ferizaj, Gjilan.
  Most consumer apps launch in Prishtina only.
- Money: euro is the currency; cash still dominant in daily shopping, card use growing fast; PayPal cannot
  pay out to Kosovo accounts; Stripe is unavailable; local card acquiring exists through banks and PSPs;
  cash on delivery is normal for e-commerce.
- Diaspora: several hundred thousand Kosovars abroad (Germany, Switzerland, Austria, Scandinavia, US);
  remittances are a major share of GDP; summer (July–August) and New Year bring the diaspora home and drive
  spending on weddings, cars, housing and restaurants.
- Digital life: high household internet and smartphone penetration; Android dominant; Instagram, TikTok,
  Facebook and WhatsApp/Viber are the main channels; many small businesses sell through Instagram DMs;
  e-Kosova portal digitalised many state services.
- Economy: small, service-heavy, large informal sector; wages low by EU standards; unemployment high
  among youth; strong entrepreneurial culture (cafés, car services, construction, ICT outsourcing).
- Known consumer players to treat as incumbents: Wolt (food delivery), Gjirafa (GjirafaMall, Gjirafa50,
  video), Merrjep and other classifieds, KosovaJob, Telegrafi/Koha (media), banks' apps, telecom apps.
"""


def seed_all(session) -> dict[str, int]:
    counts = {"sectors": 0, "themes": 0, "sources": 0, "digests": 0}
    for slug, name_en, name_sq, priority in SECTORS:
        if repo.get_sector(session, slug) is None:
            repo.get_or_create_sector(session, slug, name_en, name_sq, priority=priority)
            counts["sectors"] += 1
    themes = [slug for slug, _ in CULTURE_THEMES]
    if repo.get_setting(session, "culture_themes") != themes:
        repo.set_setting(session, "culture_themes", themes)
        counts["themes"] = len(themes)
    for row in SOURCES:
        if session.query(Source).filter_by(name=row["name"]).first() is None:
            session.add(Source(**row))
            counts["sources"] += 1
    session.commit()
    if repo.get_digest(session, "country") is None:
        repo.set_digest(
            session,
            "country",
            "Kosovo — starting picture",
            COUNTRY_DIGEST_SEED,
            now=datetime.now(UTC),
        )
        counts["digests"] += 1
    return counts
