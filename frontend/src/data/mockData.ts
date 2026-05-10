export interface Dataset {
  id: string;
  title: string;
  description: string;
  domain: 'energy' | 'traffic' | 'sales' | 'finance' | 'iot' | 'general';
  tags: string[];
  relevanceScore: number;
  isTimeSeriesValidated: boolean;
  rowCount: number;
  columnCount: number;
  timeRange: {
    start: string;
    end: string;
  };
  missingPercent: number;
  thumbnail?: string;
  source?: string;
  ref?: string | null;
  validationSummary?: string | null;
}

export interface ColumnInfo {
  name: string;
  type: 'numeric' | 'categorical' | 'datetime';
  missingPercent: number;
  description: string;
  uniqueValues?: number;
  min?: number;
  max?: number;
  mean?: number;
}

export interface TimeSeriesDataPoint {
  timestamp: string;
  value: number;
  predicted?: number;
  lower?: number;
  upper?: number;
}

export interface DistributionDataPoint {
  range: string;
  frequency: number;
}

export interface CorrelationDataPoint {
  feature1: string;
  feature2: string;
  correlation: number;
}

export interface ModelMetrics {
  mae: number;
  rmse: number;
  mape: number;
  r2: number;
  lastUpdated: string;
}

export interface SystemAlert {
  id: string;
  type: 'drift' | 'error' | 'info' | 'warning';
  title: string;
  message: string;
  timestamp: string;
  acknowledged: boolean;
}

export interface PipelineNode {
  id: string;
  type: 'dataIngestion' | 'preprocessing' | 'featureEngineering' | 'model' | 'evaluation';
  label: string;
  description: string;
  status: 'ready' | 'processing' | 'complete' | 'error';
  config: Record<string, unknown>;
}

export interface ForecastSummary {
  period: string;
  prediction: number;
  confidence: {
    lower: number;
    upper: number;
  };
  trend: 'up' | 'down' | 'stable';
}

export interface DecisionInsight {
  id: string;
  priority: 'high' | 'medium' | 'low';
  title: string;
  description: string;
  action: string;
  expectedImpact: string;
}

