import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Cell,
} from 'recharts';
import type { DistributionDataPoint } from '../../data/mockData';

interface DistributionChartProps {
  data: DistributionDataPoint[];
  height?: number;
}

export function DistributionChart({ data, height = 300 }: DistributionChartProps) {
  const maxFreq = Math.max(...data.map((d) => d.frequency), 0);
  const modeIndex = data.findIndex((d) => d.frequency === maxFreq);

  const formatY = (value: number) => {
    if (value >= 1_000_000) return `${(value / 1_000_000).toFixed(1)}M`;
    if (value >= 1_000) return `${(value / 1_000).toFixed(0)}K`;
    return String(value);
  };

  const CustomTooltip = ({ active, payload }: any) => {
    if (active && payload && payload.length) {
      return (
        <div className="bg-space-800 border border-space-600 rounded-lg p-3 shadow-xl">
          <p className="text-sm font-medium text-white">{payload[0].payload.range}</p>
          <p className="text-sm font-mono text-indigo-400">
            {payload[0].value.toLocaleString()} records
          </p>
        </div>
      );
    }
    return null;
  };

  if (data.length === 0) {
    return (
      <div className="flex items-center justify-center h-40 text-slate-400 text-sm">
        No distribution data available.
      </div>
    );
  }

  return (
    <ResponsiveContainer width="100%" height={height}>
      <BarChart data={data} margin={{ top: 10, right: 10, left: 10, bottom: 20 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="#2d3344" vertical={false} />
        <XAxis
          dataKey="range"
          stroke="#64748b"
          tick={{ fill: '#64748b', fontSize: 10 }}
          tickLine={{ stroke: '#2d3344' }}
          angle={-35}
          textAnchor="end"
          interval={0}
          height={50}
        />
        <YAxis
          stroke="#64748b"
          tick={{ fill: '#64748b', fontSize: 11 }}
          tickLine={{ stroke: '#2d3344' }}
          tickFormatter={formatY}
          width={50}
        />
        <Tooltip content={<CustomTooltip />} />
        <Bar dataKey="frequency" radius={[4, 4, 0, 0]}>
          {data.map((_, index) => (
            <Cell
              key={`cell-${index}`}
              fill={index === modeIndex ? '#6366f1' : '#4f5d75'}
            />
          ))}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}
