import { useEffect, useState } from 'react';
import { useNavigate, useParams, useSearchParams } from 'react-router-dom';
import { motion } from 'framer-motion';
import {
  Activity,
  ArrowLeft,
  BarChart3,
  BrainCircuit,
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  CheckCircle2,
  Circle,
  Copy,
  Database,
  Hash,
  Loader2,
  Network,
  Radar,
  ScanSearch,
  ShieldCheck,
  Siren,
  Sparkles,
  TrendingUp,
} from 'lucide-react';
import { Badge, Button, Card, Skeleton, StatusBadge, Table } from '../components/common';
import { CorrelationHeatmap, DistributionChart, TimeSeriesChart } from '../components/charts';
import {
  type Dataset,
} from '../data/mockData';
import { getDatasetRows, resetEdaState, streamDatasetProfile, type DatasetProfile, type DatasetRowsResponse, type EDAStreamEvent } from '../lib/api';

const tabs = [
  { id: 'overview', label: 'Overview', icon: Database },
  { id: 'intelligence', label: 'Intelligence', icon: BrainCircuit },
  { id: 'raw', label: 'Raw Data', icon: Hash },
  { id: 'timeseries', label: 'Time Series', icon: TrendingUp },
  { id: 'distribution', label: 'Distribution', icon: BarChart3 },
  { id: 'correlation', label: 'Correlation', icon: Network },
];

const edaStages = [
  { id: 'retrieve_dataset', label: 'Dataset Retrieved', description: 'Download/load dataframe and inspect basic shape.' },
  { id: 'statistical_profile', label: 'Statistical Profiling', description: 'Analyze column types, missingness, uniqueness, distributions, and preview rows.' },
  { id: 'temporal_analysis', label: 'Temporal Analysis', description: 'Detect time column, cadence, ordering, anomalies, drift, and seasonality signals.' },
  { id: 'forecastability_analysis', label: 'Forecastability', description: 'Calculate forecastability score, confidence, risks, and model recommendation.' },
  { id: 'semantic_embeddings', label: 'Evidence Store', description: 'Persist EDA JSON and semantic vectors before insight generation.' },
  { id: 'intelligence_report', label: 'AI Report', description: 'Generate the final human-readable intelligence report from deterministic evidence.' },
];

const llmInsights = `
## Dataset Intelligence Summary

### Behavioral Understanding

The profiling engine detected recurring temporal structure with meaningful exogenous influence. The target behavior appears suitable for forecasting, but reliability depends on handling noisy windows and validating anomaly periods before training.

### Risk View

- Missingness should be interpreted in context, especially if it overlaps with high-value operational periods
- Regime shifts and spikes should be reviewed before locking the model family
- Leakage checks remain important for columns that look target-adjacent or future-aware

### Strategy

Use deterministic preprocessing, lag feature generation, walk-forward validation, and a model family chosen from the forecastability and feature-intelligence layers rather than only summary statistics.
`;