export const datasets: Dataset[] = [
  {
    id: 'energy-001',
    title: 'California Energy Consumption',
    description: 'Hourly energy consumption data for California grid covering residential, commercial, and industrial sectors from 2018 to 2024.',
    domain: 'energy',
    tags: ['energy', 'consumption', 'california', 'grid', 'hourly'],
    relevanceScore: 0.95,
    isTimeSeriesValidated: true,
    rowCount: 52584,
    columnCount: 12,
    timeRange: { start: '2018-01-01', end: '2024-12-31' },
    missingPercent: 2.3,
  },
  {
    id: 'energy-002',
    title: 'Solar Panel Generation Data',
    description: 'Solar power generation readings from distributed panels with weather correlation data including irradiance and temperature.',
    domain: 'energy',
    tags: ['solar', 'renewable', 'generation', 'weather'],
    relevanceScore: 0.88,
    isTimeSeriesValidated: true,
    rowCount: 87600,
    columnCount: 18,
    timeRange: { start: '2020-01-01', end: '2024-06-30' },
    missingPercent: 5.7,
  },
  {
    id: 'traffic-001',
    title: 'Highway Traffic Flow Analysis',
    description: 'Real-time traffic flow data from highway sensors including vehicle count, average speed, and occupancy rates.',
    domain: 'traffic',
    tags: ['traffic', 'highway', 'vehicles', 'speed', 'flow'],
    relevanceScore: 0.92,
    isTimeSeriesValidated: true,
    rowCount: 234890,
    columnCount: 15,
    timeRange: { start: '2019-06-01', end: '2024-05-31' },
    missingPercent: 1.2,
  },
  {
    id: 'traffic-002',
    title: 'Urban Traffic Congestion Index',
    description: 'City-wide traffic congestion measurements derived from GPS probe data across major metropolitan areas.',
    domain: 'traffic',
    tags: ['congestion', 'urban', 'gps', 'city', 'mobility'],
    relevanceScore: 0.85,
    isTimeSeriesValidated: true,
    rowCount: 156420,
    columnCount: 8,
    timeRange: { start: '2021-01-01', end: '2024-04-30' },
    missingPercent: 3.8,
  },
  {
    id: 'sales-001',
    title: 'E-commerce Transaction Records',
    description: 'Complete transaction logs from a large e-commerce platform including product categories, customer segments, and revenue metrics.',
    domain: 'sales',
    tags: ['e-commerce', 'transactions', 'revenue', 'retail'],
    relevanceScore: 0.91,
    isTimeSeriesValidated: true,
    rowCount: 1247890,
    columnCount: 24,
    timeRange: { start: '2020-01-01', end: '2024-03-31' },
    missingPercent: 0.8,
  },
  {
    id: 'sales-002',
    title: 'Retail Store Inventory Levels',
    description: 'Daily inventory tracking across 500+ retail locations with stock levels, reorder points, and supplier lead times.',
    domain: 'sales',
    tags: ['inventory', 'retail', 'stock', 'supply-chain'],
    relevanceScore: 0.78,
    isTimeSeriesValidated: true,
    rowCount: 456789,
    columnCount: 16,
    timeRange: { start: '2022-01-01', end: '2024-05-15' },
    missingPercent: 4.2,
  },
  {
    id: 'finance-001',
    title: 'Stock Market Microstructure',
    description: 'High-frequency trading data including order book dynamics, bid-ask spreads, and trade volumes with millisecond precision.',
    domain: 'finance',
    tags: ['stocks', 'trading', 'high-frequency', 'order-book'],
    relevanceScore: 0.89,
    isTimeSeriesValidated: true,
    rowCount: 8945621,
    columnCount: 32,
    timeRange: { start: '2023-01-01', end: '2024-05-01' },
    missingPercent: 0.1,
  },
  {
    id: 'finance-002',
    title: 'Cryptocurrency Volatility Index',
    description: 'Volatility indices calculated from major cryptocurrency exchanges with real-time price feeds and derived indicators.',
    domain: 'finance',
    tags: ['crypto', 'volatility', 'bitcoin', 'ethereum'],
    relevanceScore: 0.82,
    isTimeSeriesValidated: true,
    rowCount: 525600,
    columnCount: 28,
    timeRange: { start: '2022-01-01', end: '2024-05-10' },
    missingPercent: 2.1,
  },
  {
    id: 'iot-001',
    title: 'Industrial IoT Sensor Network',
    description: 'Sensor data from an industrial manufacturing facility including temperature, pressure, vibration, and equipment health metrics.',
    domain: 'iot',
    tags: ['iot', 'sensors', 'manufacturing', 'industrial', 'health'],
    relevanceScore: 0.94,
    isTimeSeriesValidated: true,
    rowCount: 3456789,
    columnCount: 45,
    timeRange: { start: '2021-03-01', end: '2024-05-20' },
    missingPercent: 1.5,
  },
  {
    id: 'iot-002',
    title: 'Smart Building Energy Management',
    description: 'Building management system data including HVAC usage, lighting patterns, occupancy sensing, and energy consumption.',
    domain: 'iot',
    tags: ['building', 'hvac', 'energy', 'smart-building', 'occupancy'],
    relevanceScore: 0.87,
    isTimeSeriesValidated: true,
    rowCount: 189234,
    columnCount: 38,
    timeRange: { start: '2022-06-01', end: '2024-04-30' },
    missingPercent: 6.3,
  },
];

