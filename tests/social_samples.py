"""Sample Apify payloads in the documented output shape of the two actors."""

PROFILES = [
    {
        "username": "tortat.e.mira",
        "fullName": "Tortat e Mira",
        "isBusinessAccount": True,
        "businessCategoryName": "Bakery",
        "followersCount": 5400,
        "private": False,
        "url": "https://www.instagram.com/tortat.e.mira/",
        "latestPosts": [
            {
                "timestamp": "2026-10-01T10:00:00.000Z",
                "latestComments": [
                    {"text": "Sa kushton kjo torte?", "ownerUsername": "private.person1"},
                    {"text": "A dergoni ne Prizren?", "ownerUsername": "private.person2"},
                    {"text": "Ku gjendeni?", "ownerUsername": "private.person3"},
                    {"text": "Shume e bukur", "ownerUsername": "private.person4"},
                ],
            },
            {"timestamp": "2026-09-20T10:00:00.000Z", "latestComments": []},
        ],
    },
    {
        "username": "ana.private",
        "fullName": "Ana",
        "isBusinessAccount": False,
        "followersCount": 300,
        "latestPosts": [
            {
                "timestamp": "2026-10-02T10:00:00.000Z",
                "latestComments": [{"text": "sa kushton?", "ownerUsername": "x"}],
            }
        ],
    },
    {"username": "secret.shop", "isBusinessAccount": True, "private": True, "followersCount": 10},
]

ADS = [
    {
        "adArchiveID": "111",
        "pageName": "Torta Shop",
        "isActive": True,
        "startDate": 1756684800,
        "publisherPlatform": ["FACEBOOK", "INSTAGRAM"],
        "snapshot": {
            "body": {"text": "Porosit torten tende! Tel +383 44 123 456, Prishtinë"},
            "pageProfileUri": "https://facebook.com/tortashop",
            "linkUrl": "https://tortashop.rks",
        },
    },
    {
        "adArchiveID": "222",
        "pageName": "Shopi AL",
        "isActive": True,
        "startDateFormatted": "2026-10-01T00:00:00",
        "publisherPlatform": ["INSTAGRAM"],
        "snapshot": {
            "body": {"text": "Dërgesa në Kosovë për 2 ditë"},
            "linkUrl": "https://shopi.al/products",
        },
    },
    {
        "ad_archive_id": "333",
        "page_name": "Mystery",
        "is_active": False,
        "start_date": 1759276800,
        "end_date": 1759708800,
        "snapshot": {"body": {"text": "Best deals"}},
    },
    {"pageName": "no id"},
]
