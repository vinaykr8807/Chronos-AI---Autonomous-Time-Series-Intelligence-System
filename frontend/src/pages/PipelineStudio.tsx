import { useEffect, useRef, useState, useCallback, useMemo } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { motion } from 'framer-motion';
import {
  ReactFlow,
  Controls,
  Background,
  useNodesState,
  useEdgesState,
  addEdge,
  Handle,
  Position,
  type Node,
  type Edge,
  type Connection,
} from 'reactflow';
import 'reactflow/dist/style.css';
import {
  Database,
  Settings,
  Cpu,
  CheckCircle2,
  AlertCircle,
  Loader2,
  Zap,
  ChevronRight,
  Sliders,
  Activity,
  Target,
  Circle,
  LockKeyhole,
} from 'lucide-react';
import { Badge, Button, Card, StatusBadge } from '../components/common';
import { streamPipeline, type PipelineRunResult, type PipelineStreamEvent, type PipelineTraceEvent } from '../lib/api';

const nodeTypes = {
  dataIngestion: DataIngestionNode,
  cleaning: CleaningNode,
  preprocessing: PreprocessingNode,
  featureEngineering: FeatureEngineeringNode,
  model: ModelNode,
  evaluation: EvaluationNode,
  deployment: DeploymentNode,
};

interface PipelineNodeData {
  label: string;
  description: string;
  status: 'ready' | 'processing' | 'complete' | 'error';
  config: Record<string, unknown>;
}

function DataIngestionNode({ data }: { data: PipelineNodeData }) {
  return (
    <div className="bg-space-800 border-2 border-cyan-500/50 rounded-xl p-4 min-w-[200px] shadow-lg shadow-cyan-500/10">
      <Handle type="target" position={Position.Top} className="!bg-cyan-500" />
      <div className="flex items-center gap-3 mb-2">
        <div className="p-2 rounded-lg bg-cyan-500/20">
          <Database className="w-5 h-5 text-cyan-400" />
        </div>
        <span className="text-sm font-semibold text-white">{data.label}</span>
      </div>
      <p className="text-xs text-slate-400 mb-3">{data.description}</p>
      <StatusBadge status={data.status} />
      <Handle type="source" position={Position.Bottom} className="!bg-cyan-500" />
    </div>
  );
}

function PreprocessingNode({ data }: { data: PipelineNodeData }) {
  return (
    <div className="bg-space-800 border-2 border-indigo-500/50 rounded-xl p-4 min-w-[200px] shadow-lg shadow-indigo-500/10">
      <Handle type="target" position={Position.Top} className="!bg-indigo-500" />
      <div className="flex items-center gap-3 mb-2">
        <div className="p-2 rounded-lg bg-indigo-500/20">
          <Sliders className="w-5 h-5 text-indigo-400" />
        </div>
        <span className="text-sm font-semibold text-white">{data.label}</span>
      </div>
      <p className="text-xs text-slate-400 mb-3">{data.description}</p>
      <StatusBadge status={data.status} />
      <Handle type="source" position={Position.Bottom} className="!bg-indigo-500" />
    </div>
  );
}

function CleaningNode({ data }: { data: PipelineNodeData }) {
  return (
    <div className="bg-space-800 border-2 border-amber-500/50 rounded-xl p-4 min-w-[200px] shadow-lg shadow-amber-500/10">
      <Handle type="target" position={Position.Top} className="!bg-amber-500" />
      <div className="flex items-center gap-3 mb-2">
        <div className="p-2 rounded-lg bg-amber-500/20">
          <Sliders className="w-5 h-5 text-amber-400" />
        </div>
        <span className="text-sm font-semibold text-white">{data.label}</span>
      </div>
      <p className="text-xs text-slate-400 mb-3">{data.description}</p>
      <StatusBadge status={data.status} />
      <Handle type="source" position={Position.Bottom} className="!bg-amber-500" />
    </div>
  );
}

function FeatureEngineeringNode({ data }: { data: PipelineNodeData }) {
  return (
    <div className="bg-space-800 border-2 border-purple-500/50 rounded-xl p-4 min-w-[200px] shadow-lg shadow-purple-500/10">
      <Handle type="target" position={Position.Top} className="!bg-purple-500" />
      <div className="flex items-center gap-3 mb-2">
        <div className="p-2 rounded-lg bg-purple-500/20">
          <Activity className="w-5 h-5 text-purple-400" />
        </div>
        <span className="text-sm font-semibold text-white">{data.label}</span>
      </div>
      <p className="text-xs text-slate-400 mb-3">{data.description}</p>
      <StatusBadge status={data.status} />
      <Handle type="source" position={Position.Bottom} className="!bg-purple-500" />
    </div>
  );
}

function ModelNode({ data }: { data: PipelineNodeData }) {
  return (
    <div className="bg-space-800 border-2 border-pink-500/50 rounded-xl p-4 min-w-[200px] shadow-lg shadow-pink-500/10">
      <Handle type="target" position={Position.Top} className="!bg-pink-500" />
      <div className="flex items-center gap-3 mb-2">
        <div className="p-2 rounded-lg bg-pink-500/20">
          <Cpu className="w-5 h-5 text-pink-400" />
        </div>
        <span className="text-sm font-semibold text-white">{data.label}</span>
      </div>
      <p className="text-xs text-slate-400 mb-3">{data.description}</p>
      <StatusBadge status={data.status} />
      <Handle type="source" position={Position.Bottom} className="!bg-pink-500" />
    </div>
  );
}

function EvaluationNode({ data }: { data: PipelineNodeData }) {
  return (
    <div className="bg-space-800 border-2 border-emerald-500/50 rounded-xl p-4 min-w-[200px] shadow-lg shadow-emerald-500/10">
      <Handle type="target" position={Position.Top} className="!bg-emerald-500" />
      <div className="flex items-center gap-3 mb-2">
        <div className="p-2 rounded-lg bg-emerald-500/20">
          <Target className="w-5 h-5 text-emerald-400" />
        </div>
        <span className="text-sm font-semibold text-white">{data.label}</span>
      </div>
      <p className="text-xs text-slate-400 mb-3">{data.description}</p>
      <StatusBadge status={data.status} />
    </div>
  );
}

function DeploymentNode({ data }: { data: PipelineNodeData }) {
  return (
    <div className="bg-space-800 border-2 border-cyan-500/50 rounded-xl p-4 min-w-[200px] shadow-lg shadow-cyan-500/10">
      <Handle type="target" position={Position.Top} className="!bg-cyan-500" />
      <div className="flex items-center gap-3 mb-2">
        <div className="p-2 rounded-lg bg-cyan-500/20">
          <Zap className="w-5 h-5 text-cyan-400" />
        </div>
        <span className="text-sm font-semibold text-white">{data.label}</span>
      </div>
      <p className="text-xs text-slate-400 mb-3">{data.description}</p>
      <StatusBadge status={data.status} />
    </div>
  );
}

const initialNodes: Node[] = [];
const initialEdges: Edge[] = [];

function compactJson(value: unknown) {
  try {
    return JSON.stringify(value, null, 2);
  } catch {
    return String(value);
  }
}

function evidenceValue(value: unknown, fallback = 'pending') {
  return value === undefined || value === null || value === '' ? fallback : String(value);
}

function formatMetricValue(value: number | undefined, digits = 2) {
  if (typeof value !== 'number' || Number.isNaN(value)) {
    return 'Pending';
  }
  if (value !== 0 && Math.abs(value) < 1) {
    return value.toFixed(4);
  }
  return value.toFixed(digits);
}

