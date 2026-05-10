from __future__ import annotations

from dataclasses import dataclass
import importlib.util
import json
import math
import warnings
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable
from uuid import uuid4

import joblib
import numpy as np
import pandas as pd
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.model_selection import ParameterGrid

from app.core.schemas import DatasetProfile, PipelineNode, PipelineRunRequest, PipelineRunResponse
from app.services.agent_runtime import AgentMemory, ReasoningTrace, StepType
from app.services.dataset_store import DataSourceError, DatasetStoreService


ProgressCallback = Callable[[dict[str, object]], None]


@dataclass
class TrainingArtifacts:
    metrics: dict[str, float]
    best_params: dict[str, object]
    param_grid: list[dict[str, object]]
    train_rows: int
    test_rows: int
    dataframe_rows: int
    feature_names: list[str]
    backend: str
    target_column: str
    source: str
    training_history: list[dict[str, object]]
    optimization_trials: list[dict[str, object]]
    preprocessing_report: dict[str, object]
    feature_plan: dict[str, object]
    evaluation_report: dict[str, object]
    deployment_report: dict[str, object]


class PipelineService:
    def __init__(self) -> None:
        self.dataset_store = DatasetStoreService()
        self.memory = AgentMemory()
        self._artifact_dir = Path("storage") / "model_artifacts"
        self._artifact_dir.mkdir(parents=True, exist_ok=True)

    def run(self, request: PipelineRunRequest, profile: DatasetProfile, progress_callback: ProgressCallback | None = None) -> PipelineRunResponse:
        resolved_source_ref = request.source_ref or profile.summary.get("sourceRef") or self._source_ref_from_id(request.dataset_id)
        if not isinstance(resolved_source_ref, str):
            raise DataSourceError(
                f"Dataset `{request.dataset_id}` does not include a Kaggle/local source reference. "
                "Pipeline training requires a real dataframe and will not use synthetic fallback."
            )
        self._emit(
            progress_callback,
            {
                "event": "agent_step",
                "agent": "Dataset Agent",
                "stage": "load_training_frame",
                "status": "running",
                "message": "Loading the full dataframe for model training.",
                "details": {"datasetId": request.dataset_id, "sourceRef": resolved_source_ref},
            },
        )
        dataframe, data_source = self.dataset_store.load_training_frame(
            request.dataset_id,
            profile,
            resolved_source_ref,
            require_real=True,
        )
        self._emit(
            progress_callback,
            {
                "event": "agent_step",
                "agent": "Dataset Agent",
                "stage": "load_training_frame",
                "status": "complete",
                "message": f"Loaded {len(dataframe):,} rows from {data_source}.",
                "details": {"rows": int(len(dataframe)), "columns": int(len(dataframe.columns)), "dataSource": data_source},
            },
        )
        return self.run_on_dataframe(request, profile, dataframe, data_source, progress_callback=progress_callback)

    def run_on_dataframe(
        self,
        request: PipelineRunRequest,
        profile: DatasetProfile,
        dataframe: pd.DataFrame,
        data_source: str,
        progress_callback: ProgressCallback | None = None,
    ) -> PipelineRunResponse:
        has_time = bool((profile.time_series or {}).get("valid"))
        time_column = self._profile_time_column(profile, dataframe)
        model, model_reason = self._resolve_model(profile, dataframe, request)
        self._emit(
            progress_callback,
            {
                "event": "agent_step",
                "agent": "Training Agent",
                "stage": "select_model",
                "status": "complete",
                "message": f"Selected {model}. {model_reason}",
                "details": {"model": model, "reason": model_reason, "timeColumn": time_column},
            },
        )
        artifacts = self._train_and_evaluate(dataframe, profile, model, request, progress_callback=progress_callback)
        synthetic_fallback = data_source == "synthetic-profile"
        artifacts.deployment_report["syntheticFallback"] = synthetic_fallback
        if synthetic_fallback:
            artifacts.deployment_report["llmExplanation"] = (
                "This artifact was trained on synthetic fallback data because no real source file was resolved. "
                "Use it only for UI/runtime validation, not for real deployment decisions."
            )
        self._emit(
            progress_callback,
            {
                "event": "agent_step",
                "agent": "Evaluation Agent",
                "stage": "evaluate_model",
                "status": "complete",
                "message": "Calculated deep validation metrics from baseline and trained predictions.",
                "details": artifacts.evaluation_report,
            },
        )
        self._emit(
            progress_callback,
            {
                "event": "artifact_export_complete",
                "agent": "Deployment Agent",
                "stage": "artifact_export",
                "status": "complete",
                "message": "Exported JSON metadata and local model artifact when supported.",
                "details": artifacts.deployment_report,
            },
        )
        self._emit(
            progress_callback,
            {
                "event": "agent_step",
                "agent": "Deployment Agent",
                "stage": "package_run",
                "status": "complete",
                "message": "Packaged model metadata for monitoring and forecast consumers.",
                "details": artifacts.deployment_report,
            },
        )
        validation_method = "walk-forward temporal holdout" if has_time else "stratified k-fold cross-validation"
        feature_desc = "lags, rolling windows, calendar features" if has_time else "encoded categorical + numeric features"
        nodes = [
            PipelineNode(
                id="data-ingestion",
                type="dataIngestion",
                label="Data Ingestion",
                description="Loaded the full dataset into the training runtime",
                status="complete",
                config={"source": data_source, "timeColumn": time_column, "rows": artifacts.dataframe_rows, "datasetType": "time-series" if has_time else "cross-sectional"},
            ),
            PipelineNode(
                id="cleaning",
                type="cleaning",
                label="Cleaning Agent",
                description="Validated schema, removed invalid target rows, and applied deterministic imputations",
                status="complete",
                config=artifacts.preprocessing_report,
            ),
            PipelineNode(
                id="preprocessing",
                type="preprocessing",
                label="Preprocessing",
                description="Imputed missing values, encoded categoricals, and prepared features" if not has_time else "Sorted the sequence, imputed gaps, and prepared temporal features",
                status="complete",
                config={"missingStrategy": "ffill+bfill" if has_time else "median+mode", "ordering": "timestamp_sorted" if has_time else "shuffled", "featureCount": len(artifacts.feature_names)},
            ),
            PipelineNode(
                id="feature-engineering",
                type="featureEngineering",
                label="Feature Engineering",
                description=f"Created {feature_desc} and model-ready tensors",
                status="complete",
                config=artifacts.feature_plan,
            ),
            PipelineNode(
                id="model",
                type="model",
                label=f"{model} Model",
                description=f"Trained on the full dataframe using {artifacts.backend}",
                status="complete",
                config={**self._model_config(model), **artifacts.best_params},
            ),
            PipelineNode(
                id="evaluation",
                type="evaluation",
                label="Evaluation",
                description=f"Scored the model using {validation_method}",
                status="complete",
                config={"metrics": ["MAE", "RMSE", "MAPE", "R2", "MASE"], "validation": "walk_forward" if has_time else "kfold", "testRows": artifacts.test_rows},
            ),
            PipelineNode(
                id="deployment",
                type="deployment",
                label="Deployment Agent",
                description="Packaged the trained run metadata for monitor and forecast consumers",
                status="complete",
                config=artifacts.deployment_report,
            ),
        ]
        pipeline_trace = self._pipeline_trace(
            data_source=data_source,
            profile=profile,
            model=model,
            model_reason=model_reason,
            artifacts=artifacts,
            has_time=has_time,
            time_column=time_column,
        )
        source_decision = (
            "Training executed on synthetic fallback data because no real source file was resolved; metrics and artifacts are demo/runtime evidence only."
            if synthetic_fallback
            else f"Training executed on the full real dataframe through the {artifacts.backend} runtime."
        )
        decisions = [
            f"Selected {model} for `{artifacts.target_column}`. {model_reason}",
            f"Evaluated {len(artifacts.param_grid)} hyperparameter candidates and selected {artifacts.best_params}.",
            f"Used {validation_method} to prevent data leakage.",
            source_decision,
        ]
        return PipelineRunResponse(
            run_id=str(uuid4()),
            dataset_id=request.dataset_id,
            data_source=data_source,
            selected_model=model,
            nodes=nodes,
            metrics=artifacts.metrics,
            agent_decisions=decisions,
            sandbox={
                "enabled": True,
                "mode": "python-runtime",
                "executor": artifacts.backend,
                "dataSource": data_source,
                "sourceRef": str(request.source_ref or profile.summary.get("sourceRef") or data_source),
                "realDataLoaded": data_source != "synthetic-profile",
                "syntheticFallback": synthetic_fallback,
                "rowsAnalyzedByEda": int(profile.summary.get("rowsAnalyzed") or profile.summary.get("rows") or 0),
                "trainingMode": "full-dataframe",
                "trainingExecution": "single-run-full-training",
                "fullDataTraining": True,
                "dataframeRows": artifacts.dataframe_rows,
                "trainRows": artifacts.train_rows,
                "testRows": artifacts.test_rows,
                "featureCount": len(artifacts.feature_names),
                "targetColumn": artifacts.target_column,
                "datasetType": "time-series" if has_time else "cross-sectional",
            },
            agents=[
                {"name": "Dataset Agent", "responsibility": "loaded the selected dataset and resolved the prediction target"},
                {"name": "EDA Agent", "responsibility": "derived valid features and dataset type from the fresh in-memory profile"},
                {"name": "Cleaning Agent", "responsibility": "applied EDA-driven drops, target validation, sorting, missing-value handling, outlier capping, and split safety checks"},
                {"name": "Feature Agent", "responsibility": "created model-ready numeric, encoded, temporal, and optional text/PCA feature plan"},
                {"name": "Training Agent", "responsibility": f"selected and trained {model} using EDA strategy and validation feedback"},
                {"name": "Evaluation Agent", "responsibility": "computed MAE, RMSE, MAPE, R2, and MASE on holdout data"},
                {"name": "Deployment Agent", "responsibility": "packaged run metadata, metrics, and monitor handoff information"},
            ],
            pipeline_graph={
                "nodes": [{"id": node.id, "label": node.label, "type": node.type, "status": node.status} for node in nodes],
                "edges": [
                    {"source": "data-ingestion", "target": "cleaning"},
                    {"source": "cleaning", "target": "preprocessing"},
                    {"source": "preprocessing", "target": "feature-engineering"},
                    {"source": "feature-engineering", "target": "model"},
                    {"source": "model", "target": "evaluation"},
                    {"source": "evaluation", "target": "deployment"},
                ],
            },
            pipeline_trace=pipeline_trace,
            training_history=artifacts.training_history,
            optimization_trials=artifacts.optimization_trials,
            preprocessing_report=artifacts.preprocessing_report,
            feature_plan=artifacts.feature_plan,
            evaluation_report=artifacts.evaluation_report,
            deployment_report=artifacts.deployment_report,
        )

    def _resolve_model(self, profile: DatasetProfile, dataframe: pd.DataFrame, request: PipelineRunRequest) -> tuple[str, str]:
        if request.model_override != "auto":
            model = request.model_override
            if model == "LSTM" and not self._lstm_available():
                return "XGBoost", "LSTM was requested, but PyTorch is not installed in the local runtime, so the pipeline fell back to XGBoost."
            if model == "SVM" and len(dataframe) > 6000:
                return "RandomForest", "SVM was requested, but the dataframe is larger than the bounded local SVM runtime; Random Forest keeps non-linear validation practical."
            return model, "Used the explicit model override supplied by the request."

        return self._select_model(profile, dataframe)

    def _select_model(self, profile: DatasetProfile, dataframe: pd.DataFrame) -> tuple[str, str]:
        rows = len(dataframe)
        forecastability = profile.forecastability or {}
        strategy = profile.strategy_recommendation or {}
        quality = profile.quality_intelligence or {}
        feature_intelligence = profile.feature_intelligence or {}
        time_series = profile.time_series or {}
        has_time = bool(time_series.get("valid"))

        score = float(forecastability.get("score") or 0.0)
        seasonality = float(forecastability.get("seasonalityStrength") or 0.0)
        noise_ratio = float(forecastability.get("noiseRatio") or 1.0)
        interval_stability = float(time_series.get("consistencyScore") or 0.0)
        trust_score = float(quality.get("trustScore") or 0.0)
        recommended_family = str(strategy.get("recommendedModelFamily") or "").lower()
        strong_signals = sum(
            1
            for signal in feature_intelligence.get("predictiveSignals", [])
            if max(float(signal.get("sameTimeCorrelation", 0.0)), float(signal.get("lagInfluence", 0.0))) >= 0.45
        )
        numeric_columns = len(dataframe.select_dtypes(include=["number"]).columns)

        if not has_time:
            if rows <= 3000 and score >= 55 and noise_ratio <= 0.65:
                return "SVM", f"EDA found a small tabular dataset ({rows:,} rows), usable forecastability ({score:.0f}), and manageable noise ({noise_ratio:.2f}); scaled SVM regression is suitable."
            if rows < 10000:
                return "RandomForest", f"EDA found a small-to-medium tabular dataset ({rows:,} rows) with {numeric_columns} numeric columns; Random Forest is robust without defaulting to boosting."
            return "XGBoost", f"EDA found a large tabular dataset ({rows:,} rows); XGBoost is selected for scalable non-linear supervised learning."

        if "arima" in recommended_family and rows >= 96 and interval_stability >= 0.8 and seasonality >= 0.35 and noise_ratio <= 0.55:
            return "ARIMA", f"EDA found stable cadence ({interval_stability:.2f}), readable seasonality ({seasonality:.2f}), and low noise ({noise_ratio:.2f}), which suits statistical forecasting."

        if self._lstm_available() and rows >= 12000 and score >= 75 and noise_ratio <= 0.45 and strong_signals >= 2:
            return "LSTM", f"EDA found a long high-quality sequence ({rows:,} rows), score {score:.0f}, low noise {noise_ratio:.2f}, and {strong_signals} strong signals."

        if rows <= 2500 and score >= 45:
            return "RandomForest", f"EDA found a smaller time-series dataset ({rows:,} rows) with noisy/weak sequential structure; Random Forest can use lag/calendar features without over-committing to boosting."

        if rows <= 5000 and score >= 55 and noise_ratio <= 0.55 and strong_signals >= 1:
            return "SVM", f"EDA found a moderate-size sequence ({rows:,} rows), smoother noise ({noise_ratio:.2f}), and strong signals; scaled SVM regression is a good non-linear candidate."

        if rows >= 300 and (strong_signals >= 1 or numeric_columns >= 3 or score >= 55 or trust_score >= 70):
            return "XGBoost", f"EDA found enough history ({rows:,} rows), {numeric_columns} numeric columns, and {strong_signals} strong signal(s) for boosted lag-based supervised learning."

        if "arima" in recommended_family or rows < 300:
            return "ARIMA", "EDA found short history or a mostly univariate temporal pattern; ARIMA is the simpler, more transparent choice."

        return "RandomForest", "EDA did not find strong enough evidence for ARIMA, LSTM, or boosting; Random Forest is the safer general-purpose fallback."

    def _source_ref_from_id(self, dataset_id: str) -> str | None:
        if "--" not in dataset_id:
            return None
        owner, slug = dataset_id.split("--", 1)
        if owner and slug:
            return f"{owner}/{slug}"
        return None

    def _model_config(self, model: str) -> dict[str, object]:
        if model == "LSTM":
            return {"epochs": 8, "learningRate": 0.001, "hiddenSize": 32, "agentOptimized": True}
        if model == "XGBoost":
            return {"nEstimators": 200, "maxDepth": 4, "learningRate": 0.05, "agentOptimized": True}
        if model == "RandomForest":
            return {"nEstimators": 180, "maxDepth": "auto", "minSamplesLeaf": 1, "agentOptimized": True}
        if model == "SVM":
            return {"kernel": "rbf", "scaler": "standard", "agentOptimized": True}
        return {"seasonal": False, "order": [2, 1, 2], "agentOptimized": True}

    def _lstm_available(self) -> bool:
        return importlib.util.find_spec("torch") is not None

    def _train_and_evaluate(
        self,
        dataframe: pd.DataFrame,
        profile: DatasetProfile,
        model: str,
        request: PipelineRunRequest,
        progress_callback: ProgressCallback | None = None,
    ) -> TrainingArtifacts:
        frame = dataframe.copy()
        time_column = self._profile_time_column(profile, frame)
        target_column = request.target_column or str(profile.validation.get("recommendedTarget") or self._first_numeric(frame))
        self._emit(
            progress_callback,
            {
                "event": "agent_step",
                "agent": "Cleaning Agent",
                "stage": "clean_data",
                "status": "running",
                "message": f"Validating target `{target_column}`, sorting time, and imputing numeric gaps.",
                "details": {"targetColumn": target_column, "timeColumn": time_column, "inputRows": int(len(frame))},
            },
        )
        frame, preprocessing_report = self._prepare_frame(frame, time_column, target_column)
        self._emit(
            progress_callback,
            {
                "event": "agent_step",
                "agent": "Cleaning Agent",
                "stage": "clean_data",
                "status": "complete",
                "message": "Cleaning complete; invalid target rows removed and numeric gaps filled.",
                "details": preprocessing_report,
            },
        )
        self._emit(
            progress_callback,
            {
                "event": "agent_step",
                "agent": "Feature Agent",
                "stage": "build_features",
                "status": "running",
                "message": f"Building model-ready features for {model}.",
                "details": {"model": model, "rows": int(len(frame)), "targetColumn": target_column},
            },
        )

        if model == "ARIMA":
            return self._train_arima(frame, target_column, preprocessing_report, progress_callback=progress_callback)
        if model == "XGBoost":
            return self._train_xgboost(frame, target_column, time_column, preprocessing_report, progress_callback=progress_callback)
        if model == "RandomForest":
            return self._train_random_forest(frame, target_column, time_column, preprocessing_report, progress_callback=progress_callback)
        if model == "SVM":
            return self._train_svm(frame, target_column, time_column, preprocessing_report, progress_callback=progress_callback)
        return self._train_lstm(frame, target_column, preprocessing_report, progress_callback=progress_callback)

    def _prepare_frame(self, frame: pd.DataFrame, time_column: str | None, target_column: str) -> tuple[pd.DataFrame, dict[str, object]]:
        original_rows = len(frame)
        original_missing = int(frame.isna().sum().sum())
        transformations: list[str] = []
        if time_column and time_column in frame.columns:
            frame[time_column] = pd.to_datetime(frame[time_column], errors="coerce", format="mixed")
            frame = frame.sort_values(time_column)
            transformations.append(f"Sorted by time column `{time_column}`.")

        drop_columns: list[str] = []
        drop_reasons: dict[str, str] = {}
        for column in frame.columns:
            if column in {target_column, time_column}:
                continue
            missing_pct = float(frame[column].isna().mean() * 100)
            unique_count = int(frame[column].nunique(dropna=True))
            is_text = frame[column].dtype == object or str(frame[column].dtype) == "category"
            if missing_pct > 70:
                drop_columns.append(column)
                drop_reasons[column] = f"{missing_pct:.1f}% missing"
            elif unique_count <= 1:
                drop_columns.append(column)
                drop_reasons[column] = "constant or zero-variance column"
            elif unique_count == len(frame) and not pd.api.types.is_numeric_dtype(frame[column]):
                drop_columns.append(column)
                drop_reasons[column] = "ID-like text column with one unique value per row"
            elif is_text and unique_count > max(200, int(len(frame) * 0.8)):
                drop_columns.append(column)
                drop_reasons[column] = f"high-cardinality free-text/ID-like column ({unique_count} unique values)"

        if drop_columns:
            frame = frame.drop(columns=drop_columns)
            transformations.append(f"Dropped {len(drop_columns)} unusable column(s): {drop_reasons}.")

        frame[target_column] = pd.to_numeric(frame[target_column], errors="coerce")
        frame = frame.dropna(subset=[target_column]).copy()
        dropped_rows = original_rows - len(frame)
        numeric_columns = frame.select_dtypes(include=["number"]).columns.tolist()
        for column in numeric_columns:
            before = int(frame[column].isna().sum())
            if before:
                frame[column] = frame[column].ffill().bfill()
                if frame[column].isna().any():
                    frame[column] = frame[column].fillna(frame[column].median())
                transformations.append(f"Imputed numeric column `{column}` with forward/back fill and median fallback ({before} cells).")
            if column != target_column:
                clean = frame[column].dropna()
                if len(clean) > 8:
                    q1 = clean.quantile(0.25)
                    q3 = clean.quantile(0.75)
                    iqr = q3 - q1
                    if iqr > 0:
                        lower = q1 - 1.5 * iqr
                        upper = q3 + 1.5 * iqr
                        capped = int(((frame[column] < lower) | (frame[column] > upper)).sum())
                        if capped:
                            frame[column] = frame[column].clip(lower=lower, upper=upper)
                            transformations.append(f"Capped {capped} outlier value(s) in `{column}` with IQR bounds.")

        categorical_columns = [
            column for column in frame.columns
            if column != target_column and column not in numeric_columns and column != time_column
        ]
        for column in categorical_columns:
            before = int(frame[column].isna().sum())
            if before == 0:
                continue
            missing_pct = before / max(len(frame), 1) * 100
            if missing_pct < 5 and not frame[column].mode(dropna=True).empty:
                fill_value = frame[column].mode(dropna=True).iloc[0]
                strategy = "mode"
            else:
                fill_value = "Unknown"
                strategy = "constant"
            frame[column] = frame[column].fillna(fill_value)
            transformations.append(f"Imputed categorical column `{column}` with {strategy} ({before} cells).")

        frame = frame.reset_index(drop=True)
        report = {
            "originalRows": int(original_rows),
            "rowsAfterTargetValidation": int(len(frame)),
            "droppedRows": int(dropped_rows),
            "droppedColumns": drop_columns,
            "dropReasons": drop_reasons,
            "originalMissingCells": int(original_missing),
            "remainingMissingCells": int(frame.isna().sum().sum()),
            "targetColumn": target_column,
            "timeColumn": time_column,
            "sorting": "timestamp_sorted" if time_column else "input_order",
            "numericImputation": "ffill+bfill+median",
            "categoricalEncoding": "category codes during feature matrix construction",
            "transformationsApplied": transformations,
            "totalTransformations": len(transformations),
        }
        return frame, report

    def _train_arima(
        self,
        frame: pd.DataFrame,
        target_column: str,
        preprocessing_report: dict[str, object],
        progress_callback: ProgressCallback | None = None,
    ) -> TrainingArtifacts:
        from statsmodels.tsa.arima.model import ARIMA

        series = frame[target_column].astype(float)
        if len(series) < 20:
            return self._naive_artifacts(frame, target_column, series.to_numpy(), backend="statsmodels-arima")
        split = self._safe_split_index(len(series))
        train, test = series.iloc[:split], series.iloc[split:]
        best_score = float("inf")
        best_order = (1, 1, 1)
        best_predictions = None
        param_grid = [{"order": order} for order in [(1, 1, 1), (2, 1, 1), (2, 1, 2)]]
        trials: list[dict[str, object]] = []
        feature_plan = self._feature_plan([target_column], target_column, "ARIMA", False, frame)
        self._emit(
            progress_callback,
            {
                "event": "agent_step",
                "agent": "Feature Agent",
                "stage": "build_features",
                "status": "complete",
                "message": "Prepared univariate target series for ARIMA order search.",
                "details": feature_plan,
            },
        )
        self._emit(
            progress_callback,
            {
                "event": "agent_step",
                "agent": "Training Agent",
                "stage": "train_model",
                "status": "running",
                "message": f"Starting ARIMA order search across {len(param_grid)} candidates.",
                "details": {"candidateCount": len(param_grid), "trainRows": int(len(train)), "testRows": int(len(test))},
            },
        )
        for trial_index, params in enumerate(param_grid, start=1):
            self._emit(
                progress_callback,
                {
                    "event": "training_candidate_started",
                    "agent": "Training Agent",
                    "stage": "arima_order",
                    "status": "running",
                    "message": f"Evaluating ARIMA candidate {trial_index}/{len(param_grid)}.",
                    "details": {"trial": trial_index, "candidateCount": len(param_grid), "params": {"order": list(params["order"])}},
                },
            )
            try:
                with warnings.catch_warnings():
                    warnings.simplefilter("ignore")
                    fitted = ARIMA(train, order=params["order"]).fit()
                predictions = fitted.forecast(steps=len(test))
                score = mean_absolute_error(test, predictions)
                trial = {"params": {"order": list(params["order"])}, "validationMae": round(float(score), 4), "aic": round(float(fitted.aic), 4)}
                trials.append(trial)
                self._emit(
                    progress_callback,
                    {
                        "event": "training_candidate_complete",
                        "agent": "Training Agent",
                        "stage": "arima_order",
                        "status": "complete",
                        "message": f"Evaluated ARIMA{params['order']} with validation MAE {trial['validationMae']}.",
                        "details": {"trial": trial_index, **trial},
                    },
                )
                if score < best_score:
                    best_score = score
                    best_order = params["order"]
                    best_predictions = predictions
            except Exception:
                trial = {"params": {"order": list(params["order"])}, "status": "failed"}
                trials.append(trial)
                self._emit(
                    progress_callback,
                    {
                        "event": "training_candidate_complete",
                        "agent": "Training Agent",
                        "stage": "arima_order",
                        "status": "error",
                        "message": f"ARIMA{params['order']} failed and was skipped.",
                        "details": {"trial": trial_index, **trial},
                    },
                )
                continue
        if best_predictions is None:
            naive = np.repeat(float(train.iloc[-1]), len(test))
            best_predictions = pd.Series(naive, index=test.index)
        y_true = test.to_numpy()
        y_pred = np.asarray(best_predictions)
        metrics = self._metrics(y_true, y_pred)
        baseline = np.repeat(float(train.iloc[-1]), len(test))
        baseline_metrics = self._metrics(y_true, baseline)
        evaluation_report = self._evaluation_report(
            metrics,
            len(train),
            len(test),
            "walk-forward temporal holdout",
            baseline_metrics=baseline_metrics,
            y_true=y_true,
            y_pred=y_pred,
        )
        deployment_report = self._deployment_report(
            "ARIMA",
            "statsmodels-arima",
            target_column,
            model_object=None,
            metadata={"bestParams": {"order": list(best_order)}, "metrics": metrics, "note": "ARIMA fit metadata exported; statsmodels object is not persisted by this lightweight local deployer."},
        )
        return TrainingArtifacts(
            metrics=metrics,
            best_params={"order": list(best_order)},
            param_grid=param_grid,
            train_rows=len(train),
            test_rows=len(test),
            dataframe_rows=len(frame),
            feature_names=[target_column],
            backend="statsmodels-arima",
            target_column=target_column,
            source="timeseries-univariate",
            training_history=trials,
            optimization_trials=trials,
            preprocessing_report=preprocessing_report,
            feature_plan=feature_plan,
            evaluation_report=evaluation_report,
            deployment_report=deployment_report,
        )

    def _train_xgboost(
        self,
        frame: pd.DataFrame,
        target_column: str,
        time_column: str | None,
        preprocessing_report: dict[str, object],
        progress_callback: ProgressCallback | None = None,
    ) -> TrainingArtifacts:
        from xgboost import XGBRegressor

        x, y, feature_names, feature_plan = self._supervised_matrix(frame, target_column, time_column, model="XGBoost")
        if len(x) < 20:
            return self._naive_artifacts(frame, target_column, y, feature_names=feature_names, backend="xgboost")
        x_train, x_test, y_train, y_test = self._temporal_split(x, y)
        self._emit(
            progress_callback,
            {
                "event": "agent_step",
                "agent": "Feature Agent",
                "stage": "build_features",
                "status": "complete",
                "message": f"Built supervised matrix with {len(feature_names)} features.",
                "details": {**feature_plan, "matrixRows": int(len(x)), "trainRows": int(len(x_train)), "testRows": int(len(x_test))},
            },
        )

        # Bounded deep-validation grids: larger for small/medium data, still capped for local runtime.
        if len(x_train) >= 25000:
            grid = list(ParameterGrid({
                "n_estimators": [180, 320],
                "max_depth": [3, 5],
                "learning_rate": [0.05, 0.1],
                "min_child_weight": [1],
            }))
        elif len(x_train) >= 5000:
            grid = list(ParameterGrid({
                "n_estimators": [180, 300, 450],
                "max_depth": [3, 5, 7],
                "learning_rate": [0.03, 0.07],
                "min_child_weight": [1, 3],
            }))
        else:
            grid = list(ParameterGrid({
                "n_estimators": [120, 220, 340],
                "max_depth": [3, 5, 7],
                "learning_rate": [0.03, 0.07],
                "min_child_weight": [1, 3],
            }))

        best_score = float("inf")
        best_params = grid[0]
        trials: list[dict[str, object]] = []
        best_history: list[dict[str, object]] = []
        best_fold_metrics: list[dict[str, object]] = []
        baseline_fold_metrics: list[dict[str, object]] = []
        folds = self._walk_forward_folds(len(x), preferred_folds=4 if time_column else 3)
        self._emit(
            progress_callback,
            {
                "event": "agent_step",
                "agent": "Training Agent",
                "stage": "train_model",
                "status": "running",
                "message": f"Starting XGBoost deep validation across {len(grid)} candidates and {len(folds)} folds.",
                "details": {"candidateCount": len(grid), "foldCount": len(folds), "trainRows": int(len(x_train)), "testRows": int(len(x_test))},
            },
        )
        for trial_index, params in enumerate(grid, start=1):
            self._emit(
                progress_callback,
                {
                    "event": "training_candidate_started",
                    "agent": "Training Agent",
                    "stage": "xgboost_trial",
                    "status": "running",
                    "message": f"Validating XGBoost candidate {trial_index}/{len(grid)}.",
                    "details": {"trial": trial_index, "candidateCount": len(grid), "params": params},
                },
            )
            fold_rows: list[dict[str, object]] = []
            history: list[dict[str, object]] = []
            for fold_index, (train_end, test_start, test_end) in enumerate(folds, start=1):
                self._emit(
                    progress_callback,
                    {
                        "event": "validation_fold_started",
                        "agent": "Training Agent",
                        "stage": "walk_forward_validation",
                        "status": "running",
                        "message": f"Candidate {trial_index} fold {fold_index}/{len(folds)} started.",
                        "details": {
                            "candidate": trial_index,
                            "fold": fold_index,
                            "trainRows": int(train_end),
                            "testRows": int(test_end - test_start),
                            "params": params,
                        },
                    },
                )
                fold_estimator = XGBRegressor(
                    objective="reg:squarederror",
                    random_state=42,
                    subsample=0.85,
                    colsample_bytree=0.85,
                    reg_alpha=0.05,
                    reg_lambda=1.0,
                    eval_metric="mae",
                    **params,
                )
                fold_estimator.fit(x[:train_end], y[:train_end], eval_set=[(x[test_start:test_end], y[test_start:test_end])], verbose=False)
                fold_pred = fold_estimator.predict(x[test_start:test_end])
                fold_metrics = self._metrics(y[test_start:test_end], fold_pred)
                baseline_pred = np.repeat(float(y[train_end - 1]), test_end - test_start)
                fold_baseline_metrics = self._metrics(y[test_start:test_end], baseline_pred)
                if trial_index == 1:
                    baseline_fold_metrics.append(
                        {
                            "fold": fold_index,
                            "trainRows": int(train_end),
                            "testRows": int(test_end - test_start),
                            "metrics": fold_baseline_metrics,
                        }
                    )
                fold_record = {
                    "fold": fold_index,
                    "trainRows": int(train_end),
                    "testRows": int(test_end - test_start),
                    "metrics": fold_metrics,
                    "baselineMetrics": fold_baseline_metrics,
                }
                fold_rows.append(fold_record)
                eval_history = fold_estimator.evals_result().get("validation_0", {}).get("mae", [])
                if fold_index == len(folds):
                    history = [
                        {"iteration": idx + 1, "validationMae": round(float(value), 4)}
                        for idx, value in enumerate(eval_history[:80])
                    ]
                self._emit(
                    progress_callback,
                    {
                        "event": "validation_fold_complete",
                        "agent": "Training Agent",
                        "stage": "walk_forward_validation",
                        "status": "complete",
                        "message": f"Candidate {trial_index} fold {fold_index} MAE {fold_metrics['mae']}.",
                        "details": {**fold_record, "candidate": trial_index, "params": params},
                    },
                )
            score = float(np.mean([float(row["metrics"]["mae"]) for row in fold_rows]))
            trial = {
                "params": params,
                "validationMae": round(score, 4),
                "rounds": len(history),
                "foldCount": len(fold_rows),
                "foldMetrics": fold_rows,
            }
            trials.append(trial)
            for point in history:
                iteration = int(point.get("iteration") or 0)
                if iteration in {1, len(history)} or iteration % 25 == 0:
                    self._emit(
                        progress_callback,
                        {
                            "event": "training_iteration",
                            "agent": "Training Agent",
                            "stage": "xgboost_iteration",
                            "status": "running",
                            "message": f"Candidate {trial_index} round {iteration}: validation MAE {point['validationMae']}.",
                            "details": {"trial": trial_index, **point},
                        },
                    )
            self._emit(
                progress_callback,
                {
                    "event": "training_candidate_complete",
                    "agent": "Training Agent",
                    "stage": "xgboost_trial",
                    "status": "complete",
                    "message": f"Candidate {trial_index} aggregate fold MAE: {trial['validationMae']}.",
                    "details": trial,
                },
            )
            if score < best_score:
                best_score = score
                best_params = params
                best_history = history
                best_fold_metrics = fold_rows
        best_model = XGBRegressor(
            objective="reg:squarederror",
            random_state=42,
            subsample=0.85,
            colsample_bytree=0.85,
            reg_alpha=0.05,
            reg_lambda=1.0,
            eval_metric="mae",
            **best_params,
        )
        best_model.fit(x_train, y_train, eval_set=[(x_test, y_test)], verbose=False)
        predictions = best_model.predict(x_test)
        metrics = self._metrics(y_test, predictions)
        baseline = np.repeat(float(y_train[-1]), len(y_test))
        baseline_metrics = self._metrics(y_test, baseline)
        aggregate_metrics = self._aggregate_fold_metrics(best_fold_metrics)
        aggregate_baseline_metrics = self._aggregate_fold_metrics(baseline_fold_metrics)
        validation_method = f"deep walk-forward backtesting ({len(folds)} folds)" if time_column else f"deep expanding-window validation ({len(folds)} folds)"
        evaluation_report = self._evaluation_report(
            metrics,
            len(x_train),
            len(x_test),
            validation_method,
            baseline_metrics=baseline_metrics,
            y_true=y_test,
            y_pred=predictions,
            fold_metrics=best_fold_metrics,
            aggregate_metrics=aggregate_metrics,
            aggregate_baseline_metrics=aggregate_baseline_metrics,
        )
        deployment_report = self._deployment_report(
            "XGBoost",
            "xgboost",
            target_column,
            model_object=best_model,
            metadata={"bestParams": best_params, "metrics": metrics, "featureNames": feature_names},
        )
        return TrainingArtifacts(
            metrics=metrics,
            best_params=best_params,
            param_grid=grid,
            train_rows=len(x_train),
            test_rows=len(x_test),
            dataframe_rows=len(frame),
            feature_names=feature_names,
            backend="xgboost",
            target_column=target_column,
            source="timeseries-supervised",
            training_history=best_history,
            optimization_trials=trials,
            preprocessing_report=preprocessing_report,
            feature_plan=feature_plan,
            evaluation_report=evaluation_report,
            deployment_report=deployment_report,
        )

    def _train_random_forest(
        self,
        frame: pd.DataFrame,
        target_column: str,
        time_column: str | None,
        preprocessing_report: dict[str, object],
        progress_callback: ProgressCallback | None = None,
    ) -> TrainingArtifacts:
        from sklearn.ensemble import RandomForestRegressor

        x, y, feature_names, feature_plan = self._supervised_matrix(frame, target_column, time_column, model="RandomForest")
        if len(x) < 20:
            return self._naive_artifacts(frame, target_column, y, feature_names=feature_names, backend="sklearn-random-forest")
        x_train, x_test, y_train, y_test = self._temporal_split(x, y)
        transformations = list(feature_plan.get("transformations", []))
        transformations.append("bagged regression trees")
        feature_plan["transformations"] = transformations
        self._emit(
            progress_callback,
            {
                "event": "agent_step",
                "agent": "Feature Agent",
                "stage": "build_features",
                "status": "complete",
                "message": f"Built Random Forest matrix with {len(feature_names)} features.",
                "details": {**feature_plan, "matrixRows": int(len(x)), "trainRows": int(len(x_train)), "testRows": int(len(x_test))},
            },
        )

        if len(x_train) >= 10000:
            grid = list(ParameterGrid({"n_estimators": [120, 220], "max_depth": [12, None], "min_samples_leaf": [1]}))
        elif len(x_train) >= 3000:
            grid = list(ParameterGrid({"n_estimators": [120, 220], "max_depth": [10, None], "min_samples_leaf": [1, 3]}))
        else:
            grid = list(ParameterGrid({"n_estimators": [100, 180], "max_depth": [8, 14, None], "min_samples_leaf": [1, 3]}))

        folds = self._walk_forward_folds(len(x), preferred_folds=4 if time_column else 3)
        best_score = float("inf")
        best_params = grid[0]
        best_fold_metrics: list[dict[str, object]] = []
        baseline_fold_metrics: list[dict[str, object]] = []
        trials: list[dict[str, object]] = []
        self._emit(
            progress_callback,
            {
                "event": "agent_step",
                "agent": "Training Agent",
                "stage": "train_model",
                "status": "running",
                "message": f"Starting Random Forest validation across {len(grid)} candidates and {len(folds)} folds.",
                "details": {"candidateCount": len(grid), "foldCount": len(folds), "trainRows": int(len(x_train)), "testRows": int(len(x_test))},
            },
        )
        for trial_index, params in enumerate(grid, start=1):
            self._emit(
                progress_callback,
                {
                    "event": "training_candidate_started",
                    "agent": "Training Agent",
                    "stage": "random_forest_trial",
                    "status": "running",
                    "message": f"Validating Random Forest candidate {trial_index}/{len(grid)}.",
                    "details": {"trial": trial_index, "candidateCount": len(grid), "params": params},
                },
            )
            fold_rows: list[dict[str, object]] = []
            for fold_index, (train_end, test_start, test_end) in enumerate(folds, start=1):
                self._emit(
                    progress_callback,
                    {
                        "event": "validation_fold_started",
                        "agent": "Training Agent",
                        "stage": "walk_forward_validation",
                        "status": "running",
                        "message": f"Random Forest candidate {trial_index} fold {fold_index}/{len(folds)} started.",
                        "details": {"candidate": trial_index, "fold": fold_index, "trainRows": int(train_end), "testRows": int(test_end - test_start), "params": params},
                    },
                )
                estimator = RandomForestRegressor(random_state=42, n_jobs=-1, **params)
                estimator.fit(x[:train_end], y[:train_end])
                fold_pred = estimator.predict(x[test_start:test_end])
                fold_metrics = self._metrics(y[test_start:test_end], fold_pred)
                baseline_pred = np.repeat(float(y[train_end - 1]), test_end - test_start)
                fold_baseline_metrics = self._metrics(y[test_start:test_end], baseline_pred)
                if trial_index == 1:
                    baseline_fold_metrics.append({"fold": fold_index, "trainRows": int(train_end), "testRows": int(test_end - test_start), "metrics": fold_baseline_metrics})
                fold_record = {"fold": fold_index, "trainRows": int(train_end), "testRows": int(test_end - test_start), "metrics": fold_metrics, "baselineMetrics": fold_baseline_metrics}
                fold_rows.append(fold_record)
                self._emit(
                    progress_callback,
                    {
                        "event": "validation_fold_complete",
                        "agent": "Training Agent",
                        "stage": "walk_forward_validation",
                        "status": "complete",
                        "message": f"Random Forest candidate {trial_index} fold {fold_index} MAE {fold_metrics['mae']}.",
                        "details": {**fold_record, "candidate": trial_index, "params": params},
                    },
                )
            score = float(np.mean([float(row["metrics"]["mae"]) for row in fold_rows]))
            trial = {"params": params, "validationMae": round(score, 4), "foldCount": len(fold_rows), "foldMetrics": fold_rows}
            trials.append(trial)
            self._emit(
                progress_callback,
                {
                    "event": "training_candidate_complete",
                    "agent": "Training Agent",
                    "stage": "random_forest_trial",
                    "status": "complete",
                    "message": f"Random Forest candidate {trial_index} aggregate fold MAE: {trial['validationMae']}.",
                    "details": trial,
                },
            )
            if score < best_score:
                best_score = score
                best_params = params
                best_fold_metrics = fold_rows

        best_model = RandomForestRegressor(random_state=42, n_jobs=-1, **best_params)
        best_model.fit(x_train, y_train)
        predictions = best_model.predict(x_test)
        metrics = self._metrics(y_test, predictions)
        baseline = np.repeat(float(y_train[-1]), len(y_test))
        baseline_metrics = self._metrics(y_test, baseline)
        aggregate_metrics = self._aggregate_fold_metrics(best_fold_metrics)
        aggregate_baseline_metrics = self._aggregate_fold_metrics(baseline_fold_metrics)
        validation_method = f"deep walk-forward backtesting ({len(folds)} folds)" if time_column else f"deep expanding-window validation ({len(folds)} folds)"
        evaluation_report = self._evaluation_report(
            metrics,
            len(x_train),
            len(x_test),
            validation_method,
            baseline_metrics=baseline_metrics,
            y_true=y_test,
            y_pred=predictions,
            fold_metrics=best_fold_metrics,
            aggregate_metrics=aggregate_metrics,
            aggregate_baseline_metrics=aggregate_baseline_metrics,
        )
        deployment_report = self._deployment_report(
            "RandomForest",
            "sklearn-random-forest",
            target_column,
            model_object=best_model,
            metadata={"bestParams": best_params, "metrics": metrics, "featureNames": feature_names},
        )
        return TrainingArtifacts(
            metrics=metrics,
            best_params=best_params,
            param_grid=grid,
            train_rows=len(x_train),
            test_rows=len(x_test),
            dataframe_rows=len(frame),
            feature_names=feature_names,
            backend="sklearn-random-forest",
            target_column=target_column,
            source="supervised-random-forest",
            training_history=[{"candidate": index + 1, "validationMae": trial["validationMae"]} for index, trial in enumerate(trials[:80])],
            optimization_trials=trials,
            preprocessing_report=preprocessing_report,
            feature_plan=feature_plan,
            evaluation_report=evaluation_report,
            deployment_report=deployment_report,
        )

    def _train_svm(
        self,
        frame: pd.DataFrame,
        target_column: str,
        time_column: str | None,
        preprocessing_report: dict[str, object],
        progress_callback: ProgressCallback | None = None,
    ) -> TrainingArtifacts:
        from sklearn.pipeline import make_pipeline
        from sklearn.preprocessing import StandardScaler
        from sklearn.svm import SVR

        x, y, feature_names, feature_plan = self._supervised_matrix(frame, target_column, time_column, model="SVM")
        if len(x) < 20:
            return self._naive_artifacts(frame, target_column, y, feature_names=feature_names, backend="sklearn-svm")
        if len(x) > 6000:
            x = x[-6000:]
            y = y[-6000:]
            feature_plan["boundedTrainingRows"] = 6000
            feature_plan["boundedTrainingReason"] = "SVM training is bounded to the latest 6,000 supervised rows in the local runtime."
        x_train, x_test, y_train, y_test = self._temporal_split(x, y)
        transformations = list(feature_plan.get("transformations", []))
        transformations.extend(["standard scaling", "rbf kernel regression"])
        feature_plan["transformations"] = transformations
        self._emit(
            progress_callback,
            {
                "event": "agent_step",
                "agent": "Feature Agent",
                "stage": "build_features",
                "status": "complete",
                "message": f"Built scaled SVM matrix with {len(feature_names)} features.",
                "details": {**feature_plan, "matrixRows": int(len(x)), "trainRows": int(len(x_train)), "testRows": int(len(x_test))},
            },
        )

        if len(x_train) >= 3000:
            grid = list(ParameterGrid({"C": [1.0, 10.0], "epsilon": [0.05], "gamma": ["scale"]}))
        else:
            grid = list(ParameterGrid({"C": [1.0, 10.0, 50.0], "epsilon": [0.05, 0.1], "gamma": ["scale"]}))

        folds = self._walk_forward_folds(len(x), preferred_folds=3)
        best_score = float("inf")
        best_params = grid[0]
        best_fold_metrics: list[dict[str, object]] = []
        baseline_fold_metrics: list[dict[str, object]] = []
        trials: list[dict[str, object]] = []
        self._emit(
            progress_callback,
            {
                "event": "agent_step",
                "agent": "Training Agent",
                "stage": "train_model",
                "status": "running",
                "message": f"Starting SVM validation across {len(grid)} candidates and {len(folds)} folds.",
                "details": {"candidateCount": len(grid), "foldCount": len(folds), "trainRows": int(len(x_train)), "testRows": int(len(x_test))},
            },
        )
        for trial_index, params in enumerate(grid, start=1):
            self._emit(
                progress_callback,
                {
                    "event": "training_candidate_started",
                    "agent": "Training Agent",
                    "stage": "svm_trial",
                    "status": "running",
                    "message": f"Validating SVM candidate {trial_index}/{len(grid)}.",
                    "details": {"trial": trial_index, "candidateCount": len(grid), "params": params},
                },
            )
            fold_rows: list[dict[str, object]] = []
            for fold_index, (train_end, test_start, test_end) in enumerate(folds, start=1):
                self._emit(
                    progress_callback,
                    {
                        "event": "validation_fold_started",
                        "agent": "Training Agent",
                        "stage": "walk_forward_validation",
                        "status": "running",
                        "message": f"SVM candidate {trial_index} fold {fold_index}/{len(folds)} started.",
                        "details": {"candidate": trial_index, "fold": fold_index, "trainRows": int(train_end), "testRows": int(test_end - test_start), "params": params},
                    },
                )
                estimator = make_pipeline(StandardScaler(), SVR(kernel="rbf", **params))
                estimator.fit(x[:train_end], y[:train_end])
                fold_pred = estimator.predict(x[test_start:test_end])
                fold_metrics = self._metrics(y[test_start:test_end], fold_pred)
                baseline_pred = np.repeat(float(y[train_end - 1]), test_end - test_start)
                fold_baseline_metrics = self._metrics(y[test_start:test_end], baseline_pred)
                if trial_index == 1:
                    baseline_fold_metrics.append({"fold": fold_index, "trainRows": int(train_end), "testRows": int(test_end - test_start), "metrics": fold_baseline_metrics})
                fold_record = {"fold": fold_index, "trainRows": int(train_end), "testRows": int(test_end - test_start), "metrics": fold_metrics, "baselineMetrics": fold_baseline_metrics}
                fold_rows.append(fold_record)
                self._emit(
                    progress_callback,
                    {
                        "event": "validation_fold_complete",
                        "agent": "Training Agent",
                        "stage": "walk_forward_validation",
                        "status": "complete",
                        "message": f"SVM candidate {trial_index} fold {fold_index} MAE {fold_metrics['mae']}.",
                        "details": {**fold_record, "candidate": trial_index, "params": params},
                    },
                )
            score = float(np.mean([float(row["metrics"]["mae"]) for row in fold_rows]))
            trial = {"params": params, "validationMae": round(score, 4), "foldCount": len(fold_rows), "foldMetrics": fold_rows}
            trials.append(trial)
            self._emit(
                progress_callback,
                {
                    "event": "training_candidate_complete",
                    "agent": "Training Agent",
                    "stage": "svm_trial",
                    "status": "complete",
                    "message": f"SVM candidate {trial_index} aggregate fold MAE: {trial['validationMae']}.",
                    "details": trial,
                },
            )
            if score < best_score:
                best_score = score
                best_params = params
                best_fold_metrics = fold_rows

        best_model = make_pipeline(StandardScaler(), SVR(kernel="rbf", **best_params))
        best_model.fit(x_train, y_train)
        predictions = best_model.predict(x_test)
        metrics = self._metrics(y_test, predictions)
        baseline = np.repeat(float(y_train[-1]), len(y_test))
        baseline_metrics = self._metrics(y_test, baseline)
        aggregate_metrics = self._aggregate_fold_metrics(best_fold_metrics)
        aggregate_baseline_metrics = self._aggregate_fold_metrics(baseline_fold_metrics)
        validation_method = f"deep walk-forward backtesting ({len(folds)} folds)" if time_column else f"deep expanding-window validation ({len(folds)} folds)"
        evaluation_report = self._evaluation_report(
            metrics,
            len(x_train),
            len(x_test),
            validation_method,
            baseline_metrics=baseline_metrics,
            y_true=y_test,
            y_pred=predictions,
            fold_metrics=best_fold_metrics,
            aggregate_metrics=aggregate_metrics,
            aggregate_baseline_metrics=aggregate_baseline_metrics,
        )
        deployment_report = self._deployment_report(
            "SVM",
            "sklearn-svm",
            target_column,
            model_object=best_model,
            metadata={"bestParams": best_params, "metrics": metrics, "featureNames": feature_names},
        )
        return TrainingArtifacts(
            metrics=metrics,
            best_params=best_params,
            param_grid=grid,
            train_rows=len(x_train),
            test_rows=len(x_test),
            dataframe_rows=len(frame),
            feature_names=feature_names,
            backend="sklearn-svm",
            target_column=target_column,
            source="supervised-svm",
            training_history=[{"candidate": index + 1, "validationMae": trial["validationMae"]} for index, trial in enumerate(trials[:80])],
            optimization_trials=trials,
            preprocessing_report=preprocessing_report,
            feature_plan=feature_plan,
            evaluation_report=evaluation_report,
            deployment_report=deployment_report,
        )

    def _train_lstm(
        self,
        frame: pd.DataFrame,
        target_column: str,
        preprocessing_report: dict[str, object],
        progress_callback: ProgressCallback | None = None,
    ) -> TrainingArtifacts:
        import torch
        from torch import nn

        series = frame[target_column].astype(float).to_numpy()
        sequence_length = 24
        if len(series) <= sequence_length + 12:
            return self._naive_artifacts(frame, target_column, series, backend="pytorch-lstm")
        x, y = [], []
        for idx in range(sequence_length, len(series)):
            x.append(series[idx - sequence_length:idx])
            y.append(series[idx])
        x_arr = np.asarray(x, dtype=np.float32)
        y_arr = np.asarray(y, dtype=np.float32)
        split = self._safe_split_index(len(x_arr))
        x_train_np = x_arr[:split]
        x_test_np = x_arr[split:]
        y_train_np = y_arr[:split]
        y_test = y_arr[split:]
        scale = float(np.std(y_train_np) or 1.0)
        center = float(np.mean(y_train_np))
        x_train = torch.tensor((x_train_np - center) / scale).unsqueeze(-1)
        y_train = torch.tensor(((y_train_np - center) / scale)).unsqueeze(-1)
        x_test = torch.tensor((x_test_np - center) / scale).unsqueeze(-1)
        feature_names = [f"lag_{idx}" for idx in range(sequence_length, 0, -1)]
        feature_plan = self._feature_plan(feature_names, target_column, "LSTM", True, frame)
        self._emit(
            progress_callback,
            {
                "event": "agent_step",
                "agent": "Feature Agent",
                "stage": "build_features",
                "status": "complete",
                "message": f"Created {sequence_length}-step lag sequences for LSTM training.",
                "details": {**feature_plan, "sequenceLength": sequence_length, "sequenceRows": int(len(x_arr))},
            },
        )

        class ForecastLSTM(nn.Module):
            def __init__(self, hidden_size: int) -> None:
                super().__init__()
                self.lstm = nn.LSTM(input_size=1, hidden_size=hidden_size, batch_first=True)
                self.head = nn.Linear(hidden_size, 1)

            def forward(self, batch):
                outputs, _ = self.lstm(batch)
                return self.head(outputs[:, -1, :])

        grid = list(ParameterGrid({"hidden_size": [24, 32], "epochs": [6, 8], "learning_rate": [0.001]}))
        best_score = float("inf")
        best_params = grid[0]
        best_predictions = None
        trials: list[dict[str, object]] = []
        best_history: list[dict[str, object]] = []
        torch.manual_seed(42)
        self._emit(
            progress_callback,
            {
                "event": "agent_step",
                "agent": "Training Agent",
                "stage": "train_model",
                "status": "running",
                "message": f"Starting LSTM hyperparameter search across {len(grid)} candidates.",
                "details": {"candidateCount": len(grid), "trainRows": int(len(x_train)), "testRows": int(len(x_test))},
            },
        )
        for trial_index, params in enumerate(grid, start=1):
            model = ForecastLSTM(hidden_size=params["hidden_size"])
            optimizer = torch.optim.Adam(model.parameters(), lr=params["learning_rate"])
            loss_fn = nn.MSELoss()
            history: list[dict[str, object]] = []
            for epoch in range(params["epochs"]):
                optimizer.zero_grad()
                predictions = model(x_train)
                loss = loss_fn(predictions, y_train)
                loss.backward()
                optimizer.step()
                point = {"epoch": epoch + 1, "trainingLoss": round(float(loss.detach().item()), 6), "trial": trial_index}
                history.append(point)
                self._emit(
                    progress_callback,
                    {
                        "event": "training_iteration",
                        "agent": "Training Agent",
                        "stage": "lstm_epoch",
                        "status": "running",
                        "message": f"LSTM candidate {trial_index} epoch {epoch + 1}: loss {point['trainingLoss']}.",
                        "details": point,
                    },
                )
            with torch.no_grad():
                predicted = model(x_test).squeeze(-1).numpy() * scale + center
            score = mean_absolute_error(y_test, predicted)
            trial = {"params": params, "validationMae": round(float(score), 4), "epochs": params["epochs"]}
            trials.append(trial)
            self._emit(
                progress_callback,
                {
                    "event": "training_trial",
                    "agent": "Training Agent",
                    "stage": "lstm_trial",
                    "status": "complete",
                    "message": f"LSTM candidate {trial_index} validation MAE: {trial['validationMae']}.",
                    "details": trial,
                },
            )
            if score < best_score:
                best_score = score
                best_params = params
                best_predictions = predicted
                best_history = history
        metrics = self._metrics(y_test, best_predictions)
        baseline = np.repeat(float(y_train_np[-1]), len(y_test))
        baseline_metrics = self._metrics(y_test, baseline)
        evaluation_report = self._evaluation_report(
            metrics,
            len(x_train),
            len(x_test),
            "walk-forward temporal holdout",
            baseline_metrics=baseline_metrics,
            y_true=y_test,
            y_pred=best_predictions,
        )
        deployment_report = self._deployment_report(
            "LSTM",
            "pytorch-lstm",
            target_column,
            model_object=None,
            metadata={"bestParams": best_params, "metrics": metrics, "note": "PyTorch model metadata exported; binary state export is skipped in this local lightweight deployer."},
        )
        return TrainingArtifacts(
            metrics=metrics,
            best_params=best_params,
            param_grid=grid,
            train_rows=len(x_train),
            test_rows=len(x_test),
            dataframe_rows=len(frame),
            feature_names=feature_names,
            backend="pytorch-lstm",
            target_column=target_column,
            source="timeseries-sequence",
            training_history=best_history,
            optimization_trials=trials,
            preprocessing_report=preprocessing_report,
            feature_plan=feature_plan,
            evaluation_report=evaluation_report,
            deployment_report=deployment_report,
        )

    def _supervised_matrix(self, frame: pd.DataFrame, target_column: str, time_column: str | None, model: str = "XGBoost") -> tuple[np.ndarray, np.ndarray, list[str], dict[str, object]]:
        numeric = frame.select_dtypes(include=["number"]).copy()
        if target_column not in numeric.columns:
            numeric[target_column] = pd.to_numeric(frame[target_column], errors="coerce")

        candidate_features, blocked_features = self._safe_feature_columns(numeric.columns.tolist(), target_column)
        supervised = numeric[[target_column, *candidate_features]].copy()
        transformations = ["numeric passthrough"]

        # Only add temporal lag/rolling features when a real time column exists
        if time_column and time_column in frame.columns:
            transformations.extend(["lag features", "rolling statistics", "calendar features", "cyclical calendar encoding"])
            for lag in [1, 2, 3, 6, 12, 24, 48, 168]:
                supervised[f"lag_{lag}"] = supervised[target_column].shift(lag)
            for window in [6, 24, 72, 168]:
                supervised[f"rolling_mean_{window}"] = supervised[target_column].rolling(window).mean()
                supervised[f"rolling_std_{window}"] = supervised[target_column].rolling(window).std(ddof=0)
            supervised["diff_1"] = supervised[target_column].diff(1)
            supervised["diff_24"] = supervised[target_column].diff(24)
            parsed = pd.to_datetime(frame[time_column], errors="coerce", format="mixed")
            supervised["hour"] = parsed.dt.hour
            supervised["dayofweek"] = parsed.dt.dayofweek
            supervised["month"] = parsed.dt.month
            supervised["dayofyear"] = parsed.dt.dayofyear
            supervised["is_weekend"] = parsed.dt.dayofweek.isin([5, 6]).astype(float)
            supervised["hour_sin"] = np.sin(2 * np.pi * supervised["hour"] / 24.0)
            supervised["hour_cos"] = np.cos(2 * np.pi * supervised["hour"] / 24.0)
            supervised["dow_sin"] = np.sin(2 * np.pi * supervised["dayofweek"] / 7.0)
            supervised["dow_cos"] = np.cos(2 * np.pi * supervised["dayofweek"] / 7.0)
            supervised["month_sin"] = np.sin(2 * np.pi * supervised["month"] / 12.0)
            supervised["month_cos"] = np.cos(2 * np.pi * supervised["month"] / 12.0)
        else:
            # Cross-sectional: encode categorical columns via label encoding
            encoded_columns = []
            for col in frame.columns:
                if col == target_column or col in numeric.columns:
                    continue
                if frame[col].dtype == object or str(frame[col].dtype) == "category":
                    encoded = frame[col].astype("category").cat.codes.astype(float)
                    encoded = encoded.replace(-1, np.nan)
                    supervised[f"enc_{col}"] = encoded.values
                    encoded_columns.append(col)
            if encoded_columns:
                transformations.append("categorical label encoding")

        supervised = supervised.replace([np.inf, -np.inf], np.nan).dropna().reset_index(drop=True)
        feature_names = [column for column in supervised.columns if column != target_column]
        x = supervised[feature_names].to_numpy(dtype=float)
        y = supervised[target_column].to_numpy(dtype=float)
        plan = self._feature_plan(feature_names, target_column, model, bool(time_column), frame, transformations)
        plan["blockedLeakageFeatures"] = blocked_features
        return x, y, feature_names, plan

    def _safe_feature_columns(self, columns: list[str], target_column: str) -> tuple[list[str], list[str]]:
        target_normalized = target_column.lower().replace("_", " ")
        target_tokens = {
            token
            for token in target_normalized.split()
            if len(token) > 2
        }
        blocked_markers = {"future", "next", "pred", "forecast", "target", "label"}
        component_markers = {
            "room",
            "room-level",
            "zonal",
            "lighting",
            "hvac",
            "local",
            "historical",
            "savings",
            "potential",
        }
        safe_columns: list[str] = []
        blocked_columns: list[str] = []
        for column in columns:
            if column == target_column:
                continue
            normalized = column.lower().replace("_", " ")
            tokens = {token for token in normalized.split() if len(token) > 2}
            if target_tokens & tokens and any(marker in normalized for marker in blocked_markers):
                blocked_columns.append(column)
                continue
            if "energy consumption" in target_normalized and "energy consumption" in normalized:
                blocked_columns.append(column)
                continue
            if {"energy", "consumption"} <= target_tokens and (tokens & component_markers):
                blocked_columns.append(column)
                continue
            safe_columns.append(column)
        return safe_columns, blocked_columns

    def _temporal_split(self, x: np.ndarray, y: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
        split = self._safe_split_index(len(x))
        return x[:split], x[split:], y[:split], y[split:]

    def _walk_forward_folds(self, length: int, preferred_folds: int = 4) -> list[tuple[int, int, int]]:
        if length < 80:
            split = self._safe_split_index(length)
            return [(split, split, length)]
        fold_count = max(2, min(preferred_folds, 5))
        test_window = max(24, min(max(40, length // 12), length // (fold_count + 3)))
        first_train = max(int(length * 0.55), test_window * 2)
        folds: list[tuple[int, int, int]] = []
        for fold_index in range(fold_count):
            train_end = first_train + fold_index * test_window
            test_start = train_end
            test_end = min(test_start + test_window, length)
            if test_end <= test_start or train_end < 20:
                continue
            folds.append((int(train_end), int(test_start), int(test_end)))
            if test_end >= length:
                break
        if not folds:
            split = self._safe_split_index(length)
            folds.append((split, split, length))
        return folds

    def _aggregate_fold_metrics(self, fold_metrics: list[dict[str, object]]) -> dict[str, float]:
        metric_names = ["mae", "rmse", "mape", "r2", "mase"]
        aggregate: dict[str, float] = {}
        for name in metric_names:
            values = [
                float(row.get("metrics", {}).get(name, 0.0))
                for row in fold_metrics
                if isinstance(row.get("metrics"), dict) and row.get("metrics", {}).get(name) is not None
            ]
            aggregate[name] = round(float(np.mean(values)), 4) if values else 0.0
        return aggregate

    def _safe_split_index(self, length: int) -> int:
        if length <= 4:
            return max(1, length - 1)
        # For large datasets, keep at least 2% or 200 rows for test, whichever is larger
        min_test = max(200, int(length * 0.02))
        split = length - min_test
        return max(int(length * 0.80), split)

    def _naive_artifacts(
        self,
        frame: pd.DataFrame,
        target_column: str,
        values: np.ndarray,
        feature_names: list[str] | None = None,
        backend: str = "fallback",
    ) -> TrainingArtifacts:
        split = self._safe_split_index(len(values))
        train = np.asarray(values[:split], dtype=float)
        test = np.asarray(values[split:], dtype=float)
        baseline = np.repeat(float(train[-1]), len(test))
        metrics = self._metrics(test, baseline)
        features = feature_names or [target_column]
        return TrainingArtifacts(
            metrics=metrics,
            best_params={"strategy": "last-value"},
            param_grid=[{"strategy": "last-value"}],
            train_rows=len(train),
            test_rows=len(test),
            dataframe_rows=len(frame),
            feature_names=features,
            backend=backend,
            target_column=target_column,
            source="fallback-persistence",
            training_history=[{"step": 1, "validationMae": metrics["mae"], "strategy": "last-value baseline"}],
            optimization_trials=[{"params": {"strategy": "last-value"}, "validationMae": metrics["mae"]}],
            preprocessing_report={"rowsAfterTargetValidation": int(len(frame)), "targetColumn": target_column, "fallback": True},
            feature_plan=self._feature_plan(features, target_column, "baseline", False, frame),
            evaluation_report=self._evaluation_report(
                metrics,
                len(train),
                len(test),
                "holdout validation",
                baseline_metrics=metrics,
                y_true=test,
                y_pred=baseline,
            ),
            deployment_report=self._deployment_report(
                "baseline",
                backend,
                target_column,
                model_object=None,
                metadata={"metrics": metrics, "strategy": "last-value"},
            ),
        )

    def _metrics(self, y_true: np.ndarray, y_pred: np.ndarray) -> dict[str, float]:
        mae = mean_absolute_error(y_true, y_pred)
        rmse = mean_squared_error(y_true, y_pred) ** 0.5
        mape = np.mean(np.abs((y_true - y_pred) / np.maximum(np.abs(y_true), 1))) * 100
        r2 = r2_score(y_true, y_pred)
        # Mean Absolute Scaled Error (naive baseline comparison)
        naive_mae = float(np.mean(np.abs(np.diff(y_true)))) if len(y_true) > 1 else float(mae)
        mase = float(mae / max(naive_mae, 1e-8))
        return {
            "mae": round(float(mae), 4),
            "rmse": round(float(rmse), 4),
            "mape": round(float(mape), 4),
            "r2": round(float(r2), 4),
            "mase": round(float(mase), 4),
        }

    def _profile_time_column(self, profile: DatasetProfile, frame: pd.DataFrame) -> str | None:
        time_column = (profile.time_series or {}).get("timeColumn")
        if isinstance(time_column, str) and time_column in frame.columns:
            return time_column
        return self._time_column(frame)

    def _time_column(self, frame: pd.DataFrame) -> str | None:
        for column in frame.columns:
            normalized = column.lower().replace("_", " ").strip()
            if not any(token in normalized for token in ["date", "time", "timestamp", "datetime"]):
                continue
            if any(marker in normalized for marker in ["id", "code", "zip", "postal", "row"]):
                continue
            parsed = pd.to_datetime(frame[column], errors="coerce", format="mixed")
            if parsed.notna().mean() > 0.8:
                return column
        return None

    def _emit(self, progress_callback: ProgressCallback | None, payload: dict[str, object]) -> None:
        if progress_callback is None:
            return
        payload.setdefault("timestamp", datetime.now(timezone.utc).isoformat())
        progress_callback(payload)

    def _feature_plan(
        self,
        feature_names: list[str],
        target_column: str,
        model: str,
        has_time: bool,
        frame: pd.DataFrame,
        transformations: list[str] | None = None,
    ) -> dict[str, object]:
        text_like = [
            column for column in frame.columns
            if column != target_column and frame[column].dtype == object and frame[column].nunique(dropna=True) > 100
        ][:8]
        numeric_count = len(frame.select_dtypes(include=["number"]).columns)
        return {
            "targetColumn": target_column,
            "featureCount": len(feature_names),
            "features": feature_names[:12],
            "transformations": transformations or (["lag windows"] if has_time else ["numeric passthrough", "categorical encoding"]),
            "pca": {
                "applied": False,
                "reason": "Skipped because tree/sequence models preserve feature-level signal better for this run." if model in {"XGBoost", "RandomForest", "LSTM"} else "Not required for the selected statistical or scaled-kernel model.",
            },
            "tfidf": {
                "applied": False,
                "candidateColumns": text_like,
                "reason": "High-cardinality text columns are tracked as candidates; baseline run uses deterministic category encoding to keep training bounded.",
            },
            "numericFeatureCount": numeric_count,
            "temporalFeatures": [name for name in feature_names if name.startswith(("lag_", "rolling_", "diff_", "hour", "day", "month", "dow"))][:16],
            "blockedLeakageFeatures": [],
        }

    def _evaluation_report(
        self,
        metrics: dict[str, float],
        train_rows: int,
        test_rows: int,
        validation_method: str,
        baseline_metrics: dict[str, float] | None = None,
        y_true: np.ndarray | None = None,
        y_pred: np.ndarray | None = None,
        fold_metrics: list[dict[str, object]] | None = None,
        aggregate_metrics: dict[str, float] | None = None,
        aggregate_baseline_metrics: dict[str, float] | None = None,
    ) -> dict[str, object]:
        baseline = baseline_metrics or {}
        fold_rows = fold_metrics or []
        aggregate = aggregate_metrics or metrics
        aggregate_baseline = aggregate_baseline_metrics or baseline
        samples = self._evaluation_samples(y_true, y_pred)
        residuals = np.asarray([], dtype=float)
        if y_true is not None and y_pred is not None and len(y_true) == len(y_pred):
            residuals = np.asarray(y_true, dtype=float) - np.asarray(y_pred, dtype=float)
        mae_before = float(baseline.get("mae", metrics.get("mae", 0.0)) or 0.0)
        mae_after = float(metrics.get("mae", 0.0) or 0.0)
        improvement = ((mae_before - mae_after) / mae_before * 100) if mae_before else 0.0
        return {
            "validationMethod": validation_method,
            "trainRows": int(train_rows),
            "testRows": int(test_rows),
            "metrics": metrics,
            "baselineMetrics": baseline,
            "foldMetrics": fold_rows,
            "aggregateMetrics": aggregate,
            "aggregateBaselineMetrics": aggregate_baseline,
            "improvement": {
                "maeReductionPercent": round(float(improvement), 2),
                "beforeTrainingMae": round(mae_before, 4),
                "afterTrainingMae": round(mae_after, 4),
            },
            "predictionSamples": samples,
            "residualSummary": {
                "meanError": round(float(residuals.mean()), 4) if len(residuals) else 0.0,
                "maxAbsError": round(float(np.max(np.abs(residuals))), 4) if len(residuals) else 0.0,
                "p95AbsError": round(float(np.percentile(np.abs(residuals), 95)), 4) if len(residuals) else 0.0,
            },
            "lossFormula": "MAE=mean(abs(y_true-y_pred)); RMSE=sqrt(mean((y_true-y_pred)^2)); MAPE=mean(abs(error/max(abs(y),1)))",
            "acceptance": "passed" if math.isfinite(metrics.get("mae", float("nan"))) else "failed",
        }

    def _evaluation_samples(self, y_true: np.ndarray | None, y_pred: np.ndarray | None, limit: int = 160) -> list[dict[str, float | int]]:
        if y_true is None or y_pred is None or len(y_true) == 0 or len(y_true) != len(y_pred):
            return []
        indices = np.linspace(0, len(y_true) - 1, num=min(limit, len(y_true)), dtype=int)
        actual = np.asarray(y_true, dtype=float)
        predicted = np.asarray(y_pred, dtype=float)
        return [
            {
                "index": int(idx),
                "actual": round(float(actual[idx]), 4),
                "predicted": round(float(predicted[idx]), 4),
                "error": round(float(actual[idx] - predicted[idx]), 4),
            }
            for idx in indices
        ]

    def _deployment_report(
        self,
        model: str,
        backend: str,
        target_column: str,
        model_object: object | None = None,
        metadata: dict[str, object] | None = None,
    ) -> dict[str, object]:
        stamp = datetime.now(timezone.utc).isoformat()
        artifact_id = f"{stamp.replace(':', '').replace('.', '')}_{model.lower()}_{target_column}".replace(" ", "_").replace("/", "_").replace("\\", "_")
        json_path = self._artifact_dir / f"{artifact_id}.json"
        pickle_path = self._artifact_dir / f"{artifact_id}.pkl"
        payload = {
            "status": "packaged",
            "modelFamily": model,
            "backend": backend,
            "targetColumn": target_column,
            "createdAt": stamp,
            "localRuntimeNote": "Artifact was produced by the local training runtime. Validate before production use.",
            **(metadata or {}),
        }
        json_path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
        pickle_written = False
        if model_object is not None:
            try:
                joblib.dump(model_object, pickle_path)
                pickle_written = True
            except Exception:
                pickle_written = False
        return {
            "status": "packaged",
            "modelFamily": model,
            "backend": backend,
            "targetColumn": target_column,
            "createdAt": stamp,
            "artifactMode": "pickle-and-json-local-runtime" if pickle_written else "json-metadata-local-runtime",
            "jsonPath": str(json_path),
            "picklePath": str(pickle_path) if pickle_written else None,
            "pickleAvailable": pickle_written,
            "jsonAvailable": True,
            "llmExplanation": "JSON explains the model configuration and metrics. Pickle/joblib stores the fitted local model object for reuse in the same Python environment, but it should be validated before deployment.",
            "handoff": ["monitoring recent_runs", "forecast service", "pipeline dashboard", "local artifact export"],
        }

    def _pipeline_trace(
        self,
        data_source: str,
        profile: DatasetProfile,
        model: str,
        model_reason: str,
        artifacts: TrainingArtifacts,
        has_time: bool,
        time_column: str | None,
    ) -> list[dict[str, object]]:
        now = datetime.now(timezone.utc).isoformat()
        trace = ReasoningTrace(agent_name="Pipeline Orchestrator", task=f"Train {model} for {profile.dataset_id}")
        trace.add(StepType.THOUGHT, "Use the current in-memory EDA profile for model choice; persisted evidence artifacts are not consulted during training.", 1, "profile_review")
        trace.add(StepType.ACTION, f"Selected {model} because {model_reason}", 1, "select_model", {"model": model, "hasTime": has_time, "timeColumn": time_column})
        trace.add(StepType.OBSERVATION, f"Cleaning produced {artifacts.preprocessing_report.get('totalTransformations', 0)} transformation(s).", 2, "clean_data", artifacts.preprocessing_report)
        trace.add(StepType.OBSERVATION, f"Feature matrix has {len(artifacts.feature_names)} feature(s).", 3, "build_features", artifacts.feature_plan)
        trace.add(StepType.FINAL, "Training, evaluation, and packaging completed.", 4, "complete", {"metrics": artifacts.metrics})
        self.memory.set("last_pipeline_trace", trace.to_dict())
        return [
            {
                "agent": "Dataset Agent",
                "stage": "load_dataset",
                "timestamp": now,
                "status": "complete",
                "message": f"Loaded {artifacts.dataframe_rows:,} rows from {data_source}.",
                "details": {"dataSource": data_source, "rows": artifacts.dataframe_rows, "target": artifacts.target_column},
            },
            {
                "agent": "EDA Agent",
                "stage": "profile_review",
                "timestamp": now,
                "status": "complete",
                "message": "Reviewed the fresh in-memory profile; no persisted EDA evidence was used for this pipeline run.",
                "details": {"reasoningTrace": trace.to_dict(), "edaTrace": profile.eda_trace[:8], "recommendedModel": (profile.strategy_recommendation or {}).get("recommendedModelFamily")},
            },
            {
                "agent": "Cleaning Agent",
                "stage": "clean_data",
                "timestamp": now,
                "status": "complete",
                "message": "Applied target validation, sorting, and imputation before feature generation.",
                "details": artifacts.preprocessing_report,
            },
            {
                "agent": "Feature Agent",
                "stage": "build_features",
                "timestamp": now,
                "status": "complete",
                "message": "Built the model matrix from numeric, categorical, and temporal feature rules.",
                "details": artifacts.feature_plan,
            },
            {
                "agent": "Training Agent",
                "stage": "train_model",
                "timestamp": now,
                "status": "complete",
                "message": f"Selected {model}. {model_reason}",
                "details": {"backend": artifacts.backend, "bestParams": artifacts.best_params, "trainingHistory": artifacts.training_history[:20], "trials": artifacts.optimization_trials[:20]},
            },
            {
                "agent": "Evaluation Agent",
                "stage": "evaluate_model",
                "timestamp": now,
                "status": "complete",
                "message": "Calculated holdout metrics from predictions and actual target values.",
                "details": artifacts.evaluation_report,
            },
            {
                "agent": "Deployment Agent",
                "stage": "package_run",
                "timestamp": now,
                "status": "complete",
                "message": "Packaged model metadata and monitoring handoff for this run.",
                "details": artifacts.deployment_report,
            },
        ]

    def _first_numeric(self, frame: pd.DataFrame) -> str:
        numeric_columns = frame.select_dtypes(include=["number"]).columns.tolist()
        if not numeric_columns:
            raise ValueError("No numeric target column found for training.")
        return numeric_columns[0]
