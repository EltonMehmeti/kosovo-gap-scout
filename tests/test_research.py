from decimal import Decimal

from scout.llm.gateway import LLM
from scout.worker.profiles import PROFILES
from scout.worker.research import PER_ITERATION_EST_EUR, ResearchWorker
from scout.worker.tools import ToolContext
from tests.fakes import (
    FakeClient,
    FakeGuard,
    FakeMessage,
    FakeUsage,
    fake_runner_factory,
    text_block,
    tool_use_block,
)

SYSTEM = [
    {"type": "text", "text": "rules"},
    {"type": "text", "text": "memory", "cache_control": {"type": "ephemeral"}},
]


def _ctx(guard):
    return ToolContext(
        session=None, guard=guard, now=None, run_id=1, task_id=5, places=None, askdata=None
    )


def _worker(guard, script, calls):
    llm = LLM(FakeClient(), guard, Decimal("0.92"))
    return ResearchWorker(
        FakeClient(), llm, guard, SYSTEM, runner_factory=fake_runner_factory(script, calls)
    )


def test_worker_runs_to_end_turn_and_records_each_message():
    guard, calls = FakeGuard(), []
    script = [
        [
            FakeMessage(
                content=[tool_use_block("kb_search", {"query": "pets"})], stop_reason="tool_use"
            ),
            FakeMessage(
                content=[text_block("Found 3 players.\nleads: pet sitting")], stop_reason="end_turn"
            ),
        ]
    ]
    out = _worker(guard, script, calls).run(5, PROFILES["map-sector"], "brief", _ctx(guard))
    assert out.summary_md.endswith("leads: pet sitting") and out.stop_reason == "end_turn"
    assert (
        out.iterations == 2 and out.restarts == 0 and not out.truncated and not out.budget_stopped
    )
    assert len(guard.records) == 2 and all(r.task_id == 5 for r in guard.records)
    assert out.cost_eur == sum(r.cost_eur for r in guard.records)
    kw = calls[0]
    assert (
        kw["model"] == "claude-sonnet-5-5" and kw["system"] is SYSTEM and kw["max_iterations"] == 14
    )
    assert kw["output_config"] == {"effort": "medium"} and kw["max_tokens"] == 4096
    assert "thinking" not in kw and "tool_choice" not in kw
    names = [t.name for t in kw["tools"] if hasattr(t, "name")]
    assert names[0] == "kb_search" and len(names) == 11
    assert {"type": "web_search_20260209", "name": "web_search", "max_uses": 12} in kw["tools"]
    assert kw["messages"] == [{"role": "user", "content": "brief"}]


def test_worker_restarts_on_pause_turn():
    guard, calls = FakeGuard(), []
    paused = FakeMessage(content=[text_block("searching...")], stop_reason="pause_turn")
    done = FakeMessage(content=[text_block("done. leads: none")], stop_reason="end_turn")
    out = _worker(guard, [[paused], [done]], calls).run(
        5, PROFILES["news-scan"], "brief", _ctx(guard)
    )
    assert out.restarts == 1 and out.stop_reason == "end_turn" and out.iterations == 2
    history = calls[1]["messages"]
    assert history[0] == {"role": "user", "content": "brief"}
    assert history[1]["role"] == "assistant" and history[1]["content"] is paused.content
    assert calls[1]["max_iterations"] == 5  # 6 minus the iteration already used


def test_worker_gives_up_after_max_restarts():
    guard, calls = FakeGuard(), []
    script = [[FakeMessage(content=[text_block("p")], stop_reason="pause_turn")] for _ in range(5)]
    out = _worker(guard, script, calls).run(5, PROFILES["news-scan"], "brief", _ctx(guard))
    assert out.restarts == ResearchWorker.MAX_RESTARTS and out.stop_reason == "pause_turn"
    assert len(calls) == ResearchWorker.MAX_RESTARTS + 1


def test_worker_stops_when_budget_tight():
    guard, calls = FakeGuard(cap=Decimal("0.05")), []
    big = FakeUsage(input_tokens=10_000, output_tokens=0)  # €0.0184 per message on Sonnet
    msgs = [
        FakeMessage(
            content=[tool_use_block("kb_search", {"query": "x"}, id=f"t{i}")],
            stop_reason="tool_use",
            usage=big,
        )
        for i in range(3)
    ]
    msgs.append(FakeMessage(content=[text_block("summary")], stop_reason="end_turn", usage=big))
    out = _worker(guard, [msgs], calls).run(5, PROFILES["map-sector"], "brief", _ctx(guard))
    assert PER_ITERATION_EST_EUR["claude-sonnet-5-5"] == Decimal("0.03")
    assert out.iterations == 2 and out.budget_stopped is True
    assert "budget" in out.summary_md and len(guard.records) == 2


def test_worker_reports_max_tokens():
    guard, calls = FakeGuard(), []
    cut = FakeMessage(content=[text_block("long memo that was cut")], stop_reason="max_tokens")
    out = _worker(guard, [[cut]], calls).run(None, PROFILES["deep-dive"], "brief", _ctx(guard))
    assert (
        out.truncated and out.stop_reason == "max_tokens" and out.summary_md.startswith("long memo")
    )
    assert (
        calls[0]["output_config"] == {"effort": "high"} and calls[0]["model"] == "claude-opus-5-5"
    )


def test_end_turn_over_cap_is_not_budget_stopped():
    guard, calls = FakeGuard(cap=Decimal("0.03")), []
    big = FakeUsage(input_tokens=20_000, output_tokens=0)
    done = FakeMessage(content=[text_block("all done")], stop_reason="end_turn", usage=big)
    out = _worker(guard, [[done]], calls).run(5, PROFILES["map-sector"], "brief", _ctx(guard))
    assert out.budget_stopped is False and out.summary_md == "all done"
    assert "stopped early" not in out.summary_md and out.iterations == 1


def test_max_tokens_turn_does_not_run_tools():
    from tests import fakes

    guard, calls, executed = FakeGuard(), [], []

    class CountingRunner(fakes.FakeRunner):
        def generate_tool_call_response(self):
            executed.append(1)
            return super().generate_tool_call_response()

    def factory(**kwargs):
        calls.append(kwargs)
        return CountingRunner(script.pop(0), kwargs.get("max_iterations"))

    script = [
        [
            FakeMessage(
                content=[tool_use_block("kb_search", {"query": "x"})], stop_reason="max_tokens"
            )
        ]
    ]
    llm = LLM(FakeClient(), guard, Decimal("0.92"))
    worker = ResearchWorker(FakeClient(), llm, guard, SYSTEM, runner_factory=factory)
    out = worker.run(5, PROFILES["map-sector"], "brief", _ctx(guard))
    assert executed == [] and out.truncated and out.iterations == 1
