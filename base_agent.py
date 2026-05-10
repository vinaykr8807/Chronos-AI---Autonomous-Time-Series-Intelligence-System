"""
Base ReAct Agent — foundation of all AgentML agents.
Uses OpenAI-compatible client (works with Gemini).
Supports step_callback for real-time UI updates.
"""

from __future__ import annotations

import json
import os
import time
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Callable
import time
from openai import OpenAI
from dotenv import load_dotenv

from core.reasoning_trace import ReasoningTrace, TraceStep, StepType
from core.memory import AgentMemory

load_dotenv()
logger = logging.getLogger(__name__)


class MaxIterationsError(Exception):
    """Raised when the ReAct loop exceeds the configured iteration budget."""


class AgentExecutionError(Exception):
    """Raised when a tool call fails irrecoverably."""


@dataclass
class AgentResult:
    success: bool
    output: dict[str, Any]
    reasoning_trace: ReasoningTrace
    iterations_used: int
    duration_seconds: float
    agent_name: str
    observation_summary: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "success": self.success,
            "output": self.output,
            "agent_name": self.agent_name,
            "iterations_used": self.iterations_used,
            "duration_seconds": round(self.duration_seconds, 2),
            "observation_summary": self.observation_summary,
            "trace": self.reasoning_trace.to_dict(),
        }


class BaseAgent(ABC):
    """
    Abstract base class implementing the ReAct loop.
    step_callback fires after every trace step for live UI updates.
    """

    FINAL_ANSWER_TOOL: dict[str, Any] = {
        "type": "function",
        "function": {
            "name": "final_answer",
            "description": "Call this ONLY when the task is fully complete.",
            "parameters": {
                "type": "object",
                "properties": {
                    "result": {"type": "object"},
                    "observation_summary": {"type": "string"},
                    "confidence": {"type": "number"},
                    "needs_replan": {"type": "boolean"},
                    "replan_reason": {"type": "string"},
                },
                "required": ["result", "observation_summary", "confidence"],
            },
        },
    }

    def __init__(
        self,
        model: str = "gemini-2.5-flash",
        max_iterations: int = 20,
        temperature: float = 0.2,
        step_callback: Callable[[TraceStep], None] | None = None,
    ) -> None:
        self.client = OpenAI(
            api_key=os.environ.get("GEMINI_API_KEY"),
            base_url=os.environ.get("GEMINI_BASE_URL"),
        )
        self.model = model
        self.max_iterations = max_iterations
        self.temperature = temperature
        self.memory = AgentMemory()
        self.step_callback = step_callback

    @abstractmethod
    def get_tool_schemas(self) -> list[dict[str, Any]]: ...

    @abstractmethod
    def execute_tool(self, tool_name: str, tool_input: dict[str, Any]) -> Any: ...

    @abstractmethod
    def get_system_prompt(self) -> str: ...

    @property
    @abstractmethod
    def name(self) -> str: ...

    def run(self, task: str, context: dict[str, Any] | None = None) -> AgentResult:
        start_time = time.time()
        trace = ReasoningTrace(agent_name=self.name, task=task)
        messages: list[dict[str, Any]] = []

        messages.append({"role": "system", "content": self.get_system_prompt()})

        initial_content = task
        if context:
            initial_content = f"{task}\n\n<context>\n{json.dumps(context, indent=2)}\n</context>"
        messages.append({"role": "user", "content": initial_content})

        all_tools = [*self.get_tool_schemas(), self.FINAL_ANSWER_TOOL]

        logger.info("[%s] Starting ReAct loop | task=%r", self.name, task[:120])

        for iteration in range(1, self.max_iterations + 1):
            time.sleep(20)

            for attempt in range(5):  # retry up to 5 times
                try:
                    response = self.client.chat.completions.create(
                        model=self.model,
                        temperature=self.temperature,
                        tools=all_tools,
                        messages=messages,
                    )
                    break  # success — exit retry loop
                except Exception as e:
                    if "429" in str(e):
                        wait = 60 * (attempt + 1)  # 60s, 120s, 180s...
                        logger.warning(
                            "[%s] 429 rate limit — waiting %ds before retry %d/5",
                            self.name, wait, attempt + 1
                        )
                        time.sleep(wait)
                    else:
                        raise  # not a 429 — raise immediately
            else:
                raise Exception("Rate limit: failed after 5 retries")

            message = response.choices[0].message
            finish_reason = response.choices[0].finish_reason

            if message.content:
                step = TraceStep(StepType.THOUGHT, message.content, iteration)
                trace.add_step(step)
                self._fire_callback(step)

            if finish_reason == "stop" and not message.tool_calls:
                duration = time.time() - start_time
                return AgentResult(
                    success=True,
                    output={"text_response": message.content},
                    reasoning_trace=trace,
                    iterations_used=iteration,
                    duration_seconds=duration,
                    agent_name=self.name,
                    observation_summary=(message.content or "")[:500],
                )

            messages.append(message)

            for tool_call in (message.tool_calls or []):
                tool_name = tool_call.function.name
                tool_input = json.loads(tool_call.function.arguments)

                step = TraceStep(
                    StepType.ACTION,
                    f"Calling tool: {tool_name}",
                    iteration,
                    tool_name=tool_name,
                    tool_input=tool_input,
                )
                trace.add_step(step)
                self._fire_callback(step)

                if tool_name == "final_answer":
                    duration = time.time() - start_time
                    final_step = TraceStep(
                        StepType.FINAL,
                        tool_input.get("observation_summary", ""),
                        iteration,
                    )
                    trace.add_step(final_step)
                    self._fire_callback(final_step)
                    logger.info("[%s] Completed in %d iterations (%.1fs)", self.name, iteration, duration)
                    return AgentResult(
                        success=True,
                        output=tool_input.get("result", {}),
                        reasoning_trace=trace,
                        iterations_used=iteration,
                        duration_seconds=duration,
                        agent_name=self.name,
                        observation_summary=tool_input.get("observation_summary", ""),
                    )

                try:
                    time.sleep(20)
                    result = self.execute_tool(tool_name, tool_input)
                    result_content = json.dumps(result, default=str)
                    is_error = False
                except AgentExecutionError as exc:
                    result_content = f"ERROR: {exc}"
                    is_error = True
                    logger.error("[%s] Tool %r failed: %s", self.name, tool_name, exc)
                except Exception as exc:
                    result_content = f"UNEXPECTED ERROR: {exc}"
                    is_error = True
                    logger.exception("[%s] Unexpected error in tool %r", self.name, tool_name)

                obs_step = TraceStep(
                    StepType.OBSERVATION,
                    result_content[:2000],
                    iteration,
                    tool_name=tool_name,
                    is_error=is_error,
                )
                trace.add_step(obs_step)
                self._fire_callback(obs_step)

                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": result_content,
                })

        raise MaxIterationsError(f"{self.name} exceeded max_iterations={self.max_iterations}")

    def _fire_callback(self, step: TraceStep) -> None:
        if self.step_callback:
            try:
                self.step_callback(step)
            except Exception:
                pass