from __future__ import annotations

from datetime import datetime, timezone
from time import perf_counter
from typing import Callable, TypedDict

from fastapi import UploadFile
from langgraph.graph import END, START, StateGraph

from app.core.schemas import AnalyzeRequest, DatasetProfile, DatasetRowsResponse, ForecastResponse, PipelineRunRequest, PipelineRunResponse
from app.services.dataset_store import DataSourceError
from app.services.eda import AutoEDAService
from app.services.evidence_store import EDAEvidenceStore
from app.services.dataset_store import DatasetStoreService
from app.services.forecasting import ForecastService
from app.services.intelligence import DatasetIntelligenceService
from app.services.monitoring import MonitoringService
from app.services.pipeline import PipelineService


class OrchestrationState(TypedDict, total=False):
    operation: str
    dataset_id: str
    source_ref: str | None
    pipeline_request: PipelineRunRequest | None
    profile: DatasetProfile
    pipeline_result: PipelineRunResponse


class OrchestrationAgent:
    """Coordinator for dataset handling, profiling, model selection, forecasting, and monitoring."""

    def __init__(
        self,
        eda_service: AutoEDAService,
        intelligence_service: DatasetIntelligenceService,
        pipeline_service: PipelineService,
        forecast_service: ForecastService,
        monitoring_service: MonitoringService,
    ) -> None:
        self.eda_service = eda_service
        self.intelligence_service = intelligence_service
        self.pipeline_service = pipeline_service
        self.forecast_service = forecast_service
        self.monitoring_service = monitoring_service
        self.dataset_store = DatasetStoreService()
        self.evidence_store = EDAEvidenceStore()
        self._profiles: dict[tuple[str, str | None], DatasetProfile] = {}
        self._graph = self._build_graph()

    def clear_runtime_state(self) -> dict[str, int]:
        profile_count = len(self._profiles)
        self._profiles.clear()
        evidence_files = self.evidence_store.clear()
        return {"profileCacheEntries": profile_count, "evidenceFiles": evidence_files}

    def profile_dataset(self, request: AnalyzeRequest) -> DatasetProfile:
        started_at = perf_counter()
        result = self._graph.invoke(
            {
                "operation": "profile",
                "dataset_id": request.dataset_id,
                "source_ref": request.source_ref,
            }
        )
        profile = result["profile"]
        profile.summary["totalTimeMs"] = round((perf_counter() - started_at) * 1000, 1)
        return profile

    def stream_profile_events(self, request: AnalyzeRequest, emit: Callable[[dict[str, object]], None]) -> DatasetProfile:
        started_at = perf_counter()
        profile = self._profile_from_source_streaming(request.dataset_id, request.source_ref, emit)

        self._emit_profile_snapshot(emit, "semantic_embeddings", "running", "Persisting EDA JSON and semantic embedding evidence.", profile)
        explain_started_at = perf_counter()
        profile.evidence_refs = self._persist_eda_evidence(profile)
        self._emit_profile_snapshot(emit, "semantic_embeddings", "complete", "EDA evidence is stored and the LLM gate is ready.", profile)

        self._emit_profile_snapshot(emit, "intelligence_report", "running", "Generating dataset intelligence report from EDA evidence.", profile)
        profile.insights = self.intelligence_service.explain(profile)
        profile.decisions = self._dataset_decisions(profile)
        profile.summary["explainTimeMs"] = round((perf_counter() - explain_started_at) * 1000, 1)
        profile.summary["totalTimeMs"] = round((perf_counter() - started_at) * 1000, 1)
        profile.summary["profileCacheHit"] = False
        self._emit_profile_snapshot(emit, "intelligence_report", "complete", "Dataset intelligence report generated.", profile)
        self._emit_profile_snapshot(emit, "complete", "complete", "EDA completed. Pipeline creation is now unlocked.", profile)
        return profile

    async def profile_uploaded_dataset(self, file: UploadFile) -> DatasetProfile:
        profile = await self.eda_service.profile_upload(file)
        profile = self._enrich_profile(profile)
        self._profiles[self._profile_cache_key(profile.dataset_id, None)] = profile
        return profile

    def run_pipeline(self, request: PipelineRunRequest) -> PipelineRunResponse:
        result = self._graph.invoke(
            {
                "operation": "pipeline",
                "dataset_id": request.dataset_id,
                "source_ref": request.source_ref,
                "pipeline_request": request,
            }
        )
        return result["pipeline_result"]

    def stream_pipeline_events(self, request: PipelineRunRequest, emit: Callable[[dict[str, object]], None]) -> PipelineRunResponse:
        """Run the same deterministic pipeline while emitting LangGraph-style progress events."""
        self._emit_stream(
            emit,
            {
                "event": "agent_step",
                "agent": "Dataset Agent",
                "stage": "resolve_profile",
                "status": "running",
                "message": "Resolving a fresh in-memory dataset profile for this training run.",
                "details": {"datasetId": request.dataset_id, "sourceRef": request.source_ref},
            },
        )
        profile_started_at = perf_counter()
        profile = self._fresh_pipeline_profile(request.dataset_id, request.source_ref)
        self._emit_stream(
            emit,
            {
                "event": "agent_step",
                "agent": "EDA Agent",
                "stage": "profile_ready",
                "status": "complete",
                "message": "Fresh profile is ready; model selection will use current column, quality, and signal analysis.",
                "details": {
                    "elapsedMs": round((perf_counter() - profile_started_at) * 1000, 1),
                    "rows": profile.summary.get("rows"),
                    "columns": profile.summary.get("columns"),
                    "recommendedTarget": profile.validation.get("recommendedTarget"),
                    "recommendedModel": (profile.strategy_recommendation or {}).get("recommendedModelFamily"),
                    "tracePreview": profile.eda_trace[:8],
                },
            },
        )
        result = self.pipeline_service.run(request, profile, progress_callback=emit)
        self.monitoring_service.record_pipeline_run(result)
        return result

    def forecast(self, dataset_id: str) -> ForecastResponse:
        return self.forecast_service.forecast(dataset_id)

    def raw_rows(self, dataset_id: str, page: int = 1, page_size: int = 25, source_ref: str | None = None) -> DatasetRowsResponse:
        profile = self.profile_dataset(AnalyzeRequest(dataset_id=dataset_id, source_ref=source_ref))
        rows, columns, total_rows, source = self.dataset_store.preview_rows(dataset_id, profile, page=page, page_size=page_size, source_ref=source_ref)
        total_pages = max(1, (total_rows + max(page_size, 1) - 1) // max(page_size, 1))
        return DatasetRowsResponse(
            dataset_id=dataset_id,
            source=source,
            page=page,
            page_size=page_size,
            total_rows=total_rows,
            total_pages=total_pages,
            columns=columns,
            rows=rows,
        )

    def _build_graph(self):
        graph = StateGraph(OrchestrationState)
        graph.add_node("load_profile", self._load_profile_node)
        graph.add_node("enrich_profile", self._enrich_profile_node)
        graph.add_node("run_pipeline", self._run_pipeline_node)
        graph.add_node("record_monitoring", self._record_monitoring_node)
        graph.add_edge(START, "load_profile")
        graph.add_edge("load_profile", "enrich_profile")
        graph.add_conditional_edges(
            "enrich_profile",
            self._next_after_profile,
            {
                "run_pipeline": "run_pipeline",
                "end": END,
            },
        )
        graph.add_edge("run_pipeline", "record_monitoring")
        graph.add_edge("record_monitoring", END)
        return graph.compile()

    def _load_profile_node(self, state: OrchestrationState) -> OrchestrationState:
        dataset_id = state["dataset_id"]
        source_ref = state.get("source_ref")
        if state.get("operation") == "pipeline":
            profile = self._profile_from_source(dataset_id, source_ref)
            profile.summary["profileCacheHit"] = False
            return {"profile": profile}

        profile = self._profile_from_source(dataset_id, source_ref)
        profile.summary["profileCacheHit"] = False
        return {"profile": profile}

    def _enrich_profile_node(self, state: OrchestrationState) -> OrchestrationState:
        profile = state["profile"]
        explain_started_at = perf_counter()
        if state.get("operation") == "pipeline":
            profile.evidence_refs = {"llmGate": "not_used", "reason": "Pipeline runs use the fresh in-memory profile instead of persisted EDA evidence."}
            profile.decisions = self._dataset_decisions(profile)
        else:
            profile = self._enrich_profile(profile)
        profile.summary["explainTimeMs"] = round((perf_counter() - explain_started_at) * 1000, 1)
        return {"profile": profile}

    def _run_pipeline_node(self, state: OrchestrationState) -> OrchestrationState:
        request = state.get("pipeline_request")
        if request is None:
            raise ValueError("Pipeline request was not supplied to the orchestration graph.")
        return {"pipeline_result": self.pipeline_service.run(request, state["profile"])}

    def _record_monitoring_node(self, state: OrchestrationState) -> OrchestrationState:
        result = state.get("pipeline_result")
        if result is not None:
            self.monitoring_service.record_pipeline_run(result)
        return {}

    def _next_after_profile(self, state: OrchestrationState) -> str:
        return "run_pipeline" if state.get("operation") == "pipeline" else "end"

    def _profile_from_source(self, dataset_id: str, source_ref: str | None) -> DatasetProfile:
        resolved_source_ref = self._resolve_source_ref(dataset_id, source_ref)
        if not resolved_source_ref:
            raise DataSourceError(
                f"Dataset `{dataset_id}` does not include a Kaggle/local source reference. "
                "Choose a Kaggle/local-storage dataset card with a real `ref` so EDA can scan the real dataframe."
            )
        real_dataset_requested = True

        # Always attempt to load real data first (Kaggle or local CSV)
        load_started_at = perf_counter()
        frame, data_source = self.dataset_store.load_training_frame(
            dataset_id,
            self._fallback_profile(dataset_id),
            resolved_source_ref,
            require_real=real_dataset_requested,
        )
        load_ms = round((perf_counter() - load_started_at) * 1000, 1)
        profile_started_at = perf_counter()
        profile = self.eda_service.profile_dataframe(dataset_id, frame)
        profile.summary["loadTimeMs"] = load_ms
        profile.summary["profileTimeMs"] = round((perf_counter() - profile_started_at) * 1000, 1)
        profile.summary["dataSource"] = data_source
        profile.summary["profileInputSource"] = data_source
        profile.summary["rowsAnalyzed"] = int(len(frame))
        profile.summary["rowsScanned"] = int(len(frame))
        profile.summary["columnsScanned"] = int(len(frame.columns))
        profile.summary["targetColumn"] = profile.validation.get("recommendedTarget")
        profile.summary["syntheticFallback"] = False
        profile.summary["sourceRef"] = resolved_source_ref
        profile.summary["realDataLoaded"] = True
        return profile

    def _profile_from_source_streaming(self, dataset_id: str, source_ref: str | None, emit: Callable[[dict[str, object]], None]) -> DatasetProfile:
        resolved_source_ref = self._resolve_source_ref(dataset_id, source_ref)
        if not resolved_source_ref:
            raise DataSourceError(
                f"Dataset `{dataset_id}` does not include a Kaggle/local source reference. "
                "Choose a Kaggle/local-storage dataset card with a real `ref` so EDA can scan the real dataframe."
            )
        real_dataset_requested = True

        self._emit_stream(
            emit,
            {
                "event": "eda_step",
                "agent": "Dataset Agent",
                "stage": "retrieve_dataset",
                "status": "running",
                "message": "Fetching dataset file and preparing dataframe load.",
                "details": {"datasetId": dataset_id, "sourceRef": resolved_source_ref},
            },
        )
        load_started_at = perf_counter()
        frame, data_source = self.dataset_store.load_training_frame(
            dataset_id,
            self._fallback_profile(dataset_id),
            resolved_source_ref,
            require_real=real_dataset_requested,
        )
        load_ms = round((perf_counter() - load_started_at) * 1000, 1)
        self._emit_stream(
            emit,
            {
                "event": "eda_step",
                "agent": "Dataset Agent",
                "stage": "retrieve_dataset",
                "status": "complete",
                "message": f"Dataset loaded from {data_source}.",
                "details": {"rows": int(len(frame)), "columns": int(len(frame.columns)), "loadTimeMs": load_ms, "dataSource": data_source},
            },
        )
        profile = self._profile_loaded_frame(dataset_id, resolved_source_ref, frame, data_source, load_ms, emit)
        profile.summary["profileCacheHit"] = False
        return profile

    def _profile_loaded_frame(
        self,
        dataset_id: str,
        source_ref: str | None,
        frame,
        data_source: str,
        load_ms: float,
        emit: Callable[[dict[str, object]], None],
    ) -> DatasetProfile:
        self._emit_stream(
            emit,
            {
                "event": "eda_step",
                "agent": "EDA Agent",
                "stage": "statistical_profile",
                "status": "running",
                "message": "Running statistical profiling, type inference, visual sampling, and temporal detection.",
                "details": {"rows": int(len(frame)), "columns": int(len(frame.columns))},
            },
        )
        profile_started_at = perf_counter()
        profile = self.eda_service.profile_dataframe(dataset_id, frame)
        profile.summary["loadTimeMs"] = load_ms
        profile.summary["profileTimeMs"] = round((perf_counter() - profile_started_at) * 1000, 1)
        profile.summary["dataSource"] = data_source
        profile.summary["profileInputSource"] = data_source
        profile.summary["rowsAnalyzed"] = int(len(frame))
        profile.summary["syntheticFallback"] = data_source == "synthetic-profile"
        if source_ref:
            profile.summary["sourceRef"] = source_ref
        profile.summary["realDataLoaded"] = data_source != "synthetic-profile"
        self._emit_profile_snapshot(emit, "statistical_profile", "complete", "Column profiling and data quality analysis completed.", profile)
        self._emit_profile_snapshot(emit, "temporal_analysis", "complete", "Time-series structure, cadence, anomalies, and drift signals evaluated.", profile)
        self._emit_profile_snapshot(emit, "forecastability_analysis", "complete", "Forecastability score and model strategy recommendation calculated.", profile)
        return profile

    def _enrich_profile(self, profile: DatasetProfile) -> DatasetProfile:
        profile.evidence_refs = self._persist_eda_evidence(profile)
        profile.insights = self.intelligence_service.explain(profile)
        profile.decisions = self._dataset_decisions(profile)
        return profile

    def _persist_eda_evidence(self, profile: DatasetProfile) -> dict[str, object]:
        try:
            return self.evidence_store.persist(profile)
        except Exception as exc:
            return {"llmGate": "blocked", "error": str(exc)}

    def _fresh_pipeline_profile(self, dataset_id: str, source_ref: str | None) -> DatasetProfile:
        profile = self._profile_from_source(dataset_id, source_ref)
        profile.summary["profileCacheHit"] = False
        profile.evidence_refs = {"llmGate": "not_used", "reason": "Pipeline run avoids persisted evidence artifacts."}
        profile.decisions = self._dataset_decisions(profile)
        return profile

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

    def _dataset_decisions(self, profile: DatasetProfile) -> list[str]:
        decisions = []
        has_time = bool(profile.time_series.get("valid"))
        target = (profile.structural_intelligence or {}).get("targetColumn") or profile.validation.get("recommendedTarget")
        missing = float(profile.summary.get("missingPercent", 0) or 0)
        rows = int(profile.summary.get("rows", 0) or 0)
        model = (profile.strategy_recommendation or {}).get("recommendedModelFamily", "XGBoost")
        fc_score = float((profile.forecastability or {}).get("score") or 0)
        fc_grade = (profile.forecastability or {}).get("grade", "unknown")
        domain = (profile.semantic_understanding or {}).get("inferredDomain", "general")
        trust = float((profile.quality_intelligence or {}).get("trustScore") or 0)
        strong_signals = [
            s["feature"] for s in ((profile.feature_intelligence or {}).get("predictiveSignals") or [])
            if max(float(s.get("sameTimeCorrelation", 0)), float(s.get("lagInfluence", 0))) >= 0.45
        ]
        redundant = (profile.feature_intelligence or {}).get("redundantFeatures") or []
        anomaly_count = len((profile.temporal_behavior or {}).get("anomalies") or [])
        dataset_type = "time-series" if has_time else "cross-sectional"

        # Decision 1: dataset type and target
        if has_time:
            tc = profile.time_series.get("timeColumn")
            freq = profile.time_series.get("frequency", "unknown")
            decisions.append(f"Identified as a {domain} time-series dataset. Time column `{tc}` at {freq} frequency. Target set to `{target}`.")
        else:
            decisions.append(f"Identified as a {domain} cross-sectional dataset with {rows:,} rows. No time index detected. Target set to `{target}` for regression modeling.")

        # Decision 2: data quality
        if missing > 10:
            decisions.append(f"High missingness ({missing:.1f}%) detected. Imputation required before training — forward-fill for time-series, median/mode for cross-sectional.")
        elif missing > 0:
            decisions.append(f"Low missingness ({missing:.1f}%, trust score {trust:.0f}/100). Standard imputation applied during preprocessing.")
        else:
            decisions.append(f"Dataset is complete with 0% missing values (trust score {trust:.0f}/100). No imputation required.")

        # Decision 3: predictive signals
        if strong_signals:
            decisions.append(f"Strong predictive signals identified: {', '.join(strong_signals[:4])}. These features will be prioritized in the feature matrix.")
        elif redundant:
            pairs = ["+".join(r["features"]) for r in redundant[:2]]
            decisions.append(f"No strong individual signals found. Redundant feature pairs detected: {', '.join(pairs)}. Consider dimensionality reduction.")
        else:
            decisions.append("Feature signal analysis complete. All features will be included in the initial model; importance will be evaluated post-training.")

        # Decision 4: model selection rationale
        if has_time and anomaly_count > 0:
            decisions.append(f"{anomaly_count} temporal anomalies detected. Robust loss function and anomaly-aware preprocessing will be applied before {model} training.")
        else:
            decisions.append(f"Selected {model} based on {dataset_type} structure, {rows:,} rows, and forecastability score {fc_score:.0f}% ({fc_grade}). {(profile.strategy_recommendation or {}).get('reason', '')}")

        decisions.append("LLM output reserved for interpretability only. All modeling decisions are deterministic and driven by EDA metrics.")
        return decisions

    def _profile_cache_key(self, dataset_id: str, source_ref: str | None) -> tuple[str, str | None]:
        return (dataset_id, source_ref)

    def _catalog_source_ref(self, dataset_id: str) -> str | None:
        try:
            from app.services.catalog import CATALOG

            for dataset in CATALOG:
                if dataset.id == dataset_id:
                    return dataset.ref
            return None
        except Exception:
            return None

    def _resolve_source_ref(self, dataset_id: str, source_ref: str | None) -> str | None:
        if source_ref:
            return source_ref
        catalog_ref = self._catalog_source_ref(dataset_id)
        if catalog_ref:
            return catalog_ref
        if "--" in dataset_id:
            owner, slug = dataset_id.split("--", 1)
            if owner and slug:
                return f"{owner}/{slug}"
        return None

    def _emit_stream(self, emit: Callable[[dict[str, object]], None], payload: dict[str, object]) -> None:
        payload.setdefault("timestamp", datetime.now(timezone.utc).isoformat())
        emit(payload)

    def _emit_profile_snapshot(
        self,
        emit: Callable[[dict[str, object]], None],
        stage: str,
        status: str,
        message: str,
        profile: DatasetProfile,
    ) -> None:
        self._emit_stream(
            emit,
            {
                "event": "eda_step",
                "agent": "EDA Agent" if stage != "retrieve_dataset" else "Dataset Agent",
                "stage": stage,
                "status": status,
                "message": message,
                "details": {
                    "title": profile.title,
                    "rows": profile.summary.get("rows"),
                    "columns": profile.summary.get("columns"),
                    "missingPercent": profile.summary.get("missingPercent"),
                    "timeSeriesValidated": profile.summary.get("timeSeriesValidated"),
                    "timeColumn": (profile.time_series or {}).get("timeColumn"),
                    "frequency": (profile.time_series or {}).get("frequency"),
                    "recommendedTarget": profile.validation.get("recommendedTarget"),
                    "forecastability": (profile.forecastability or {}).get("score"),
                    "recommendedModel": (profile.strategy_recommendation or {}).get("recommendedModelFamily"),
                    "trustScore": (profile.quality_intelligence or {}).get("trustScore"),
                },
            },
        )
