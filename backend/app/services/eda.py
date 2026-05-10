from __future__ import annotations

import io
import hashlib
import re
from collections import Counter
from concurrent.futures import ThreadPoolExecutor

import numpy as np
import pandas as pd
from fastapi import UploadFile

from app.core.schemas import ColumnProfile, DatasetProfile
from app.services.catalog import get_dataset


def _profile_column_batch(service: "AutoEDAService", df: pd.DataFrame, columns: list[str]) -> list[ColumnProfile]:
    return [service._profile_column(df, column) for column in columns]


class AutoEDAService:
    def __init__(self, workers: int | None = None, batch_size: int = 8) -> None:
        self.workers = max(1, workers or 4)
        self.batch_size = max(1, batch_size)

    def profile_catalog_dataset(self, dataset_id: str) -> DatasetProfile:
        dataset = get_dataset(dataset_id)
        df = self._catalog_sample_frame(dataset.id, dataset.rowCount)
        columns = [
            ColumnProfile(name="timestamp", type="datetime", missingPercent=0, description="Time index for sequential observations", topValues=[]),
            ColumnProfile(name="target_value", type="numeric", missingPercent=dataset.missingPercent, description="Primary value used for forecasting", uniqueValues=1200, min=100.0, max=90000.0, mean=45000.0, median=44720.0, std=8320.0, variance=69222400.0, outlierPercent=1.6, topValues=[]),
            ColumnProfile(name="temperature", type="numeric", missingPercent=1.2, description="External numeric regressor", uniqueValues=400, min=-10.0, max=48.0, mean=23.4, median=22.9, std=8.7, variance=75.69, outlierPercent=0.4, topValues=[]),
            ColumnProfile(name="segment", type="categorical", missingPercent=0, description="Business or sensor segment", uniqueValues=5, topValues=["residential", "commercial", "industrial"]),
        ]
        time_series = {
            "valid": True,
            "timeColumn": "timestamp",
            "frequency": "hourly",
            "gapRatio": 0.01,
            "orderingScore": 0.99,
            "consistencyScore": 0.97,
            "seasonalityHint": "daily and weekly",
        }
        return DatasetProfile(
            dataset_id=dataset.id,
            title=dataset.title,
            summary={
                "rows": dataset.rowCount,
                "columns": dataset.columnCount,
                "missingPercent": dataset.missingPercent,
                "timeSeriesValidated": dataset.isTimeSeriesValidated,
                "timeRangeStart": dataset.timeRange["start"],
                "timeRangeEnd": dataset.timeRange["end"],
            },
            columns=columns,
            time_series=time_series,
            validation={
                "timestampPresence": True,
                "sequentialOrdering": True,
                "frequencyConsistency": 0.97,
                "duplicateTimestampRatio": 0.0,
                "missingIntervalRatio": 0.01,
                "recommendedTarget": "target_value",
            },
            numerical_analysis={
                "target_value": {"trendStrength": 0.71, "seasonalityStrength": 0.83, "outlierPercent": 1.6},
                "temperature": {"trendStrength": 0.22, "seasonalityStrength": 0.58, "outlierPercent": 0.4},
            },
            categorical_analysis={
                "segment": {"uniqueValues": 5, "topValues": ["residential", "commercial", "industrial"], "dominantShare": 0.45},
            },
            structural_intelligence=self._structural_intelligence(df, columns, time_series),
            forecastability=self._forecastability(df, time_series, "target_value"),
            temporal_behavior=self._temporal_behavior(df, time_series, "target_value"),
            quality_intelligence=self._quality_intelligence(df, time_series, "target_value"),
            feature_intelligence=self._feature_intelligence(df, "target_value"),
            strategy_recommendation=self._strategy_recommendation(self._forecastability(df, time_series, "target_value"), time_series, len(df)),
            semantic_understanding=self._semantic_understanding(dataset.title, columns, time_series, "target_value"),
            chart_data=self._chart_data(df, time_series, "target_value"),
            visualizations=[
                {"type": "time_series", "title": "Target Value Behavior Timeline", "reason": "Expose trend shifts, seasonal cycles, and anomaly windows"},
                {"type": "seasonality", "title": "Periodicity Strength View", "reason": "Explain recurring daily or weekly demand signatures"},
                {"type": "anomaly", "title": "Spike and Regime Change Overlay", "reason": "Highlight behavior that may reduce forecast reliability"},
                {"type": "correlation", "title": "Predictive Signal Map", "reason": "Separate useful exogenous signals from redundant features"},
            ],
            insights="",
            decisions=[],
            agent_notes=[
                {"agent": "Dataset Agent", "note": "Catalog metadata mapped to a valid forecasting candidate."},
                {"agent": "EDA Agent", "note": "Behavioral intelligence detected seasonality, forecastability, and model strategy signals."},
            ],
        )

    async def profile_upload(self, file: UploadFile) -> DatasetProfile:
        content = await file.read()
        df = pd.read_csv(io.BytesIO(content))
        return self.profile_dataframe(file.filename or "uploaded-dataset", df)

    def _infer_title(self, dataset_id: str) -> str:
        slug = dataset_id
        for sep in ["/", "--", "__"]:
            if sep in slug:
                slug = slug.split(sep, 1)[1]
                break
        slug = re.sub(r"-v\d+$", "", slug)
        slug = re.sub(r"-\d{5,}$", "", slug)
        slug = re.sub(r"-(dataset|data)$", "", slug)
        return slug.replace("-", " ").replace("_", " ").title().strip()

    def profile_dataframe(self, dataset_id: str, df: pd.DataFrame) -> DatasetProfile:
        columns = self._profile_columns_parallel(df)
        time_info = self._detect_time_series(df)
        target = self._recommended_target(df)
        forecastability = self._forecastability(df, time_info, target)
        validation = self._validation_summary(df, time_info)
        numerical_analysis = self._numerical_analysis(df)
        categorical_analysis = self._categorical_analysis(df)
        structural_intelligence = self._structural_intelligence(df, columns, time_info)
        temporal_behavior = self._temporal_behavior(df, time_info, target)
        quality_intelligence = self._quality_intelligence(df, time_info, target)
        feature_intelligence = self._feature_intelligence(df, target)
        strategy_recommendation = self._strategy_recommendation(forecastability, time_info, len(df))
        semantic_understanding = self._semantic_understanding(dataset_id, columns, time_info, target)
        chart_sample_points = min(500, len(df))
        title = self._infer_title(dataset_id)
        eda_trace = self._eda_trace(
            df=df,
            columns=columns,
            time_info=time_info,
            target=target,
            validation=validation,
            forecastability=forecastability,
            temporal_behavior=temporal_behavior,
            quality_intelligence=quality_intelligence,
            feature_intelligence=feature_intelligence,
            strategy_recommendation=strategy_recommendation,
        )
        return DatasetProfile(
            dataset_id=dataset_id,
            title=title,
            summary={
                "rows": int(len(df)),
                "columns": int(len(df.columns)),
                "rowsScanned": int(len(df)),
                "columnsScanned": int(len(df.columns)),
                "targetColumn": target,
                "missingPercent": round(float(df.isna().sum().sum() / max(df.size, 1) * 100), 2),
                "timeSeriesValidated": bool(time_info["valid"]),
                "timeRangeStart": str(time_info.get("start") or "unknown"),
                "timeRangeEnd": str(time_info.get("end") or "unknown"),
                "edaMode": "full-dataframe",
                "edaExecution": "parallel-batched",
                "batchSize": int(self.batch_size),
                "workerCount": int(self.workers),
                "chartMode": "sampled-evenly",
                "chartSamplePoints": int(chart_sample_points),
                "chartSourceRows": int(len(df)),
            },
            columns=columns,
            time_series=time_info,
            validation=validation,
            numerical_analysis=numerical_analysis,
            categorical_analysis=categorical_analysis,
            structural_intelligence=structural_intelligence,
            forecastability=forecastability,
            temporal_behavior=temporal_behavior,
            quality_intelligence=quality_intelligence,
            feature_intelligence=feature_intelligence,
            strategy_recommendation=strategy_recommendation,
            semantic_understanding=semantic_understanding,
            chart_data=self._chart_data(df, time_info, target),
            visualizations=self._visualization_plan(df, time_info),
            eda_trace=eda_trace,
            evidence_refs={},
            insights="",
            decisions=[],
            agent_notes=[
                {"agent": "Dataset Agent", "note": "Dataset loaded and profiled successfully."},
                {"agent": "EDA Agent", "note": "Generated structural, temporal, forecastability, feature, and strategy intelligence."},
            ],
        )

    def _profile_columns_parallel(self, df: pd.DataFrame) -> list[ColumnProfile]:
        column_names = list(df.columns)
        if len(column_names) <= self.batch_size or self.workers == 1:
            return [self._profile_column(df, column) for column in column_names]

        batches = [column_names[index:index + self.batch_size] for index in range(0, len(column_names), self.batch_size)]
        profiles: list[ColumnProfile] = []
        max_workers = min(self.workers, len(batches))
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = [executor.submit(_profile_column_batch, self, df, batch) for batch in batches]
            for future in futures:
                profiles.extend(future.result())
        return profiles

    def _eda_trace(
        self,
        df: pd.DataFrame,
        columns: list[ColumnProfile],
        time_info: dict[str, object],
        target: str | None,
        validation: dict[str, object],
        forecastability: dict[str, object],
        temporal_behavior: dict[str, object],
        quality_intelligence: dict[str, object],
        feature_intelligence: dict[str, object],
        strategy_recommendation: dict[str, object],
    ) -> list[dict[str, object]]:
        numeric_count = sum(1 for column in columns if column.type == "numeric")
        categorical_count = sum(1 for column in columns if column.type == "categorical")
        datetime_count = sum(1 for column in columns if column.type == "datetime")
        text_count = sum(1 for column in columns if column.type == "text")
        target_profile = next((column for column in columns if column.name == target), None)
        top_missing = sorted(columns, key=lambda column: column.missingPercent, reverse=True)[:5]
        high_cardinality = [
            column.name for column in columns
            if (column.uniqueValues or 0) > min(500, max(50, int(len(df) * 0.5)))
        ][:8]
        return [
            {
                "stage": "load_dataset",
                "status": "complete",
                "rowsScanned": int(len(df)),
                "columnsScanned": int(len(df.columns)),
                "memoryBytes": int(df.memory_usage(deep=True).sum()),
            },
            {
                "stage": "profile_columns",
                "status": "complete",
                "execution": "parallel-batched" if len(columns) > self.batch_size and self.workers > 1 else "single-batch",
                "workerCount": int(self.workers),
                "batchSize": int(self.batch_size),
                "typeCounts": {
                    "numeric": numeric_count,
                    "categorical": categorical_count,
                    "datetime": datetime_count,
                    "text": text_count,
                },
                "highMissingColumns": [
                    {"name": column.name, "missingPercent": column.missingPercent}
                    for column in top_missing
                    if column.missingPercent > 0
                ],
                "highCardinalityColumns": high_cardinality,
            },
            {
                "stage": "detect_time_axis",
                "status": "complete",
                "valid": bool(time_info.get("valid")),
                "timeColumn": time_info.get("timeColumn"),
                "frequency": time_info.get("frequency"),
                "consistencyScore": time_info.get("consistencyScore"),
                "orderingScore": time_info.get("orderingScore"),
                "decision": "Use temporal validation and walk-forward modeling." if time_info.get("valid") else "Treat as cross-sectional; do not use temporal forecast assumptions.",
            },
            {
                "stage": "select_target",
                "status": "complete",
                "targetColumn": target,
                "targetType": target_profile.type if target_profile else None,
                "uniqueValues": target_profile.uniqueValues if target_profile else None,
                "missingPercent": target_profile.missingPercent if target_profile else None,
                "reason": "Target selected from numeric business-outcome names after excluding IDs, ranks, date parts, decomposition components, and interval bounds.",
            },
            {
                "stage": "validate_quality",
                "status": "complete",
                "validation": validation,
                "qualityIntelligence": quality_intelligence,
            },
            {
                "stage": "analyze_relationships",
                "status": "complete",
                "topPredictiveSignals": (feature_intelligence.get("predictiveSignals") or [])[:8],
                "redundantFeatures": (feature_intelligence.get("redundantFeatures") or [])[:5],
                "leakageWarnings": feature_intelligence.get("leakageWarnings") or [],
            },
            {
                "stage": "analyze_behavior",
                "status": "complete",
                "forecastability": forecastability,
                "temporalBehavior": temporal_behavior,
            },
            {
                "stage": "select_model_strategy",
                "status": "complete",
                "strategy": strategy_recommendation,
                "decision": "Model strategy selected from deterministic EDA metrics before LLM explanation.",
            },
        ]

    def _profile_column(self, df: pd.DataFrame, column: str) -> ColumnProfile:
        series = df[column]
        missing = round(float(series.isna().mean() * 100), 2)
        n_unique = int(series.nunique(dropna=True))
        n_total = max(len(series.dropna()), 1)

        if pd.api.types.is_datetime64_any_dtype(series) or self._looks_datetime(series):
            kind = "datetime"
            description = "Detected timestamp or date-like feature"
        elif pd.api.types.is_numeric_dtype(series):
            kind = "numeric"
            description = "Numeric feature with statistical profile"
        elif n_unique > min(500, max(50, n_total * 0.5)):
            # High cardinality relative to dataset size — treat as text
            kind = "text"
            description = "High-cardinality textual or identifier feature"
        else:
            kind = "categorical"
            description = "Categorical feature with frequency profile"
        numeric = pd.to_numeric(series, errors="coerce") if kind == "numeric" else None
        return ColumnProfile(
            name=column,
            type=kind,
            missingPercent=missing,
            description=description,
            uniqueValues=n_unique,
            min=float(np.nanmin(numeric)) if numeric is not None and numeric.notna().any() else None,
            max=float(np.nanmax(numeric)) if numeric is not None and numeric.notna().any() else None,
            mean=float(np.nanmean(numeric)) if numeric is not None and numeric.notna().any() else None,
            median=float(np.nanmedian(numeric)) if numeric is not None and numeric.notna().any() else None,
            std=float(np.nanstd(numeric)) if numeric is not None and numeric.notna().any() else None,
            variance=float(np.nanvar(numeric)) if numeric is not None and numeric.notna().any() else None,
            outlierPercent=self._outlier_percent(numeric) if numeric is not None and numeric.notna().any() else None,
            wordCountMean=self._word_count_mean(series) if kind == "text" else None,
            topValues=self._top_values(series),
        )

    # Demographic / non-temporal numeric column names that must never be treated as a time index
    _NON_TIME_NUMERIC = frozenset([
        "age", "year_of_birth", "birth_year", "yob", "grade", "class", "level",
        "score", "rating", "rank", "user_id", "customer_id",
        "row", "row_id", "row id", "seq", "num", "number", "count", "quantity", "amount",
        "id", "order_id", "order id", "customer_id", "customer id", "product_id", "product id",
        "postal_code", "postal code", "zip", "zipcode", "code",
        "year",  # standalone 'year' column is a grouping variable, not a time index
    ])

    def _detect_time_series(self, df: pd.DataFrame) -> dict[str, str | bool | float | None]:
        datetime_candidates: list[tuple[float, str, pd.Series, pd.Series]] = []
        for column in df.columns:
            col_lower = column.lower().strip()
            # Skip columns whose names are clearly demographic / non-temporal
            if self._is_non_temporal_identifier(col_lower):
                continue
            # Numeric columns are dangerous to parse as datetimes because integer IDs
            # can be interpreted as tiny epoch offsets. Only parse them when the name
            # strongly says this is a date/time field.
            if pd.api.types.is_numeric_dtype(df[column]):
                if not self._has_temporal_name(col_lower):
                    continue
                series = pd.to_numeric(df[column], errors="coerce").dropna()
                n_unique = series.nunique()
                val_range = float(series.max() - series.min()) if len(series) else 0
                # A real time index has many unique values; skip if it looks like a small-range integer
                if n_unique < 50 and val_range < 200:
                    continue
            parsed = self._parse_datetime_series(df[column])
            if parsed.notna().mean() > 0.8:
                parsed_clean = parsed.dropna()
                ordered_unique = parsed_clean.drop_duplicates().sort_values()
                gaps = ordered_unique.diff().dropna()
                if len(gaps) == 0:
                    continue
                # Reject if the modal gap is zero or negative (not a real time progression)
                modal_gap = gaps.mode().iloc[0] if not gaps.mode().empty else pd.Timedelta(0)
                if modal_gap <= pd.Timedelta(0):
                    continue
                # Reject if the total time span is less than 2 days (likely a small integer parsed as date)
                total_span = ordered_unique.max() - ordered_unique.min()
                if total_span < pd.Timedelta(days=2):
                    continue
                score = self._time_column_name_score(col_lower)
                datetime_candidates.append((score, column, parsed_clean, ordered_unique))

        if datetime_candidates:
            _, column, parsed_clean, ordered_unique = max(
                datetime_candidates,
                key=lambda item: (item[0], item[3].nunique(), item[2].notna().mean()),
            )
            gaps = ordered_unique.diff().dropna()
            modal_gap = gaps.mode().iloc[0] if not gaps.mode().empty else pd.Timedelta(days=1)
            consistency = float((gaps == modal_gap).mean()) if len(gaps) else 1.0
            non_decreasing = parsed_clean.diff().dropna() >= pd.Timedelta(0)
            ordering = float(non_decreasing.mean()) if len(non_decreasing) else 1.0
            duplicate_ratio = float(1 - (ordered_unique.nunique() / max(len(parsed_clean), 1)))
            frequency = str(modal_gap)
            return {
                "valid": True,
                "timeColumn": column,
                "frequency": frequency,
                "gapRatio": round(float((gaps != modal_gap).mean()) if len(gaps) else 0.0, 3),
                "orderingScore": round(ordering, 3),
                "consistencyScore": round(consistency, 3),
                "seasonalityHint": "daily-like" if "days" in frequency.lower() else "sub-daily",
                "start": ordered_unique.min().isoformat() if len(ordered_unique) else None,
                "end": ordered_unique.max().isoformat() if len(ordered_unique) else None,
                "duplicateTimestampRatio": round(duplicate_ratio, 4),
            }

        # Second pass: detect implicit integer sequence index (e.g. 0,1,2,...,N)
        # This handles datasets like hourly energy demand with no explicit timestamp
        for column in df.columns:
            col_lower = column.lower().strip()
            if self._is_non_temporal_identifier(col_lower):
                continue
            if not pd.api.types.is_numeric_dtype(df[column]):
                continue
            series = pd.to_numeric(df[column], errors="coerce").dropna()
            if len(series) < 100:
                continue
            # Must be integer-like, monotonically increasing, nearly unique, starting near 0 or 1
            is_integer_like = (series == series.round()).all()
            is_monotonic = series.is_monotonic_increasing
            uniqueness = series.nunique() / len(series)
            starts_near_zero = float(series.min()) <= 10
            step = float(series.diff().dropna().mode().iloc[0]) if len(series) > 1 else 1.0
            is_unit_step = abs(step - 1.0) < 0.01
            if is_integer_like and is_monotonic and uniqueness > 0.95 and starts_near_zero and is_unit_step:
                # Treat as an implicit sequential time index
                n = len(series)
                return {
                    "valid": True,
                    "timeColumn": column,
                    "frequency": "1 step (integer sequence)",
                    "gapRatio": 0.0,
                    "orderingScore": 1.0,
                    "consistencyScore": 1.0,
                    "seasonalityHint": "unknown — integer index only",
                    "start": str(int(series.min())),
                    "end": str(int(series.max())),
                    "implicitIndex": True,
                }

        return {"valid": False, "timeColumn": None, "frequency": "unknown", "gapRatio": None, "orderingScore": 0.0, "consistencyScore": 0.0, "seasonalityHint": "undetermined"}

    def _has_temporal_name(self, name: str) -> bool:
        normalized = name.replace("_", " ")
        return any(token in normalized for token in ["date", "time", "timestamp", "period", "datetime", "month", "year"])

    def _time_column_name_score(self, name: str) -> float:
        normalized = name.replace("_", " ")
        score = 0.0
        if "order date" in normalized or "transaction date" in normalized:
            score += 5.0
        if "date" in normalized:
            score += 4.0
        if "timestamp" in normalized or "datetime" in normalized:
            score += 4.0
        if "time" in normalized:
            score += 3.0
        if "month" in normalized or "year" in normalized:
            score += 3.0
        if "ship date" in normalized or "delivery date" in normalized:
            score += 1.0
        if any(marker in normalized for marker in ["id", "code", "zip", "postal", "row"]):
            score -= 5.0
        return score

    def _is_non_temporal_identifier(self, name: str) -> bool:
        normalized = name.replace("_", " ").strip()
        return (
            normalized in self._NON_TIME_NUMERIC
            or normalized.endswith(" id")
            or normalized.endswith(" code")
            or normalized in {"id", "row id", "postal code", "zip code", "zipcode"}
        )

    def _looks_datetime(self, series: pd.Series) -> bool:
        if pd.api.types.is_numeric_dtype(series):
            return False
        if not self._is_date_like_text(series):
            return False
        parsed = self._parse_datetime_series(series)
        return bool(parsed.notna().mean() > 0.8)

    def _is_date_like_text(self, series: pd.Series) -> bool:
        sample = series.dropna()
        if sample.empty:
            return False
        sample_text = sample.astype(str).head(25)
        date_like = 0
        for value in sample_text:
            text = value.strip()
            if len(text) < 6:
                continue
            if re.search(r"\d{4}[-/]\d{1,2}[-/]\d{1,2}", text) or re.search(r"\d{1,2}[-/]\d{1,2}[-/]\d{2,4}", text):
                date_like += 1
                continue
            if ":" in text and any(ch.isdigit() for ch in text):
                date_like += 1
        return date_like / max(len(sample_text), 1) >= 0.6

    def _parse_datetime_series(self, series: pd.Series) -> pd.Series:
        parsed = pd.to_datetime(series, errors="coerce", format="mixed")
        if parsed.notna().mean() > 0.8:
            return parsed

        text = series.dropna().astype(str).str.strip()
        if text.empty:
            return parsed

        for fmt in ("%y-%b", "%Y-%b", "%b-%y", "%b-%Y", "%m-%Y", "%Y-%m"):
            formatted = pd.to_datetime(series.astype(str).str.strip(), errors="coerce", format=fmt)
            if formatted.notna().mean() > 0.8:
                return formatted

        return parsed

    def _outlier_percent(self, numeric: pd.Series) -> float:
        clean = numeric.dropna()
        if clean.empty:
            return 0.0
        q1 = clean.quantile(0.25)
        q3 = clean.quantile(0.75)
        iqr = q3 - q1
        if iqr == 0:
            return 0.0
        outliers = ((clean < q1 - 1.5 * iqr) | (clean > q3 + 1.5 * iqr)).mean() * 100
        return round(float(outliers), 2)

    def _word_count_mean(self, series: pd.Series) -> float:
        text_series = series.dropna().astype(str)
        if text_series.empty:
            return 0.0
        return round(float(text_series.str.split().str.len().mean()), 2)

    def _top_values(self, series: pd.Series) -> list[str]:
        values = [str(value) for value in series.dropna().astype(str).value_counts().head(3).index.tolist()]
        return values

    def _validation_summary(self, df: pd.DataFrame, time_info: dict[str, str | bool | float | None]) -> dict[str, str | bool | float | int | None]:
        time_column = time_info.get("timeColumn")
        duplicate_ratio = 0.0
        if isinstance(time_column, str) and time_column in df.columns:
            parsed = pd.to_datetime(df[time_column], errors="coerce", format="mixed").dropna()
            duplicate_ratio = float(parsed.duplicated().mean()) if len(parsed) else 0.0
        return {
            "timestampPresence": bool(time_info.get("valid")),
            "sequentialOrdering": bool((time_info.get("orderingScore") or 0) > 0.8),
            "frequencyConsistency": float(time_info.get("consistencyScore") or 0.0),
            "duplicateTimestampRatio": round(duplicate_ratio, 4),
            "missingIntervalRatio": float(time_info.get("gapRatio") or 0.0) if time_info.get("gapRatio") is not None else None,
            "recommendedTarget": self._recommended_target(df),
        }

    # Columns that are demographic/metadata and should never be the forecast target
    _NON_TARGET_COLS = frozenset([
        "age", "year", "year_of_birth", "birth_year", "yob", "id", "user_id",
        "customer_id", "index", "row", "row_id", "seq", "num", "number", "day", "month",
        "hour", "minute", "second", "week", "quarter", "grade", "class",
        "rank", "rank_in_year", "order", "position", "zip", "postal", "code",
        "postal_code", "zipcode", "country_code",
        "lower_whisker", "upper_whisker",  # confidence interval bounds, not targets
    ])

    _TARGET_EXCLUDE_MARKERS = frozenset([
        "explained", "whisker", "residual", "dystopia", "rank", "id", "code",
        "index", "row", "postal", "zip", "year",
    ])

    _TARGET_PREFERRED_PHRASES = (
        "energy consumption",
        "hourly demand",
        "energy demand",
        "power demand",
        "electricity demand",
        "sales",
        "revenue",
        "price",
        "target value",
        "target",
    )

    _TARGET_LOW_PRIORITY_MARKERS = (
        "indicator",
        "status",
        "flag",
        "category",
        "class",
        "participation",
        "outage",
        "reduction",
    )

    _TARGET_UNIT_HINTS = ("kwh", "mwh", "mw", "kw", "watt", "$", "price", "revenue", "sales")

    _TARGET_COMPONENT_MARKERS = (
        "historical",
        "room-level",
        "room level",
        "zonal",
        "lighting",
        "hvac",
        "local",
        "savings",
        "potential",
        "target %",
        "carbon",
        "emission",
        "reactive",
        "smart plug",
        "water",
        "temperature",
        "humidity",
        "occupancy",
        "price",
    )

    def _recommended_target(self, df: pd.DataFrame) -> str | None:
        numeric_columns = [col for col in df.columns if pd.api.types.is_numeric_dtype(df[col])]
        if not numeric_columns:
            return None
        # High-priority exact target hints (score 3.0)
        high_priority_hints = [
            "happiness_score", "happiness", "wellbeing", "life_satisfaction",
            "demand", "consumption", "load", "energy", "price", "value", "target",
            "sales", "revenue", "output", "production", "total", "rate", "generation",
            "usage", "kwh", "mwh", "mw", "kw", "watt", "emission", "traffic",
            "score", "hours", "minutes", "session", "mental", "addiction", "screen", "sleep",
            "gdp", "expectancy", "life", "freedom", "generosity", "support",
            "measure", "metric", "flow", "volume", "count",
        ]
        # Columns to always skip as target
        id_hints = ["id", "code", "key", "seq", "row"]
        scored: list[tuple[str, float]] = []
        for col in numeric_columns:
            col_lower = col.lower().replace("_", " ").replace("(", " ").replace(")", " ")
            col_tokens = col_lower.split()
            if self._is_excluded_target_name(col_lower, col_tokens):
                continue
            # Skip known non-target demographic/metadata columns
            if col.lower() in self._NON_TARGET_COLS or col_lower.strip() in self._NON_TARGET_COLS:
                continue
            if any(t in self._NON_TARGET_COLS for t in col_tokens):
                continue
            series = pd.to_numeric(df[col], errors="coerce").dropna()
            if series.empty:
                continue
            unique_count = int(series.nunique(dropna=True))
            unique_ratio = unique_count / max(len(series), 1)
            # Skip likely ID columns
            is_id = (
                any(hint in col_tokens for hint in id_hints)
                or (series.is_monotonic_increasing and series.nunique() == len(series) and series.dtype in ["int64", "int32"])
            )
            if is_id:
                continue
            score = 0.0
            if any(phrase in col_lower for phrase in self._TARGET_PREFERRED_PHRASES):
                score += 8.0
            if any(unit in col_lower for unit in self._TARGET_UNIT_HINTS):
                score += 3.0
            if col_lower.strip() in {"happiness score", "happiness_score", "score", "sales", "price", "demand", "hourly demand", "target", "energy consumption"}:
                score += 6.0
            # Check for exact column name match first (highest priority)
            if col.lower() in {h.replace(" ", "_") for h in high_priority_hints}:
                score += 3.0
            else:
                for hint in high_priority_hints:
                    if hint.replace("_", " ") in col_lower:
                        score += 2.0
                        break
            if unique_count <= 2:
                score -= 7.0
            elif unique_count <= 10 and any(marker in col_lower for marker in self._TARGET_LOW_PRIORITY_MARKERS):
                score -= 5.0
            elif unique_ratio < 0.01 and any(marker in col_lower for marker in self._TARGET_LOW_PRIORITY_MARKERS):
                score -= 3.0
            if any(marker in col_lower for marker in self._TARGET_LOW_PRIORITY_MARKERS):
                score -= 2.0
            if any(marker in col_lower for marker in self._TARGET_COMPONENT_MARKERS):
                score -= 4.0
            if col_lower.strip() in {"energy consumption kwh", "energy consumption"}:
                score += 6.0
            mean_val = abs(float(series.mean()))
            if mean_val > 0:
                cv = float(series.std(ddof=0)) / mean_val
                score += min(cv, 1.0)  # reduced weight vs before
            score += min(unique_ratio, 1.0)
            scored.append((col, score))
        if not scored:
            for col in numeric_columns:
                col_lower = col.lower().replace("_", " ").strip()
                if col_lower not in self._NON_TARGET_COLS and not self._is_excluded_target_name(col_lower, col_lower.split()):
                    return col
            return numeric_columns[0]
        return max(scored, key=lambda x: x[1])[0]

    def _is_excluded_target_name(self, col_lower: str, col_tokens: list[str]) -> bool:
        normalized = col_lower.strip()
        if normalized in {"happiness score", "sales", "price", "hourly demand", "demand", "target"}:
            return False
        return any(marker in normalized for marker in self._TARGET_EXCLUDE_MARKERS) or any(token in self._NON_TARGET_COLS for token in col_tokens)

    def _numerical_analysis(self, df: pd.DataFrame) -> dict[str, dict[str, float | int | str]]:
        analysis: dict[str, dict[str, float | int | str]] = {}
        for column in df.columns:
            if pd.api.types.is_numeric_dtype(df[column]):
                series = pd.to_numeric(df[column], errors="coerce").dropna()
                if series.empty:
                    continue
                trend = float(np.corrcoef(np.arange(len(series)), series)[0, 1]) if len(series) > 2 else 0.0
                seasonality = self._seasonality_strength(series)
                analysis[column] = {
                    "mean": round(float(series.mean()), 3),
                    "median": round(float(series.median()), 3),
                    "std": round(float(series.std(ddof=0)), 3),
                    "variance": round(float(series.var(ddof=0)), 3),
                    "min": round(float(series.min()), 3),
                    "max": round(float(series.max()), 3),
                    "skewness": round(float(series.skew()), 3),
                    "kurtosis": round(float(series.kurtosis()), 3),
                    "outlierPercent": self._outlier_percent(series),
                    "trendStrength": round(abs(trend), 3) if not np.isnan(trend) else 0.0,
                    "seasonalityStrength": round(seasonality, 3),
                }
        return analysis

    def _categorical_analysis(self, df: pd.DataFrame) -> dict[str, dict[str, float | int | str | list[str]]]:
        analysis: dict[str, dict[str, float | int | str | list[str]]] = {}
        for column in df.columns:
            if pd.api.types.is_numeric_dtype(df[column]) or self._looks_datetime(df[column]):
                continue
            series = df[column].dropna().astype(str)
            if series.empty:
                continue
            counts = Counter(series)
            top = counts.most_common(5)
            analysis[column] = {
                "uniqueValues": int(series.nunique()),
                "topValues": [value for value, _ in top],
                "dominantShare": round(top[0][1] / max(len(series), 1), 3),
                "wordCountMean": self._word_count_mean(series),
            }
        return analysis

    def _visualization_plan(self, df: pd.DataFrame, time_info: dict[str, str | bool | float | None]) -> list[dict[str, str]]:
        plans = []
        if time_info.get("valid"):
            plans.append({"type": "time_series", "title": "Behavior Timeline", "reason": "Explain trend shifts, spikes, forecast windows, and continuity"})
            plans.append({"type": "seasonality", "title": "Seasonality Strength", "reason": "Show the dominant repeating cycle behind the target behavior"})
            plans.append({"type": "anomaly", "title": "Anomaly Concentration", "reason": "Locate unusual periods that may affect forecasting reliability"})
        if any(pd.api.types.is_numeric_dtype(df[column]) for column in df.columns):
            plans.append({"type": "distribution", "title": "Target Distribution Risk", "reason": "Expose skew, heavy tails, and unstable ranges"})
            plans.append({"type": "correlation", "title": "Predictive Signal Map", "reason": "Guide feature selection, leakage checks, and model choice"})
        return plans

    def _chart_data(self, df: pd.DataFrame, time_info: dict[str, object], target: str | None) -> dict[str, list[dict[str, object]]]:
        if not target or target not in df.columns:
            return {"timeSeries": [], "distribution": [], "correlation": []}
        return {
            "timeSeries": self._time_series_points(df, time_info, target),
            "distribution": self._distribution_bins(df, target),
            "correlation": self._correlation_points(df, target),
        }

    def _catalog_sample_frame(self, dataset_id: str, rows: int) -> pd.DataFrame:
        sample_rows = min(max(int(rows or 2400), 600), 5000)
        rng = np.random.default_rng(self._stable_seed(dataset_id))
        timestamps = pd.date_range("2021-01-01", periods=sample_rows, freq="h")
        index = np.arange(sample_rows)
        trend = index * 0.42
        daily = np.sin(index / 24 * 2 * np.pi) * 1200
        weekly = np.sin(index / 168 * 2 * np.pi) * 2100
        temperature = 24 + np.sin(index / 24 * 2 * np.pi) * 8 + rng.normal(0, 1.4, sample_rows)
        target = 43000 + trend + daily + weekly + temperature * 105 + rng.normal(0, 310, sample_rows)
        return pd.DataFrame(
            {
                "timestamp": timestamps,
                "target_value": target,
                "temperature": temperature,
                "segment": rng.choice(["residential", "commercial", "industrial"], sample_rows),
            }
        )

    def _stable_seed(self, value: str) -> int:
        digest = hashlib.sha256(value.encode("utf-8")).digest()
        return int.from_bytes(digest[:4], "little")

    def _time_series_points(self, df: pd.DataFrame, time_info: dict[str, object], target: str) -> list[dict[str, object]]:
        time_column = time_info.get("timeColumn")
        target_series = pd.to_numeric(df[target], errors="coerce")
        if isinstance(time_column, str) and time_column in df.columns:
            points = pd.DataFrame(
                {
                    "timestamp": pd.to_datetime(df[time_column], errors="coerce", format="mixed"),
                    "value": target_series,
                }
            ).dropna().sort_values("timestamp")
            if points["timestamp"].duplicated().any():
                points = points.groupby("timestamp", as_index=False)["value"].sum()
        else:
            points = pd.DataFrame(
                {
                    "timestamp": pd.RangeIndex(start=0, stop=len(df), step=1).astype(str),
                    "value": target_series,
                }
            ).dropna()
        # Evenly sample up to 500 points across the full time range
        max_points = 500
        if len(points) > max_points:
            step = max(1, len(points) // max_points)
            sampled = points.iloc[::step].head(max_points)
        else:
            sampled = points
        return [
            {
                "timestamp": item["timestamp"].isoformat() if hasattr(item["timestamp"], "isoformat") else str(item["timestamp"]),
                "value": round(float(item["value"]), 3),
            }
            for item in sampled.to_dict(orient="records")
        ]

    def _target_series_for_time_analysis(self, df: pd.DataFrame, time_info: dict[str, object], target: str) -> pd.Series:
        target_series = pd.to_numeric(df[target], errors="coerce")
        time_column = time_info.get("timeColumn")
        if isinstance(time_column, str) and time_column in df.columns and not bool(time_info.get("implicitIndex")):
            points = pd.DataFrame(
                {
                    "timestamp": pd.to_datetime(df[time_column], errors="coerce", format="mixed"),
                    "value": target_series,
                }
            ).dropna().sort_values("timestamp")
            if points.empty:
                return target_series.dropna()
            return points.groupby("timestamp")["value"].sum().reset_index(drop=True)
        return target_series.dropna()

    def _distribution_bins(self, df: pd.DataFrame, target: str) -> list[dict[str, object]]:
        series = pd.to_numeric(df[target], errors="coerce").dropna()
        if series.empty:
            return []
        bin_count = min(12, max(6, int(np.sqrt(len(series)) // 2)))
        counts, edges = np.histogram(series, bins=bin_count)

        # Pick decimal precision based on the value range
        val_range = float(edges[-1] - edges[0])
        if val_range == 0:
            decimals = 2
        elif val_range >= 10_000:
            # Use K suffix
            def fmt(v: float) -> str:
                return f"{v / 1000:.1f}K"
        elif val_range >= 100:
            decimals = 0
            def fmt(v: float) -> str:  # type: ignore[misc]
                return f"{v:.0f}"
        elif val_range >= 1:
            decimals = 1
            def fmt(v: float) -> str:  # type: ignore[misc]
                return f"{v:.1f}"
        else:
            # Small decimals (0.0–1.0 range)
            sig = max(2, -int(np.floor(np.log10(val_range))) + 1)
            def fmt(v: float, _s=sig) -> str:  # type: ignore[misc]
                return f"{v:.{_s}f}"

        bins: list[dict[str, object]] = []
        for idx, count in enumerate(counts):
            left = float(edges[idx])
            right = float(edges[idx + 1])
            bins.append({"range": f"{fmt(left)}-{fmt(right)}", "frequency": int(count)})
        return bins

    def _correlation_points(self, df: pd.DataFrame, target: str) -> list[dict[str, object]]:
        numeric = df.select_dtypes(include=["number"]).copy()
        if target not in numeric.columns:
            numeric[target] = pd.to_numeric(df[target], errors="coerce")
        numeric = numeric.dropna(axis=1, how="all")
        if numeric.shape[1] < 2:
            return []
        corr_matrix = numeric.corr(numeric_only=True)
        # Pick up to 7 features: top 4 by |corr with target| + up to 3 others with diverse correlations
        target_corr = corr_matrix[target].abs().drop(labels=[target], errors="ignore").sort_values(ascending=False)
        top_by_target = target_corr.head(4).index.tolist()
        # Add features that have low correlation with already-selected ones (diversity)
        remaining = [c for c in target_corr.index if c not in top_by_target]
        diverse = []
        for col in remaining:
            if len(diverse) >= 3:
                break
            max_corr_with_selected = max(
                abs(float(corr_matrix.loc[col, sel])) for sel in top_by_target + diverse
            ) if top_by_target + diverse else 0.0
            if max_corr_with_selected < 0.85:
                diverse.append(col)
        features = [target] + top_by_target + diverse
        features = list(dict.fromkeys(features))[:8]  # deduplicate, cap at 8
        sub = corr_matrix.loc[features, features]
        points: list[dict[str, object]] = []
        for i, f1 in enumerate(features):
            for f2 in features[i + 1:]:
                val = float(sub.loc[f1, f2])
                if not (val != val):  # skip NaN
                    points.append({"feature1": f1, "feature2": f2, "correlation": round(val, 3)})
                    points.append({"feature1": f2, "feature2": f1, "correlation": round(val, 3)})
        return points

    # Column names that are panel/grouping variables (not targets, not time indices)
    _PANEL_GROUP_COLS = frozenset([
        "year", "month", "quarter", "week", "day", "hour",
        "country", "region", "state", "city", "district",
        "rank", "rank_in_year", "position",
    ])

    def _structural_intelligence(self, df: pd.DataFrame, columns: list[ColumnProfile], time_info: dict[str, object]) -> dict[str, object]:
        roles = {}
        target = self._recommended_target(df)
        time_column = time_info.get("timeColumn")
        has_time = bool(time_info.get("valid"))
        for column in columns:
            col_lower = column.name.lower()
            if column.name == time_column:
                role = "temporal_index"
            elif column.name == target:
                role = "forecast_target" if has_time else "prediction_target"
            elif col_lower in self._PANEL_GROUP_COLS or column.type == "categorical":
                role = "entity_or_grouping"
            elif column.type == "numeric":
                role = "external_regressor" if has_time else "numeric_feature"
            else:
                role = "context_feature"
            roles[column.name] = {"role": role, "type": column.type, "reason": self._role_reason(role)}
        return {
            "columnRoles": roles,
            "entityColumns": [name for name, item in roles.items() if item["role"] == "entity_or_grouping"],
            "targetColumn": target,
            "timeColumn": time_column,
            "temporalHierarchy": self._temporal_hierarchy(str(time_info.get("frequency") or "")) if has_time else [],
            "relationshipSummary": self._relationship_summary(roles, has_time),
            "datasetType": "time-series" if has_time else "cross-sectional",
        }

    def _forecastability(self, df: pd.DataFrame, time_info: dict[str, object], target: str | None) -> dict[str, object]:
        if not target or target not in df.columns:
            return {"score": 0, "grade": "not forecastable", "reasons": ["No numeric target column was detected."], "risks": ["Model training cannot proceed without a target."]}
        series = self._target_series_for_time_analysis(df, time_info, target)
        if len(series) < 24:
            return {"score": 25, "grade": "weak", "reasons": ["Too few observations for reliable temporal learning."], "risks": ["Forecast validation would be unstable."]}

        has_time = bool(time_info.get("valid"))

        # For cross-sectional datasets, forecastability measures predictability, not temporal structure
        if not has_time:
            stationarity = self._stationarity_score(series)
            noise_ratio = self._noise_ratio(series)
            numeric_cols = df.select_dtypes(include=["number"]).columns.tolist()
            n_features = max(len(numeric_cols) - 1, 0)
            rows = len(df)
            # Score based on: data volume, feature richness, signal-to-noise
            volume_score = min(rows / 10000, 1.0) * 30
            feature_score = min(n_features / 5, 1.0) * 30
            signal_score = max(0.0, 1 - noise_ratio) * 40
            score = volume_score + feature_score + signal_score
            return {
                "score": round(float(min(max(score, 0), 100)), 1),
                "grade": self._score_grade(score),
                "seasonalityStrength": 0.0,
                "trendConsistency": 0.0,
                "stationarityScore": round(stationarity, 3),
                "noiseRatio": round(noise_ratio, 3),
                "intervalStability": 0.0,
                "reasons": [
                    f"Dataset has {rows:,} rows and {n_features} numeric feature(s) available for prediction.",
                    "No time index detected — this is a cross-sectional dataset suited for regression/classification.",
                    f"Signal-to-noise ratio is {'good' if noise_ratio < 0.5 else 'moderate'} (noise ratio: {noise_ratio:.2f}).",
                ],
                "risks": [
                    "Without a time index, temporal forecasting is not applicable.",
                    "Use cross-validation instead of walk-forward splits.",
                ] if not has_time else ["No major forecastability blockers detected."],
            }

        trend_strength = self._trend_strength(series)
        seasonality = self._seasonality_strength(series)
        stationarity = self._stationarity_score(series)
        noise_ratio = self._noise_ratio(series)
        interval_score = float(time_info.get("consistencyScore") or 0.0)
        score = (
            trend_strength * 20
            + seasonality * 25
            + stationarity * 15
            + max(0.0, 1 - noise_ratio) * 20
            + interval_score * 20
        )
        reasons = [
            f"Seasonality strength is {seasonality:.2f}, indicating {'clear recurring behavior' if seasonality > 0.45 else 'limited repeating structure'}.",
            f"Trend consistency is {trend_strength:.2f}, showing {'directional movement' if trend_strength > 0.35 else 'mostly flat or irregular movement'}.",
            f"Noise ratio is {noise_ratio:.2f}, so signal quality is {'usable' if noise_ratio < 0.55 else 'noisy'} for forecasting.",
        ]
        risks = []
        if interval_score < 0.7:
            risks.append("Temporal intervals are inconsistent; resampling is recommended before modeling.")
        if noise_ratio > 0.65:
            risks.append("High randomness may reduce forecast confidence.")
        if stationarity < 0.35:
            risks.append("Non-stationary behavior may require differencing or trend-aware models.")
        return {
            "score": round(float(min(max(score, 0), 100)), 1),
            "grade": self._score_grade(score),
            "seasonalityStrength": round(seasonality, 3),
            "trendConsistency": round(trend_strength, 3),
            "stationarityScore": round(stationarity, 3),
            "noiseRatio": round(noise_ratio, 3),
            "intervalStability": round(interval_score, 3),
            "reasons": reasons,
            "risks": risks or ["No major forecastability blockers detected."],
        }

    def _temporal_behavior(self, df: pd.DataFrame, time_info: dict[str, object], target: str | None) -> dict[str, object]:
        if not target or target not in df.columns:
            return {"anomalies": [], "regimeChanges": [], "periodicity": "undetermined", "driftScore": 0.0}
        clean = self._target_series_for_time_analysis(df, time_info, target)
        has_time = bool(time_info.get("valid"))

        # Cross-sectional: report distribution shape instead of temporal behavior
        if not has_time:
            q1 = float(clean.quantile(0.25))
            q3 = float(clean.quantile(0.75))
            iqr = q3 - q1
            outlier_count = int(((clean < q1 - 1.5 * iqr) | (clean > q3 + 1.5 * iqr)).sum())
            skew = float(clean.skew())
            return {
                "periodicity": "not applicable — cross-sectional dataset",
                "anomalies": [],
                "anomalyRate": round(outlier_count / max(len(clean), 1), 4),
                "outlierCount": outlier_count,
                "regimeChanges": [],
                "driftScore": 0.0,
                "skewness": round(skew, 3),
                "distributionShape": "right-skewed" if skew > 0.5 else "left-skewed" if skew < -0.5 else "approximately normal",
                "interpretation": f"Cross-sectional dataset. Target `{target}` has {outlier_count:,} outliers ({round(outlier_count/max(len(clean),1)*100,1)}% of rows). Distribution is {'right-skewed' if skew > 0.5 else 'left-skewed' if skew < -0.5 else 'approximately normal'}.",
            }

        anomalies = self._anomaly_windows(df, time_info, target)
        rolling_mean = clean.rolling(max(12, min(48, len(clean) // 8))).mean().dropna()
        regime_changes = []
        if len(rolling_mean) > 10:
            diffs = rolling_mean.diff().abs().dropna()
            threshold = diffs.mean() + 2.5 * diffs.std(ddof=0)
            regime_changes = [int(index) for index in diffs[diffs > threshold].index[:5]]
        early = clean.iloc[: max(1, len(clean) // 3)]
        late = clean.iloc[-max(1, len(clean) // 3):]
        drift = abs(float(late.mean() - early.mean())) / max(float(clean.std(ddof=0)), 1.0)
        return {
            "periodicity": self._dominant_period(clean),
            "anomalies": anomalies,
            "anomalyRate": round(len(anomalies) / max(len(clean), 1), 4),
            "regimeChanges": regime_changes,
            "driftScore": round(min(drift / 3, 1.0), 3),
            "interpretation": "Behavior is stable enough for forecasting." if drift < 1.2 else "Distribution shift detected; retraining checks should be enabled.",
        }

    def _quality_intelligence(self, df: pd.DataFrame, time_info: dict[str, object], target: str | None) -> dict[str, object]:
        missing_total = float(df.isna().sum().sum() / max(df.size, 1))
        has_time = bool(time_info.get("valid"))
        missing_context = "No missing values detected — dataset is complete."
        if missing_total > 0:
            # Identify which columns are missing and whether it's structural (e.g. panel data)
            col_missing = {col: round(float(df[col].isna().mean() * 100), 1) for col in df.columns if df[col].isna().any()}
            high_missing_cols = [c for c, m in col_missing.items() if m > 30]
            if high_missing_cols and len(high_missing_cols) >= len(col_missing) * 0.5:
                missing_context = f"Structural missingness: {len(high_missing_cols)} column(s) have >30% missing values ({', '.join(high_missing_cols[:3])}{'...' if len(high_missing_cols) > 3 else ''}). This is common in panel datasets where not all records have all fields."
            elif target and target in df.columns:
                target_series = pd.to_numeric(df[target], errors="coerce")
                high_value_mask = target_series > target_series.quantile(0.75)
                if high_value_mask.any():
                    high_missing = float(df.loc[high_value_mask].isna().mean().mean())
                    normal_missing = float(df.loc[~high_value_mask].isna().mean().mean()) if (~high_value_mask).any() else 0.0
                    if high_missing > normal_missing * 1.5 and high_missing > 0.01:
                        missing_context = "Missing values are concentrated during high-value periods, which may harm peak prediction."
                    else:
                        missing_context = f"Missingness is broadly distributed across {len(col_missing)} column(s)."
                else:
                    missing_context = f"Missingness detected in {len(col_missing)} column(s)."
            else:
                missing_context = f"Missingness detected in {len(col_missing)} column(s)."
        # Trust score: use a gentler penalty for structural/panel missingness
        # Cap the missing penalty so structural datasets aren't unfairly penalised
        missing_penalty = min(missing_total * 120, 65)  # max 65 point penalty for missing
        interval_penalty = (1 - float(time_info.get("consistencyScore") or 0.0)) * 35 if has_time else 0.0
        trust = round(max(0.0, 100 - missing_penalty - interval_penalty), 1)
        dup_risk = "low" if float(time_info.get("gapRatio") or 0.0) < 0.05 else "medium"
        if has_time:
            recommendations = [
                "Use interpolation or forward-fill only after sorting by time.",
                "Validate performance with temporal holdout, not random split.",
                "Review high-cardinality identifiers before using them as predictors.",
            ]
        else:
            recommendations = [
                "Encode categorical features before training (label or one-hot encoding).",
                "Use stratified k-fold cross-validation for unbiased evaluation.",
                "Check for class imbalance in the target variable.",
                "Review high-cardinality columns — consider target encoding or dropping.",
            ]
        return {
            "trustScore": trust,
            "missingPattern": missing_context,
            "leakageRisk": self._leakage_risk(df, target),
            "duplicateRisk": dup_risk,
            "recommendations": recommendations,
        }

    def _feature_intelligence(self, df: pd.DataFrame, target: str | None) -> dict[str, object]:
        if not target or target not in df.columns:
            return {"predictiveSignals": [], "redundantFeatures": [], "leakageWarnings": []}
        target_series = pd.to_numeric(df[target], errors="coerce")
        signals = []

        # Numeric features: Pearson correlation + lag correlation
        numeric_columns = [
            c for c in df.columns
            if c != target
            and pd.api.types.is_numeric_dtype(df[c])
            and not self._is_excluded_feature_name(c)
        ]
        for column in numeric_columns:
            feature = pd.to_numeric(df[column], errors="coerce")
            same_time = self._safe_corr(feature, target_series)
            lagged = self._safe_corr(feature.shift(1), target_series)
            strength = max(abs(same_time), abs(lagged))
            signals.append({
                "feature": column,
                "sameTimeCorrelation": round(abs(same_time), 3),
                "lagInfluence": round(abs(lagged), 3),
                "associationMethod": "pearson",
                "role": "strong_driver" if strength > 0.45 else "weak_or_contextual",
            })

        # Categorical features: eta-squared (ANOVA-based association with numeric target)
        cat_columns = [
            c for c in df.columns
            if c != target
            and not pd.api.types.is_numeric_dtype(df[c])
            and not pd.api.types.is_datetime64_any_dtype(df[c])
            and not self._is_excluded_feature_name(c)
        ]
        target_clean = target_series.dropna()
        for column in cat_columns:
            try:
                groups = df.loc[target_clean.index, column].astype(str)
                grand_mean = float(target_clean.mean())
                ss_between = sum(
                    len(grp) * (float(grp.mean()) - grand_mean) ** 2
                    for _, grp in target_clean.groupby(groups)
                    if len(grp) > 0
                )
                ss_total = float(((target_clean - grand_mean) ** 2).sum())
                eta2 = float(ss_between / ss_total) if ss_total > 0 else 0.0
                eta2 = round(min(eta2, 1.0), 3)
                signals.append({
                    "feature": column,
                    "sameTimeCorrelation": eta2,
                    "lagInfluence": 0.0,
                    "associationMethod": "eta_squared",
                    "role": "strong_driver" if eta2 > 0.06 else "weak_or_contextual",
                })
            except Exception:
                continue

        redundant = self._redundant_features(df)
        return {
            "predictiveSignals": sorted(signals, key=lambda s: max(s["sameTimeCorrelation"], s["lagInfluence"]), reverse=True)[:10],
            "redundantFeatures": redundant,
            "leakageWarnings": self._leakage_risk(df, target),
            "preTrainingRecommendation": (
                "Use lagged target features plus the strongest exogenous regressors."
                if (profile_time_valid := any(pd.api.types.is_datetime64_any_dtype(df[c]) or self._looks_datetime(df[c]) for c in df.columns))
                else "Encode categorical features and use cross-validated feature importance to rank predictors."
            ),
        }

    def _is_excluded_feature_name(self, column: str) -> bool:
        normalized = column.lower().replace("_", " ").strip()
        return (
            normalized in {"index", "row", "row id", "id"}
            or normalized.endswith(" id")
            or normalized.endswith(" code")
            or normalized in {"postal code", "zip", "zipcode"}
            or normalized == "year"
            or "whisker" in normalized
            or "rank" in normalized
            or "residual" in normalized
            or "dystopia" in normalized
        )

    def _strategy_recommendation(self, forecastability: dict[str, object], time_info: dict[str, object], rows: int) -> dict[str, object]:
        score = float(forecastability.get("score") or 0)
        seasonality = float(forecastability.get("seasonalityStrength") or 0)
        interval_stability = float(time_info.get("consistencyScore") or 0.0)
        noise_ratio = float(forecastability.get("noiseRatio") or 1.0)
        has_time_index = bool(time_info.get("valid"))

        # Non-temporal dataset: recommend tabular regression, not time-series models
        if not has_time_index:
            if rows <= 3000 and score >= 55 and noise_ratio <= 0.65:
                model = "SVM"
                reason = "Small cross-sectional dataset with a usable signal. SVM regression with scaling can model smooth non-linear relationships without heavy boosting."
                plan = ["encode categorical features", "scale numeric features", "use expanding-window or k-fold validation", "tune C and epsilon"]
            elif rows < 10000:
                model = "RandomForest"
                reason = "Small-to-medium cross-sectional dataset. Random Forest is a strong, stable baseline for noisy tabular features and gives clearer robustness than a single boosted default."
                plan = ["encode categorical features", "impute missing values", "use k-fold validation", "tune tree depth and leaf size"]
            else:
                model = "XGBoost"
                reason = "Large cross-sectional dataset without a time index. XGBoost regression with feature engineering is the appropriate choice."
                plan = ["encode categorical features", "scale numeric features", "use stratified k-fold cross-validation", "tune hyperparameters via grid search"]
            return {
                "recommendedModelFamily": model,
                "reason": reason,
                "preprocessingPlan": plan,
                "optimizationFocus": "minimize MAE/RMSE with cross-validated hyperparameter tuning",
                "confidence": self._score_grade(score),
                "datasetType": "cross-sectional",
            }

        # Temporal dataset
        if rows < 800 or (interval_stability > 0.85 and seasonality > 0.45 and rows < 4000 and noise_ratio <= 0.65):
            model = "ARIMA"
            reason = "Stable intervals and readable seasonality favor statistical forecasting."
        elif rows <= 2500 and score >= 45:
            model = "RandomForest"
            reason = "Small-to-medium temporal dataset. Random Forest can use lag/calendar features while staying robust when the signal is noisy."
        elif rows <= 4000 and score >= 55 and noise_ratio <= 0.55:
            model = "SVM"
            reason = "Moderate-size temporal dataset with a smooth enough signal. SVM regression with scaled lag features is worth using before heavier boosted trees."
        elif rows >= 4000 and score > 65:
            model = "XGBoost"
            reason = "Enough history exists for lag features and non-linear external effects."
        elif score < 45 or noise_ratio > 0.75:
            model = "RandomForest"
            reason = "The target signal is noisy or weakly forecastable, so a bagged tree model with lag/calendar features is a safer default than an LSTM."
        else:
            model = "XGBoost"
            reason = "The dataset has useful structured fields, but not enough high-quality sequential evidence to justify an LSTM by default."
        return {
            "recommendedModelFamily": model,
            "reason": reason,
            "preprocessingPlan": ["sort by timestamp", "impute temporal gaps", "create lag features", "use walk-forward validation"],
            "optimizationFocus": "minimize MAE and monitor MAPE drift across recent windows",
            "confidence": self._score_grade(score),
            "datasetType": "time-series",
        }

    def _semantic_understanding(self, title: str, columns: list[ColumnProfile], time_info: dict[str, object], target: str | None = None) -> dict[str, object]:
        text = " ".join([title, *[column.name for column in columns]]).lower()
        has_time = bool(time_info.get("valid"))

        # Domain detection — order matters: more specific domains first
        domain_signals: list[tuple[str, set[str]]] = [
            ("happiness", {"happiness", "wellbeing", "life", "satisfaction", "dystopia", "generosity", "freedom", "corruption", "gdp", "whisker"}),
            ("energy",    {"energy", "demand", "consumption", "load", "power", "electricity", "kwh", "mwh", "watt", "grid"}),
            ("finance",   {"price", "stock", "trade", "market", "gold", "forex", "crypto", "revenue", "profit", "cost"}),
            ("traffic",   {"traffic", "vehicle", "speed", "flow", "highway", "transport", "road"}),
            ("sales",     {"sales", "retail", "ecommerce", "transaction", "order", "purchase", "customer"}),
            ("health",    {"health", "mental", "medical", "patient", "clinical", "hospital", "disease", "bmi", "expectancy"}),
            ("social",    {"social", "media", "usage", "platform", "screen", "addiction", "genz", "gen", "behavior"}),
            ("weather",   {"weather", "temperature", "humidity", "rain", "wind", "pressure", "forecast", "climate"}),
            ("iot",       {"sensor", "iot", "vibration", "manufacturing", "industrial", "machine"}),
            ("supply_chain", {"supply", "chain", "disruption", "resilience", "logistics", "inventory", "shipment"}),
        ]
        words = set(re.sub(r"[^a-z0-9 ]", " ", text).split())
        domain = "general"
        best_overlap = 0
        for candidate, signals in domain_signals:
            overlap = len(words & signals)
            if overlap > best_overlap:
                best_overlap = overlap
                domain = candidate

        # Use case based on domain + time index presence
        use_case_map = {
            "happiness":     "happiness score prediction, wellbeing analysis, and cross-country comparison" if not has_time else "happiness trend forecasting across countries and years",
            "energy":        "energy demand forecasting and grid optimization" if has_time else "energy consumption analysis and segmentation",
            "finance":       "price forecasting and risk modeling" if has_time else "financial pattern analysis",
            "traffic":       "traffic flow forecasting and congestion prediction" if has_time else "traffic pattern analysis",
            "sales":         "sales forecasting and demand planning" if has_time else "customer behavior analysis",
            "health":        "health outcome prediction and risk scoring",
            "social":        "behavioral analysis, usage pattern modeling, and mental health risk scoring",
            "weather":       "weather forecasting and climate trend analysis" if has_time else "climate pattern analysis",
            "iot":           "anomaly detection and predictive maintenance" if has_time else "sensor data analysis",
            "supply_chain":  "supply chain disruption prediction and resilience scoring",
            "general":       "forecasting and operational planning" if has_time else "exploratory analysis and predictive modeling",
        }
        use_case = use_case_map.get(domain, use_case_map["general"])

        # Target meaning — use the pre-computed target passed in from profile_dataframe
        if not target:
            target = next((col.name for col in columns if col.type == "numeric" and col.name.lower() not in self._NON_TARGET_COLS), None)
        if target:
            action = "forecast" if has_time else "predict"
            target_meaning = f"`{target}` is likely the primary quantity to {action}."
        else:
            target_meaning = "No clear numeric target was detected."

        biz_meaning_map = {
            "happiness":     "This dataset captures national happiness scores, life expectancy, GDP, social support, freedom, generosity, and corruption perception across countries and years.",
            "energy":        "This dataset captures energy consumption or generation patterns.",
            "finance":       "This dataset captures financial market or transaction behavior.",
            "traffic":       "This dataset captures vehicle flow and road usage patterns.",
            "sales":         "This dataset captures retail or e-commerce transaction behavior.",
            "health":        "This dataset captures health metrics and clinical indicators.",
            "social":        "This dataset captures social media usage behavior, screen time, and mental health indicators across demographic groups.",
            "weather":       "This dataset captures atmospheric measurements and weather conditions.",
            "iot":           "This dataset captures industrial sensor readings and machine health signals.",
            "supply_chain":  "This dataset captures global supply chain disruption events, resilience metrics, and logistics indicators.",
            "general":       f"This dataset appears to describe {domain} behavior{'  over time' if has_time else ''}.",
        }

        return {
            "inferredDomain": domain,
            "businessMeaning": biz_meaning_map.get(domain, biz_meaning_map["general"]),
            "likelyUseCase": use_case,
            "targetMeaning": target_meaning,
            "datasetType": "time-series" if has_time else "cross-sectional",
        }

    def _trend_strength(self, series: pd.Series) -> float:
        if len(series) < 3:
            return 0.0
        corr = np.corrcoef(np.arange(len(series)), series)[0, 1]
        return 0.0 if np.isnan(corr) else float(abs(corr))

    def _seasonality_strength(self, series: pd.Series) -> float:
        clean = pd.Series(series).dropna().reset_index(drop=True)
        if len(clean) < 48:
            return 0.0
        candidates = [7, 12, 24, 30, 48, 168]
        scores = []
        for lag in candidates:
            if len(clean) > lag * 2:
                scores.append(abs(self._safe_corr(clean.shift(lag), clean)))
        return float(max(scores or [0.0]))

    def _stationarity_score(self, series: pd.Series) -> float:
        clean = pd.Series(series).dropna()
        if len(clean) < 24:
            return 0.0
        first = clean.iloc[: len(clean) // 2]
        second = clean.iloc[len(clean) // 2 :]
        mean_shift = abs(float(second.mean() - first.mean())) / max(float(clean.std(ddof=0)), 1.0)
        variance_shift = abs(float(second.var(ddof=0) - first.var(ddof=0))) / max(float(clean.var(ddof=0)), 1.0)
        return float(max(0.0, 1 - min(1.0, mean_shift / 3 + variance_shift / 4)))

    def _noise_ratio(self, series: pd.Series) -> float:
        clean = pd.Series(series).dropna()
        if len(clean) < 10:
            return 1.0
        smoothed = clean.rolling(max(3, min(24, len(clean) // 10)), min_periods=1).mean()
        residual = clean - smoothed
        return float(min(1.0, residual.std(ddof=0) / max(clean.std(ddof=0), 1.0)))

    def _anomaly_windows(self, df: pd.DataFrame, time_info: dict[str, object], target: str) -> list[dict[str, object]]:
        values = self._target_series_for_time_analysis(df, time_info, target)
        clean = values.dropna()
        if clean.empty:
            return []
        z = (values - clean.mean()) / max(clean.std(ddof=0), 1.0)
        anomaly_indices = z[abs(z) > 3].dropna().index[:8]
        time_column = time_info.get("timeColumn")
        windows = []
        for index in anomaly_indices:
            timestamp = str(df.loc[index, time_column]) if isinstance(time_column, str) and time_column in df.columns else str(index)
            windows.append({"index": int(index), "timestamp": timestamp, "severity": round(float(abs(z.loc[index])), 2)})
        return windows

    def _dominant_period(self, series: pd.Series) -> str:
        clean = pd.Series(series).dropna().reset_index(drop=True)
        if len(clean) < 48:
            return "insufficient history"
        candidates = {7: "weekly-like", 12: "half-day-like", 24: "daily-like", 48: "two-day-like", 168: "weekly-hourly-like"}
        scored = [(lag, abs(self._safe_corr(clean.shift(lag), clean))) for lag in candidates if len(clean) > lag * 2]
        if not scored:
            return "undetermined"
        lag, score = max(scored, key=lambda item: item[1])
        return candidates[lag] if score > 0.25 else "weak periodicity"

    def _redundant_features(self, df: pd.DataFrame) -> list[dict[str, object]]:
        numeric = df.select_dtypes(include=["number"])
        if numeric.shape[1] < 2:
            return []
        corr = numeric.corr(numeric_only=True).abs()
        redundant = []
        for i, first in enumerate(corr.columns):
            for second in corr.columns[i + 1 :]:
                value = corr.loc[first, second]
                if value > 0.92:
                    redundant.append({"features": [first, second], "correlation": round(float(value), 3)})
        return redundant[:8]

    def _leakage_risk(self, df: pd.DataFrame, target: str | None) -> list[str]:
        risks = []
        if not target:
            return risks
        target_tokens = {token for token in target.lower().replace("_", " ").split() if len(token) > 2}
        for column in df.columns:
            if column == target:
                continue
            tokens = set(column.lower().replace("_", " ").split())
            if target_tokens & tokens and any(word in column.lower() for word in ["future", "next", "pred", "forecast", "target"]):
                risks.append(f"`{column}` may leak future target information.")
        return risks or ["No obvious leakage columns detected by naming analysis."]

    def _safe_corr(self, left: pd.Series, right: pd.Series) -> float:
        aligned = pd.concat([left, right], axis=1).dropna()
        if len(aligned) < 3:
            return 0.0
        value = aligned.iloc[:, 0].corr(aligned.iloc[:, 1])
        return 0.0 if pd.isna(value) else float(value)

    def _score_grade(self, score: float) -> str:
        if score >= 80:
            return "strong"
        if score >= 60:
            return "moderate"
        if score >= 40:
            return "weak"
        return "poor"

    def _temporal_hierarchy(self, frequency: str) -> list[str]:
        text = frequency.lower()
        if "hour" in text or ":00:00" in text:
            return ["hour", "day", "week"]
        if "day" in text:
            return ["day", "week", "month"]
        if "month" in text:
            return ["month", "quarter", "year"]
        return ["observation_order"]

    def _relationship_summary(self, roles: dict[str, dict[str, str]], has_time: bool = True) -> str:
        target_role = "forecast_target" if has_time else "prediction_target"
        target = next((name for name, item in roles.items() if item["role"] == target_role), "target")
        drivers = [name for name, item in roles.items() if item["role"] in ("external_regressor", "numeric_feature")]
        groups = [name for name, item in roles.items() if item["role"] == "entity_or_grouping"]
        if has_time:
            return f"`{target}` is modeled over time using {', '.join(drivers[:3]) or 'lag features'}" + (f" and grouped by {', '.join(groups[:2])}." if groups else ".")
        return f"`{target}` is predicted from {', '.join(drivers[:4]) or 'available features'}" + (f" segmented by {', '.join(groups[:2])}." if groups else ".")

    def _role_reason(self, role: str) -> str:
        reasons = {
            "temporal_index": "High date-like parse rate makes this the sequence anchor.",
            "forecast_target": "Numeric column selected as the primary quantity to predict over time.",
            "prediction_target": "Numeric column selected as the primary quantity to predict.",
            "external_regressor": "Numeric feature may explain movement in the target over time.",
            "numeric_feature": "Numeric feature available as a predictor in regression/classification.",
            "entity_or_grouping": "Low-cardinality categorical feature can segment behavior.",
            "context_feature": "Textual or high-cardinality field may provide context.",
        }
        return reasons.get(role, "Feature role inferred from column type and name.")
