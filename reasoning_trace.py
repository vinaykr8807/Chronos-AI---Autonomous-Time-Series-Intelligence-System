"""
ReasoningTrace — first-class logging of every Thought/Action/Observation.

This is not an afterthought. The trace is the primary artifact that makes
AgentML explainable. It is persisted to MLflow and returned in every
AgentResult so the UI can render a full decision audit.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any


class StepType(str, Enum):
    THOUGHT = "thought"
    ACTION = "action"
    OBSERVATION = "observation"
    FINAL = "final"


@dataclass
class TraceStep:
    step_type: StepType
    content: str
    iteration: int
    tool_name: str | None = None
    tool_input: dict[str, Any] | None = None
    is_error: bool = False
    timestamp: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def to_dict(self) -> dict[str, Any]:
        return {
            "step_type": self.step_type.value,
            "content": self.content,
            "iteration": self.iteration,
            "tool_name": self.tool_name,
            "tool_input": self.tool_input,
            "is_error": self.is_error,
            "timestamp": self.timestamp,
        }

    def __str__(self) -> str:
        prefix = {
            StepType.THOUGHT: "💭 THOUGHT",
            StepType.ACTION: "⚡ ACTION",
            StepType.OBSERVATION: "👁  OBS",
            StepType.FINAL: "✅ FINAL",
        }[self.step_type]
        suffix = f" [{self.tool_name}]" if self.tool_name else ""
        error_flag = " ⚠️ ERROR" if self.is_error else ""
        return f"[iter={self.iteration}] {prefix}{suffix}{error_flag}\n  {self.content[:300]}"


@dataclass
class ReasoningTrace:
    """
    Ordered sequence of ReAct steps for one agent invocation.

    Designed to be serialised to JSON and stored in MLflow as an artifact,
    so the full decision chain is always recoverable.
    """

    agent_name: str
    task: str
    steps: list[TraceStep] = field(default_factory=list)
    started_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def add_step(self, step: TraceStep) -> None:
        self.steps.append(step)

    def thoughts(self) -> list[TraceStep]:
        return [s for s in self.steps if s.step_type == StepType.THOUGHT]

    def actions(self) -> list[TraceStep]:
        return [s for s in self.steps if s.step_type == StepType.ACTION]

    def observations(self) -> list[TraceStep]:
        return [s for s in self.steps if s.step_type == StepType.OBSERVATION]

    def errors(self) -> list[TraceStep]:
        return [s for s in self.steps if s.is_error]

    def summary(self) -> str:
        """Compact human-readable trace for logs."""
        lines = [f"=== {self.agent_name} Trace | task: {self.task[:80]} ==="]
        for step in self.steps:
            lines.append(str(step))
        return "\n".join(lines)

    def to_dict(self) -> dict[str, Any]:
        return {
            "agent_name": self.agent_name,
            "task": self.task,
            "started_at": self.started_at,
            "total_steps": len(self.steps),
            "steps": [s.to_dict() for s in self.steps],
        }

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent)