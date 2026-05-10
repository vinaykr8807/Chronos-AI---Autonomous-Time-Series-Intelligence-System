"""
OrchestratorAgent — the reasoning brain of AgentML.

The orchestrator:
1. Receives the user's ML goal and dataset path
2. Uses a ReAct loop to plan, spawn, and direct sub-agents AS TOOLS
3. Re-plans dynamically when a sub-agent reports needs_replan=True
4. Produces a final pipeline plan and result summary

Sub-agents are registered as Claude tools. The LLM decides which agent to
call, when, and with what context — there is no hardcoded sequence.

Example tool flow the LLM might choose:
    call_eda_agent → call_cleaning_agent → call_feature_agent
                   ↘ (if EDA reveals time-series) → call_feature_agent with time_features=True

This is the ONLY place where execution order is determined, and it is
determined by the LLM, not by us.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Callable

from agents.base_agent import BaseAgent, AgentResult, AgentExecutionError
from core.llm_client import LLMClient
from core.reasoning_trace import TraceStep


logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Tool schemas for each sub-agent
# These define the interface the orchestrator's LLM uses to call sub-agents.
# ---------------------------------------------------------------------------

EDA_AGENT_TOOL = {
    "type": "function",
    "function": {
        "name": "call_eda_agent",
        "description": (
            "Run exploratory data analysis on the dataset. "
            "Returns: shape, dtypes, missing value counts, distribution summaries, "
            "correlation matrix highlights, class imbalance stats (for classification), "
            "and a list of anomalies/concerns. "
            "Call this FIRST before any other agent when you have a new dataset."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "dataset_path": {
                    "type": "string",
                    "description": "Absolute or relative path to the dataset file (CSV, Parquet, etc.).",
                },
                "target_column": {
                    "type": "string",
                    "description": "Name of the target/label column.",
                },
                "task_type": {
                    "type": "string",
                    "enum": ["classification", "regression", "clustering", "unknown"],
                    "description": "ML task type. Use 'unknown' if not yet determined.",
                },
                "focus_areas": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": (
                        "Optional specific aspects to focus on, e.g. "
                        "['class_imbalance', 'temporal_patterns', 'high_cardinality_categoricals']"
                    ),
                },
            },
            "required": ["dataset_path", "target_column", "task_type"],
        },
    },
}

CLEANING_AGENT_TOOL = {
    "type": "function",
    "function": {
        "name": "call_cleaning_agent",
        "description": (
            "Clean the dataset based on EDA observations. "
            "The agent reasons about the best cleaning strategy given the data "
            "characteristics — it does NOT apply a fixed set of steps. "
            "Returns: cleaned dataset path, list of transformations applied, and "
            "a summary of what changed."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "dataset_path": {"type": "string"},
                "target_column": {"type": "string"},
                "eda_observations": {
                    "type": "object",
                    "description": "The full output from call_eda_agent.",
                },
                "cleaning_priorities": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": (
                        "Issues to prioritise, e.g. ['missing_values', 'outliers', "
                        "'duplicate_rows', 'inconsistent_categoricals']"
                    ),
                },
            },
            "required": ["dataset_path", "target_column", "eda_observations"],
        },
    },
}

FEATURE_AGENT_TOOL = {
    "type": "function",
    "function": {
        "name": "call_feature_agent",
        "description": (
            "Engineer and select features. The agent reasons about which transformations "
            "add signal based on the data characteristics. May create polynomial features, "
            "target encodings, datetime decompositions, interaction terms, etc. "
            "Returns: transformed dataset path, feature importance scores, and dropped features."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "dataset_path": {"type": "string"},
                "target_column": {"type": "string"},
                "task_type": {"type": "string"},
                "eda_observations": {"type": "object"},
                "engineering_hints": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": (
                        "Hints from EDA, e.g. ['has_datetime_columns', "
                        "'high_cardinality_categoricals', 'potential_interaction_terms']"
                    ),
                },
            },
            "required": ["dataset_path", "target_column", "task_type"],
        },
    },
}

TRAINING_AGENT_TOOL = {
    "type": "function",
    "function": {
        "name": "call_training_agent",
        "description": (
            "Select and train models. The agent reasons about model selection based on "
            "dataset size, feature types, task type, and available compute. "
            "It does NOT train all possible models — it selects the most promising ones. "
            "Returns: model paths, CV scores, training time, and reasoning for model selection."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "dataset_path": {"type": "string"},
                "target_column": {"type": "string"},
                "task_type": {"type": "string"},
                "dataset_stats": {
                    "type": "object",
                    "description": "Key stats: n_rows, n_features, class_balance, etc.",
                },
                "optimization_target": {
                    "type": "string",
                    "description": "Metric to optimise, e.g. 'f1_weighted', 'rmse', 'auc'.",
                },
                "time_budget_minutes": {
                    "type": "number",
                    "description": "Maximum training time in minutes.",
                    "default": 10,
                },
            },
            "required": ["dataset_path", "target_column", "task_type", "optimization_target"],
        },
    },
}

EVALUATION_AGENT_TOOL = {
    "type": "function",
    "function": {
        "name": "call_evaluation_agent",
        "description": (
            "Evaluate trained models on hold-out test data. "
            "Computes metrics, calibration curves, feature importances, and error analysis. "
            "If results are below acceptable thresholds, sets needs_replan=True with recommendations. "
            "Returns: per-model metrics, best model identifier, and evaluation report."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "model_paths": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Paths to trained model artifacts.",
                },
                "test_dataset_path": {"type": "string"},
                "target_column": {"type": "string"},
                "task_type": {"type": "string"},
                "optimization_target": {"type": "string"},
                "minimum_acceptable_score": {
                    "type": "number",
                    "description": "If best score < this, agent will request replan.",
                },
            },
            "required": [
                "model_paths", "test_dataset_path", "target_column",
                "task_type", "optimization_target",
            ],
        },
    },
}

DEPLOYMENT_AGENT_TOOL = {
    "type": "function",
    "function": {
        "name": "call_deployment_agent",
        "description": (
            "Package and deploy the best model as a FastAPI prediction endpoint. "
            "Returns: endpoint URL, health check status, and sample request/response."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "model_path": {"type": "string"},
                "model_name": {"type": "string"},
                "feature_schema": {
                    "type": "object",
                    "description": "Input feature names and types for the prediction API.",
                },
                "task_type": {"type": "string"},
            },
            "required": ["model_path", "model_name", "task_type"],
        },
    },
}

ALL_AGENT_TOOLS = [
    EDA_AGENT_TOOL,
    CLEANING_AGENT_TOOL,
    FEATURE_AGENT_TOOL,
    TRAINING_AGENT_TOOL,
    EVALUATION_AGENT_TOOL,
    DEPLOYMENT_AGENT_TOOL,
]


# ---------------------------------------------------------------------------
# OrchestratorAgent
# ---------------------------------------------------------------------------

class OrchestratorAgent(BaseAgent):
    """
    Top-level orchestrator that manages the full ML pipeline.

    Sub-agents are injected as a registry so the orchestrator can call them
    when the LLM issues a tool_use block. If a sub-agent is not yet implemented,
    a stub result is returned with a clear message.
    """

    def __init__(
        self,
        llm_client: LLMClient,
        sub_agents: dict[str, BaseAgent] | None = None,
        max_iterations: int = 30,
        max_replan_attempts: int = 3,
        # FIX: accept step_callback here and forward it to BaseAgent
        step_callback: Callable[[TraceStep], None] | None = None,
    ) -> None:
        """
        Args:
            llm_client:          Shared LLM client.
            sub_agents:          Map of tool_name → agent instance.
                                 e.g. {"call_eda_agent": EDAAgent(...)}
            max_iterations:      ReAct loop budget.
            max_replan_attempts: How many times the orchestrator may replan
                                 before giving up.
            step_callback:       Optional callback fired after every trace step
                                 for live UI updates.
        """
        # FIX: BaseAgent.__init__ takes (model, max_iterations, temperature, step_callback)
        # There is no 'client' parameter — the client is created inside BaseAgent using env vars.
        super().__init__(
            model="gemini-2.5-flash",  # FIX: use actual Gemini model name
            max_iterations=max_iterations,
            step_callback=step_callback,             # FIX: forward callback to base
        )
        self.llm_client = llm_client
        self.sub_agents: dict[str, BaseAgent] = sub_agents or {}
        self.max_replan_attempts = max_replan_attempts
        self._replan_count = 0

    @property
    def name(self) -> str:
        return "OrchestratorAgent"

    def get_system_prompt(self) -> str:
        return """You are OrchestratorAgent, the reasoning brain of AgentML — an autonomous AutoML system.

