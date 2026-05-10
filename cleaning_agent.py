"""
CleaningAgent — Data Cleaning Agent.

Uses a ReAct loop with pandas-powered tools to clean any dataset
based on EDA observations passed from the OrchestratorAgent.

Tools available to the LLM:
    load_dataset          → load CSV into memory
    drop_columns          → drop useless or high-missing columns
    impute_missing        → fill missing values (median/mode/constant)
    remove_outliers       → cap outliers using IQR method
    encode_categoricals   → label encode or one-hot encode categoricals
    save_cleaned_dataset  → save final cleaned CSV to local disk
"""

from __future__ import annotations

import logging
import os
from typing import Any

import numpy as np
import pandas as pd

from agents.base_agent import BaseAgent, AgentExecutionError

logger = logging.getLogger(__name__)

# Global dataset store — persists across tool calls within one agent run
_DATASET: pd.DataFrame | None = None
_DATASET_PATH: str | None = None
_TRANSFORMATIONS: list[str] = []

# Output directory
OUTPUT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "outputs")


class CleaningAgent(BaseAgent):

    @property
    def name(self) -> str:
        return "CleaningAgent"

    def get_system_prompt(self) -> str:
        return """You are CleaningAgent, an expert data scientist specialising in data cleaning.

You receive EDA observations and use them to clean ANY dataset intelligently.
You must NOT hardcode assumptions about specific datasets — all decisions must
come from the EDA observations you receive in context.

## Your approach

1. ALWAYS start by loading the dataset with load_dataset
2. Read the EDA observations carefully to understand what needs cleaning
3. Drop columns based on EDA findings:
   - Columns with >70% missing values → drop
   - ID-like columns (unique count == row count) → drop (no signal)
   - Constant columns (1 unique value) → drop (no signal)
   - High cardinality text columns (names, free text, IDs) → drop
4. Impute missing values based on EDA findings:
   - Numeric columns → impute with median
   - Categorical columns with <5% missing → impute with mode
   - Categorical columns with 5-70% missing → impute with constant "Unknown"
5. Cap outliers in numeric columns using IQR method
6. Encode categorical columns:
   - Binary (2 unique values) → label_encode
   - Low cardinality (3-10 unique) → onehot_encode
7. ALWAYS end by calling save_cleaned_dataset

## Rules that apply to ANY dataset

- NEVER drop the target column
- NEVER impute the target column
- missing > 70% → drop
- unique count == row count → ID column → drop
- unique count == 1 → constant → drop
"""

    def get_tool_schemas(self) -> list[dict[str, Any]]:
        return [
            {
                "type": "function",
                "function": {
                    "name": "load_dataset",
                    "description": "Load the dataset from disk. Always call this first.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "dataset_path": {
                                "type": "string",
                                "description": "Path to the CSV file.",
                            }
                        },
                        "required": ["dataset_path"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "drop_columns",
                    "description": (
                        "Drop one or more columns. Use for: "
                        "high-missing (>70%), ID columns, constant columns, "
                        "high cardinality text columns."
                    ),
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "columns": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": "Column names to drop.",
                            },
                            "reason": {
                                "type": "string",
                                "description": "Why these columns are being dropped.",
                            },
                        },
                        "required": ["columns", "reason"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "impute_missing",
                    "description": (
                        "Fill missing values. "
                        "median: for numeric columns. "
                        "mode: for categorical with few missing. "
                        "constant: for categorical with many missing."
                    ),
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "columns": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": "Column names to impute.",
                            },
                            "strategy": {
                                "type": "string",
                                "enum": ["median", "mode", "constant"],
                            },
                            "fill_value": {
                                "type": "string",
                                "description": "Value for constant strategy. Default 'Unknown'.",
                                "default": "Unknown",
                            },
                        },
                        "required": ["columns", "strategy"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "remove_outliers",
                    "description": (
                        "Cap outliers in numeric columns using IQR method. "
                        "Preserves all rows — values are capped not removed."
                    ),
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "columns": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": "Numeric column names to cap.",
                            },
                            "threshold": {
                                "type": "number",
                                "description": "IQR multiplier. Default 1.5.",
                                "default": 1.5,
                            },
                        },
                        "required": ["columns"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "encode_categoricals",
                    "description": (
                        "Encode categorical columns as numbers. "
                        "label_encode: for binary columns (2 unique values). "
                        "onehot_encode: for low cardinality (3-10 unique values)."
                    ),
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "columns": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": "Categorical column names to encode.",
                            },
                            "strategy": {
                                "type": "string",
                                "enum": ["label_encode", "onehot_encode"],
                            },
                        },
                        "required": ["columns", "strategy"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "save_cleaned_dataset",
                    "description": (
                        "Save the cleaned dataset to a local CSV file. "
                        "ALWAYS call this as the last tool before final_answer."
                    ),
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "filename": {
                                "type": "string",
                                "description": "Output filename. Default 'cleaned_dataset.csv'.",
                                "default": "cleaned_dataset.csv",
                            },
                        },
                        "required": [],
                    },
                },
            },
        ]

    def execute_tool(self, tool_name: str, tool_input: dict[str, Any]) -> Any:
        dispatch = {
            "load_dataset": self._load_dataset,
            "drop_columns": self._drop_columns,
            "impute_missing": self._impute_missing,
            "remove_outliers": self._remove_outliers,
            "encode_categoricals": self._encode_categoricals,
            "save_cleaned_dataset": self._save_cleaned_dataset,
        }
        fn = dispatch.get(tool_name)
        if fn is None:
            raise AgentExecutionError(f"Unknown tool: {tool_name}")
        return fn(**tool_input)

    # ------------------------------------------------------------------
    # Tool implementations
    # ------------------------------------------------------------------

    def _load_dataset(self, dataset_path: str) -> dict[str, Any]:
        global _DATASET, _DATASET_PATH, _TRANSFORMATIONS
        try:
            df = pd.read_csv(dataset_path)
            _DATASET = df.copy()
            _DATASET_PATH = dataset_path
            _TRANSFORMATIONS = []
        except FileNotFoundError:
            raise AgentExecutionError(f"Dataset not found: {dataset_path}")
        except Exception as e:
            raise AgentExecutionError(f"Failed to load dataset: {e}")

        missing_summary = {
            col: f"{round(df[col].isna().mean() * 100, 1)}%"
            for col in df.columns
            if df[col].isna().any()
        }

        dtype_map = {}
        for col in df.columns:
            if pd.api.types.is_numeric_dtype(df[col]):
                dtype_map[col] = "numeric"
            elif pd.api.types.is_datetime64_any_dtype(df[col]):
                dtype_map[col] = "datetime"
            else:
                dtype_map[col] = "categorical"

        return {
            "shape": list(df.shape),
            "columns": list(df.columns),
            "dtypes": dtype_map,
            "missing_summary": missing_summary,
            "unique_counts": {col: int(df[col].nunique()) for col in df.columns},
        }

    def _drop_columns(self, columns: list[str], reason: str) -> dict[str, Any]:
        existing = [c for c in columns if c in _DATASET.columns]
        not_found = [c for c in columns if c not in _DATASET.columns]

        if existing:
            _DATASET.drop(columns=existing, inplace=True)
            msg = f"Dropped {existing}: {reason}"
            _TRANSFORMATIONS.append(msg)
            logger.info("[%s] %s", self.name, msg)

        return {
            "dropped": existing,
            "not_found": not_found,
            "remaining_columns": list(_DATASET.columns),
            "new_shape": list(_DATASET.shape),
        }

    def _impute_missing(
        self,
        columns: list[str],
        strategy: str,
        fill_value: str = "Unknown",
    ) -> dict[str, Any]:
        results = {}

        for col in columns:
            if col not in _DATASET.columns:
                results[col] = "not found"
                continue

            before = int(_DATASET[col].isna().sum())
            if before == 0:
                results[col] = "no missing values"
                continue

            if strategy == "median":
                if pd.api.types.is_numeric_dtype(_DATASET[col]):
                    fill = _DATASET[col].median()
                    _DATASET[col] = _DATASET[col].fillna(fill)
                    msg = f"Imputed {col} with median={round(float(fill), 4)} ({before} values)"
                else:
                    results[col] = "cannot use median on non-numeric"
                    continue
            elif strategy == "mode":
                fill = _DATASET[col].mode()[0]
                _DATASET[col] = _DATASET[col].fillna(fill)
                msg = f"Imputed {col} with mode='{fill}' ({before} values)"
            elif strategy == "constant":
                _DATASET[col] = _DATASET[col].fillna(fill_value)
                msg = f"Imputed {col} with '{fill_value}' ({before} values)"
            else:
                results[col] = f"unknown strategy: {strategy}"
                continue

            _TRANSFORMATIONS.append(msg)
            results[col] = f"filled {before} missing values"

        return {"strategy": strategy, "results": results}

    def _remove_outliers(
        self,
        columns: list[str],
        threshold: float = 1.5,
    ) -> dict[str, Any]:
        results = {}

        for col in columns:
            if col not in _DATASET.columns:
                results[col] = "not found"
                continue
            if not pd.api.types.is_numeric_dtype(_DATASET[col]):
                results[col] = "not numeric — skipped"
                continue

            q1 = _DATASET[col].quantile(0.25)
            q3 = _DATASET[col].quantile(0.75)
            iqr = q3 - q1
            lower = q1 - threshold * iqr
            upper = q3 + threshold * iqr

            n_low = int((_DATASET[col] < lower).sum())
            n_high = int((_DATASET[col] > upper).sum())

            _DATASET[col] = _DATASET[col].clip(lower=lower, upper=upper)

            msg = f"Capped {col}: {n_low} low → {round(lower,4)}, {n_high} high → {round(upper,4)}"
            _TRANSFORMATIONS.append(msg)
            results[col] = {"capped_low": n_low, "capped_high": n_high}

        return {"threshold": threshold, "results": results}

    def _encode_categoricals(
        self,
        columns: list[str],
        strategy: str,
    ) -> dict[str, Any]:
        results = {}
        new_columns: list[str] = []

        for col in columns:
            if col not in _DATASET.columns:
                results[col] = "not found"
                continue

            if strategy == "label_encode":
                unique_vals = sorted(_DATASET[col].dropna().unique())
                mapping = {v: i for i, v in enumerate(unique_vals)}
                _DATASET[col] = _DATASET[col].map(mapping)
                msg = f"Label encoded {col}: {mapping}"
                _TRANSFORMATIONS.append(msg)
                results[col] = {"mapping": mapping}

            elif strategy == "onehot_encode":
                dummies = pd.get_dummies(_DATASET[col], prefix=col, drop_first=False)
                new_cols = list(dummies.columns)
                _DATASET.drop(columns=[col], inplace=True)
                for new_col in new_cols:
                    _DATASET[new_col] = dummies[new_col].values
                new_columns.extend(new_cols)
                msg = f"One-hot encoded {col} → {new_cols}"
                _TRANSFORMATIONS.append(msg)
                results[col] = {"new_columns": new_cols}

        return {
            "strategy": strategy,
            "results": results,
            "new_columns": new_columns,
            "current_shape": list(_DATASET.shape),
        }

    def _save_cleaned_dataset(self, filename: str = "cleaned_dataset.csv") -> dict[str, Any]:
        if _DATASET is None:
            raise AgentExecutionError("No dataset loaded.")

        try:
            os.makedirs(OUTPUT_DIR, exist_ok=True)
            output_path = os.path.join(OUTPUT_DIR, filename)
            _DATASET.to_csv(output_path, index=False)
            logger.info("[%s] Cleaned dataset saved to %s", self.name, output_path)

            return {
                "success": True,
                "output_path": output_path,
                "final_shape": list(_DATASET.shape),
                "columns": list(_DATASET.columns),
                "file_size_kb": round(os.path.getsize(output_path) / 1024, 2),
                "transformations_applied": _TRANSFORMATIONS,
                "total_transformations": len(_TRANSFORMATIONS),
            }
        except Exception as e:
            raise AgentExecutionError(f"Failed to save: {e}")

    # ------------------------------------------------------------------
    # Helper
    # ------------------------------------------------------------------

    @staticmethod
    def _get_df() -> pd.DataFrame:
        if _DATASET is None:
            raise AgentExecutionError("Dataset not loaded. Call load_dataset first.")
        return _DATASET