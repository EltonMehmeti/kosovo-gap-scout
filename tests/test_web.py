from scout.sources.web import web_tools


def test_web_tools_use_dynamic_filtering_types_and_caps():
    assert web_tools(12, 8) == [
        {"type": "web_search_20260209", "name": "web_search", "max_uses": 12},
        {"type": "web_fetch_20260209", "name": "web_fetch", "max_uses": 8},
    ]
