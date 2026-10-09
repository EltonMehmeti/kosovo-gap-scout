from scout.sources.web import web_tools


def test_web_tools_use_basic_types_and_caps():
    assert web_tools(12, 8) == [
        {"type": "web_search_20250305", "name": "web_search", "max_uses": 12},
        {"type": "web_fetch_20250910", "name": "web_fetch", "max_uses": 8},
    ]
