"""The research worker: one tool-runner conversation per task, priced per message, stopped by the budget."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from decimal import Decimal

from scout.budget.pricing import usage_units
from scout.llm.gateway import LLM, message_text
from scout.sources.web import web_tools
from scout.worker.profiles import Profile
from scout.worker.tools import ToolContext, build_tools

PER_ITERATION_EST_EUR: dict[str, Decimal] = {
    "claude-sonnet-5-5": Decimal("0.03"),
    "claude-opus-5-5": Decimal("0.08"),
    "claude-haiku-5-5": Decimal("0.005"),
}
# I1 — cost control. The next request is gated on max(profile estimate, 1.25 x the last request's actual
# cost): with cached history a request costs about the last one plus the new turn. Web search is capped per
# TASK (profile.max_searches): `max_uses` only binds one API request, so each request gets at most
# PER_REQUEST_MAX_SEARCHES (and never more than what is left); once the allowance is used up the model is told
# in every tool result, and the task stops if it searches past it — overrun ≤ one request's max_uses.
STEP_GROWTH = Decimal("1.25")
PER_REQUEST_MAX_SEARCHES = 4
CACHE_CONTROL = {"type": "ephemeral"}  # top-level automatic caching: the growing history is cached


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
    search_capped: bool = False
    web_searches: int = 0


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
        custom_tools = build_tools(ctx)
        messages: list[dict] = [{"role": "user", "content": brief}]
        base_est = PER_ITERATION_EST_EUR.get(profile.model, Decimal("0.03"))
        step_est = base_est
        total = Decimal("0")
        iterations = restarts = searches = 0
        last = None
        truncated = budget_stopped = search_capped = False

        while True:
            remaining_iterations = profile.max_iterations - iterations
            if remaining_iterations <= 0:
                break
            remaining_searches = profile.max_searches - searches
            per_request = max(
                1, min(profile.max_searches, PER_REQUEST_MAX_SEARCHES, remaining_searches)
            )
            runner = self.runner_factory(
                model=profile.model,
                max_tokens=profile.max_tokens,
                system=self.system,
                tools=custom_tools + web_tools(per_request, profile.max_fetches),
                messages=list(messages),
                max_iterations=remaining_iterations,
                output_config={"effort": profile.effort},
                cache_control=CACHE_CONTROL,
            )
            stream = iter(runner)
            # Gate only when a paid request follows: the first of a runner, or after a tool_use turn.
            paid_request_next = True
            while True:
                if paid_request_next and not self.guard.can_afford(step_est):
                    budget_stopped = True
                    break
                try:
                    message = next(stream)
                except StopIteration:
                    break
                iterations += 1
                last = message
                cost = self.llm.record_message(profile.model, message, task_id=task_id)
                total += cost
                step_est = max(base_est, cost * STEP_GROWTH)
                searches += usage_units(message.usage)["web_search_requests"]
                if message.stop_reason == "max_tokens":
                    truncated = True
                # Mirror the history: the runner keeps its own copy and does not expose it.
                messages.append({"role": "assistant", "content": message.content})
                if message.stop_reason != "tool_use":
                    # The SDK runner only runs tools on tool_use turns; end/pause/max_tokens stop or resume.
                    break
                if searches > profile.max_searches:
                    search_capped = True
                    break
                if searches >= profile.max_searches:
                    ctx.search_note = (
                        f"web-search allowance for this task used up ({searches}/{profile.max_searches}): "
                        "do not search again; record what you have and write your final summary now."
                    )
                # Same call the runner makes next; it caches the response, so tools run once.
                tool_response = runner.generate_tool_call_response()
                if tool_response is not None:
                    messages.append(tool_response)
            if budget_stopped or search_capped or last is None or last.stop_reason != "pause_turn":
                break
            if restarts >= self.MAX_RESTARTS:
                break
            if (
                searches >= profile.max_searches
            ):  # paused mid-search: resuming would only search more
                search_capped = True
                break
            restarts += 1  # paused mid-turn: history ends with the paused assistant turn, so resume

        summary = message_text(last) if last is not None else ""
        stop_reason = last.stop_reason if last is not None else "not_started"
        if budget_stopped:
            summary = (
                summary + "\n\n" if summary else ""
            ) + "(stopped early: daily budget exhausted before the summary was written)"
        elif search_capped:
            summary = (
                summary + "\n\n" if summary else ""
            ) + "(stopped early: the web-search allowance for this task was used up)"
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
            search_capped=search_capped,
            web_searches=searches,
        )
