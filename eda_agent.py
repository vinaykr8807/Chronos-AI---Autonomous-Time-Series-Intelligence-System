"""
EDAAgent — Exploratory Data Analysis Agent.

Uses a ReAct loop with pandas-powered tools to deeply explore a dataset
and return structured observations the orchestrator can reason about.

Tools available to the LLM:
    load_dataset         → load CSV and return basic shape/dtypes
    compute_statistics   → descriptive stats per column
    check_missing_values → missing counts and percentages
    analyze_target       → target distribution and class balance
    detect_correlations  → top correlated feature pairs
    detect_anomalies     → outliers, constants, duplicates, high cardinality
    save_report          → save full EDA report to local JSON file
"""

from __future__ import annotations

import json
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

# Output directory — all reports saved here
OUTPUT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "outputs")


class EDAAgent(BaseAgent):
    """
    Exploratory Data Analysis Agent.

    Loads a dataset and uses a suite of pandas tools to understand its
    structure, quality, and characteristics. Returns rich observations
    for the orchestrator to use when planning cleaning and feature steps.
    Saves a full EDA report to local disk.
    """

    @property
    def name(self) -> str:
        return "EDAAgent"

    def get_system_prompt(self) -> str:
        return """You are EDAAgent, a expert data scientist specialising in exploratory data analysis.

Your job is to thoroughly understand a dataset by using your tools systematically.

## Your approach

1. ALWAYS start by loading the dataset with load_dataset
2. Then compute_statistics to understand distributions
3. Then check_missing_values to find data quality issues
4. Then analyze_target to understand what you're predicting
5. Then detect_correlations to find relationships
6. Then detect_anomalies to find problems
7. ALWAYS end by calling save_report with ALL findings before final_answer

## What to look for

- Missing values: which columns, how much, what pattern?
- Class imbalance: is the target heavily skewed?
- High cardinality: categorical columns with too many unique values
- Constant columns: columns with only one value (useless)
- Outliers: extreme values that might hurt models
- Correlations: features that are highly correlated with target
- Data types: columns stored as wrong type (e.g. numbers as strings)

## Your final answer must include

- shape: [rows, cols]
- column_types: dict of column → type
- missing_values: dict of column → {count, pct}
- target_distribution: class counts for classification
- top_correlations: list of (feature, correlation_with_target)
- anomalies: list of specific issues found
- recommended_cleaning: concrete steps for CleaningAgent
- engineering_hints: specific feature ideas for FeatureAgent
- is_imbalanced: true/false
- high_cardinality_cols: list of columns with >20 unique values
- report_path: path where the EDA report was saved

Be specific and data-driven. Every recommendation must reference actual numbers from the data.
"""

    def get_tool_schemas(self) -> list[dict[str, Any]]:
        return [
            {
                "type": "function",
                "function": {
                    "name": "load_dataset",
                    "description": (
                        "Load the dataset from disk. Always call this first. "
                        "Returns shape, column names, dtypes, and first 3 rows."
                    ),
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
                    "name": "compute_statistics",
                    "description": (
                        "Compute descriptive statistics for all columns. "
                        "Returns mean, std, min, max, percentiles for numeric cols "
                        "and value counts for categorical cols."
                    ),
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "max_categories": {
                                "type": "integer",
                                "description": "Max unique values to show for categorical columns.",
                                "default": 10,
                            }
                        },
                        "required": [],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "check_missing_values",
                    "description": (
                        "Check for missing values in all columns. "
                        "Returns count and percentage of missing values per column, "
                        "sorted by severity."
                    ),
                    "parameters": {
                        "type": "object",
                        "properties": {},
                        "required": [],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "analyze_target",
                    "description": (
                        "Analyze the target column distribution. "
                        "For classification: class counts and imbalance ratio. "
                        "For regression: distribution stats and skewness."
                    ),
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "target_column": {
                                "type": "string",
                                "description": "Name of the target column.",
                            },
                            "task_type": {
                                "type": "string",
                                "enum": ["classification", "regression", "unknown"],
                            },
                        },
                        "required": ["target_column", "task_type"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "detect_correlations",
                    "description": (
                        "Detect correlations between features and target. "
                        "Returns top correlated feature pairs and "
                        "feature-target correlations sorted by strength."
                    ),
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "target_column": {
                                "type": "string",
                                "description": "Name of the target column.",
                            },
                            "top_n": {
                                "type": "integer",
                                "description": "Number of top correlations to return.",
                                "default": 10,
                            },
                        },
                        "required": ["target_column"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "detect_anomalies",
                    "description": (
                        "Detect data anomalies including: outliers (IQR method), "
                        "constant columns, duplicate rows, high cardinality categoricals, "
                        "and columns with suspicious distributions."
                    ),
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "outlier_threshold": {
                                "type": "number",
                                "description": "IQR multiplier for outlier detection.",
                                "default": 1.5,
                            }
                        },
                        "required": [],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "save_report",
                    "description": (
                        "Save the full EDA report to a local JSON file. "
                        "ALWAYS call this as the LAST tool before final_answer. "
                        "Pass all findings collected from previous tools. "
                        "Returns the path where the report was saved."
                    ),
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "report": {
                                "type": "object",
                                "description": (
                                    "Full EDA report containing all findings: "
                                    "shape, column_types, missing_values, "
                                    "target_distribution, top_correlations, "
                                    "anomalies, recommended_cleaning, "
                                    "engineering_hints, is_imbalanced, "
                                    "high_cardinality_cols."
                                ),
                            },
                            "filename": {
                                "type": "string",
                                "description": "Output filename. Defaults to 'eda_report.json'.",
                                "default": "eda_report.json",
                            },
                        },
                        "required": ["report"],
                    },
                },
            },
        ]

    def execute_tool(self, tool_name: str, tool_input: dict[str, Any]) -> Any:
        """Dispatch tool calls to pandas implementations."""
        dispatch = {
            "load_dataset": self._load_dataset,
            "compute_statistics": self._compute_statistics,
            "check_missing_values": self._check_missing_values,
            "analyze_target": self._analyze_target,
            "detect_correlations": self._detect_correlations,
            "detect_anomalies": self._detect_anomalies,
            "save_report": self._save_report,
        }
        fn = dispatch.get(tool_name)
        if fn is None:
            raise AgentExecutionError(f"Unknown tool: {tool_name}")
        return fn(**tool_input)

    # ------------------------------------------------------------------
    # Tool implementations
    # ------------------------------------------------------------------

    def _load_dataset(self, dataset_path: str) -> dict[str, Any]:
        global _DATASET, _DATASET_PATH
        try:
            df = pd.read_csv(dataset_path)
            _DATASET = df
            _DATASET_PATH = dataset_path
        except FileNotFoundError:
            raise AgentExecutionError(f"Dataset not found: {dataset_path}")
        except Exception as e:
            raise AgentExecutionError(f"Failed to load dataset: {e}")

        dtype_map: dict[str, str] = {}
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
            "sample_rows": df.head(3).to_dict(orient="records"),
            "memory_mb": round(df.memory_usage(deep=True).sum() / 1024 / 1024, 2),
        }

    def _compute_statistics(self, max_categories: int = 10) -> dict[str, Any]:
        df = self._get_df()
        result: dict[str, Any] = {"numeric": {}, "categorical": {}}

        numeric_cols = df.select_dtypes(include=[np.number]).columns
        for col in numeric_cols:
            s = df[col].dropna()
            result["numeric"][col] = {
                "mean": round(float(s.mean()), 4),
                "std": round(float(s.std()), 4),
                "min": round(float(s.min()), 4),
                "25%": round(float(s.quantile(0.25)), 4),
                "50%": round(float(s.quantile(0.50)), 4),
                "75%": round(float(s.quantile(0.75)), 4),
                "max": round(float(s.max()), 4),
                "skewness": round(float(s.skew()), 4),
            }

        cat_cols = df.select_dtypes(exclude=[np.number]).columns
        for col in cat_cols:
            vc = df[col].value_counts()
            result["categorical"][col] = {
                "unique_count": int(df[col].nunique()),
                "top_values": vc.head(max_categories).to_dict(),
            }

        return result

    def _check_missing_values(self) -> dict[str, Any]:
        df = self._get_df()
        total = len(df)
        missing: dict[str, Any] = {}

        for col in df.columns:
            count = int(df[col].isna().sum())
            if count > 0:
                missing[col] = {
                    "count": count,
                    "percentage": round(count / total * 100, 2),
                    "severity": (
                        "high" if count / total > 0.3
                        else "medium" if count / total > 0.05
                        else "low"
                    ),
                }

        missing = dict(
            sorted(missing.items(), key=lambda x: x[1]["count"], reverse=True)
        )

        return {
            "total_rows": total,
            "columns_with_missing": len(missing),
            "missing_by_column": missing,
            "total_missing_cells": sum(v["count"] for v in missing.values()),
        }

    def _analyze_target(self, target_column: str, task_type: str) -> dict[str, Any]:
        df = self._get_df()

        if target_column not in df.columns:
            raise AgentExecutionError(
                f"Target column '{target_column}' not found. "
                f"Available columns: {list(df.columns)}"
            )

        target = df[target_column]
        result: dict[str, Any] = {
            "column": target_column,
            "task_type": task_type,
            "missing_in_target": int(target.isna().sum()),
        }

        if task_type == "classification" or target.nunique() <= 20:
            vc = target.value_counts()
            result["class_counts"] = vc.to_dict()
            result["class_percentages"] = (vc / len(target) * 100).round(2).to_dict()
            result["num_classes"] = int(target.nunique())

            if len(vc) >= 2:
                imbalance_ratio = round(float(vc.iloc[0] / vc.iloc[-1]), 2)
                result["imbalance_ratio"] = imbalance_ratio
                result["is_imbalanced"] = imbalance_ratio > 3.0
            else:
                result["is_imbalanced"] = False
        else:
            result["mean"] = round(float(target.mean()), 4)
            result["std"] = round(float(target.std()), 4)
            result["min"] = round(float(target.min()), 4)
            result["max"] = round(float(target.max()), 4)
            result["skewness"] = round(float(target.skew()), 4)
            result["is_skewed"] = abs(target.skew()) > 1.0

        return result

    def _detect_correlations(self, target_column: str, top_n: int = 10) -> dict[str, Any]:
        df = self._get_df()
        numeric_df = df.select_dtypes(include=[np.number])

        if target_column not in numeric_df.columns:
            return {
                "note": f"Target '{target_column}' is not numeric — correlation skipped.",
                "feature_target_correlations": {},
                "top_feature_pairs": [],
            }

        corr_with_target = (
            numeric_df.corr()[target_column]
            .drop(target_column, errors="ignore")
            .abs()
            .sort_values(ascending=False)
        )

        features = [c for c in numeric_df.columns if c != target_column]
        corr_matrix = numeric_df[features].corr().abs()
        pairs = []
        for i, col_a in enumerate(features):
            for col_b in features[i + 1:]:
                pairs.append({
                    "feature_a": col_a,
                    "feature_b": col_b,
                    "correlation": round(float(corr_matrix.loc[col_a, col_b]), 4),
                })
        pairs = sorted(pairs, key=lambda x: x["correlation"], reverse=True)[:top_n]

        return {
            "feature_target_correlations": {
                col: round(float(val), 4)
                for col, val in corr_with_target.head(top_n).items()
            },
            "top_feature_pairs": pairs,
            "highly_correlated_pairs": [p for p in pairs if p["correlation"] > 0.85],
        }

    def _detect_anomalies(self, outlier_threshold: float = 1.5) -> dict[str, Any]:
        df = self._get_df()
        anomalies: list[str] = []
        details: dict[str, Any] = {}

        n_dupes = int(df.duplicated().sum())
        if n_dupes > 0:
            anomalies.append(f"{n_dupes} duplicate rows found")
            details["duplicate_rows"] = n_dupes

        constant_cols = [col for col in df.columns if df[col].nunique() <= 1]
        if constant_cols:
            anomalies.append(f"Constant columns (zero variance): {constant_cols}")
            details["constant_columns"] = constant_cols

        cat_cols = df.select_dtypes(exclude=[np.number]).columns
        high_card = {
            col: int(df[col].nunique())
            for col in cat_cols
            if df[col].nunique() > 20
        }
        if high_card:
            anomalies.append(
                "High cardinality categoricals: "
                + ", ".join(f"{k}({v})" for k, v in high_card.items())
            )
            details["high_cardinality_columns"] = high_card

        numeric_cols = df.select_dtypes(include=[np.number]).columns
        outlier_cols: dict[str, int] = {}
        for col in numeric_cols:
            s = df[col].dropna()
            q1, q3 = s.quantile(0.25), s.quantile(0.75)
            iqr = q3 - q1
            n_outliers = int(
                ((s < q1 - outlier_threshold * iqr) | (s > q3 + outlier_threshold * iqr)).sum()
            )
            if n_outliers > 0:
                outlier_cols[col] = n_outliers

        if outlier_cols:
            anomalies.append(
                "Outliers detected in: "
                + ", ".join(f"{k}({v} rows)" for k, v in outlier_cols.items())
            )
            details["outlier_columns"] = outlier_cols

        return {
            "anomaly_count": len(anomalies),
            "anomalies": anomalies,
            "details": details,
        }

    def _save_report(
        self,
        report: dict[str, Any],
        filename: str = "eda_report.json",
    ) -> dict[str, Any]:
        """Save the full EDA report to a local JSON file."""
        try:
            # Create outputs directory if it doesn't exist
            os.makedirs(OUTPUT_DIR, exist_ok=True)

            # Add metadata to report
            report["_meta"] = {
                "dataset_path": _DATASET_PATH,
                "dataset_shape": list(_DATASET.shape) if _DATASET is not None else None,
                "agent": self.name,
            }

            output_path = os.path.join(OUTPUT_DIR, filename)

            with open(output_path, "w", encoding="utf-8") as f:
                json.dump(report, f, indent=2, default=str)

            logger.info("[%s] EDA report saved to %s", self.name, output_path)

            return {
                "success": True,
                "report_path": output_path,
                "file_size_kb": round(os.path.getsize(output_path) / 1024, 2),
                "message": f"EDA report saved to {output_path}",
            }

        except Exception as e:
            raise AgentExecutionError(f"Failed to save EDA report: {e}")

    # ------------------------------------------------------------------
    # Helper
    # ------------------------------------------------------------------

    @staticmethod
    def _get_df() -> pd.DataFrame:
        if _DATASET is None:
            raise AgentExecutionError(
                "Dataset not loaded. Call load_dataset first."
            )
        return _DATASET