Your job is to take a user's ML goal and dataset, reason carefully about what needs to be done, and orchestrate a team of specialised sub-agents to accomplish it.

## Your Core Principles

1. **Reason before acting.** Before calling any agent, think through: what do I know? what do I need to know? what is the most logical next step?

2. **No hardcoded sequences.** You do NOT always call agents in the same order. EDA usually comes first because you need information, but after that, your plan must be driven by observations. If EDA reveals the data is already clean, skip CleaningAgent. If it reveals a time-series structure, tell FeatureAgent to create lag features.

3. **Every decision must be explainable.** When you call an agent, your thought must explain WHY you are calling it with THOSE specific parameters. "I'm calling TrainingAgent with XGBoost and LightGBM because EDA showed 50k rows of tabular data with high-cardinality categoricals — tree-based models handle this well without one-hot encoding overhead."

4. **Self-correct when results are poor.** If EvaluationAgent returns needs_replan=True, reason about WHY the results were poor and modify your approach. Do not just re-run the same pipeline.

5. **Be efficient.** Don't call agents you don't need. If the user just wants a quick baseline, don't over-engineer features.

## How to call sub-agents

Use the provided tools. Each tool call = one sub-agent invocation. Pass relevant context from prior agents in the tool input — agents do not share memory; you are the communication hub.

