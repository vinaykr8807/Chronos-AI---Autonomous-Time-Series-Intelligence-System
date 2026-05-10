"""
AgentMemory — lightweight key-value scratchpad for an agent's working state.

Each agent instance gets its own memory. The orchestrator uses memory to
accumulate observations from sub-agents across the planning session.
"""

from __future__ import annotations

from typing import Any


class AgentMemory:
    """
    In-process scratchpad. Not persisted between agent instantiations
    (persistence is handled by MLflow / PostgreSQL at a higher level).

    Usage:
        memory.set("eda_observations", {...})
        memory.get("eda_observations")
        memory.update("dataset_stats", {"rows": 50000})
    """

    def __init__(self) -> None:
        self._store: dict[str, Any] = {}

    def set(self, key: str, value: Any) -> None:
        self._store[key] = value

    def get(self, key: str, default: Any = None) -> Any:
        return self._store.get(key, default)

    def update(self, key: str, updates: dict[str, Any]) -> None:
        """Merge updates into an existing dict value."""
        existing = self._store.get(key, {})
        if not isinstance(existing, dict):
            raise TypeError(f"Memory key '{key}' is not a dict, cannot update.")
        existing.update(updates)
        self._store[key] = existing

    def append(self, key: str, item: Any) -> None:
        """Append to a list stored at key."""
        existing = self._store.get(key, [])
        if not isinstance(existing, list):
            raise TypeError(f"Memory key '{key}' is not a list, cannot append.")
        existing.append(item)
        self._store[key] = existing

    def all(self) -> dict[str, Any]:
        return dict(self._store)

    def clear(self) -> None:
        self._store.clear()

    def __contains__(self, key: str) -> bool:
        return key in self._store

    def __repr__(self) -> str:
        keys = list(self._store.keys())
        return f"AgentMemory(keys={keys})"