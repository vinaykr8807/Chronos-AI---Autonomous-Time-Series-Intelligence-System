from __future__ import annotations

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
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict[str, Any]:
        return {
            "stepType": self.step_type.value,
            "stage": self.tool_name or self.step_type.value,
            "message": self.content,
            "iteration": self.iteration,
            "toolInput": self.tool_input,
            "isError": self.is_error,
            "timestamp": self.timestamp,
        }


@dataclass
class ReasoningTrace:
    agent_name: str
    task: str
    steps: list[TraceStep] = field(default_factory=list)
    started_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def add(self, step_type: StepType, content: str, iteration: int, tool_name: str | None = None, tool_input: dict[str, Any] | None = None, is_error: bool = False) -> None:
        self.steps.append(TraceStep(step_type, content, iteration, tool_name=tool_name, tool_input=tool_input, is_error=is_error))

    def to_dict(self) -> dict[str, Any]:
        return {
            "agentName": self.agent_name,
            "task": self.task,
            "startedAt": self.started_at,
            "totalSteps": len(self.steps),
            "steps": [step.to_dict() for step in self.steps],
        }


class AgentMemory:
    def __init__(self) -> None:
        self._store: dict[str, Any] = {}

    def set(self, key: str, value: Any) -> None:
        self._store[key] = value

    def get(self, key: str, default: Any = None) -> Any:
        return self._store.get(key, default)

    def update(self, key: str, updates: dict[str, Any]) -> None:
        existing = self._store.get(key, {})
        if not isinstance(existing, dict):
            raise TypeError(f"Memory key `{key}` is not a dict.")
        existing.update(updates)
        self._store[key] = existing

    def append(self, key: str, item: Any) -> None:
        existing = self._store.get(key, [])
        if not isinstance(existing, list):
            raise TypeError(f"Memory key `{key}` is not a list.")
        existing.append(item)
        self._store[key] = existing

    def all(self) -> dict[str, Any]:
        return dict(self._store)

    def clear(self) -> None:
        self._store.clear()