function targetMetricUnit(targetColumn?: unknown) {
  const target = String(targetColumn || '').toLowerCase();
  if (target.includes('kwh')) return 'kWh';
  if (target.includes('mwh')) return 'MWh';
  if (target.includes('mw')) return 'MW';
  if (target.includes('%')) return '%';
  if (target.includes('$') || target.includes('price') || target.includes('revenue')) return '$';
  if (target.includes('indicator') || target.includes('status') || target.includes('flag')) return '';
  return '';
}

function asStringList(value: unknown): string[] {
  return Array.isArray(value) ? value.map((item) => String(item)) : [];
}

function asNumber(value: unknown, fallback = 0) {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : fallback;
}

function PredictionMiniChart({ samples }: { samples: Array<Record<string, unknown>> }) {
  const data = samples.slice(0, 80);
  if (!data.length) {
    return <div className="flex h-52 items-center justify-center rounded border border-space-700 text-sm text-slate-500">Evaluation samples pending</div>;
  }
  const actuals = data.map((item) => asNumber(item.actual));
  const preds = data.map((item) => asNumber(item.predicted));
  const all = [...actuals, ...preds];
  const min = Math.min(...all);
  const max = Math.max(...all);
  const span = Math.max(max - min, 1);
  const width = 520;
  const height = 190;
  const points = (values: number[]) => values.map((value, index) => {
    const x = data.length === 1 ? 0 : (index / (data.length - 1)) * width;
    const y = height - ((value - min) / span) * height;
    return `${x.toFixed(1)},${y.toFixed(1)}`;
  }).join(' ');
  return (
    <div className="rounded border border-space-700 bg-space-900/70 p-3">
      <div className="mb-2 flex items-center gap-4 text-xs">
        <span className="text-cyan-300">Actual</span>
        <span className="text-indigo-300">Predicted</span>
      </div>
      <svg viewBox={`0 0 ${width} ${height}`} className="h-52 w-full">
        <polyline points={points(actuals)} fill="none" stroke="#22d3ee" strokeWidth="2" />
        <polyline points={points(preds)} fill="none" stroke="#818cf8" strokeWidth="2" />
      </svg>
    </div>
  );
}

function ErrorBars({ samples }: { samples: Array<Record<string, unknown>> }) {
  const data = samples.slice(0, 56);
  if (!data.length) {
    return <div className="flex h-32 items-center justify-center rounded border border-space-700 text-sm text-slate-500">Residuals pending</div>;
  }
  const errors = data.map((item) => asNumber(item.error));
  const maxAbs = Math.max(...errors.map(Math.abs), 1);
  return (
    <div className="flex h-32 items-center gap-1 rounded border border-space-700 bg-space-900/70 p-3">
      {errors.map((error, index) => {
        const height = Math.max(2, Math.abs(error) / maxAbs * 52);
        return (
          <div key={index} className="flex flex-1 items-center justify-center">
            <div
              className={error >= 0 ? 'bg-emerald-400/80' : 'bg-red-400/80'}
              style={{ height: `${height}px`, width: '100%', maxWidth: '6px' }}
              title={`error ${error.toFixed(2)}`}
            />
          </div>
        );
      })}
    </div>
  );
}

const defaultAgents = [
  { name: 'Dataset Agent', responsibility: 'load the selected dataset and resolve the training dataframe' },
  { name: 'EDA Agent', responsibility: 'review the fresh in-memory profile before model selection' },
  { name: 'Cleaning Agent', responsibility: 'validate targets, sort time, and impute missing values' },
  { name: 'Feature Agent', responsibility: 'build numeric, categorical, temporal, PCA, and text feature plans' },
  { name: 'Training Agent', responsibility: 'select the model, run trials, and emit losses or validation errors' },
  { name: 'Evaluation Agent', responsibility: 'calculate MAE, RMSE, MAPE, R2, and MASE from holdout predictions' },
  { name: 'Deployment Agent', responsibility: 'package the run metadata and monitoring handoff' },
];

const defaultPipelineNodes = [
  { id: 'data-ingestion', type: 'dataIngestion', label: 'Data Ingestion', agent: 'Dataset Agent', description: 'Load and validate the selected dataframe' },
  { id: 'cleaning', type: 'cleaning', label: 'Cleaning Agent', agent: 'Cleaning Agent', description: 'Validate target rows and apply deterministic imputations' },
  { id: 'preprocessing', type: 'preprocessing', label: 'Preprocessing', agent: 'EDA Agent', description: 'Use the fresh profile and prepare split rules' },
  { id: 'feature-engineering', type: 'featureEngineering', label: 'Feature Engineering', agent: 'Feature Agent', description: 'Create model-ready feature matrices' },
  { id: 'model', type: 'model', label: 'Training Agent', agent: 'Training Agent', description: 'Train candidates and stream losses' },
  { id: 'evaluation', type: 'evaluation', label: 'Evaluation', agent: 'Evaluation Agent', description: 'Calculate validation metrics' },
  { id: 'deployment', type: 'deployment', label: 'Deployment Agent', agent: 'Deployment Agent', description: 'Package run metadata' },
];

const defaultPipelineEdges = [
  { source: 'data-ingestion', target: 'cleaning' },
  { source: 'cleaning', target: 'preprocessing' },
  { source: 'preprocessing', target: 'feature-engineering' },
  { source: 'feature-engineering', target: 'model' },
  { source: 'model', target: 'evaluation' },
  { source: 'evaluation', target: 'deployment' },
];

const yPositions = [40, 170, 300, 430, 560, 690, 820];

function initialGraphNodes(status: PipelineNodeData['status'] = 'ready') {
  return defaultPipelineNodes.map((node, index) => ({
    id: node.id,
    type: node.type,
    position: { x: 250, y: yPositions[index] ?? 50 + index * 150 },
    data: {
      label: node.label,
      description: node.description,
      status,
      config: { agent: node.agent },
    },
  }));
}

function initialGraphEdges(animated = false) {
  return defaultPipelineEdges.map((edge, index) => ({
    id: `${edge.source}-${edge.target}-${index}`,
    source: edge.source,
    target: edge.target,
    animated,
    type: 'smoothstep',
    style: { stroke: animated ? '#6366f1' : '#4f5d75', strokeWidth: 2 },
  }));
}

function traceFromStream(event: PipelineStreamEvent): PipelineTraceEvent | null {
  if (!event.agent || !event.stage || !event.message) {
    return null;
  }
  return {
    agent: event.agent,
    stage: event.stage,
    timestamp: event.timestamp,
    status: event.status || 'running',
    message: event.message,
    details: event.details || {},
  };
}

type StageStatus = 'complete' | 'running' | 'waiting' | 'locked' | 'error';

function StageIcon({ status }: { status: StageStatus }) {
  if (status === 'complete') {
    return <CheckCircle2 className="h-5 w-5 text-emerald-300" />;
  }
  if (status === 'running') {
    return <Loader2 className="h-5 w-5 animate-spin text-indigo-300" />;
  }
  if (status === 'error') {
    return <AlertCircle className="h-5 w-5 text-red-300" />;
  }
  if (status === 'locked') {
    return <LockKeyhole className="h-5 w-5 text-slate-500" />;
  }
  return <Circle className="h-5 w-5 text-slate-500" />;
}

