"""The research worker: one tool-runner conversation per task, priced per message, stopped by the budget."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from decimal import Decimal

from scout.llm.gateway import LLM, message_text
from scout.sources.web import web_tools
from scout.worker.profiles import Profile
from scout.worker.tools import ToolContext, build_tools

PER_ITERATION_EST_EUR: dict[str, Decimal] = {
    "claude-sonnet-5-5": Decimal("0.03"),
    "claude-opus-5-5": Decimal("0.08"),
    "claude-haiku-5-5": Decimal("0.005"),
}


@dataclass
class TaskOutcome:
    summary_md: str
    stop_reason: str
    iterations: int
    cost_eur: Decimal
    restarts: int
    tool_calls: int
    truncated: bool
    budget_stopped: bool


class ResearchWorker:
    MAX_RESTARTS = 3

    def __init__(
        self, client, llm: LLM, guard, system: list[dict], runner_factory: Callable | None = None
    ) -> None:
        self.client = client
        self.llm = llm
        self.guard = guard
        self.system = system
        self.runner_factory = runner_factory or (
            lambda **kw: client.beta.messages.tool_runner(**kw)
        )

    def run(
        self, task_id: int | None, profile: Profile, brief: str, ctx: ToolContext
    ) -> TaskOutcome:
        tools = build_tools(ctx) + web_tools(profile.max_searches, profile.max_fetches)
        messages: list[dict] = [{"role": "user", "content": brief}]
        step_est = PER_ITERATION_EST_EUR.get(profile.model, Decimal("0.03"))
        total = Decimal("0")
        iterations = restarts = 0
        last = None
        truncated = budget_stopped = False

        while True:
            remaining_iterations = profile.max_iterations - iterations
            if remaining_iterations <= 0:
                break
            runner = self.runner_factory(
                model=profile.model,
                max_tokens=profile.max_tokens,
                system=self.system,
                tools=tools,
                messages=list(messages),
                max_iterations=remaining_iterations,
                output_config={"effort": profile.effort},
            )
            stream = iter(runner)
            while True:
                if not self.guard.can_afford(step_est):
                    budget_stopped = True
                    break
                try:
                    message = next(stream)
                except StopIteration:
                    break
                iterations += 1
                last = message
                total += self.llm.record_message(profile.model, message, task_id=task_id)
                if message.stop_reason == "max_tokens":
                    truncated = True
                # Mirror the history: the runner keeps its own copy and does not expose it.
                messages.append({"role": "assistant", "content": message.content})
                tool_response = runner.generate_tool_call_response()  # cached; tools still run once
                if tool_response is not None:
                    messages.append(tool_response)
            if budget_stopped or last is None or last.stop_reason != "pause_turn":
                break
            if restarts >= self.MAX_RESTARTS:
                break
            restarts += 1  # paused mid-turn: history ends with the paused assistant turn, so resume

        summary = message_text(last) if last is not None else ""
        stop_reason = last.stop_reason if last is not None else "not_started"
        if budget_stopped:
            summary = (
                summary + "\n\n" if summary else ""
            ) + "(stopped early: daily budget exhausted before the summary was written)"
        elif not summary:
            summary = f"(no summary text; stop_reason={stop_reason})"
        return TaskOutcome(
            summary_md=summary.strip(),
            stop_reason=stop_reason,
            iterations=iterations,
            cost_eur=total,
            restarts=restarts,
            tool_calls=len(ctx.events),
            truncated=truncated,
            budget_stopped=budget_stopped,
        )
