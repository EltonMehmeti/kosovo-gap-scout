from decimal import Decimal

from scout.extract.extractor import EXTRACTOR_SYSTEM, MAX_TEXT_CHARS, Extractor
from scout.extract.schemas import AppClassification, AppClassificationBatch
from scout.llm.gateway import LLM
from tests.fakes import FakeClient, FakeGuard, FakeMessage, text_block


def test_schema_is_structured_output_safe():
    schema = AppClassificationBatch.model_json_schema()
    assert schema["additionalProperties"] is False
    item = schema["$defs"]["AppClassification"]
    assert item["additionalProperties"] is False
    assert "enum" in item["properties"]["kosovo_relevance"]
    assert all(k not in str(schema) for k in ("minimum", "maximum", "minLength", "pattern"))


def test_extract_calls_haiku_low_effort_and_clips_text():
    batch = AppClassificationBatch(
        items=[
            AppClassification(
                app_key="com.x",
                category="mobility",
                consumer_need="bus times",
                kosovo_relevance="high",
                sector_slug="mobility-transit",
                is_global_brand=False,
                note="",
            )
        ]
    )
    client = FakeClient([FakeMessage(content=[text_block("{}")], parsed_output=batch)])
    ex = Extractor(LLM(client, FakeGuard(), Decimal("0.92")))
    out = ex.extract(AppClassificationBatch, "Classify these apps.", "x" * (MAX_TEXT_CHARS + 10))
    assert out is batch
    kw = client.messages.calls[0]
    assert kw["model"] == "claude-haiku-5-5" and kw["output_config"] == {"effort": "low"}
    assert kw["system"] == EXTRACTOR_SYSTEM and kw["output_format"] is AppClassificationBatch
    expected = f"Classify these apps.\n\n<text>\n{'x' * MAX_TEXT_CHARS}\n</text>"
    assert kw["messages"][0]["content"] == expected