## Replanning protocol

If any agent returns needs_replan=True:
- Read replan_reason carefully
- Form a new hypothesis about what went wrong
- Modify your plan accordingly (different features, different models, different cleaning strategy)
- You have a limited replan budget — use it wisely

## Final answer format

When you have a trained and evaluated model (or have decided deployment is appropriate), call final_answer with:
- result: summary of the pipeline that was run, best model info, final metrics
- observation_summary: dense summary for the system log
- confidence: your confidence in the result
- needs_replan: false (if you're calling final_answer, the task is done)
"""

    def get_tool_schemas(self) -> list[dict[str, Any]]:
        """Return all sub-agent tool schemas."""
        return ALL_AGENT_TOOLS

    def execute_tool(self, tool_name: str, tool_input: dict[str, Any]) -> Any:
        """
        Dispatch a sub-agent tool call.

        If the sub-agent is registered, run it and return its AgentResult as a dict.
        If not yet implemented, return a stub so development can proceed incrementally.
        """
        agent = self.sub_agents.get(tool_name)

        if agent is None:
            logger.warning(
                "[Orchestrator] Tool '%s' not yet implemented — returning stub",
                tool_name,
            )
            return self._stub_result(tool_name, tool_input)

        # Build task description and context for the sub-agent
        task = self._build_subtask(tool_name, tool_input)
        context = dict(tool_input)

        # Accumulate prior observations so sub-agents can use them
        context["orchestrator_memory"] = self.memory.all()

        result: AgentResult = agent.run(task=task, context=context)

        # Store the agent's observation in orchestrator memory for future agents
        self.memory.set(f"{tool_name}_result", result.output)
        self.memory.append("agent_observations", {
            "agent": result.agent_name,
            "observation_summary": result.observation_summary,
            "success": result.success,
        })

        # Handle replan signal
        if result.output.get("needs_replan") and self._replan_count < self.max_replan_attempts:
            self._replan_count += 1
            logger.warning(
                "[Orchestrator] Replan triggered by %s (attempt %d/%d): %s",
                tool_name,
                self._replan_count,
                self.max_replan_attempts,
                result.output.get("replan_reason", "no reason given"),
            )

        return result.to_dict()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _build_subtask(tool_name: str, tool_input: dict[str, Any]) -> str:
        """Create a natural-language task string for a sub-agent."""
        task_map = {
            "call_eda_agent": (
                "Perform exploratory data analysis on the dataset at '{dataset_path}'. "
                "Target column: '{target_column}'. Task type: {task_type}."
            ),
            "call_cleaning_agent": (
                "Clean the dataset at '{dataset_path}' for column '{target_column}'. "
                "Use the provided EDA observations to decide cleaning steps."
            ),
            "call_feature_agent": (
                "Engineer and select features for the dataset at '{dataset_path}'. "
                "Task: {task_type}, target: '{target_column}'."
            ),
            "call_training_agent": (
                "Select and train models on '{dataset_path}'. "
                "Task: {task_type}, target: '{target_column}', optimise: {optimization_target}."
            ),
            "call_evaluation_agent": (
                "Evaluate trained models on test data at '{test_dataset_path}'. "
                "Target: '{target_column}', task: {task_type}, metric: {optimization_target}."
            ),
            "call_deployment_agent": (
                "Deploy model '{model_name}' from path '{model_path}'."
            ),
        }
        template = task_map.get(tool_name, f"Execute {tool_name}.")
        try:
            return template.format(**{k: tool_input.get(k, f"<{k}>") for k in tool_input})
        except KeyError:
            return template

    @staticmethod
    def _stub_result(tool_name: str, tool_input: dict[str, Any]) -> dict[str, Any]:
        """
        Placeholder result for agents not yet implemented.
        Returns enough structure for the orchestrator to continue reasoning.
        """
        return {
            "success": True,
            "agent_name": tool_name,
            "output": {
                "status": "STUB — agent not yet implemented",
                "tool_input_received": tool_input,
                "result": {},
                "observation_summary": (
                    f"{tool_name} is not yet implemented. "
                    "This is a development stub. Treat this step as completed successfully "
                    "and continue planning, but note that no real work was done."
                ),
                "confidence": 0.0,
                "needs_replan": False,
            },
            "iterations_used": 0,
            "duration_seconds": 0.0,
            "observation_summary": f"{tool_name} stub — not implemented yet.",
            "trace": {"steps": []},
        }