export const columnInfos: ColumnInfo[] = [
  {
    name: 'timestamp',
    type: 'datetime',
    missingPercent: 0,
    description: 'Date and time of the measurement in ISO 8601 format',
  },
  {
    name: 'demand_value',
    type: 'numeric',
    missingPercent: 0.5,
    uniqueValues: 45230,
    min: 12450,
    max: 89450,
    mean: 45230,
    description: 'Total energy demand in megawatts',
  },
  {
    name: 'temperature',
    type: 'numeric',
    missingPercent: 1.2,
    uniqueValues: 892,
    min: -12,
    max: 48,
    mean: 22.5,
    description: 'Ambient temperature in Celsius',
  },
  {
    name: 'humidity',
    type: 'numeric',
    missingPercent: 1.5,
    uniqueValues: 456,
    min: 15,
    max: 95,
    mean: 62.3,
    description: 'Relative humidity percentage',
  },
  {
    name: 'sector_residential',
    type: 'numeric',
    missingPercent: 0,
    uniqueValues: 12340,
    min: 0,
    max: 1,
    mean: 0.45,
    description: 'Residential sector consumption indicator (0-1 normalized)',
  },
  {
    name: 'sector_commercial',
    type: 'numeric',
    missingPercent: 0,
    uniqueValues: 11230,
    min: 0,
    max: 1,
    mean: 0.32,
    description: 'Commercial sector consumption indicator (0-1 normalized)',
  },
  {
    name: 'sector_industrial',
    type: 'numeric',
    missingPercent: 0,
    uniqueValues: 8920,
    min: 0,
    max: 1,
    mean: 0.23,
    description: 'Industrial sector consumption indicator (0-1 normalized)',
  },
  {
    name: 'grid_status',
    type: 'categorical',
    missingPercent: 0,
    uniqueValues: 5,
    description: 'Current grid operational status (normal, alert, emergency, maintenance, offline)',
  },
  {
    name: 'price_per_mwh',
    type: 'numeric',
    missingPercent: 2.3,
    uniqueValues: 3456,
    min: 12.50,
    max: 245.80,
    mean: 58.90,
    description: 'Market price per megawatt-hour',
  },
  {
    name: 'renewable_percentage',
    type: 'numeric',
    missingPercent: 0.8,
    uniqueValues: 789,
    min: 0,
    max: 100,
    mean: 34.5,
    description: 'Percentage of demand met by renewable sources',
  },
];

export function generateTimeSeriesData(days: number = 90): TimeSeriesDataPoint[] {
  const data: TimeSeriesDataPoint[] = [];
  const now = new Date();

  for (let i = days; i >= 0; i--) {
    const date = new Date(now);
    date.setDate(date.getDate() - i);
    const timestamp = date.toISOString();

    const baseValue = 45000;
    const seasonal = Math.sin((i / 30) * Math.PI) * 5000;
    const weekly = Math.sin((i / 7) * Math.PI) * 2000;
    const trend = i * 20;
    const noise = (Math.random() - 0.5) * 3000;

    const value = baseValue + seasonal + weekly + trend + noise;
    const predicted = value + (Math.random() - 0.5) * 1500;
    const uncertainty = 2000 + Math.random() * 1000;

    data.push({
      timestamp,
      value: Math.round(value),
      predicted: Math.round(predicted),
      lower: Math.round(value - uncertainty),
      upper: Math.round(value + uncertainty),
    });
  }

  return data;
}

export function generateDistributionData(): DistributionDataPoint[] {
  return [
    { range: '0-10K', frequency: 245 },
    { range: '10K-20K', frequency: 890 },
    { range: '20K-30K', frequency: 1560 },
    { range: '30K-40K', frequency: 2340 },
    { range: '40K-50K', frequency: 1890 },
    { range: '50K-60K', frequency: 1230 },
    { range: '60K-70K', frequency: 780 },
    { range: '70K-80K', frequency: 450 },
    { range: '80K-90K', frequency: 210 },
    { range: '90K+', frequency: 85 },
  ];
}

export function generateCorrelationData(): CorrelationDataPoint[] {
  const features = ['demand', 'temperature', 'humidity', 'price', 'renewable'];
  const data: CorrelationDataPoint[] = [];

  for (const f1 of features) {
    for (const f2 of features) {
      if (f1 !== f2) {
        data.push({
          feature1: f1,
          feature2: f2,
          correlation: (Math.random() - 0.5) * 2,
        });
      }
    }
  }

  return data;
}

export const modelMetrics: ModelMetrics = {
  mae: 1245.67,
  rmse: 1567.89,
  mape: 2.34,
  r2: 0.9456,
  lastUpdated: '2024-05-15T14:32:00Z',
};

export const pipelineNodes: PipelineNode[] = [
  {
    id: 'data-ingestion',
    type: 'dataIngestion',
    label: 'Data Ingestion',
    description: 'Connect to data sources and load time-series data',
    status: 'complete',
    config: { source: 'api', batchSize: 10000, format: 'json' },
  },
  {
    id: 'preprocessing',
    type: 'preprocessing',
    label: 'Preprocessing',
    description: 'Handle missing values, outliers, and data normalization',
    status: 'complete',
    config: { missingStrategy: 'interpolate', outlierMethod: 'iqr', normalize: true },
  },
  {
    id: 'feature-engineering',
    type: 'featureEngineering',
    label: 'Feature Engineering',
    description: 'Generate temporal features and aggregations',
    status: 'complete',
    config: { features: ['rolling_mean', 'lag', 'diff'], windows: [24, 168] },
  },
  {
    id: 'model',
    type: 'model',
    label: 'LSTM Model',
    description: 'Long Short-Term Memory neural network',
    status: 'processing',
    config: { layers: [128, 64, 32], epochs: 100, batchSize: 32 },
  },
  {
    id: 'evaluation',
    type: 'evaluation',
    label: 'Evaluation',
    description: 'Assess model performance and validate predictions',
    status: 'ready',
    config: { metrics: ['mae', 'rmse', 'mape'], validationSplit: 0.2 },
  },
];

