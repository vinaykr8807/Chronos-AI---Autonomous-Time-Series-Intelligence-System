from typing import Literal

from pydantic import BaseModel, Field


Domain = Literal["energy", "traffic", "sales", "finance", "iot", "general"]


class SearchRequest(BaseModel):
    query: str = Field(default="", description="Natural language dataset search query.")
    domain: Domain | None = None
    time_series_only: bool = True
    limit: int = Field(default=10, ge=1, le=25)


class DatasetResult(BaseModel):
    id: str
    title: str
    description: str
    domain: Domain
    tags: list[str]
    relevanceScore: float
    isTimeSeriesValidated: bool
    rowCount: int
    columnCount: int
    timeRange: dict[str, str]
    missingPercent: float
    source: str = "catalog"
    ref: str | None = None
    semanticScore: float | None = None
    validationSummary: str | None = None


class DatasetSearchResponse(BaseModel):
    query: str
    results: list[DatasetResult]
    engine: str
    retrieval: dict[str, str | int | bool | float]


class AnalyzeRequest(BaseModel):
    dataset_id: str
    source_ref: str | None = None


class ColumnProfile(BaseModel):
    name: str
    type: Literal["numeric", "categorical", "datetime", "text"]
    missingPercent: float
    description: str
    uniqueValues: int | None = None
    min: float | None = None
    max: float | None = None
    mean: float | None = None
    median: float | None = None
    std: float | None = None
    variance: float | None = None
    outlierPercent: float | None = None
    wordCountMean: float | None = None
    topValues: list[str] = []


class DatasetProfile(BaseModel):
    dataset_id: str
    title: str
    summary: dict[str, int | float | str | bool]
    columns: list[ColumnProfile]
    time_series: dict[str, str | bool | float | None]
    validation: dict[str, str | bool | float | int | None]
    numerical_analysis: dict[str, dict[str, float | int | str]]
    categorical_analysis: dict[str, dict[str, float | int | str | list[str]]]
    structural_intelligence: dict[str, object] = Field(default_factory=dict)
    forecastability: dict[str, object] = Field(default_factory=dict)
    temporal_behavior: dict[str, object] = Field(default_factory=dict)
    quality_intelligence: dict[str, object] = Field(default_factory=dict)
    feature_intelligence: dict[str, object] = Field(default_factory=dict)
    strategy_recommendation: dict[str, object] = Field(default_factory=dict)
    semantic_understanding: dict[str, object] = Field(default_factory=dict)
    chart_data: dict[str, list[dict[str, object]]] = Field(default_factory=dict)
    visualizations: list[dict[str, str]]
    eda_trace: list[dict[str, object]] = Field(default_factory=list)
    evidence_refs: dict[str, object] = Field(default_factory=dict)
    insights: str
    decisions: list[str]
    agent_notes: list[dict[str, str]]


class DatasetRowsResponse(BaseModel):
    dataset_id: str
    source: str
    page: int
    page_size: int
    total_rows: int
    total_pages: int
    columns: list[str]
    rows: list[dict[str, object]]


class PipelineRunRequest(BaseModel):
    dataset_id: str
    source_ref: str | None = None
    target_column: str | None = None
    horizon: int = Field(default=14, ge=1, le=90)
    model_override: Literal["auto", "ARIMA", "XGBoost", "RandomForest", "SVM", "LSTM"] = "auto"


class PipelineNode(BaseModel):
    id: str
    type: str
    label: str
    description: str
    status: Literal["ready", "processing", "complete", "error"]
    config: dict[str, object]


class PipelineRunResponse(BaseModel):
    run_id: str
    dataset_id: str
    data_source: str
    selected_model: str
    nodes: list[PipelineNode]
    metrics: dict[str, float]
    agent_decisions: list[str]
    sandbox: dict[str, str | bool | int | float]
    agents: list[dict[str, str]]
    pipeline_graph: dict[str, list[dict[str, object]]]
    pipeline_trace: list[dict[str, object]] = Field(default_factory=list)
    training_history: list[dict[str, object]] = Field(default_factory=list)
    optimization_trials: list[dict[str, object]] = Field(default_factory=list)
    preprocessing_report: dict[str, object] = Field(default_factory=dict)
    feature_plan: dict[str, object] = Field(default_factory=dict)
    evaluation_report: dict[str, object] = Field(default_factory=dict)
    deployment_report: dict[str, object] = Field(default_factory=dict)


class ForecastPoint(BaseModel):
    timestamp: str
    value: float
    predicted: float
    lower: float
    upper: float


class ForecastResponse(BaseModel):
    dataset_id: str
    horizon: int
    points: list[ForecastPoint]
    summary: list[dict[str, object]]
    decisions: list[dict[str, str]]


class SystemMonitorResponse(BaseModel):
    kpis: dict[str, float | int | str]
    alerts: list[dict[str, object]]
    performance: list[dict[str, float | str]]
    recent_runs: list[dict[str, object]]
