import type { DecisionInsight, Dataset, ForecastSummary, SystemAlert } from '../data/mockData';

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || '/api';

const ROWS_TTL_MS = 60 * 1000;

type CacheEntry<T> = {
  expiresAt: number;
  value: T;
};

const profileInFlight = new Map<string, Promise<DatasetProfile>>();
const rowsCache = new Map<string, CacheEntry<DatasetRowsResponse>>();
const rowsInFlight = new Map<string, Promise<DatasetRowsResponse>>();

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    headers: {
      'Content-Type': 'application/json',
      ...options?.headers,
    },
    ...options,
  });

  if (!response.ok) {
    let detail = `API request failed: ${response.status}`;
    try {
      const payload = await response.json() as { detail?: string };
      if (payload?.detail) {
        detail = payload.detail;
      }
    } catch {
      // Keep the status-based fallback when the response body is not JSON.
    }
    throw new Error(detail);
  }

  return response.json() as Promise<T>;
}

export interface DatasetProfile {
  dataset_id: string;
  title: string;
  summary: {
    rows: number;
    columns: number;
    missingPercent: number;
    timeSeriesValidated: boolean;
    timeRangeStart: string;
    timeRangeEnd: string;
    dataSource?: string;
    sourceRef?: string;
    realDataLoaded?: boolean;
    profileInputSource?: string;
    rowsAnalyzed?: number;
    rowsScanned?: number;
    columnsScanned?: number;
    targetColumn?: string | null;
    syntheticFallback?: boolean;
    edaMode?: string;
    edaExecution?: string;
    batchSize?: number;
    workerCount?: number;
    recordBatchCount?: number;
    batchRowsProfiled?: number;
    chartMode?: string;
    chartSamplePoints?: number;
    chartSourceRows?: number;
    loadTimeMs?: number;
    profileTimeMs?: number;
    explainTimeMs?: number;
    totalTimeMs?: number;
    profileCacheHit?: boolean;
  };
  columns: Array<{
    name: string;
    type: 'numeric' | 'categorical' | 'datetime' | 'text';
    missingPercent: number;
    description: string;
    uniqueValues?: number;
    min?: number;
    max?: number;
    mean?: number;
    median?: number;
    std?: number;
    variance?: number;
    outlierPercent?: number;
    wordCountMean?: number;
    topValues?: string[];
  }>;
  time_series: {
    valid: boolean;
    timeColumn: string | null;
    frequency: string;
    gapRatio: number | null;
    orderingScore?: number | null;
    consistencyScore?: number | null;
    seasonalityHint?: string | null;
  };
  validation?: Record<string, string | boolean | number | null>;
  numerical_analysis?: Record<string, Record<string, string | number>>;
  categorical_analysis?: Record<string, Record<string, string | number | string[]>>;
  structural_intelligence?: {
    columnRoles?: Record<string, { role: string; type: string; reason: string }>;
    entityColumns?: string[];
    targetColumn?: string | null;
    timeColumn?: string | null;
    temporalHierarchy?: string[];
    relationshipSummary?: string;
  };
  forecastability?: {
    score?: number;
    grade?: string;
    seasonalityStrength?: number;
    trendConsistency?: number;
    stationarityScore?: number;
    noiseRatio?: number;
    intervalStability?: number;
    reasons?: string[];
    risks?: string[];
  };
  temporal_behavior?: {
    periodicity?: string;
    anomalies?: Array<{ index: number; timestamp: string; severity: number }>;
    anomalyRate?: number;
    regimeChanges?: number[];
    driftScore?: number;
    interpretation?: string;
  };
  quality_intelligence?: {
    trustScore?: number;
    missingPattern?: string;
    leakageRisk?: string[];
    duplicateRisk?: string;
    recommendations?: string[];
  };
  feature_intelligence?: {
    predictiveSignals?: Array<{
      feature: string;
      sameTimeCorrelation: number;
      lagInfluence: number;
      role: string;
    }>;
    redundantFeatures?: Array<{ features: string[]; correlation: number }>;
    leakageWarnings?: string[];
    preTrainingRecommendation?: string;
  };
  strategy_recommendation?: {
    recommendedModelFamily?: string;
    reason?: string;
    preprocessingPlan?: string[];
    optimizationFocus?: string;
    confidence?: string;
  };
  semantic_understanding?: {
    inferredDomain?: string;
    businessMeaning?: string;
    likelyUseCase?: string;
    targetMeaning?: string;
  };
  chart_data?: {
    timeSeries?: Array<{ timestamp: string; value: number; predicted?: number; lower?: number; upper?: number }>;
    distribution?: Array<{ range: string; frequency: number }>;
    correlation?: Array<{ feature1: string; feature2: string; correlation: number }>;
  };
  visualizations?: Array<{ type: string; title: string; reason: string }>;
  insights: string;
  decisions: string[];
  agent_notes?: Array<{ agent: string; note: string }>;
}