export const systemAlerts: SystemAlert[] = [
  {
    id: 'alert-001',
    type: 'drift',
    title: 'Data Drift Detected',
    message: 'Feature distribution shift detected in temperature variable. Model retraining recommended.',
    timestamp: '2024-05-15T10:23:00Z',
    acknowledged: false,
  },
  {
    id: 'alert-002',
    type: 'info',
    title: 'Model Update Complete',
    message: 'LSTM model successfully retrained on latest 30 days of data. Performance improved by 3.2%.',
    timestamp: '2024-05-15T08:00:00Z',
    acknowledged: true,
  },
  {
    id: 'alert-003',
    type: 'warning',
    title: 'Missing Data Spike',
    message: 'Increased missing values (12.3%) detected in humidity sensor data from sector 7.',
    timestamp: '2024-05-14T22:45:00Z',
    acknowledged: false,
  },
  {
    id: 'alert-004',
    type: 'error',
    title: 'API Connection Issue',
    message: 'Temporary connection timeout to weather API. Retrying with exponential backoff.',
    timestamp: '2024-05-14T18:30:00Z',
    acknowledged: true,
  },
  {
    id: 'alert-005',
    type: 'info',
    title: 'Scheduled Maintenance',
    message: 'System maintenance scheduled for May 20, 2024. Expected downtime: 2 hours.',
    timestamp: '2024-05-13T15:00:00Z',
    acknowledged: true,
  },
];

export const forecastSummaries: ForecastSummary[] = [
  {
    period: 'Next 24 Hours',
    prediction: 48234,
    confidence: { lower: 46500, upper: 50200 },
    trend: 'up',
  },
  {
    period: 'Next 7 Days',
    prediction: 47560,
    confidence: { lower: 44200, upper: 51800 },
    trend: 'stable',
  },
  {
    period: 'Next 30 Days',
    prediction: 49120,
    confidence: { lower: 43500, upper: 55200 },
    trend: 'up',
  },
];

export const decisionInsights: DecisionInsight[] = [
  {
    id: 'insight-001',
    priority: 'high',
    title: 'Peak Demand Alert',
    description: 'Expected 15% increase in peak demand on May 20-21 due to forecasted heat wave.',
    action: 'Pre-position 500MW additional capacity',
    expectedImpact: 'Prevent potential grid strain and maintain service reliability',
  },
  {
    id: 'insight-002',
    priority: 'medium',
    title: 'Price Optimization Window',
    description: 'Low renewable generation expected May 18. Price may spike during 6-9 PM peak hours.',
    action: 'Consider forward contracts for 200MW',
    expectedImpact: 'Reduce exposure to spot market volatility by estimated $45K',
  },
  {
    id: 'insight-003',
    priority: 'low',
    title: 'Maintenance Window',
    description: 'Optimal maintenance window identified for May 22-23 with minimal demand impact.',
    action: 'Schedule planned outage for transmission line T7',
    expectedImpact: 'Extend equipment lifespan by 18 months with zero service disruption',
  },
];

export const systemKPIs = {
  modelAccuracy: 94.56,
  retrainingCycles: 12,
  driftScore: 0.23,
  lastRetraining: '2024-05-15T08:00:00Z',
  totalPredictions: 1245893,
  uptime: 99.97,
};

export function generatePerformanceHistory(hours: number = 168) {
  const data = [];
  const now = new Date();

  for (let i = hours; i >= 0; i--) {
    const date = new Date(now);
    date.setHours(date.getHours() - i);

    data.push({
      timestamp: date.toISOString(),
      accuracy: 94 + Math.random() * 4,
      drift: Math.random() * 0.5,
      latency: 45 + Math.random() * 30,
    });
  }

  return data;
}
