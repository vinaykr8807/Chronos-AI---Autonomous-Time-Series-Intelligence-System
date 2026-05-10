from __future__ import annotations

from datetime import datetime, timedelta, timezone
import warnings

import numpy as np
import pandas as pd

from app.core.schemas import ForecastPoint, ForecastResponse
from app.core.schemas import DatasetProfile
from app.services.catalog import CATALOG
from app.services.dataset_store import DatasetStoreService
from app.services.eda import AutoEDAService


class ForecastService:
    def __init__(self) -> None:
        self.dataset_store = DatasetStoreService()

    def forecast(self, dataset_id: str, horizon: int = 30) -> ForecastResponse:
        source_ref = self._catalog_source_ref(dataset_id)
        frame, source = self.dataset_store.load_training_frame(
            dataset_id,
            self._fallback_profile(dataset_id),
            source_ref=source_ref,
            require_real=bool(source_ref or "--" in dataset_id),
        )
        target_column = AutoEDAService(workers=1, batch_size=8)._recommended_target(frame) or self._first_numeric(frame)
        time_column = self._time_column(frame)
        frame[target_column] = pd.to_numeric(frame[target_column], errors="coerce")
        frame = frame.dropna(subset=[target_column]).reset_index(drop=True)

        history = frame[target_column].astype(float).to_numpy()
        predictions = self._project(history, horizon)
        future_times = self._future_timestamps(frame, time_column, horizon)
        actual_tail = history[-horizon:] if len(history) >= horizon else np.pad(history, (max(horizon - len(history), 0), 0), mode="edge")[-horizon:]

        rolling_std = float(pd.Series(history).tail(min(len(history), 60)).std(ddof=0) or 0.0)
        interval_base = max(rolling_std * 0.9, 1.0)
        points: list[ForecastPoint] = []
        for index, (timestamp, actual, predicted) in enumerate(zip(future_times, actual_tail, predictions)):
            width = interval_base * (1 + index * 0.04)
            points.append(
                ForecastPoint(
                    timestamp=timestamp.isoformat(),
                    value=round(float(actual), 2),
                    predicted=round(float(predicted), 2),
                    lower=round(float(predicted - width), 2),
                    upper=round(float(predicted + width), 2),
                )
            )

        short_window = points[: min(7, len(points))]
        long_window = points
        recent_mean = float(np.mean(history[-14:])) if len(history) >= 14 else float(np.mean(history))
        first_delta = points[0].predicted - recent_mean
        return ForecastResponse(
            dataset_id=dataset_id,
            horizon=horizon,
            points=points,
            summary=[
                {
                    "period": "Next 24 Hours",
                    "prediction": round(points[0].predicted, 2),
                    "confidence": {"lower": points[0].lower, "upper": points[0].upper},
                    "trend": "up" if first_delta >= 0 else "down",
                    "targetColumn": target_column,
                    "dataSource": source,
                },
                {
                    "period": "Next 7 Days",
                    "prediction": round(sum(p.predicted for p in short_window) / max(len(short_window), 1), 2),
                    "confidence": {"lower": min(p.lower for p in short_window), "upper": max(p.upper for p in short_window)},
                    "trend": self._trend_label(short_window),
                    "targetColumn": target_column,
                    "dataSource": source,
                },
                {
                    "period": "Next 30 Days",
                    "prediction": round(sum(p.predicted for p in long_window) / max(len(long_window), 1), 2),
                    "confidence": {"lower": min(p.lower for p in long_window), "upper": max(p.upper for p in long_window)},
                    "trend": self._trend_label(long_window),
                    "targetColumn": target_column,
                    "dataSource": source,
                },
            ],
            decisions=[
                {
                    "id": "decision-001",
                    "priority": "high",
                    "title": "Forecast Driver Review",
                    "description": f"Generated forecast from {source} using observed target dynamics.",
                    "action": "Compare projected peaks against recent operational thresholds.",
                    "expectedImpact": "Improves confidence in short-horizon planning decisions.",
                },
                {
                    "id": "decision-002",
                    "priority": "medium",
                    "title": "Uncertainty Watch",
                    "description": "Confidence intervals widen across the forecast horizon.",
                    "action": "Trigger a fresh training run when interval growth exceeds tolerance.",
                    "expectedImpact": "Keeps longer-horizon forecasts aligned with current system behavior.",
                },
            ],
        )

    def _project(self, history: np.ndarray, horizon: int) -> np.ndarray:
        if len(history) < 12:
            return np.repeat(history[-1], horizon)

        try:
            from statsmodels.tsa.arima.model import ARIMA

            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                fitted = ARIMA(history, order=(2, 1, 2)).fit()
            return np.asarray(fitted.forecast(steps=horizon), dtype=float)
        except Exception:
            recent = history[-min(len(history), 24):]
            slope = (recent[-1] - recent[0]) / max(len(recent) - 1, 1)
            cycle = recent[-7:] if len(recent) >= 7 else recent
            baseline = float(recent[-1])
            projected = []
            for step in range(1, horizon + 1):
                seasonal = float(cycle[(step - 1) % len(cycle)] - np.mean(cycle))
                projected.append(baseline + slope * step + seasonal * 0.35)
            return np.asarray(projected, dtype=float)

    def _future_timestamps(self, frame: pd.DataFrame, time_column: str | None, horizon: int) -> list[datetime]:
        if time_column and time_column in frame.columns:
            parsed = pd.to_datetime(frame[time_column], errors="coerce", format="mixed").dropna()
            if not parsed.empty:
                ordered = parsed.sort_values()
                frequency = (ordered.diff().dropna().mode().iloc[0] if len(ordered) > 1 and not ordered.diff().dropna().mode().empty else pd.Timedelta(days=1))
                start = ordered.iloc[-1].to_pydatetime()
                return [(start + frequency * step).to_pydatetime() if hasattr(start + frequency * step, "to_pydatetime") else start + frequency * step for step in range(1, horizon + 1)]
        now = datetime.now(timezone.utc)
        return [now + timedelta(days=step) for step in range(horizon)]

    def _trend_label(self, points: list[ForecastPoint]) -> str:
        if len(points) < 2:
            return "stable"
        delta = points[-1].predicted - points[0].predicted
        if delta > 0:
            return "up"
        if delta < 0:
            return "down"
        return "stable"

    def _time_column(self, frame: pd.DataFrame) -> str | None:
        for column in frame.columns:
            parsed = pd.to_datetime(frame[column], errors="coerce", format="mixed")
            if parsed.notna().mean() > 0.8:
                return column
        return None

    def _first_numeric(self, frame: pd.DataFrame) -> str:
        numeric_columns = frame.select_dtypes(include=["number"]).columns.tolist()
        if not numeric_columns:
            raise ValueError("No numeric column available for forecasting.")
        return numeric_columns[0]

    def _catalog_source_ref(self, dataset_id: str) -> str | None:
        for dataset in CATALOG:
            if dataset.id == dataset_id:
                return dataset.ref
        return None

    def _fallback_profile(self, dataset_id: str) -> DatasetProfile:
        return DatasetProfile(
            dataset_id=dataset_id,
            title=dataset_id,
            summary={"rows": 2400, "columns": 4, "missingPercent": 0.0, "timeSeriesValidated": True},
            columns=[],
            time_series={"valid": True, "timeColumn": "timestamp", "frequency": "H"},
            validation={"recommendedTarget": "target_value"},
            numerical_analysis={},
            categorical_analysis={},
            structural_intelligence={},
            forecastability={},
            temporal_behavior={},
            quality_intelligence={},
            feature_intelligence={},
            strategy_recommendation={},
            semantic_understanding={},
            chart_data={},
            visualizations=[],
            insights="",
            decisions=[],
            agent_notes=[],
        )