export interface DatasetRowsResponse {
  dataset_id: string;
  source: string;
  page: number;
  page_size: number;
  total_rows: number;
  total_pages: number;
  columns: string[];
  rows: Array<Record<string, unknown>>;
}

export interface EDAStreamEvent {
  event: string;
  agent?: string;
  stage?: string;
  timestamp?: string;
  status?: string;
  message?: string;
  details?: Record<string, unknown>;
  result?: DatasetProfile;
}

export async function searchDatasets(query: string, domain: string, timeSeriesOnly = true) {
  return request<{ query: string; results: Dataset[]; engine: string }>('/datasets/search', {
    method: 'POST',
    body: JSON.stringify({
      query,
      domain: domain === 'all' ? null : domain,
      time_series_only: timeSeriesOnly,
      limit: 12,
    }),
  });
}

export async function resetEdaState() {
  return request<{ status: string; profileCacheEntries: number; evidenceFiles: number }>('/eda/reset', {
    method: 'POST',
  });
}

export async function getDatasetProfile(datasetId: string, sourceRef?: string | null) {
  const params = new URLSearchParams();
  if (sourceRef) {
    params.set('source_ref', sourceRef);
  }
  const suffix = params.size ? `?${params.toString()}` : '';
  const path = `/datasets/${encodeURIComponent(datasetId)}/profile${suffix}`;
  const pending = profileInFlight.get(path);
  if (pending) {
    return pending;
  }
  const promise = request<DatasetProfile>(path)
    .then((response) => {
      profileInFlight.delete(path);
      return response;
    })
    .catch((error) => {
      profileInFlight.delete(path);
      throw error;
    });
  profileInFlight.set(path, promise);
  return promise;
}

export function streamDatasetProfile(
  datasetId: string,
  sourceRef: string | null | undefined,
  onEvent: (event: EDAStreamEvent) => void,
  onError: (message: string) => void,
) {
  if (typeof EventSource === 'undefined') {
    onError('Streaming is not supported in this browser.');
    return () => undefined;
  }

  const params = new URLSearchParams();
  if (sourceRef) {
    params.set('source_ref', sourceRef);
  }
  const suffix = params.size ? `?${params.toString()}` : '';
  const path = `/datasets/${encodeURIComponent(datasetId)}/profile/stream${suffix}`;
  const source = new EventSource(`${API_BASE_URL}${path}`);
  source.onmessage = (message) => {
    try {
      const event = JSON.parse(message.data) as EDAStreamEvent;
      onEvent(event);
      if (event.event === 'complete' || event.event === 'error') {
        source.close();
      }
    } catch {
      onError('EDA stream returned an invalid event.');
      source.close();
    }
  };
  source.onerror = () => {
    onError('EDA stream disconnected.');
    source.close();
  };

  return () => source.close();
}

