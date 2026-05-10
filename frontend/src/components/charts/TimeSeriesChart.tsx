import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
  Area,
  ComposedChart,
} from 'recharts';
import type { TimeSeriesDataPoint } from '../../data/mockData';

interface TimeSeriesChartProps {
  data: TimeSeriesDataPoint[];
  showPrediction?: boolean;
  showConfidence?: boolean;
  height?: number;
}

/** Smart Y-axis formatter: picks the right scale (K/M) based on actual data range. */
function makeYFormatter(data: TimeSeriesDataPoint[]) {
  const values = data.flatMap((d) => [
    typeof d.value === 'number' ? d.value : null,
    typeof d.predicted === 'number' ? d.predicted : null,
  ]).filter((v): v is number => v !== null);

  if (values.length === 0) return (v: number) => String(v);

  const max = Math.max(...values);
  const min = Math.min(...values);
  const range = max - min;

  if (max >= 1_000_000) {
    const decimals = range / 1_000_000 < 5 ? 1 : 0;
    return (v: number) => `${(v / 1_000_000).toFixed(decimals)}M`;
  }
  if (max >= 1_000) {
    const decimals = range / 1_000 < 10 ? 1 : 0;
    return (v: number) => `${(v / 1_000).toFixed(decimals)}K`;
  }
  const decimals = range < 10 ? 2 : range < 100 ? 1 : 0;
  return (v: number) => v.toFixed(decimals);
}

/** Smart X-axis formatter: detects integer index vs real timestamp. */
function makeXFormatter(data: TimeSeriesDataPoint[]) {
  if (data.length === 0) return (v: string) => v;

  const sample = data[0].timestamp;
  // Integer index (e.g. "0", "1000", "201317")
  if (/^\d+$/.test(String(sample))) {
    const total = data.length;
    return (v: string) => {
      const idx = Number(v);
      if (isNaN(idx)) return v;
      // Show every ~10% as a step label
      return `#${idx.toLocaleString()}`;
    };
  }
  // Real timestamp
  const first = new Date(data[0].timestamp);
  const last = new Date(data[data.length - 1].timestamp);
  const spanDays = (last.getTime() - first.getTime()) / 86_400_000;

  return (dateStr: string) => {
    const d = new Date(dateStr);
    if (isNaN(d.getTime())) return dateStr;
    if (spanDays > 365 * 2)
      return d.toLocaleDateString('en-US', { month: 'short', year: '2-digit' });
    if (spanDays > 60)
      return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
    if (spanDays > 2)
      return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
    return d.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit' });
  };
}

export function TimeSeriesChart({
  data,
  showPrediction = true,
  showConfidence = true,
  height = 400,
}: TimeSeriesChartProps) {
  const yFormatter = makeYFormatter(data);
  const xFormatter = makeXFormatter(data);

  const isIntegerIndex = data.length > 0 && /^\d+$/.test(String(data[0].timestamp));

  const CustomTooltip = ({ active, payload, label }: any) => {
    if (!active || !payload?.length) return null;
    const labelText = isIntegerIndex
      ? `Step #${Number(label).toLocaleString()}`
      : (() => {
          const d = new Date(label);
          return isNaN(d.getTime())
            ? label
            : d.toLocaleDateString('en-US', {
                month: 'short', day: 'numeric', year: 'numeric',
                hour: '2-digit', minute: '2-digit',
              });
        })();
    return (
      <div className="bg-space-800 border border-space-600 rounded-lg p-3 shadow-xl">
        <p className="text-xs text-slate-400 mb-2">{labelText}</p>
        {payload.map((entry: any, i: number) => (
          <p key={i} className="text-sm font-mono" style={{ color: entry.color }}>
            {entry.name}: {typeof entry.value === 'number' ? entry.value.toLocaleString(undefined, { maximumFractionDigits: 2 }) : entry.value}
          </p>
        ))}
      </div>
    );
  };

  // Reduce tick density for large datasets
  const tickCount = Math.min(8, Math.max(4, Math.floor(data.length / 50)));

  return (
    <ResponsiveContainer width="100%" height={height}>
      <ComposedChart data={data} margin={{ top: 10, right: 30, left: 10, bottom: 0 }}>
        <defs>
          <linearGradient id="confidenceGradient" x1="0" y1="0" x2="0" y2="1">
            <stop offset="5%" stopColor="#6366f1" stopOpacity={0.2} />
            <stop offset="95%" stopColor="#6366f1" stopOpacity={0} />
          </linearGradient>
        </defs>
        <CartesianGrid strokeDasharray="3 3" stroke="#2d3344" />
        <XAxis
          dataKey="timestamp"
          tickFormatter={xFormatter}
          stroke="#64748b"
          tick={{ fill: '#64748b', fontSize: 11 }}
          tickLine={{ stroke: '#2d3344' }}
          tickCount={tickCount}
          interval="preserveStartEnd"
        />
        <YAxis
          stroke="#64748b"
          tick={{ fill: '#64748b', fontSize: 11 }}
          tickLine={{ stroke: '#2d3344' }}
          tickFormatter={yFormatter}
          width={55}
        />
        <Tooltip content={<CustomTooltip />} />

        {showConfidence && (
          <Area type="monotone" dataKey="upper" stroke="none" fill="url(#confidenceGradient)" name="Upper Bound" />
        )}
        {showConfidence && (
          <Area type="monotone" dataKey="lower" stroke="none" fill="#0f1117" name="Lower Bound" />
        )}

        <Line
          type="monotone"
          dataKey="value"
          stroke="#22d3ee"
          strokeWidth={2}
          dot={false}
          name="Actual"
          activeDot={{ r: 4, fill: '#22d3ee' }}
        />

        {showPrediction && (
          <Line
            type="monotone"
            dataKey="predicted"
            stroke="#6366f1"
            strokeWidth={2}
            strokeDasharray="5 5"
            dot={false}
            name="Predicted"
            activeDot={{ r: 4, fill: '#6366f1' }}
          />
        )}

        <Legend
          wrapperStyle={{ paddingTop: 20 }}
          iconType="line"
          formatter={(value) => <span className="text-slate-300 text-sm">{value}</span>}
        />
      </ComposedChart>
    </ResponsiveContainer>
  );
}

interface SimpleLineChartProps {
  data: any[];
  dataKey: string;
  name?: string;
  color?: string;
  height?: number;
}

export function SimpleLineChart({
  data,
  dataKey,
  name,
  color = '#6366f1',
  height = 200,
}: SimpleLineChartProps) {
  return (
    <ResponsiveContainer width="100%" height={height}>
      <LineChart data={data} margin={{ top: 10, right: 10, left: 0, bottom: 0 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="#2d3344" />
        <XAxis
          dataKey="timestamp"
          tickFormatter={(value) => new Date(value).toLocaleTimeString('en-US', { hour: '2-digit' })}
          stroke="#64748b"
          tick={{ fill: '#64748b', fontSize: 10 }}
        />
        <YAxis stroke="#64748b" tick={{ fill: '#64748b', fontSize: 10 }} />
        <Tooltip
          contentStyle={{
            backgroundColor: '#1a1d27',
            border: '1px solid #2d3344',
            borderRadius: 8,
          }}
          labelStyle={{ color: '#94a3b8' }}
        />
        <Line
          type="monotone"
          dataKey={dataKey}
          stroke={color}
          strokeWidth={2}
          dot={false}
          name={name || dataKey}
        />
      </LineChart>
    </ResponsiveContainer>
  );
}
