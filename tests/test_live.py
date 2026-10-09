"""Live checks against real services. Run by hand: uv run pytest tests/test_live.py -m network -v"""

import os
from decimal import Decimal

import pytest

pytestmark = pytest.mark.network


@pytest.fixture
def client():
    import anthropic

    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        pytest.skip("ANTHROPIC_API_KEY not set")
    return anthropic.Anthropic(api_key=key)


def test_prompt_cache_hits_on_second_call(client):
    from scout.budget.pricing import usage_units

    filler = "Kosovo Gap Scout rules. " * 400  # ≈ 2k tokens, above the minimum cacheable prefix
    system = [{"type": "text", "text": filler, "cache_control": {"type": "ephemeral"}}]
    kwargs = dict(
        model="claude-haiku-5-5",
        max_tokens=20,
        system=system,
        messages=[{"role": "user", "content": "Reply with the single word: ok"}],
        output_config={"effort": "low"},
    )
    first = client.messages.create(**kwargs)
    second = client.messages.create(**kwargs)
    assert (
        usage_units(first.usage)["cache_write_tokens"] > 0
        or usage_units(first.usage)["cache_read_tokens"] > 0
    )
    assert usage_units(second.usage)["cache_read_tokens"] > 0


def test_places_region_code_xk(client):
    from scout.sources.places import PlacesClient

    key = os.environ.get("GOOGLE_PLACES_API_KEY")
    if not key:
        pytest.skip("GOOGLE_PLACES_API_KEY not set")
    res = PlacesClient(key).text_search("dentist Prizren")
    assert res.count > 0 and any("Prizren" in p.address for p in res.places)


def test_tool_runner_accepts_system_and_effort(client):
    """Spec B19 #3: tool_runner takes system=, max_iterations=, output_config= on anthropic 1.x."""
    from anthropic import beta_tool

    @beta_tool
    def ping(word: str) -> str:
        """Echo a word.

        Args:
            word: The word to echo.
        """
        return word

    runner = client.beta.messages.tool_runner(
        model="claude-haiku-5-5",
        max_tokens=200,
        system="Use the ping tool once with the word hello, then stop.",
        tools=[ping],
        messages=[{"role": "user", "content": "go"}],
        max_iterations=3,
        output_config={"effort": "low"},
    )
    last = runner.until_done()
    assert last.stop_reason in ("end_turn", "tool_use")
    assert Decimal(last.usage.input_tokens) > 0