export async function getDatasetRows(datasetId: string, page = 1, pageSize = 25, sourceRef?: string | null) {
  const params = new URLSearchParams({
    page: String(page),
    page_size: String(pageSize),
  });
  if (sourceRef) {
    params.set('source_ref', sourceRef);
  }
  const path = `/datasets/${encodeURIComponent(datasetId)}/rows?${params.toString()}`;
  const now = Date.now();
  const cached = rowsCache.get(path);
  if (cached && cached.expiresAt > now) {
    return cached.value;
  }
  const pending = rowsInFlight.get(path);
  if (pending) {
    return pending;
  }
  const promise = request<DatasetRowsResponse>(path)
    .then((response) => {
      rowsCache.set(path, { value: response, expiresAt: Date.now() + ROWS_TTL_MS });
      rowsInFlight.delete(path);
      return response;
    })
    .catch((error) => {
      rowsInFlight.delete(path);
      throw error;
    });
  rowsInFlight.set(path, promise);
  return promise;
}

export interface PipelineRunResult {
  run_id: string;
  dataset_id: string;
  data_source: string;
  selected_model: string;
  nodes: Array<{
    id: string;
    type: string;
    label: string;
    description: string;
    status: 'ready' | 'processing' | 'complete' | 'error';
    config: Record<string, unknown>;
  }>;
  metrics: Record<string, number>;
  agent_decisions: string[];
  sandbox: Record<string, string | boolean | number>;
  agents: Array<{ name: string; responsibility: string }>;
  pipeline_graph: {
    nodes: Array<{ id: string; label: string; type: string; status: string }>;
    edges: Array<{ source: string; target: string }>;
  };
  pipeline_trace: PipelineTraceEvent[];
  training_history: Array<Record<string, unknown>>;
  optimization_trials: Array<Record<string, unknown>>;
  preprocessing_report: Record<string, unknown>;
  feature_plan: Record<string, unknown>;
  evaluation_report: Record<string, unknown>;
  deployment_report: Record<string, unknown>;
}

export interface PipelineTraceEvent {
  agent: string;
  stage: string;
  timestamp?: string;
  status: string;
  message: string;
  details?: Record<string, unknown>;
}

export interface PipelineStreamEvent {
  event: string;
  agent?: string;
  stage?: string;
  timestamp?: string;
  status?: string;
  message?: string;
  details?: Record<string, unknown>;
  result?: PipelineRunResult;
}

export async function runPipeline(datasetId = 'energy-001', sourceRef?: string | null) {
  return request<PipelineRunResult>('/pipeline/run', {
    method: 'POST',
    body: JSON.stringify({ dataset_id: datasetId, source_ref: sourceRef, horizon: 14, model_override: 'auto' }),
  });
}

export function streamPipeline(
  datasetId = 'energy-001',
  sourceRef: string | null | undefined,
  onEvent: (event: PipelineStreamEvent) => void,
  onError: (message: string) => void,
) {
  if (typeof EventSource === 'undefined') {
    onError('Streaming is not supported in this browser.');
    return () => undefined;
  }

  const params = new URLSearchParams({
    dataset_id: datasetId,
    horizon: '14',
    model_override: 'auto',
  });
  if (sourceRef) {
    params.set('source_ref', sourceRef);
  }

  const source = new EventSource(`${API_BASE_URL}/pipeline/run/stream?${params.toString()}`);
  source.onmessage = (message) => {
    try {
      const event = JSON.parse(message.data) as PipelineStreamEvent;
      onEvent(event);
      if (event.event === 'complete' || event.event === 'error') {
        source.close();
      }
    } catch {
      onError('Pipeline stream returned an invalid event.');
      source.close();
    }
  };
  source.onerror = () => {
    onError('Pipeline stream disconnected.');
    source.close();
  };

  return () => source.close();
}

export async function getForecast(datasetId: string) {
  return request<{
    dataset_id: string;
    horizon: number;
    points: Array<{ timestamp: string; value: number; predicted: number; lower: number; upper: number }>;
    summary: ForecastSummary[];
    decisions: DecisionInsight[];
  }>(`/forecast/${encodeURIComponent(datasetId)}`);
}

export async function getMonitorSnapshot() {
  return request<{
    kpis: {
      modelAccuracy: number;
      modelUsed: string;
      retrainingCycles: number;
      driftScore: number;
      uptime: number;
      totalPredictions: number;
    };
    alerts: SystemAlert[];
    performance: Array<{ timestamp: string; accuracy: number; drift: number; latency: number }>;
    recent_runs: Array<Record<string, unknown>>;
  }>('/monitor');
}