function formatInsightText(text: string) {
  return text
    .replace(/^#+\s*/gm, '')
    .replace(/\*\*/g, '')
    .replace(/^\s*[-*]\s+/gm, '• ')
    .replace(/\n{3,}/g, '\n\n')
    .trim();
}

function datasetSubtitle(profile: DatasetProfile | null, fallback: string) {
  if (!profile) return fallback;
  const hasTimeSeries = Boolean(profile.time_series?.valid);
  const frequency = hasTimeSeries ? profile.time_series.frequency || 'detected cadence' : 'cross-sectional';
  const missing = profile.summary.missingPercent;
  const rows = Number(profile.summary.rows || 0).toLocaleString();
  const forecastability = profile.forecastability?.score;
  const model = profile.strategy_recommendation?.recommendedModelFamily;
  const cadenceText = hasTimeSeries ? `${frequency} cadence` : 'no time index detected';
  return `Behavioral profile generated from the selected dataset: ${rows} records, ${profile.summary.columns} columns, ${missing}% missing values, ${cadenceText}${typeof forecastability === 'number' ? `, predictability score ${forecastability.toFixed(0)}%` : ''}${model ? `, strategy leans toward ${model}` : ''}.`;
}

function scoreVariant(score?: number) {
  if ((score ?? 0) >= 80) return 'success' as const;
  if ((score ?? 0) >= 60) return 'warning' as const;
  return 'error' as const;
}

function gradeVariant(grade?: string) {
  if (grade === 'strong') return 'success' as const;
  if (grade === 'moderate') return 'warning' as const;
  return 'info' as const;
}

function percentage(value?: number, digits = 0) {
  if (typeof value !== 'number' || Number.isNaN(value)) return 'N/A';
  return `${value.toFixed(digits)}%`;
}

function formatMs(value?: number) {
  return typeof value === 'number' ? `${value.toFixed(0)} ms` : 'N/A';
}

function edaStageStatus(stageId: string, events: EDAStreamEvent[]) {
  const stageEvent = [...events].reverse().find((event) => event.stage === stageId);
  if (stageEvent?.status === 'complete') return 'complete';
  if (stageEvent?.status === 'error') return 'error';
  if (stageEvent?.status === 'running') return 'running';
  return 'waiting';
}

function EDAStatusIcon({ status }: { status: string }) {
  if (status === 'complete') return <CheckCircle2 className="h-5 w-5 text-emerald-300" />;
  if (status === 'running') return <Loader2 className="h-5 w-5 animate-spin text-indigo-300" />;
  if (status === 'error') return <Siren className="h-5 w-5 text-red-300" />;
  return <Circle className="h-5 w-5 text-slate-500" />;
}

export function DatasetIntelligence() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const [activeTab, setActiveTab] = useState('overview');
  const [isLoading, setIsLoading] = useState(true);
  const [isAnalyzing, setIsAnalyzing] = useState(false);
  const [showInsights, setShowInsights] = useState(true);
  const [profile, setProfile] = useState<DatasetProfile | null>(null);
  const [profileEvents, setProfileEvents] = useState<EDAStreamEvent[]>([]);
  const [profileError, setProfileError] = useState<string | null>(null);
  const [rawRows, setRawRows] = useState<DatasetRowsResponse | null>(null);
  const [rawPage, setRawPage] = useState(1);
  const [isRawLoading, setIsRawLoading] = useState(false);
  const [rawError, setRawError] = useState<string | null>(null);
  const [refreshNonce, setRefreshNonce] = useState(0);
  const sourceRef = searchParams.get('ref');



  useEffect(() => {
    if (!id) return;
    let cancelled = false;
    setIsLoading(true);
    setProfileError(null);
    setProfile(null);
    setProfileEvents([]);
    const stopStream = streamDatasetProfile(
      id,
      sourceRef,
      (event) => {
        if (!cancelled) {
          if (event.event !== 'heartbeat') {
            setProfileEvents((current) => [...current, event].slice(-80));
          }
          if (event.event === 'complete' && event.result) {
            setProfile(event.result);
            setIsLoading(false);
          }
          if (event.event === 'error') {
            setProfile(null);
            setProfileError(event.message || 'Profile loading failed.');
            setIsLoading(false);
          }
        }
      },
      (message) => {
        if (!cancelled) {
          setProfile(null);
          setProfileError(message);
          setIsLoading(false);
        }
      }
    );
    return () => {
      cancelled = true;
      stopStream();
    };
  }, [id, sourceRef, refreshNonce]);

  useEffect(() => {
    if (!id || activeTab !== 'raw') return;
    let cancelled = false;
    setIsRawLoading(true);
    setRawError(null);
    getDatasetRows(id, rawPage, 25, sourceRef)
      .then((response) => {
        if (!cancelled) {
          setRawRows({
            ...response,
            rows: response.rows.map((row, index) => ({
              __rowId: `${response.page}-${index}-${String(row.timestamp || row.id || index)}`,
              ...row,
            })),
          });
        }
      })
      .catch((error) => {
        if (!cancelled) {
          setRawRows(null);
          setRawError(error instanceof Error ? error.message : 'Raw data loading failed.');
        }
      })
      .finally(() => {
        if (!cancelled) {
          setIsRawLoading(false);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [activeTab, id, rawPage, sourceRef]);

  const dataset: Dataset | null = (profile ? {
    id: profile.dataset_id,
    title: profile.title,
    description: datasetSubtitle(profile, ''),
    domain: (profile.semantic_understanding?.inferredDomain as any) || 'general',
    tags: ['kaggle', 'time-series', 'semantic-match'],
    relevanceScore: 0.86,
    isTimeSeriesValidated: profile.summary.timeSeriesValidated,
    rowCount: profile.summary.rows,
    columnCount: profile.summary.columns,
    timeRange: {
      start: profile.summary.timeRangeStart,
      end: profile.summary.timeRangeEnd,
    },
    missingPercent: profile.summary.missingPercent,
  } : null);
  const latestProfileEvent = [...profileEvents].reverse().find((event) => event.message);
  const latestProfileDetails = [...profileEvents].reverse().find((event) => event.details)?.details || {};

  const handleAnalyze = () => {
    setIsAnalyzing(true);
    resetEdaState()
      .catch(() => undefined)
      .finally(() => {
        setRawRows(null);
        setRawPage(1);
        setRefreshNonce((value) => value + 1);
        setIsAnalyzing(false);
      });
  };

  if (!dataset && isLoading) {
    return (
      <div className="min-h-[calc(100vh-4rem)]">
        <div className="border-b border-space-600 bg-space-900/50">
          <div className="max-w-7xl mx-auto px-6 py-5 lg:px-8">
            <div className="flex items-center gap-4 mb-4">
              <Button variant="ghost" icon={ArrowLeft} onClick={() => navigate('/discover')}>
                Back
              </Button>
            </div>
            <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
              <div>
                <div className="flex items-center gap-3">
                  <h1 className="text-2xl font-bold text-white">{String(id || 'Dataset')}</h1>
                  <Badge variant="info" size="sm">EDA Running</Badge>
                </div>
                <p className="mt-2 max-w-3xl text-sm leading-relaxed text-slate-400">
                  {latestProfileEvent?.message || 'Starting dataset retrieval and staged EDA analysis.'}
                </p>
              </div>
              <div className="rounded-full border border-indigo-500/40 bg-indigo-500/10 px-4 py-2 text-sm text-indigo-200">
                Live Dataset Intelligence
              </div>
            </div>
          </div>
        </div>

        <div className="max-w-7xl mx-auto px-6 py-6 lg:px-8">
          <div className="grid gap-4 md:grid-cols-4">
            {[
              { label: 'Rows', value: latestProfileDetails.rows ? Number(latestProfileDetails.rows).toLocaleString() : 'Detecting' },
              { label: 'Columns', value: latestProfileDetails.columns ? String(latestProfileDetails.columns) : 'Detecting' },
              { label: 'Time Column', value: String(latestProfileDetails.timeColumn || 'Scanning') },
              { label: 'Forecastability', value: typeof latestProfileDetails.forecastability === 'number' ? `${Number(latestProfileDetails.forecastability).toFixed(0)}%` : 'Pending' },
            ].map((item) => (
              <Card key={item.label}>
                <p className="text-xs uppercase tracking-wide text-slate-500">{item.label}</p>
                <p className="mt-2 text-xl font-semibold text-white font-mono">{item.value}</p>
              </Card>
            ))}
          </div>

          <div className="mt-6 grid gap-6 lg:grid-cols-[1fr_24rem]">
            <Card>
              <div className="flex items-center justify-between gap-4">
                <div>
                  <h2 className="text-lg font-semibold text-white">Live EDA Pipeline Status</h2>
                  <p className="mt-1 text-sm text-slate-400">
                    The page stays responsive while Kaggle loading, profiling, embeddings, and report generation run in the backend.
                  </p>
                </div>
                <Loader2 className="h-5 w-5 animate-spin text-indigo-300" />
              </div>

              <div className="mt-6 space-y-3">
                {edaStages.map((stage) => {
                  const status = edaStageStatus(stage.id, profileEvents);
                  const event = [...profileEvents].reverse().find((item) => item.stage === stage.id);
                  return (
                    <div
                      key={stage.id}
                      className={`rounded-lg border p-4 ${
                        status === 'complete'
                          ? 'border-emerald-500/30 bg-emerald-500/5'
                          : status === 'running'
                            ? 'border-indigo-500/40 bg-indigo-500/10'
                            : 'border-space-700 bg-space-900/40'
                      }`}
                    >
                      <div className="flex items-start gap-3">
                        <EDAStatusIcon status={status} />
                        <div>
                          <p className="font-semibold text-white">{stage.label}</p>
                          <p className="mt-1 text-sm text-slate-400">{event?.message || stage.description}</p>
                        </div>
                      </div>
                    </div>
                  );
                })}
              </div>
            </Card>

            <Card>
              <h2 className="text-lg font-semibold text-white">Live Events</h2>
              <div className="mt-4 max-h-[32rem] space-y-3 overflow-y-auto pr-1">
                {profileEvents.filter((event) => event.event !== 'connected').map((event, index) => (
                  <div key={`${event.stage}-${index}`} className="rounded-lg bg-space-900/70 p-3">
                    <div className="flex items-center justify-between gap-3">
                      <p className="font-mono text-xs text-indigo-300">{event.stage || event.event}</p>
                      <span className={`rounded-full px-2 py-1 text-xs ${event.status === 'complete' ? 'bg-emerald-500/10 text-emerald-300' : 'bg-indigo-500/10 text-indigo-300'}`}>
                        {event.status || 'running'}
                      </span>
                    </div>
                    <p className="mt-2 text-xs leading-relaxed text-slate-300">{event.message}</p>
                  </div>
                ))}
                {profileEvents.length === 0 && (
                  <p className="text-sm text-slate-500">Waiting for first backend event...</p>
                )}
              </div>
            </Card>
          </div>
        </div>
      </div>
    );
  }

  if (!dataset) {
    return (
      <div className="min-h-[calc(100vh-4rem)] flex items-center justify-center">
        <div className="text-center">
          <h2 className="text-2xl font-bold text-white mb-2">Dataset Unavailable</h2>
          <p className="text-slate-400 mb-4">{profileError || "The dataset couldn't be profiled."}</p>
          <Button onClick={() => navigate('/discover')}>Back to Discovery</Button>
        </div>
      </div>
    );
  }

  const timeSeriesData = profile?.chart_data?.timeSeries || [];
  const distributionData = profile?.chart_data?.distribution || [];
  const correlationData = profile?.chart_data?.correlation || [];
  const forecastabilityScore = profile?.forecastability?.score;
  const trustScore = profile?.quality_intelligence?.trustScore;
  const driftScore = profile?.temporal_behavior?.driftScore;
  const hasTimeSeries = Boolean(profile?.time_series?.valid);
  const visibleTabs = hasTimeSeries ? tabs : tabs.filter((tab) => tab.id !== 'timeseries');
  const recommendedModel = profile?.strategy_recommendation?.recommendedModelFamily || 'Adaptive';
  const topSignals = profile?.feature_intelligence?.predictiveSignals || [];
  const anomalyWindows = profile?.temporal_behavior?.anomalies || [];
  const structuralRoles = Object.entries(profile?.structural_intelligence?.columnRoles || {});
  const visualizationIntents = profile?.visualizations || [];
  const rowsAnalyzed = Number(profile?.summary.rowsAnalyzed || profile?.summary.rows || 0);
  const rowsScanned = Number(profile?.summary.rowsScanned || rowsAnalyzed || 0);
  const columnsScanned = Number(profile?.summary.columnsScanned || profile?.summary.columns || 0);
  const targetColumn = profile?.summary.targetColumn || profile?.validation?.recommendedTarget || 'Pending';
  const profileInputSource = profile?.summary.profileInputSource || profile?.summary.dataSource || 'unknown';
  const isSyntheticProfile = Boolean(profile?.summary.syntheticFallback || profileInputSource === 'synthetic-profile');
  const tableColumns = profile?.columns
    ? profile.columns.map((column) => ({
        ...column,
        type: column.type === 'text' ? 'categorical' as const : column.type,
      }))
    : [];

  return (
    <div className="min-h-[calc(100vh-4rem)]">
      <div className="border-b border-space-600 bg-space-900/50">
        <div className="max-w-7xl mx-auto px-6 py-4 lg:px-8">
          <div className="flex items-center gap-4 mb-4">
            <Button variant="ghost" icon={ArrowLeft} onClick={() => navigate('/discover')}>
              Back
            </Button>
          </div>

          <div className="flex flex-col lg:flex-row lg:items-start lg:justify-between gap-4">
            <div>
              <div className="flex items-center gap-3 mb-2">
                <h1 className="text-2xl font-bold text-white">{dataset.title}</h1>
                {dataset.isTimeSeriesValidated && <StatusBadge status="validated" />}
              </div>
              <p className="text-slate-400 max-w-2xl leading-relaxed">
                {datasetSubtitle(profile, dataset.description)}
              </p>
            </div>
            <div className="flex items-center gap-3">
              <Button
                icon={ChevronRight}
                disabled={isSyntheticProfile}
                title={isSyntheticProfile ? 'Pipeline creation is locked until this dataset resolves to a real dataframe.' : 'Create evidence pipeline'}
                onClick={() => navigate(`/pipeline?dataset=${encodeURIComponent(dataset.id)}&eda=ready${sourceRef ? `&ref=${encodeURIComponent(sourceRef)}` : ''}`)}
              >
                {isSyntheticProfile ? 'Pipeline Locked' : 'Create Pipeline'}
              </Button>
            </div>
          </div>
        </div>
      </div>

      <div className="max-w-7xl mx-auto px-6 py-6 lg:px-8">
        <div className="flex flex-col lg:flex-row gap-6">
          <div className="flex-1 min-w-0">
            <div className="grid grid-cols-1 md:grid-cols-4 gap-4 mb-6">
              <Card>
                <p className="text-xs uppercase tracking-wide text-slate-400">EDA Input</p>
                <p className="mt-2 text-lg font-semibold text-white">
                  {isSyntheticProfile ? 'Synthetic fallback' : 'Real dataframe'}
                </p>
                <p className="mt-1 text-sm text-slate-400">
                  Source: {profileInputSource}.
                </p>
              </Card>
              <Card>
                <p className="text-xs uppercase tracking-wide text-slate-400">Rows Scanned</p>
                <p className="mt-2 text-lg font-semibold text-white">{rowsScanned.toLocaleString()}</p>
                <p className="mt-1 text-sm text-slate-400">
                  Columns scanned: {columnsScanned.toLocaleString()}. Charts may sample only for rendering.
                </p>
              </Card>
              <Card>
                <p className="text-xs uppercase tracking-wide text-slate-400">Target Evidence</p>
                <p className="mt-2 text-lg font-semibold text-white break-words">{String(targetColumn)}</p>
                <p className="mt-1 text-sm text-slate-400">This selected target is handed to training and forecast services.</p>
              </Card>
              <Card>
                <p className="text-xs uppercase tracking-wide text-slate-400">EDA Execution</p>
                <p className="mt-2 text-lg font-semibold text-white">
                  {profile?.summary.edaMode === 'nine-record-batch-eda'
                    ? '9 record batches'
                    : profile?.summary.edaMode === 'full-dataframe'
                      ? 'Full dataframe'
                      : 'Catalog sample'}
                </p>
                <p className="mt-1 text-sm text-slate-400">
                  {profile?.summary.edaExecution === 'record-batched-full-reconciliation'
                    ? `Scans ${Number(profile?.summary.recordBatchCount || 9).toLocaleString()} row batches first, then reconciles a full-dataframe EDA. Charts sample ${Number(profile?.summary.chartSamplePoints || 0).toLocaleString()} of ${Number(profile?.summary.chartSourceRows || profile?.summary.rows || 0).toLocaleString()} rows for rendering only.`
                    : profile?.summary.edaExecution === 'parallel-batched'
                    ? `Parallel batched profiling across ${profile?.summary.workerCount ?? 0} workers with batch size ${profile?.summary.batchSize ?? 0}. Charts sample ${Number(profile?.summary.chartSamplePoints || 0).toLocaleString()} of ${Number(profile?.summary.chartSourceRows || profile?.summary.rows || 0).toLocaleString()} rows for rendering only.`
                    : 'Profile execution details are not available.'}
                </p>
              </Card>
            </div>
            {isSyntheticProfile && (
              <Card className="mb-6 border-amber-500/30 bg-amber-500/5">
                <div className="flex items-start gap-3">
                  <Siren className="mt-0.5 h-5 w-5 text-amber-300" />
                  <div>
                    <p className="font-semibold text-amber-100">This run used synthetic demo data</p>
                    <p className="mt-1 text-sm text-amber-100/80">
                      Pick a dataset with a Kaggle/local ref, or use Regenerate after the backend can resolve the real CSV. Metrics from synthetic fallback should not be treated as real dataset results.
                    </p>
                  </div>
                </div>
              </Card>
            )}
            <Card className="mb-6">
              <div className="flex items-center justify-between gap-4">
                <div>
                  <p className="text-xs uppercase tracking-wide text-slate-400">Request Timing</p>
                  <p className="mt-2 text-lg font-semibold text-white">
                    {typeof profile?.summary.totalTimeMs === 'number'
                      ? `${(profile.summary.totalTimeMs / 1000).toFixed(2)}s total`
                      : 'Timing pending'}
                  </p>
                  <p className="mt-1 text-sm text-slate-400">
                    Real measured stages for this fresh full-dataframe EDA run.
                  </p>
                </div>
                <Badge variant="info" size="sm">
                  Fresh EDA
                </Badge>
              </div>
              <div className="mt-4 grid grid-cols-2 md:grid-cols-4 gap-3 text-sm">
                <div className="rounded-lg border border-space-600 bg-space-800/60 p-3">
                  <p className="text-slate-400">Load</p>
                  <p className="mt-1 font-mono text-white">{formatMs(profile?.summary.loadTimeMs)}</p>
                </div>
                <div className="rounded-lg border border-space-600 bg-space-800/60 p-3">
                  <p className="text-slate-400">Profile</p>
                  <p className="mt-1 font-mono text-white">{formatMs(profile?.summary.profileTimeMs)}</p>
                </div>
                <div className="rounded-lg border border-space-600 bg-space-800/60 p-3">
                  <p className="text-slate-400">Explain</p>
                  <p className="mt-1 font-mono text-white">{formatMs(profile?.summary.explainTimeMs)}</p>
                </div>
                <div className="rounded-lg border border-space-600 bg-space-800/60 p-3">
                  <p className="text-slate-400">Total</p>
                  <p className="mt-1 font-mono text-white">{formatMs(profile?.summary.totalTimeMs)}</p>
                </div>
              </div>
            </Card>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
              {[
                { icon: Hash, label: 'Total Rows', value: Number(profile?.summary.rows || dataset.rowCount).toLocaleString() },
                { icon: ScanSearch, label: hasTimeSeries ? 'Forecastability' : 'Predictability', value: typeof forecastabilityScore === 'number' ? `${forecastabilityScore.toFixed(0)}%` : 'Pending' },
                { icon: ShieldCheck, label: 'Trust Score', value: typeof trustScore === 'number' ? `${trustScore.toFixed(0)}%` : 'Pending' },
                { icon: Activity, label: hasTimeSeries ? 'Drift Signal' : 'Temporal Drift', value: hasTimeSeries && typeof driftScore === 'number' ? percentage(driftScore * 100) : 'N/A' },
              ].map((stat, index) => (
                <motion.div
                  key={stat.label}
                  initial={{ opacity: 0, y: 20 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ delay: index * 0.1 }}
                >
                  <Card className="text-center">
                    <stat.icon className="w-5 h-5 text-indigo-400 mx-auto mb-2" />
                    <p className="text-2xl font-bold text-white font-mono">{stat.value}</p>
                    <p className="text-xs text-slate-400">{stat.label}</p>
                  </Card>
                </motion.div>
              ))}
            </div>

            <Card padding="none" className="mb-6 min-w-0 overflow-hidden">
              <div className="flex border-b border-space-600 overflow-x-auto">
                {visibleTabs.map((tab) => (
                  <button
                    key={tab.id}
                    onClick={() => setActiveTab(tab.id)}
                    className={`
                      flex items-center gap-2 px-4 py-3 text-sm font-medium transition-colors
                      border-b-2 -mb-px whitespace-nowrap
                      ${activeTab === tab.id
                        ? 'border-indigo-500 text-indigo-400'
                        : 'border-transparent text-slate-400 hover:text-white'
                      }
                    `}
                  >
                    <tab.icon className="w-4 h-4" />
                    {tab.label}
                  </button>
                ))}
              </div>

              <div className="min-w-0 p-6">
                {activeTab === 'overview' && (
                  <div className="space-y-6">
                    <div className="grid md:grid-cols-2 gap-4">
                      <Card className="bg-space-800/80">
                        <div className="flex items-center gap-2 mb-3">
                          <Radar className="w-4 h-4 text-cyan-300" />
                          <h3 className="text-sm font-semibold text-white">Semantic Understanding</h3>
                        </div>
                        <div className="space-y-3 text-sm text-slate-300">
                          <div className="flex items-center gap-2 flex-wrap">
                            <Badge variant="secondary" size="sm">{profile?.semantic_understanding?.inferredDomain || 'general'}</Badge>
                            <Badge variant="info" size="sm">{profile?.semantic_understanding?.likelyUseCase || 'analysis'}</Badge>
                          </div>
                          <p>{profile?.semantic_understanding?.businessMeaning || 'Business meaning will appear after profiling.'}</p>
                          <p className="text-slate-400">{profile?.semantic_understanding?.targetMeaning || 'Target role inference pending.'}</p>
                        </div>
                      </Card>

                      <Card className="bg-space-800/80">
                        <div className="flex items-center gap-2 mb-3">
                          <BrainCircuit className="w-4 h-4 text-indigo-300" />
                          <h3 className="text-sm font-semibold text-white">Strategy Recommendation</h3>
                        </div>
                        <div className="space-y-3 text-sm text-slate-300">
                          <div className="flex items-center gap-2 flex-wrap">
                            <Badge variant="primary" size="sm">{recommendedModel}</Badge>
                            <Badge variant={gradeVariant(profile?.strategy_recommendation?.confidence)} size="sm">
                              {profile?.strategy_recommendation?.confidence || 'adaptive'}
                            </Badge>
                          </div>
                          <p>{profile?.strategy_recommendation?.reason || 'Model family recommendation will appear here.'}</p>
                          <p className="text-slate-400">{profile?.strategy_recommendation?.optimizationFocus || 'Optimization focus pending.'}</p>
                        </div>
                      </Card>
                    </div>

                    <div>
                      <h3 className="text-lg font-semibold text-white mb-4">Column Analysis</h3>
                      <Table
                        columns={[
                          {
                            key: 'name',
                            header: 'Column Name',
                            render: (item) => <span className="font-mono text-indigo-300">{item.name}</span>,
                          },
                          {
                            key: 'type',
                            header: 'Type',
                            render: (item) => (
                              <Badge
                                variant={
                                  item.type === 'numeric' ? 'primary' :
                                  item.type === 'datetime' ? 'secondary' : 'info'
                                }
                                size="sm"
                              >
                                {item.type}
                              </Badge>
                            ),
                          },
                          { key: 'description', header: 'Description' },
                          {
                            key: 'missingPercent',
                            header: 'Missing',
                            render: (item) => (
                              <span className={item.missingPercent > 0 ? 'text-amber-400' : 'text-emerald-400'}>
                                {item.missingPercent > 0 ? `${item.missingPercent}%` : 'None'}
                              </span>
                            ),
                          },
                          {
                            key: 'uniqueValues',
                            header: 'Unique',
                            render: (item) => item.uniqueValues?.toLocaleString() || '-',
                          },
                        ]}
                        data={tableColumns}
                        keyExtractor={(item) => item.name}
                      />
                    </div>
                  </div>
                )}

                {activeTab === 'intelligence' && (
                  <div className="space-y-6">
                    <div className="grid xl:grid-cols-3 gap-4">
                      <Card>
                        <div className="flex items-center justify-between mb-4">
                          <div className="flex items-center gap-2">
                            <ScanSearch className="w-4 h-4 text-emerald-300" />
                            <h3 className="text-sm font-semibold text-white">{hasTimeSeries ? 'Forecastability' : 'Predictability'}</h3>
                          </div>
                          <Badge variant={scoreVariant(forecastabilityScore)} size="sm">
                            {typeof forecastabilityScore === 'number' ? `${forecastabilityScore.toFixed(0)}%` : 'Pending'}
                          </Badge>
                        </div>
                        {hasTimeSeries ? (
                          <div className="grid grid-cols-2 gap-3 mb-4 text-sm">
                            <div>
                              <p className="text-slate-500">Seasonality</p>
                              <p className="text-white font-medium">{percentage((profile?.forecastability?.seasonalityStrength || 0) * 100)}</p>
                            </div>
                            <div>
                              <p className="text-slate-500">Stationarity</p>
                              <p className="text-white font-medium">{percentage((profile?.forecastability?.stationarityScore || 0) * 100)}</p>
                            </div>
                            <div>
                              <p className="text-slate-500">Trend Consistency</p>
                              <p className="text-white font-medium">{percentage((profile?.forecastability?.trendConsistency || 0) * 100)}</p>
                            </div>
                            <div>
                              <p className="text-slate-500">Noise Ratio</p>
                              <p className="text-white font-medium">{percentage((profile?.forecastability?.noiseRatio || 0) * 100)}</p>
                            </div>
                          </div>
                        ) : (
                          <div className="grid grid-cols-2 gap-3 mb-4 text-sm">
                            <div>
                              <p className="text-slate-500">Dataset Type</p>
                              <p className="text-white font-medium">Cross-sectional</p>
                            </div>
                            <div>
                              <p className="text-slate-500">Numeric Features</p>
                              <p className="text-white font-medium">{tableColumns.filter((column) => column.type === 'numeric').length}</p>
                            </div>
                            <div>
                              <p className="text-slate-500">Target</p>
                              <p className="text-white font-medium">{String(profile?.validation?.recommendedTarget || 'Pending')}</p>
                            </div>
                            <div>
                              <p className="text-slate-500">Validation</p>
                              <p className="text-white font-medium">K-fold</p>
                            </div>
                          </div>
                        )}
                        <div className="space-y-2 text-sm text-slate-300">
                          {(profile?.forecastability?.reasons || []).slice(0, 3).map((reason) => (
                            <p key={reason}>{reason}</p>
                          ))}
                        </div>
                      </Card>

                      {hasTimeSeries && (
                      <Card>
                        <div className="flex items-center gap-2 mb-4">
                          <Siren className="w-4 h-4 text-amber-300" />
                          <h3 className="text-sm font-semibold text-white">Temporal Behavior</h3>
                        </div>
                        <div className="grid grid-cols-2 gap-3 mb-4 text-sm">
                          <div>
                            <p className="text-slate-500">Periodicity</p>
                            <p className="text-white font-medium">{profile?.temporal_behavior?.periodicity || 'N/A'}</p>
                          </div>
                          <div>
                            <p className="text-slate-500">Anomaly Rate</p>
                            <p className="text-white font-medium">{percentage((profile?.temporal_behavior?.anomalyRate || 0) * 100, 1)}</p>
                          </div>
                          <div>
                            <p className="text-slate-500">Regime Changes</p>
                            <p className="text-white font-medium">{profile?.temporal_behavior?.regimeChanges?.length || 0}</p>
                          </div>
                          <div>
                            <p className="text-slate-500">Drift Score</p>
                            <p className="text-white font-medium">{percentage((profile?.temporal_behavior?.driftScore || 0) * 100)}</p>
                          </div>
                        </div>
                        <p className="text-sm text-slate-300">{profile?.temporal_behavior?.interpretation || 'Behavior summary pending.'}</p>
                      </Card>
                      )}

                      <Card>
                        <div className="flex items-center gap-2 mb-4">
                          <ShieldCheck className="w-4 h-4 text-cyan-300" />
                          <h3 className="text-sm font-semibold text-white">Quality Intelligence</h3>
                        </div>
                        <div className="space-y-3 text-sm text-slate-300">
                          <div className="flex items-center gap-2 flex-wrap">
                            <Badge variant={scoreVariant(trustScore)} size="sm">
                              Trust {typeof trustScore === 'number' ? `${trustScore.toFixed(0)}%` : 'Pending'}
                            </Badge>
                            <Badge variant="info" size="sm">
                              Duplicate risk {profile?.quality_intelligence?.duplicateRisk || 'N/A'}
                            </Badge>
                          </div>
                          <p>{profile?.quality_intelligence?.missingPattern || 'Missingness pattern summary pending.'}</p>
                          {(profile?.quality_intelligence?.leakageRisk || []).slice(0, 2).map((risk) => (
                            <p key={risk} className="text-amber-300">{risk}</p>
                          ))}
                        </div>
                      </Card>
                    </div>

                    <div className="grid xl:grid-cols-2 gap-4">
                      <Card>
                        <h3 className="text-sm font-semibold text-white mb-4">Structural Roles</h3>
                        <div className="space-y-3">
                          {structuralRoles.slice(0, 6).map(([name, meta]) => (
                            <div key={name} className="flex items-start justify-between gap-4 border-b border-space-700 pb-3 last:border-b-0 last:pb-0">
                              <div>
                                <p className="font-mono text-indigo-300 text-sm">{name}</p>
                                <p className="text-xs text-slate-400 mt-1">{meta.reason}</p>
                              </div>
                              <Badge variant="info" size="sm">{meta.role.replace(/_/g, ' ')}</Badge>
                            </div>
                          ))}
                          {structuralRoles.length === 0 && (
                            <p className="text-sm text-slate-400">Structural role inference appears after the profile is available.</p>
                          )}
                        </div>
                      </Card>

                      <Card>
                        <h3 className="text-sm font-semibold text-white mb-4">Feature Intelligence</h3>
                        <div className="space-y-3">
                          {topSignals.slice(0, 6).map((signal) => {
                            const method = (signal as any).associationMethod || 'pearson';
                            const isEta = method === 'eta_squared';
                            const primaryScore = signal.sameTimeCorrelation.toFixed(2);
                            return (
                              <div key={signal.feature} className="flex items-start justify-between gap-4 border-b border-space-700 pb-3 last:border-b-0 last:pb-0">
                                <div>
                                  <p className="font-medium text-white text-sm">{signal.feature}</p>
                                  <p className="text-xs text-slate-400 mt-1">
                                    {isEta
                                      ? `η² (ANOVA) = ${primaryScore}`
                                      : `Pearson r = ${primaryScore} | Lag r = ${signal.lagInfluence.toFixed(2)}`
                                    }
                                  </p>
                                </div>
                                <Badge variant={signal.role === 'strong_driver' ? 'success' : 'info'} size="sm">
                                  {signal.role.replace(/_/g, ' ')}
                                </Badge>
                              </div>
                            );
                          })}
                          {topSignals.length === 0 && (
                            <p className="text-sm text-slate-400">Predictive signal estimation appears after the profile is generated.</p>
                          )}
                        </div>
                      </Card>
                    </div>

                    <div className="grid xl:grid-cols-2 gap-4">
                      <Card>
                        <h3 className="text-sm font-semibold text-white mb-4">Anomaly Windows</h3>
                        <div className="space-y-3">
                          {anomalyWindows.length === 0 ? (
                            <p className="text-sm text-slate-400">No high-severity anomaly windows were surfaced in the current profile.</p>
                          ) : (
                            anomalyWindows.slice(0, 5).map((item) => (
                              <div key={`${item.index}-${item.timestamp}`} className="flex items-center justify-between gap-4 border-b border-space-700 pb-3 last:border-b-0 last:pb-0">
                                <div>
                                  <p className="text-sm text-white">{item.timestamp}</p>
                                  <p className="text-xs text-slate-400">Index {item.index}</p>
                                </div>
                                <Badge variant={item.severity > 4 ? 'error' : 'warning'} size="sm">
                                  Severity {item.severity.toFixed(1)}
                                </Badge>
                              </div>
                            ))
                          )}
                        </div>
                      </Card>

                      <Card>
                        <h3 className="text-sm font-semibold text-white mb-4">Visualization Intelligence</h3>
                        <div className="space-y-3">
                          {visualizationIntents.map((viz) => (
                            <div key={viz.type} className="border-b border-space-700 pb-3 last:border-b-0 last:pb-0">
                              <div className="flex items-center gap-2 mb-1">
                                <Badge variant="secondary" size="sm">{viz.type}</Badge>
                                <p className="text-sm text-white">{viz.title}</p>
                              </div>
                              <p className="text-xs text-slate-400">{viz.reason}</p>
                            </div>
                          ))}
                          {visualizationIntents.length === 0 && (
                            <p className="text-sm text-slate-400">Visualization guidance will appear after the backend profile is available.</p>
                          )}
                        </div>
                      </Card>
                    </div>
                  </div>
                )}

                {activeTab === 'raw' && (
                  <div className="min-w-0 space-y-4">
                    <div className="flex flex-col gap-4 xl:flex-row xl:items-center xl:justify-between">
                      <div>
                        <h3 className="text-lg font-semibold text-white">Raw Data Explorer</h3>
                        <p className="text-sm text-slate-400">
                          Source: {rawRows?.source || 'loading'} | Rows {rawRows ? `${((rawRows.page - 1) * rawRows.page_size) + 1}-${Math.min(rawRows.page * rawRows.page_size, rawRows.total_rows)}` : '...'} of {rawRows?.total_rows?.toLocaleString() || '...'}
                        </p>
                      </div>
                      <div className="flex items-center gap-2">
                        <Button
                          variant="secondary"
                          size="sm"
                          icon={ChevronLeft}
                          onClick={() => setRawPage((page) => Math.max(1, page - 1))}
                          disabled={rawPage <= 1 || isRawLoading}
                        >
                          Prev
                        </Button>
                        <Badge variant="info" size="sm">
                          Page {rawRows?.page || rawPage} / {rawRows?.total_pages || '...'}
                        </Badge>
                        <Button
                          variant="secondary"
                          size="sm"
                          icon={ChevronRight}
                          onClick={() => setRawPage((page) => page + 1)}
                          disabled={isRawLoading || (rawRows ? rawRows.page >= rawRows.total_pages : false)}
                        >
                          Next
                        </Button>
                      </div>
                    </div>

                    {isRawLoading ? (
                      <Skeleton className="w-full h-96 rounded-lg" />
                    ) : rawRows?.rows?.length ? (
                      <Table
                        className="max-h-[64vh] rounded-lg border border-space-700 bg-space-900/30"
                        columns={rawRows.columns.map((column) => ({
                          key: column,
                          header: column,
                          width: 'min-w-[180px] max-w-[240px]',
                          headerClassName: 'bg-space-800/80',
                          cellClassName: 'font-mono',
                          render: (item: Record<string, unknown>) => {
                            const value = item[column];
                            const text = value === null || value === undefined ? '—' : String(value);
                            return (
                              <span className="block max-w-[220px] truncate text-xs text-slate-300" title={text}>
                                {text}
                              </span>
                            );
                          },
                        }))}
                        data={rawRows.rows}
                        keyExtractor={(item) => String(item.__rowId || item.timestamp || item.id || 'row')}
                      />
                    ) : (
                      <Card>
                        <p className="text-sm text-slate-400">{rawError || 'No raw rows available for this dataset yet.'}</p>
                      </Card>
                    )}
                  </div>
                )}

                {activeTab === 'timeseries' && (
                  <div>
                    <div className="flex items-center justify-between mb-4">
                      <h3 className="text-lg font-semibold text-white">Time Series Visualization</h3>
                      <div className="flex items-center gap-4 text-sm">
                        <div className="flex items-center gap-2">
                          <span className="w-3 h-3 rounded-full bg-cyan-400" />
                          <span className="text-slate-400">Actual</span>
                        </div>
                        <div className="flex items-center gap-2">
                          <span className="w-3 h-3 rounded-full bg-indigo-500" />
                          <span className="text-slate-400">Predicted</span>
                        </div>
                      </div>
                    </div>
                    {isLoading ? (
                      <Skeleton className="w-full h-96 rounded-lg" />
                    ) : (
                      <TimeSeriesChart data={timeSeriesData} showPrediction={false} showConfidence={false} />
                    )}
                  </div>
                )}

                {activeTab === 'distribution' && (
                  <div>
                    <h3 className="text-lg font-semibold text-white mb-4">Value Distribution</h3>
                    {isLoading ? (
                      <Skeleton className="w-full h-80 rounded-lg" />
                    ) : (
                      <DistributionChart data={distributionData} />
                    )}
                  </div>
                )}

                {activeTab === 'correlation' && (
                  <div>
                    <h3 className="text-lg font-semibold text-white mb-4">Feature Correlation Matrix</h3>
                    {isLoading ? (
                      <Skeleton className="w-full h-96 rounded-lg" />
                    ) : (
                      <CorrelationHeatmap data={correlationData} />
                    )}
                  </div>
                )}
              </div>
            </Card>
          </div>

          <motion.aside
            initial={{ opacity: 0, x: 20 }}
            animate={{ opacity: 1, x: 0 }}
            className="lg:w-96 shrink-0"
          >
            <Card className="sticky top-24">
              <div className="flex items-center justify-between mb-4">
                <div className="flex items-center gap-2">
                  <Sparkles className="w-5 h-5 text-indigo-400" />
                  <h3 className="font-semibold text-white">AI Insights</h3>
                </div>
                <button
                  onClick={() => setShowInsights(!showInsights)}
                  className="text-slate-400 hover:text-white"
                >
                  <ChevronDown
                    className={`w-5 h-5 transition-transform ${showInsights ? 'rotate-180' : ''}`}
                  />
                </button>
              </div>

              {showInsights && (
                <div>
                  {isAnalyzing ? (
                    <div className="space-y-4">
                      <div className="flex items-center gap-3 text-slate-400">
                        <div className="p-2 rounded-lg bg-indigo-500/20">
                          <Sparkles className="w-4 h-4 text-indigo-400 animate-pulse" />
                        </div>
                        <span className="text-sm">Analyzing dataset...</span>
                      </div>
                      <div className="space-y-2">
                        <Skeleton className="w-full h-4 rounded" />
                        <Skeleton className="w-4/5 h-4 rounded" />
                        <Skeleton className="w-3/5 h-4 rounded" />
                      </div>
                    </div>
                  ) : (
                    <div>
                      <div className="space-y-3 text-sm leading-relaxed text-slate-400">
                        {(profile?.insights || 'Intelligence analysis pending profile generation.')
                          .split('\n')
                          .filter(Boolean)
                          .map((line, index) => {
                            const isHeading = index === 0 || line.endsWith(':') || line.includes('Summary');
                            return (
                              <p key={index} className={isHeading ? 'font-semibold text-white' : ''}>
                                {line}
                              </p>
                            );
                          })}
                      </div>

                      {profile?.strategy_recommendation && (
                        <div className="mt-6 pt-4 border-t border-space-600 space-y-3">
                          <div className="flex items-center justify-between">
                            <span className="text-xs uppercase tracking-wide text-slate-500">Recommended Strategy</span>
                            <Badge variant="primary" size="sm">
                              {profile.strategy_recommendation.recommendedModelFamily || 'Adaptive'}
                            </Badge>
                          </div>
                          <p className="text-sm text-slate-300">
                            {profile.strategy_recommendation.reason || 'Strategy explanation pending.'}
                          </p>
                          <div className="flex flex-wrap gap-2">
                            {(profile.strategy_recommendation.preprocessingPlan || []).slice(0, 4).map((item) => (
                              <Badge key={item} variant="info" size="sm">{item}</Badge>
                            ))}
                          </div>
                        </div>
                      )}

                      <div className="flex items-center gap-2 mt-6 pt-4 border-t border-space-600">
                        <Button variant="ghost" size="sm" icon={Copy}>
                          Copy
                        </Button>
                        <Button variant="ghost" size="sm" icon={Sparkles} onClick={handleAnalyze}>
                          Regenerate
                        </Button>
                      </div>
                    </div>
                  )}
                </div>
              )}
            </Card>
          </motion.aside>
        </div>
      </div>
    </div>
  );
}
