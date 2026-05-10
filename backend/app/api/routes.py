import json
from queue import Empty, Queue
from threading import Thread
from typing import Literal

from fastapi import APIRouter, UploadFile, File
from fastapi.responses import StreamingResponse

from app.agents.orchestrator import OrchestrationAgent
from app.core.schemas import (
    AnalyzeRequest,
    DatasetProfile,
    DatasetRowsResponse,
    DatasetSearchResponse,
    ForecastResponse,
    PipelineRunRequest,
    PipelineRunResponse,
    SearchRequest,
    SystemMonitorResponse,
)
from app.services.discovery import DatasetDiscoveryService
from app.services.eda import AutoEDAService
from app.services.forecasting import ForecastService
from app.services.intelligence import DatasetIntelligenceService
from app.services.monitoring import MonitoringService
from app.services.pipeline import PipelineService

router = APIRouter()

discovery_service = DatasetDiscoveryService()
eda_service = AutoEDAService()
intelligence_service = DatasetIntelligenceService()
pipeline_service = PipelineService()
forecast_service = ForecastService()
monitoring_service = MonitoringService()
orchestrator = OrchestrationAgent(
    eda_service=eda_service,
    intelligence_service=intelligence_service,
    pipeline_service=pipeline_service,
    forecast_service=forecast_service,
    monitoring_service=monitoring_service,
)


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "healthy"}


@router.post("/eda/reset")
def reset_eda_state() -> dict[str, int | str]:
    result = orchestrator.clear_runtime_state()
    return {"status": "cleared", **result}


@router.post("/datasets/search", response_model=DatasetSearchResponse)
def search_datasets(payload: SearchRequest) -> DatasetSearchResponse:
    return discovery_service.search(payload)


@router.get("/datasets/{dataset_id}/profile", response_model=DatasetProfile)
def dataset_profile(dataset_id: str, source_ref: str | None = None) -> DatasetProfile:
    return orchestrator.profile_dataset(AnalyzeRequest(dataset_id=dataset_id, source_ref=source_ref))


@router.get("/datasets/{dataset_id}/profile/stream")
def stream_dataset_profile(dataset_id: str, source_ref: str | None = None) -> StreamingResponse:
    payload = AnalyzeRequest(dataset_id=dataset_id, source_ref=source_ref)

    def event_generator():
        queue: Queue[dict[str, object] | None] = Queue()

        def emit(event: dict[str, object]) -> None:
            queue.put(event)

        def worker() -> None:
            try:
                profile = orchestrator.stream_profile_events(payload, emit)
                queue.put({"event": "complete", "status": "complete", "message": "EDA profile complete.", "result": profile.model_dump()})
            except Exception as exc:
                queue.put({"event": "error", "status": "error", "message": str(exc), "details": {"type": exc.__class__.__name__}})
            finally:
                queue.put(None)

        Thread(target=worker, daemon=True).start()
        yield f"data: {json.dumps({'event': 'connected', 'status': 'running', 'message': 'EDA stream connected.'})}\n\n"

        while True:
            try:
                event = queue.get(timeout=15)
            except Empty:
                yield f"data: {json.dumps({'event': 'heartbeat', 'status': 'running'})}\n\n"
                continue
            if event is None:
                break
            yield f"data: {json.dumps(event, default=str)}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"},
    )


@router.get("/datasets/{dataset_id}/rows", response_model=DatasetRowsResponse)
def dataset_rows(dataset_id: str, page: int = 1, page_size: int = 25, source_ref: str | None = None) -> DatasetRowsResponse:
    return orchestrator.raw_rows(dataset_id=dataset_id, page=page, page_size=page_size, source_ref=source_ref)


@router.post("/datasets/analyze", response_model=DatasetProfile)
def analyze_dataset(payload: AnalyzeRequest) -> DatasetProfile:
    return orchestrator.profile_dataset(payload)


@router.post("/datasets/upload", response_model=DatasetProfile)
async def upload_dataset(file: UploadFile = File(...)) -> DatasetProfile:
    return await orchestrator.profile_uploaded_dataset(file)


@router.post("/pipeline/run", response_model=PipelineRunResponse)
def run_pipeline(payload: PipelineRunRequest) -> PipelineRunResponse:
    return orchestrator.run_pipeline(payload)


@router.get("/pipeline/run/stream")
def stream_pipeline(
    dataset_id: str = "energy-001",
    source_ref: str | None = None,
    target_column: str | None = None,
    horizon: int = 14,
    model_override: Literal["auto", "ARIMA", "XGBoost", "RandomForest", "SVM", "LSTM"] = "auto",
) -> StreamingResponse:
    payload = PipelineRunRequest(
        dataset_id=dataset_id,
        source_ref=source_ref,
        target_column=target_column,
        horizon=horizon,
        model_override=model_override,
    )

    def event_generator():
        queue: Queue[dict[str, object] | None] = Queue()

        def emit(event: dict[str, object]) -> None:
            queue.put(event)

        def worker() -> None:
            try:
                result = orchestrator.stream_pipeline_events(payload, emit)
                queue.put({"event": "complete", "status": "complete", "message": "Pipeline run complete.", "result": result.model_dump()})
            except Exception as exc:
                queue.put({"event": "error", "status": "error", "message": str(exc), "details": {"type": exc.__class__.__name__}})
            finally:
                queue.put(None)

        Thread(target=worker, daemon=True).start()
        yield f"data: {json.dumps({'event': 'connected', 'status': 'running', 'message': 'Pipeline stream connected.'})}\n\n"

        while True:
            try:
                event = queue.get(timeout=15)
            except Empty:
                yield f"data: {json.dumps({'event': 'heartbeat', 'status': 'running'})}\n\n"
                continue
            if event is None:
                break
            yield f"data: {json.dumps(event, default=str)}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"},
    )


@router.get("/forecast/{dataset_id}", response_model=ForecastResponse)
def forecast(dataset_id: str) -> ForecastResponse:
    return orchestrator.forecast(dataset_id)


@router.get("/monitor", response_model=SystemMonitorResponse)
def monitor() -> SystemMonitorResponse:
    return monitoring_service.snapshot()