export function PipelineStudio() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const [nodes, setNodes, onNodesChange] = useNodesState(initialNodes);
  const [edges, setEdges, onEdgesChange] = useEdgesState(initialEdges);
  const [selectedNode, setSelectedNode] = useState<string | null>(null);
  const [isAgentTuning, setIsAgentTuning] = useState(false);
  const [pipelineResult, setPipelineResult] = useState<PipelineRunResult | null>(null);
  const [streamEvents, setStreamEvents] = useState<PipelineStreamEvent[]>([]);
  const [pipelineError, setPipelineError] = useState<string | null>(null);
  const streamCloser = useRef<(() => void) | null>(null);
  const datasetParam = searchParams.get('dataset');
  const datasetId = datasetParam || '';
  const sourceRef = searchParams.get('ref');
  const edaReady = searchParams.get('eda') === 'ready';
  const hasDatasetContext = Boolean(datasetParam);
  const datasetLabel = datasetParam || 'No dataset selected';

  const applyPipelineResult = useCallback((result: PipelineRunResult) => {
    setPipelineResult(result);
    setNodes(result.nodes.map((node, index) => ({
      id: node.id,
      type: node.type,
      position: { x: 250, y: yPositions[index] ?? 50 + index * 150 },
      data: {
        label: node.label,
        description: node.description,
        status: node.status,
        config: node.config,
      },
    })));
    setEdges(result.pipeline_graph.edges.map((edge, index) => ({
      id: `${edge.source}-${edge.target}-${index}`,
      source: edge.source,
      target: edge.target,
      animated: false,
      type: 'smoothstep',
      style: { stroke: '#4f5d75', strokeWidth: 2 },
    })));
    setSelectedNode(null);
  }, [setEdges, setNodes]);

  const executePipeline = useCallback(() => {
    if (!hasDatasetContext || !edaReady) {
      setPipelineError('Run EDA first, then create the pipeline from the dataset intelligence page.');
      return;
    }
    streamCloser.current?.();
    setIsAgentTuning(true);
    setPipelineError(null);
    setPipelineResult(null);
    setStreamEvents([]);
    setNodes(initialGraphNodes().map((node, index) => ({
      ...node,
      data: {
        ...node.data,
        status: index === 0 ? 'processing' : 'ready',
      },
    })));
    setEdges(initialGraphEdges(true));
    setSelectedNode(null);

    streamCloser.current = streamPipeline(
      datasetId,
      sourceRef,
      (event) => {
        if (event.event !== 'heartbeat') {
          setStreamEvents((current) => [...current, event].slice(-400));
        }
        if (event.agent) {
          setNodes((current) => current.map((node) => {
            const spec = defaultPipelineNodes.find((item) => item.id === node.id);
            if (!spec || spec.agent !== event.agent) {
              return node;
            }
            return {
              ...node,
              data: {
                ...node.data,
                status: event.status === 'complete' ? 'complete' : event.status === 'error' ? 'error' : 'processing',
                description: event.message || node.data.description,
                config: event.details || node.data.config,
              },
            };
          }));
        }
        if (event.event === 'complete' && event.result) {
          applyPipelineResult(event.result);
          setIsAgentTuning(false);
          streamCloser.current = null;
        }
        if (event.event === 'error') {
          setPipelineError(event.message || 'Pipeline run failed');
          setIsAgentTuning(false);
          streamCloser.current = null;
        }
      },
      (message) => {
        setPipelineError(message);
        setIsAgentTuning(false);
        streamCloser.current = null;
      }
    );
  }, [applyPipelineResult, datasetId, edaReady, hasDatasetContext, sourceRef, setEdges, setNodes]);

  useEffect(() => {
    if (hasDatasetContext && edaReady && nodes.length === 0) {
      setNodes(initialGraphNodes());
      setEdges(initialGraphEdges());
    }
  }, [edaReady, hasDatasetContext, nodes.length, setEdges, setNodes]);

  useEffect(() => () => {
    streamCloser.current?.();
  }, []);

  const onConnect = useCallback(
    (params: Connection) => setEdges((eds) => addEdge(params, eds)),
    [setEdges]
  );

  const selectedNodeData = useMemo(() => {
    if (!selectedNode) return null;
    return nodes.find((n) => n.id === selectedNode)?.data;
  }, [selectedNode, nodes]);

  const liveTrace = useMemo(() => {
    const streamed = streamEvents.map(traceFromStream).filter((trace): trace is PipelineTraceEvent => Boolean(trace));
    return streamed.length ? streamed : (pipelineResult?.pipeline_trace || []);
  }, [pipelineResult, streamEvents]);

  const agentStatuses = useMemo(() => {
    const agentList = pipelineResult?.agents?.length ? pipelineResult.agents : defaultAgents;
    return agentList.map((agent) => {
      const trace = [...liveTrace].reverse().find((item) => item.agent === agent.name);
      const isComplete = pipelineResult ? Boolean((pipelineResult.pipeline_trace || []).find((item) => item.agent === agent.name)) : false;
      return {
        ...agent,
        status: trace?.status || (isComplete ? 'complete' : isAgentTuning ? 'waiting' : 'waiting'),
        stage: trace?.stage || 'waiting',
      };
    });
  }, [isAgentTuning, liveTrace, pipelineResult]);

  const lastStreamEvent = streamEvents.length ? streamEvents[streamEvents.length - 1] : null;
  const metricUnit = targetMetricUnit(pipelineResult?.sandbox?.targetColumn);
  const evaluationSamples = (pipelineResult?.evaluation_report?.predictionSamples as Array<Record<string, unknown>> | undefined) || [];
  const baselineMetrics = (pipelineResult?.evaluation_report?.baselineMetrics as Record<string, number> | undefined) || {};
  const aggregateMetrics = (pipelineResult?.evaluation_report?.aggregateMetrics as Record<string, number> | undefined) || {};
  const aggregateBaselineMetrics = (pipelineResult?.evaluation_report?.aggregateBaselineMetrics as Record<string, number> | undefined) || {};
  const foldMetrics = (pipelineResult?.evaluation_report?.foldMetrics as Array<Record<string, any>> | undefined) || [];
  const improvement = (pipelineResult?.evaluation_report?.improvement as Record<string, number> | undefined) || {};
  const residualSummary = (pipelineResult?.evaluation_report?.residualSummary as Record<string, number> | undefined) || {};
  const cleaningActions = asStringList(pipelineResult?.preprocessing_report?.transformationsApplied);
  const featureTransforms = asStringList(pipelineResult?.feature_plan?.transformations);
  const blockedFeatures = asStringList(pipelineResult?.feature_plan?.blockedLeakageFeatures);
  const artifactJson = String(pipelineResult?.deployment_report?.jsonPath || '');
  const artifactPickle = String(pipelineResult?.deployment_report?.picklePath || '');
  const isSyntheticRun = Boolean(pipelineResult?.sandbox?.syntheticFallback);
  const stageSteps = useMemo(() => {
    const byAgent = new Map(agentStatuses.map((agent) => [agent.name, agent]));
    const statusFor = (agentName: string): StageStatus => {
      const status = byAgent.get(agentName)?.status;
      if (status === 'complete' || status === 'error') return status;
      if (status === 'running') return 'running';
      return edaReady ? 'waiting' : 'locked';
    };
    return [
      {
        label: 'EDA Analysis',
        agent: 'EDA Agent',
        stage: edaReady ? 'complete' : 'required',
        status: edaReady ? 'complete' as StageStatus : 'locked' as StageStatus,
        description: 'Dataset profile, raw columns, target, and model recommendation must be ready first.',
      },
      {
        label: 'Data Ingestion',
        agent: 'Dataset Agent',
        stage: byAgent.get('Dataset Agent')?.stage || 'waiting',
        status: statusFor('Dataset Agent'),
        description: 'Load the same profiled dataframe into the training runtime.',
      },
      {
        label: 'Cleaning',
        agent: 'Cleaning Agent',
        stage: byAgent.get('Cleaning Agent')?.stage || 'waiting',
        status: statusFor('Cleaning Agent'),
        description: 'Validate target rows, sort time fields, and impute missing cells.',
      },
      {
        label: 'Features',
        agent: 'Feature Agent',
        stage: byAgent.get('Feature Agent')?.stage || 'waiting',
        status: statusFor('Feature Agent'),
        description: 'Build numeric, categorical, lag, PCA, and text feature plans when applicable.',
      },
      {
        label: 'Training',
        agent: 'Training Agent',
        stage: byAgent.get('Training Agent')?.stage || 'waiting',
        status: statusFor('Training Agent'),
        description: 'Run model trials and stream validation loss or epoch loss.',
      },
      {
        label: 'Evaluation',
        agent: 'Evaluation Agent',
        stage: byAgent.get('Evaluation Agent')?.stage || 'waiting',
        status: statusFor('Evaluation Agent'),
        description: 'Calculate MAE, RMSE, MAPE, R2, and MASE on holdout data.',
      },
      {
        label: 'Deployment',
        agent: 'Deployment Agent',
        stage: byAgent.get('Deployment Agent')?.stage || 'waiting',
        status: statusFor('Deployment Agent'),
        description: 'Package run metadata and monitoring handoff.',
      },
    ];
  }, [agentStatuses, edaReady]);

  if (!hasDatasetContext || !edaReady) {
    return (
      <div className="min-h-[calc(100vh-4rem)] bg-space-900">
        <div className="border-b border-space-600 bg-space-900/50">
          <div className="max-w-7xl mx-auto px-6 py-5 lg:px-8">
            <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
              <div>
                <h1 className="text-2xl font-bold text-white">Pipeline Locked</h1>
                <p className="mt-1 max-w-2xl text-sm text-slate-400">
                  ML training opens only after a dataset has completed EDA, so the model uses the current target, column analysis, and recommendation profile.
                </p>
              </div>
              <div className="flex items-center gap-3">
                <Button variant="secondary" onClick={() => navigate('/discover')}>
                  Choose Dataset
                </Button>
                {hasDatasetContext && (
                  <Button onClick={() => navigate(`/dataset/${encodeURIComponent(datasetId)}${sourceRef ? `?ref=${encodeURIComponent(sourceRef)}` : ''}`)}>
                    Run EDA
                  </Button>
                )}
              </div>
            </div>
          </div>
        </div>

        <div className="max-w-5xl mx-auto px-6 py-8 lg:px-8">
          <Card className="border-amber-500/30 bg-amber-500/5">
            <div className="flex items-start gap-4">
              <div className="rounded-lg bg-amber-500/15 p-3">
                <LockKeyhole className="h-6 w-6 text-amber-300" />
              </div>
              <div>
                <h2 className="text-lg font-semibold text-white">EDA is the gate for this pipeline</h2>
                <p className="mt-2 text-sm leading-relaxed text-amber-100/80">
                  Open a dataset from Discover, review the EDA/Raw Data/Intelligence tabs, then use Create Pipeline. Direct `/pipeline` visits no longer start a default training run.
                </p>
              </div>
            </div>
          </Card>

          <div className="mt-6 grid gap-3 md:grid-cols-2">
            {stageSteps.map((step) => (
              <Card key={step.label} className={step.status === 'complete' ? 'border-emerald-500/30 bg-emerald-500/5' : 'opacity-80'}>
                <div className="flex items-start gap-3">
                  <StageIcon status={step.status} />
                  <div>
                    <p className="font-semibold text-white">{step.label}</p>
                    <p className="mt-1 text-xs uppercase tracking-wide text-slate-500">{step.stage}</p>
                    <p className="mt-2 text-sm text-slate-400">{step.description}</p>
                  </div>
                </div>
              </Card>
            ))}
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-[calc(100vh-4rem)] bg-space-900">
      <div className="border-b border-space-600 bg-space-900/70">
        <div className="max-w-7xl mx-auto px-6 py-5 lg:px-8">
          <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
            <div>
              <p className="text-xs uppercase tracking-[0.2em] text-slate-500">Evidence Dashboard</p>
              <h1 className="mt-2 text-2xl font-bold text-white">Pipeline Studio</h1>
              <p className="mt-1 text-sm text-slate-400">
                {datasetLabel} - {pipelineResult?.data_source || sourceRef || 'source pending'} - target {String(pipelineResult?.sandbox?.targetColumn || 'pending')}
              </p>
            </div>
            <div className="flex flex-wrap items-center gap-3">
              {isAgentTuning && (
                <Badge variant="info" size="sm">Deep validation running</Badge>
              )}
              <Button isLoading={isAgentTuning} onClick={executePipeline}>
                Train & Evaluate
              </Button>
              <Button variant="secondary" onClick={() => navigate('/forecast')}>
                View Forecasts
              </Button>
            </div>
          </div>
          {pipelineError && (
            <div className="mt-4 rounded border border-red-500/40 bg-red-500/10 px-4 py-3 text-sm text-red-200">
              {pipelineError}
            </div>
          )}
          {isSyntheticRun && (
            <div className="mt-4 rounded border border-amber-500/40 bg-amber-500/10 px-4 py-3 text-sm text-amber-100">
              This run trained on synthetic fallback data. Treat the metrics, pickle, and JSON artifact as runtime/UI validation only until a real dataset source is resolved.
            </div>
          )}
        </div>
      </div>

      <div className="max-w-7xl mx-auto space-y-6 px-6 py-6 lg:px-8">
        <section className="grid gap-4 lg:grid-cols-6">
          {stageSteps.map((step) => (
            <div
              key={step.label}
              className={`rounded-lg border px-4 py-3 ${
                step.status === 'complete'
                  ? 'border-emerald-500/30 bg-emerald-500/5'
                  : step.status === 'running'
                    ? 'border-indigo-500/40 bg-indigo-500/10'
                    : step.status === 'error'
                      ? 'border-red-500/40 bg-red-500/10'
                      : 'border-space-600 bg-space-800/40'
              }`}
            >
              <div className="flex items-center justify-between gap-2">
                <p className="text-sm font-semibold text-white">{step.label}</p>
                <StageIcon status={step.status} />
              </div>
              <p className="mt-2 truncate text-xs text-slate-400">{step.stage}</p>
            </div>
          ))}
        </section>

        <section className="grid gap-4 lg:grid-cols-5">
          {[
            { label: 'Rows Loaded', value: pipelineResult ? Number(pipelineResult.sandbox?.dataframeRows || 0).toLocaleString() : 'Not run' },
            { label: 'Train / Test', value: pipelineResult ? `${Number(pipelineResult.sandbox?.trainRows || 0).toLocaleString()} / ${Number(pipelineResult.sandbox?.testRows || 0).toLocaleString()}` : 'Not run' },
            { label: 'Model', value: pipelineResult?.selected_model || 'Auto' },
            { label: 'Validation', value: String(pipelineResult?.evaluation_report?.validationMethod || 'Deep validation pending') },
            { label: 'Events', value: streamEvents.length ? `${streamEvents.length} received` : 'Waiting' },
          ].map((item) => (
            <div key={item.label} className="rounded-lg border border-space-600 bg-space-800/60 p-4">
              <p className="text-xs uppercase tracking-wide text-slate-500">{item.label}</p>
              <p className="mt-2 break-words text-sm font-semibold text-white">{item.value}</p>
            </div>
          ))}
        </section>

        <section className="grid gap-4 lg:grid-cols-4">
          {[
            { label: 'Baseline MAE', value: formatMetricValue(aggregateBaselineMetrics.mae || baselineMetrics.mae), unit: metricUnit },
            { label: 'Trained MAE', value: formatMetricValue(aggregateMetrics.mae || pipelineResult?.metrics.mae), unit: metricUnit },
            { label: 'RMSE', value: formatMetricValue(aggregateMetrics.rmse || pipelineResult?.metrics.rmse), unit: metricUnit },
            { label: 'R2 Score', value: formatMetricValue(aggregateMetrics.r2 || pipelineResult?.metrics.r2, 4), unit: '' },
          ].map((metric) => (
            <Card key={metric.label}>
              <p className="text-sm text-slate-400">{metric.label}</p>
              <div className="mt-2 flex items-baseline gap-2">
                <span className="font-mono text-2xl font-bold text-white">{metric.value}</span>
                {metric.unit && <span className="text-sm text-slate-500">{metric.unit}</span>}
              </div>
            </Card>
          ))}
        </section>

        <section className="grid gap-4 xl:grid-cols-3">
          <Card>
            <h2 className="text-lg font-semibold text-white">Data</h2>
            <div className="mt-4 space-y-3 text-sm">
              <div className="flex justify-between gap-4"><span className="text-slate-400">Source ref</span><span className={`break-all text-right font-mono text-xs ${isSyntheticRun ? 'text-amber-300' : 'text-cyan-300'}`}>{isSyntheticRun ? 'No real source resolved' : (sourceRef || pipelineResult?.data_source || 'pending')}</span></div>
              <div className="flex justify-between gap-4"><span className="text-slate-400">EDA rows</span><span className="font-mono text-white">{evidenceValue(pipelineResult?.sandbox?.rowsAnalyzedByEda)}</span></div>
              <div className="flex justify-between gap-4"><span className="text-slate-400">Synthetic fallback</span><span className={pipelineResult?.sandbox?.syntheticFallback ? 'text-amber-300' : 'text-emerald-300'}>{pipelineResult ? String(Boolean(pipelineResult.sandbox?.syntheticFallback)) : 'pending'}</span></div>
            </div>
          </Card>

          <Card>
            <h2 className="text-lg font-semibold text-white">Cleaning</h2>
            <div className="mt-4 space-y-3 text-sm">
              <div className="flex justify-between gap-4"><span className="text-slate-400">Rows after target validation</span><span className="font-mono text-white">{evidenceValue(pipelineResult?.preprocessing_report?.rowsAfterTargetValidation)}</span></div>
              <div className="flex justify-between gap-4"><span className="text-slate-400">Missing after</span><span className="font-mono text-white">{evidenceValue(pipelineResult?.preprocessing_report?.remainingMissingCells)}</span></div>
              <div className="space-y-2">
                {(cleaningActions.length ? cleaningActions : ['Waiting for cleaning report']).slice(0, 5).map((item) => (
                  <p key={item} className="rounded border border-space-700 bg-space-900/60 px-3 py-2 text-xs text-slate-300">{item}</p>
                ))}
              </div>
            </div>
          </Card>

          <Card>
            <h2 className="text-lg font-semibold text-white">Features</h2>
            <div className="mt-4 space-y-3 text-sm">
              <div className="flex justify-between gap-4"><span className="text-slate-400">Selected features</span><span className="font-mono text-white">{evidenceValue(pipelineResult?.feature_plan?.featureCount)}</span></div>
              <div className="flex flex-wrap gap-2">
                {(featureTransforms.length ? featureTransforms : ['pending']).map((item) => (
                  <span key={item} className="rounded border border-space-600 bg-space-900 px-2 py-1 text-xs text-slate-300">{item}</span>
                ))}
              </div>
              <div>
                <p className="text-xs uppercase tracking-wide text-slate-500">Blocked leakage features</p>
                <p className="mt-1 text-xs text-slate-300">{blockedFeatures.length ? blockedFeatures.slice(0, 8).join(', ') : 'None detected'}</p>
              </div>
            </div>
          </Card>
        </section>

        <section className="grid gap-4 xl:grid-cols-2">
          <Card>
            <div className="flex items-center justify-between gap-3">
              <h2 className="text-lg font-semibold text-white">Training</h2>
              <span className="text-xs text-slate-500">{pipelineResult?.optimization_trials?.length || 0} candidates tried</span>
            </div>
            <div className="mt-4 grid gap-3 md:grid-cols-2">
              <div className="rounded border border-space-700 bg-space-900/60 p-3 text-sm">
                <p className="text-slate-400">Best params</p>
                <p className="mt-2 break-words font-mono text-xs text-white">{pipelineResult ? compactJson(pipelineResult.nodes.find((node) => node.id === 'model')?.config || {}) : 'pending'}</p>
              </div>
              <div className="rounded border border-space-700 bg-space-900/60 p-3 text-sm">
                <p className="text-slate-400">Latest event</p>
                <p className="mt-2 text-xs text-slate-300">{lastStreamEvent?.message || 'Run the pipeline to stream folds and candidates.'}</p>
              </div>
            </div>
            <div className="mt-4 max-h-56 overflow-auto rounded border border-space-700">
              <table className="w-full text-left text-xs">
                <thead className="bg-space-800 text-slate-400">
                  <tr>
                    <th className="px-3 py-2">Fold</th>
                    <th className="px-3 py-2">Train</th>
                    <th className="px-3 py-2">Test</th>
                    <th className="px-3 py-2">MAE</th>
                    <th className="px-3 py-2">R2</th>
                  </tr>
                </thead>
                <tbody>
                  {(foldMetrics.length ? foldMetrics : [{ fold: '-', trainRows: '-', testRows: '-', metrics: {} }]).map((fold, index) => (
                    <tr key={`${fold.fold}-${index}`} className="border-t border-space-700">
                      <td className="px-3 py-2 text-white">{String(fold.fold)}</td>
                      <td className="px-3 py-2 text-slate-300">{String(fold.trainRows)}</td>
                      <td className="px-3 py-2 text-slate-300">{String(fold.testRows)}</td>
                      <td className="px-3 py-2 font-mono text-emerald-300">{formatMetricValue(fold.metrics?.mae)}</td>
                      <td className="px-3 py-2 font-mono text-cyan-300">{formatMetricValue(fold.metrics?.r2, 4)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Card>

          <Card>
            <div className="flex items-center justify-between gap-3">
              <h2 className="text-lg font-semibold text-white">Evaluation</h2>
              <span className="text-xs text-slate-500">MAE reduction {formatMetricValue(improvement.maeReductionPercent)}%</span>
            </div>
            <div className="mt-4 grid gap-4 md:grid-cols-2">
              <div>
                <div className="mb-2 flex items-center justify-between">
                  <p className="text-sm font-semibold text-white">Predicted vs Actual</p>
                  <span className="text-xs text-slate-500">{evaluationSamples.length} points</span>
                </div>
                <PredictionMiniChart samples={evaluationSamples} />
              </div>
              <div>
                <div className="mb-2 flex items-center justify-between">
                  <p className="text-sm font-semibold text-white">Residuals</p>
                  <span className="text-xs text-slate-500">p95 {formatMetricValue(residualSummary.p95AbsError)} {metricUnit}</span>
                </div>
                <ErrorBars samples={evaluationSamples} />
              </div>
            </div>
          </Card>
        </section>

        <section className="grid gap-4 xl:grid-cols-2">
          <Card>
            <h2 className="text-lg font-semibold text-white">Deployment</h2>
            <div className="mt-4 space-y-3 text-sm">
              <div className="flex justify-between gap-4"><span className="text-slate-400">JSON artifact</span><span className="break-all text-right font-mono text-xs text-cyan-300">{artifactJson || 'pending'}</span></div>
              <div className="flex justify-between gap-4"><span className="text-slate-400">Pickle/joblib artifact</span><span className="break-all text-right font-mono text-xs text-emerald-300">{artifactPickle || 'not available yet'}</span></div>
              <p className="rounded border border-amber-500/30 bg-amber-500/5 px-3 py-2 text-xs text-amber-100">
                {String(pipelineResult?.deployment_report?.llmExplanation || 'Artifacts are created only after a completed local runtime training run.')}
              </p>
            </div>
          </Card>

          <Card>
            <h2 className="text-lg font-semibold text-white">Run Integrity</h2>
            <div className="mt-4 space-y-3 text-sm">
              <div className="flex justify-between gap-4">
                <span className="text-slate-400">Real data loaded</span>
                <span className={isSyntheticRun ? 'text-amber-300' : 'text-emerald-300'}>
                  {pipelineResult ? String(!isSyntheticRun) : 'pending'}
                </span>
              </div>
              <div className="flex justify-between gap-4">
                <span className="text-slate-400">Validation folds</span>
                <span className="font-mono text-white">{foldMetrics.length || 'pending'}</span>
              </div>
              <div className="flex justify-between gap-4">
                <span className="text-slate-400">Candidates completed</span>
                <span className="font-mono text-white">{pipelineResult?.optimization_trials?.length || 'pending'}</span>
              </div>
              <p className={`rounded border px-3 py-2 text-xs ${isSyntheticRun ? 'border-amber-500/30 bg-amber-500/5 text-amber-100' : 'border-emerald-500/30 bg-emerald-500/5 text-emerald-100'}`}>
                {isSyntheticRun
                  ? 'Synthetic fallback is active. Choose a dataset with a Kaggle/local source before trusting metrics.'
                  : 'All displayed metrics came from the resolved real dataframe.'}
              </p>
            </div>
          </Card>
        </section>

        {pipelineResult?.agent_decisions?.length ? (
          <section>
            <Card>
              <h2 className="text-lg font-semibold text-white">Run Decisions</h2>
              <div className="mt-4 grid gap-3 md:grid-cols-2">
                {pipelineResult.agent_decisions.map((decision) => (
                  <div key={decision} className="flex gap-2 text-sm text-slate-300">
                    <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0 text-emerald-400" />
                    <span>{decision}</span>
                  </div>
                ))}
              </div>
            </Card>
          </section>
        ) : null}
      </div>
    </div>
  );

  return (
    <div className="min-h-[calc(100vh-4rem)] flex flex-col">
      {/* Header */}
      <div className="border-b border-space-600 bg-space-900/50">
        <div className="max-w-7xl mx-auto px-6 py-4 lg:px-8">
          <div className="flex items-center justify-between">
            <div>
              <h1 className="text-2xl font-bold text-white">Pipeline Studio</h1>
              <p className="mt-1 text-sm text-slate-400">
                Visual ML pipeline builder with automated model tuning for {datasetLabel}
              </p>
            </div>
            <div className="flex items-center gap-3">
              {isAgentTuning && (
                <div className="flex items-center gap-2 px-3 py-1.5 rounded-full bg-indigo-500/20 border border-indigo-500/40">
                  <span className="relative flex h-2 w-2">
                    <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-indigo-400 opacity-75"></span>
                    <span className="relative inline-flex rounded-full h-2 w-2 bg-indigo-500"></span>
                  </span>
                  <span className="text-xs font-medium text-indigo-400">Agent Auto-Tuning Active</span>
                </div>
              )}
              <Button isLoading={isAgentTuning} onClick={executePipeline}>
                Train & Evaluate
              </Button>
              <Button variant="secondary" onClick={() => navigate('/forecast')}>
                View Forecasts
              </Button>
            </div>
          </div>
        </div>
      </div>

      <div className="flex-1 flex">
        {/* Configuration Panel - Left */}
        <div className="w-80 border-r border-space-600 bg-space-900/50 p-6 overflow-y-auto">
          <h3 className="text-lg font-semibold text-white mb-4">Stage Checklist</h3>

          <div className="space-y-3 mb-6">
            {stageSteps.map((step) => (
              <Card
                key={step.label}
                className={`p-4 ${step.status === 'complete' ? 'border-emerald-500/30 bg-emerald-500/5' : step.status === 'running' ? 'border-indigo-500/40 bg-indigo-500/10' : step.status === 'error' ? 'border-red-500/30 bg-red-500/5' : 'opacity-70'}`}
              >
                <div className="flex items-center justify-between gap-3">
                  <div>
                    <p className="text-sm font-semibold text-white">{step.label}</p>
                    <p className="mt-1 text-xs text-slate-400">{step.stage}</p>
                  </div>
                  <StageIcon status={step.status} />
                </div>
                <p className="mt-3 text-xs leading-relaxed text-slate-500">{step.description}</p>
              </Card>
            ))}
          </div>

          <h3 className="text-lg font-semibold text-white mb-4">Configuration</h3>

          {!pipelineResult && !isAgentTuning && (
            <Card className="mb-4 bg-emerald-500/10 border-emerald-500/30">
              <p className="text-sm font-semibold text-emerald-200">EDA handoff ready</p>
              <p className="mt-2 text-sm text-emerald-100/80">
                This pipeline will use the completed EDA profile for <span className="font-medium text-white">{datasetLabel}</span>. Start training when you are ready.
              </p>
            </Card>
          )}

          {pipelineResult?.sandbox && (
            <Card className="mb-4">
              <div className="flex items-center gap-2 mb-3">
                <Zap className="w-4 h-4 text-cyan-400" />
                <h4 className="font-medium text-white">Training Transparency</h4>
              </div>
              <div className="space-y-2 text-xs text-slate-400">
                <div className="flex justify-between gap-3">
                  <span>Mode</span>
                  <span className="text-cyan-300">{String(pipelineResult.sandbox.mode)}</span>
                </div>
                <div className="flex justify-between gap-3">
                  <span>Executor</span>
                  <span className="text-white">{String(pipelineResult.sandbox.executor)}</span>
                </div>
                <div className="flex justify-between gap-3">
                  <span>Input Source</span>
                  <span className={pipelineResult.sandbox.syntheticFallback ? 'text-amber-300' : 'text-emerald-300'}>
                    {String(pipelineResult.sandbox.dataSource || 'unknown')}
                  </span>
                </div>
                <div className="flex justify-between gap-3">
                  <span>EDA Rows</span>
                  <span className="text-white font-mono">{String(pipelineResult.sandbox.rowsAnalyzedByEda || 'unknown')}</span>
                </div>
                <div className="flex justify-between gap-3">
                  <span>Train / Test</span>
                  <span className="text-white font-mono">
                    {String(pipelineResult.sandbox.trainRows)} / {String(pipelineResult.sandbox.testRows)}
                  </span>
                </div>
                <div className="flex justify-between gap-3">
                  <span>Loaded Rows</span>
                  <span className="text-white font-mono">{String(pipelineResult.sandbox.dataframeRows)}</span>
                </div>
                <div className="flex justify-between gap-3">
                  <span>Training Mode</span>
                  <span className="text-white">{String(pipelineResult.sandbox.trainingMode)}</span>
                </div>
                <div className="flex justify-between gap-3">
                  <span>Target Column</span>
                  <span className="text-white font-mono">{String(pipelineResult.sandbox.targetColumn)}</span>
                </div>
                <div className="flex justify-between gap-3">
                  <span>Feature Count</span>
                  <span className="text-white font-mono">{String(pipelineResult.sandbox.featureCount)}</span>
                </div>
              </div>
            </Card>
          )}

          {selectedNodeData ? (
            <div className="space-y-4">
              <Card>
                <div className="flex items-center gap-2 mb-4">
                  <Settings className="w-4 h-4 text-slate-400" />
                  <h4 className="font-medium text-white">{selectedNodeData.label}</h4>
                </div>

                <div className="space-y-4">
                  {Object.entries(selectedNodeData.config).map(([key, value]) => (
                    <div key={key}>
                      <label className="text-xs text-slate-400 capitalize">
                        {key.replace(/([A-Z])/g, ' $1').trim()}
                      </label>
                      <div className="mt-1 flex items-center gap-2">
                        <input
                          type="text"
                          defaultValue={String(value)}
                          className="flex-1 bg-space-800 border border-space-600 rounded px-3 py-1.5 text-sm text-white focus:outline-none focus:ring-2 focus:ring-indigo-500"
                        />
                      </div>
                    </div>
                  ))}
                </div>

                <Button className="w-full mt-4" size="sm">
                  Apply Changes
                </Button>
              </Card>
            </div>
          ) : (
            <div className="flex flex-col items-center justify-center py-12 text-center">
              <Settings className="w-8 h-8 text-slate-600 mb-3" />
              <p className="text-sm text-slate-500">Select a node to configure</p>
            </div>
          )}
        </div>

        {/* Pipeline Canvas */}
        <div className="flex-1 flex flex-col min-w-0">
          <div className="flex-1 min-h-[460px] relative">
            <ReactFlow
              nodes={nodes}
              edges={edges}
              onNodesChange={onNodesChange}
              onEdgesChange={onEdgesChange}
              onConnect={onConnect}
              onNodeClick={(_, node) => setSelectedNode(node.id)}
              nodeTypes={nodeTypes}
              fitView
              className="bg-space-900"
            >
              <Controls className="!bg-space-800 !border-space-600" />
              <Background color="#2d3344" gap={20} />
            </ReactFlow>

            {/* Agent Status Overlay */}
            {isAgentTuning && (
              <div className="absolute bottom-4 left-4 bg-space-800/90 backdrop-blur border border-space-600 rounded-lg p-3">
              <div className="flex items-center gap-2">
                <Loader2 className="w-4 h-4 text-indigo-400 animate-spin" />
                <span className="text-sm text-white">Auto-tuning hyperparameters...</span>
              </div>
              <div className="mt-2 w-48 h-1.5 bg-space-700 rounded-full overflow-hidden">
                <motion.div
                  className="h-full bg-gradient-to-r from-indigo-500 to-cyan-400 rounded-full"
                  initial={{ width: 0 }}
                  animate={{ width: '65%' }}
                  transition={{ duration: 2, repeat: Infinity }}
                />
              </div>
            </div>
            )}
            {pipelineError && (
              <div className="absolute bottom-4 left-4 bg-red-500/10 border border-red-500/40 rounded-lg p-3 text-sm text-red-300">
              {pipelineError}
            </div>
            )}
          </div>

          <div className="border-t border-space-600 bg-space-900/95 p-4">
            <div className="mb-4 flex items-center justify-between">
              <h3 className="text-sm font-semibold uppercase tracking-[0.2em] text-slate-400">Training Evidence</h3>
              <span className="text-xs text-slate-500">
                {lastStreamEvent?.message || 'Run pipeline to populate evaluation evidence'}
              </span>
            </div>

            <div className="grid gap-4 xl:grid-cols-3">
              <Card>
                <h4 className="text-sm font-semibold text-white">Cleaning</h4>
                <div className="mt-3 space-y-2 text-xs text-slate-300">
                  <div className="flex justify-between">
                    <span>Rows after target check</span>
                    <span className="font-mono text-white">{String(pipelineResult?.preprocessing_report?.rowsAfterTargetValidation || 'pending')}</span>
                  </div>
                  <div className="flex justify-between">
                    <span>Remaining missing cells</span>
                    <span className="font-mono text-white">{String(pipelineResult?.preprocessing_report?.remainingMissingCells || 'pending')}</span>
                  </div>
                  <div className="max-h-28 overflow-y-auto pt-2">
                    {(cleaningActions.length ? cleaningActions : ['No cleaning actions recorded yet.']).slice(0, 6).map((item) => (
                      <p key={item} className="border-t border-space-700 py-2">{item}</p>
                    ))}
                  </div>
                </div>
              </Card>

              <Card>
                <h4 className="text-sm font-semibold text-white">Features</h4>
                <div className="mt-3 space-y-2 text-xs text-slate-300">
                  <div className="flex justify-between">
                    <span>Feature count</span>
                    <span className="font-mono text-white">{String(pipelineResult?.feature_plan?.featureCount || 'pending')}</span>
                  </div>
                  <div className="flex flex-wrap gap-2 pt-2">
                    {(featureTransforms.length ? featureTransforms : ['pending']).map((item) => (
                      <span key={item} className="rounded border border-space-600 bg-space-800 px-2 py-1 text-slate-300">{item}</span>
                    ))}
                  </div>
                  <p className="pt-2 text-slate-500">
                    {String((pipelineResult?.feature_plan?.tfidf as any)?.reason || 'Text/PCA decisions will appear after feature generation.')}
                  </p>
                </div>
              </Card>

              <Card>
                <h4 className="text-sm font-semibold text-white">Before vs After</h4>
                <div className="mt-3 grid grid-cols-2 gap-3 text-xs">
                  <div className="rounded border border-space-700 bg-space-900/60 p-3">
                    <p className="text-slate-500">Baseline MAE</p>
                    <p className="mt-1 font-mono text-lg text-white">{formatMetricValue(baselineMetrics.mae)} {metricUnit}</p>
                  </div>
                  <div className="rounded border border-space-700 bg-space-900/60 p-3">
                    <p className="text-slate-500">Trained MAE</p>
                    <p className="mt-1 font-mono text-lg text-emerald-300">{formatMetricValue(pipelineResult?.metrics.mae)} {metricUnit}</p>
                  </div>
                  <div className="col-span-2 rounded border border-space-700 bg-space-900/60 p-3">
                    <p className="text-slate-500">MAE reduction</p>
                    <p className="mt-1 font-mono text-lg text-cyan-300">{formatMetricValue(improvement.maeReductionPercent)}%</p>
                  </div>
                </div>
              </Card>
            </div>

            <div className="mt-4 grid gap-4 xl:grid-cols-2">
              <Card>
                <div className="mb-3 flex items-center justify-between">
                  <h4 className="text-sm font-semibold text-white">Predicted vs Actual</h4>
                  <span className="text-xs text-slate-500">{evaluationSamples.length} sampled holdout points</span>
                </div>
                <PredictionMiniChart samples={evaluationSamples} />
              </Card>
              <Card>
                <div className="mb-3 flex items-center justify-between">
                  <h4 className="text-sm font-semibold text-white">Residual Error</h4>
                  <span className="text-xs text-slate-500">p95 abs error {formatMetricValue(residualSummary.p95AbsError)} {metricUnit}</span>
                </div>
                <ErrorBars samples={evaluationSamples} />
                <div className="mt-3 grid grid-cols-2 gap-3 text-xs text-slate-400">
                  <span>Mean error: <b className="font-mono text-white">{formatMetricValue(residualSummary.meanError)} {metricUnit}</b></span>
                  <span>Max abs: <b className="font-mono text-white">{formatMetricValue(residualSummary.maxAbsError)} {metricUnit}</b></span>
                </div>
              </Card>
            </div>
          </div>
        </div>

        {/* Metrics Panel - Right */}
        <div className="w-80 border-l border-space-600 bg-space-900/50 p-6 overflow-y-auto">
          <h3 className="text-lg font-semibold text-white mb-4">Model Metrics</h3>

          {(isAgentTuning || lastStreamEvent) && (
            <Card className="mb-4 border-indigo-500/30 bg-indigo-500/5">
              <div className="flex items-center justify-between gap-3">
                <span className="text-sm font-semibold text-white">Live Pipeline Stream</span>
                <span className={`rounded-full px-2 py-1 text-xs ${isAgentTuning ? 'bg-indigo-500/20 text-indigo-300' : 'bg-emerald-500/10 text-emerald-300'}`}>
                  {isAgentTuning ? 'running' : 'complete'}
                </span>
              </div>
              <p className="mt-2 text-xs leading-relaxed text-slate-300">
                {lastStreamEvent?.message || 'Waiting for the first agent event...'}
              </p>
              <p className="mt-3 font-mono text-xs text-slate-500">{liveTrace.length} trace events received</p>
            </Card>
          )}

          <div className="space-y-4">
            {[
              { label: 'MAE', value: formatMetricValue(pipelineResult?.metrics.mae), unit: metricUnit, trend: 'down' },
              { label: 'RMSE', value: formatMetricValue(pipelineResult?.metrics.rmse), unit: metricUnit, trend: 'down' },
              { label: 'MAPE', value: pipelineResult ? `${formatMetricValue(pipelineResult.metrics.mape)}%` : 'Pending', trend: 'down' },
              { label: 'R2 Score', value: formatMetricValue(pipelineResult?.metrics.r2, 4), trend: 'up' },
            ].map((metric) => (
              <Card key={metric.label}>
                <div className="flex items-center justify-between">
                  <span className="text-sm text-slate-400">{metric.label}</span>
                  <span className={`text-xs ${
                    metric.trend === 'up' ? 'text-emerald-400' : 'text-amber-400'
                  }`}>
                    {metric.trend === 'up' ? 'Improved' : 'Lower is better'}
                  </span>
                </div>
                <div className="mt-2 flex items-baseline gap-1">
                  <span className="text-2xl font-bold text-white font-mono">{metric.value}</span>
                  {metric.unit && <span className="text-sm text-slate-500">{metric.unit}</span>}
                </div>
              </Card>
            ))}
          </div>

          <div className="mt-6">
            <h3 className="text-lg font-semibold text-white mb-4">Model Info</h3>
            <Card>
              <div className="space-y-3 text-sm">
                <div className="flex justify-between">
                  <span className="text-slate-400">Model Type</span>
                  <span className="text-white">{pipelineResult?.selected_model || 'Pending'}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-slate-400">Run ID</span>
                  <span className="text-white font-mono text-xs">{pipelineResult?.run_id.slice(0, 8) || 'pending'}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-slate-400">Data Source</span>
                  <span className="text-white font-mono text-xs">{pipelineResult?.data_source || 'pending'}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-slate-400">Validation</span>
                  <span className="text-white font-mono text-xs">{String(pipelineResult?.evaluation_report?.validationMethod || 'pending')}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-slate-400">Tuning</span>
                  <span className="text-white font-mono">agent optimized</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-slate-400">Last Updated</span>
                  <span className="text-slate-400 text-xs">live run</span>
                </div>
              </div>
            </Card>
          </div>

          {pipelineResult?.feature_plan && (
            <div className="mt-6">
              <h3 className="text-lg font-semibold text-white mb-4">Feature Plan</h3>
              <Card>
                <div className="space-y-3 text-sm">
                  <div className="flex justify-between gap-3">
                    <span className="text-slate-400">Features</span>
                    <span className="font-mono text-white">{String(pipelineResult.feature_plan.featureCount || 0)}</span>
                  </div>
                  <div>
                    <p className="text-slate-400">Transforms</p>
                    <p className="mt-1 text-xs text-slate-300">{((pipelineResult.feature_plan.transformations as string[]) || []).join(', ') || 'pending'}</p>
                  </div>
                  <div>
                    <p className="text-slate-400">PCA</p>
                    <p className="mt-1 text-xs text-slate-300">{String((pipelineResult.feature_plan.pca as any)?.reason || 'pending')}</p>
                  </div>
                  <div>
                    <p className="text-slate-400">TF-IDF</p>
                    <p className="mt-1 text-xs text-slate-300">{String((pipelineResult.feature_plan.tfidf as any)?.reason || 'pending')}</p>
                  </div>
                </div>
              </Card>
            </div>
          )}

          {pipelineResult?.training_history?.length > 0 && (
            <div className="mt-6">
              <h3 className="text-lg font-semibold text-white mb-4">Training History</h3>
              <Card>
                <div className="max-h-64 space-y-2 overflow-y-auto">
                  {pipelineResult.training_history.slice(0, 24).map((item, index) => (
                    <div key={index} className="flex items-center justify-between gap-3 rounded bg-space-900/60 px-3 py-2 text-xs">
                      <span className="font-mono text-slate-400">
                        {'iteration' in item ? `iter ${String(item.iteration)}` : 'epoch' in item ? `epoch ${String(item.epoch)}` : `step ${index + 1}`}
                      </span>
                      <span className="font-mono text-emerald-300">
                        {item.validationMae !== undefined
                          ? `val_mae ${Number(item.validationMae).toFixed(4)}`
                          : item.trainingLoss !== undefined
                            ? `loss ${Number(item.trainingLoss).toFixed(6)}`
                            : compactJson(item)}
                      </span>
                    </div>
                  ))}
                </div>
              </Card>
            </div>
          )}

          {pipelineResult?.deployment_report && (
            <div className="mt-6">
              <h3 className="text-lg font-semibold text-white mb-4">Deployment</h3>
              <Card>
                <div className="space-y-2 text-xs text-slate-400">
                  <div className="flex justify-between gap-3">
                    <span>Status</span>
                    <span className="text-emerald-300">{String(pipelineResult.deployment_report.status || 'pending')}</span>
                  </div>
                  <div className="flex justify-between gap-3">
                    <span>Artifact</span>
                    <span className="text-white">{String(pipelineResult.deployment_report.artifactMode || 'pending')}</span>
                  </div>
                  <div className="border-t border-space-700 pt-2">
                    <p className="text-slate-500">JSON export</p>
                    <p className="mt-1 break-all font-mono text-[11px] text-cyan-300">{artifactJson || 'pending'}</p>
                  </div>
                  <div>
                    <p className="text-slate-500">Pickle/joblib export</p>
                    <p className="mt-1 break-all font-mono text-[11px] text-emerald-300">{artifactPickle || 'not available for this backend'}</p>
                  </div>
                  <p className="pt-2 text-slate-300">{String(pipelineResult.deployment_report.llmExplanation || '')}</p>
                </div>
              </Card>
            </div>
          )}

          {pipelineResult?.agent_decisions && (
            <div className="mt-6">
              <h3 className="text-lg font-semibold text-white mb-4">Agent Decisions</h3>
              <Card>
                <div className="space-y-3">
                  {pipelineResult.agent_decisions.map((decision) => (
                    <div key={decision} className="flex gap-2 text-sm text-slate-300">
                      <CheckCircle2 className="w-4 h-4 text-emerald-400 shrink-0 mt-0.5" />
                      <span>{decision}</span>
                    </div>
                  ))}
                </div>
              </Card>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
