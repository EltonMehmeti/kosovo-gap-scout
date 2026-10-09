import httpx
import pytest

from scout.sources.crawl import CrawlClient, CrawlRefused, allowed_domain, source_for


class Clock:
    def __init__(self):
        self.t = 100.0
        self.sleeps = []

    def __call__(self):
        return self.t

    def sleep(self, s):
        self.sleeps.append(s)
        self.t += s


def _client(robots="User-agent: *\nDisallow: /admin\n", status=200, clock=None):
    hits = {"robots": 0}
    rendered = []

    def handler(request):
        if request.url.path == "/robots.txt":
            hits["robots"] += 1
            if status == "down":
                raise httpx.ConnectError("down")
            return httpx.Response(status, text=robots)
        return httpx.Response(404)

    clock = clock or Clock()
    client = CrawlClient(
        render=lambda url: rendered.append(url) or f"# page {url}",
        http=httpx.Client(transport=httpx.MockTransport(handler)),
        sleep=clock.sleep,
        clock=clock,
    )
    return client, rendered, hits


def test_allowed_domain():
    assert allowed_domain("https://www.merrjep.com/shpalljet") == "merrjep.com"
    assert allowed_domain("https://m.merrjep.com/x") == "merrjep.com"
    assert allowed_domain("https://arbk.rks-gov.net/page") == "arbk.rks-gov.net"
    for bad in ("https://evilmerrjep.com", "https://merrjep.com.evil.io", "ftp://merrjep.com", "x"):
        assert allowed_domain(bad) is None
    assert source_for("merrjep.com") == "merrjep" and source_for("koha.net") == "kosovo-sites"


def test_refuses_domains_off_the_allowlist():
    client, rendered, _ = _client()
    with pytest.raises(CrawlRefused, match="allowlist"):
        client.fetch("https://www.instagram.com/x")
    assert rendered == []


def test_obeys_robots_and_fetches_it_once_per_host():
    client, rendered, hits = _client()
    with pytest.raises(CrawlRefused, match="robots"):
        client.fetch("https://www.merrjep.com/admin/x")
    assert client.fetch("https://www.merrjep.com/shpalljet").startswith("# page")
    assert rendered == ["https://www.merrjep.com/shpalljet"] and hits["robots"] == 1


def test_unreachable_robots_means_no_crawl_and_404_means_allowed():
    client, _, _ = _client(status="down")
    with pytest.raises(CrawlRefused):
        client.fetch("https://koha.net/a")
    client, rendered, _ = _client(status=404)
    client.fetch("https://koha.net/a")
    assert rendered == ["https://koha.net/a"]


def test_pages_are_two_seconds_apart():
    clock = Clock()
    client, _, _ = _client(clock=clock)
    for n in range(3):
        client.fetch(f"https://koha.net/{n}")
    assert clock.sleeps == [2.0, 2.0]
    clock.t += 5
    client.fetch("https://koha.net/later")
    assert clock.sleeps == [2.0, 2.0]
