import { useEffect, useState, useMemo } from 'react';
import { motion } from 'framer-motion';
import {
  TrendingUp,
  TrendingDown,
  Minus,
  AlertTriangle,
  Lightbulb,
  ChevronRight,
  Calendar,
  ArrowUpRight,
  ArrowDownRight,
  Target,
  Clock,
} from 'lucide-react';
import { Button, Card, Badge } from '../components/common';
import { TimeSeriesChart } from '../components/charts';
import { getForecast } from '../lib/api';

const timeRangeOptions = [
  { id: '24h', label: '24 Hours' },
  { id: '7d', label: '7 Days' },
  { id: '30d', label: '30 Days' },
  { id: '90d', label: '90 Days' },
];

export function Forecast() {
  const [selectedRange, setSelectedRange] = useState('30d');
  const [backendForecast, setBackendForecast] = useState<Awaited<ReturnType<typeof getForecast>> | null>(null);

  useEffect(() => {
    getForecast('energy-001')
      .then(setBackendForecast)
      .catch(() => setBackendForecast(null));
  }, []);

  const data = useMemo(() => {
    const days = selectedRange === '24h' ? 1 : selectedRange === '7d' ? 7 : selectedRange === '30d' ? 30 : 90;
    const backendPoints = backendForecast?.points;
    if (backendPoints?.length) {
      return backendPoints.slice(0, days).map((point) => ({
        timestamp: point.timestamp,
        value: point.value,
        predicted: point.predicted,
        lower: point.lower,
        upper: point.upper,
      }));
    }
    return [];
  }, [backendForecast, selectedRange]);

  const predictions = useMemo(() => data.slice(-Math.min(data.length * 0.3, 14)), [data]);

  return (
    <div className="min-h-[calc(100vh-4rem)]">
      {/* Header */}
      <div className="border-b border-space-600 bg-space-900/50">
        <div className="max-w-7xl mx-auto px-6 py-4 lg:px-8">
          <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
            <div>
              <h1 className="text-2xl font-bold text-white">Forecast & Insights</h1>
              <p className="mt-1 text-sm text-slate-400">
                AI-powered predictions and actionable decision recommendations
              </p>
            </div>
            <div className="flex items-center gap-2">
              {timeRangeOptions.map((option) => (
                <button
                  key={option.id}
                  onClick={() => setSelectedRange(option.id)}
                  className={`
                    px-3 py-1.5 rounded-lg text-sm font-medium transition-colors
                    ${selectedRange === option.id
                      ? 'bg-indigo-500/20 text-indigo-300 border border-indigo-500/40'
                      : 'text-slate-400 hover:text-white hover:bg-space-700'
                    }
                  `}
                >
                  {option.label}
                </button>
              ))}
            </div>
          </div>
        </div>
      </div>

      <div className="max-w-7xl mx-auto px-6 py-6 lg:px-8">
        {/* Forecast Summary Cards */}
        <div className="grid md:grid-cols-3 gap-4 mb-8">
          {(backendForecast?.summary || []).map((forecast, index) => (
            <motion.div
              key={forecast.period}
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: index * 0.1 }}
            >
              <Card className="relative overflow-hidden">
                {/* Trend Indicator */}
                <div className={`
                  absolute top-4 right-4 p-1.5 rounded-full
                  ${forecast.trend === 'up' ? 'bg-emerald-500/20 text-emerald-400' :
                    forecast.trend === 'down' ? 'bg-red-500/20 text-red-400' :
                    'bg-slate-500/20 text-slate-400'}
                `}>
                  {forecast.trend === 'up' ? (
                    <TrendingUp className="w-4 h-4" />
                  ) : forecast.trend === 'down' ? (
                    <TrendingDown className="w-4 h-4" />
                  ) : (
                    <Minus className="w-4 h-4" />
                  )}
                </div>

                <div className="pr-12">
                  <p className="text-sm text-slate-400">{forecast.period}</p>
                  <p className="mt-2 text-3xl font-bold text-white font-mono">
                    {forecast.prediction.toLocaleString()}
                    <span className="text-lg text-slate-500 ml-2">MW</span>
                  </p>

                  <div className="mt-4 flex items-center gap-4">
                    <div>
                      <p className="text-xs text-slate-500">Lower Bound</p>
                      <p className="text-sm font-mono text-cyan-400">
                        {forecast.confidence.lower.toLocaleString()}
                      </p>
                    </div>
                    <div className="h-8 w-px bg-space-600" />
                    <div>
                      <p className="text-xs text-slate-500">Upper Bound</p>
                      <p className="text-sm font-mono text-cyan-400">
                        {forecast.confidence.upper.toLocaleString()}
                      </p>
                    </div>
                  </div>
                </div>
              </Card>
            </motion.div>
          ))}
        </div>

        {/* Main Chart */}
        <Card className="mb-8">
          <div className="p-6">
            <div className="flex items-center justify-between mb-6">
              <div>
                <h2 className="text-lg font-semibold text-white">Actual vs Predicted</h2>
                <p className="mt-1 text-sm text-slate-400">
                  Historical performance with forecast predictions and confidence intervals
                </p>
              </div>
              <div className="flex items-center gap-4 text-sm">
                <div className="flex items-center gap-2">
                  <span className="w-3 h-0.5 bg-cyan-400 rounded" />
                  <span className="text-slate-400">Actual</span>
                </div>
                <div className="flex items-center gap-2">
                  <span className="w-3 h-0.5 bg-indigo-500 rounded" style={{ borderStyle: 'dashed', borderWidth: '1px', borderColor: '#6366f1', background: 'transparent' }} />
                  <span className="text-slate-400">Predicted</span>
                </div>
                <div className="flex items-center gap-2">
                  <span className="w-3 h-3 rounded bg-indigo-500/20" />
                  <span className="text-slate-400">Confidence</span>
                </div>
              </div>
            </div>
            <TimeSeriesChart data={data} height={450} />
          </div>
        </Card>

        {/* Decision Insights */}
        <div className="grid lg:grid-cols-2 gap-6">
          <div>
            <h2 className="text-lg font-semibold text-white mb-4 flex items-center gap-2">
              <Lightbulb className="w-5 h-5 text-amber-400" />
              Actionable Insights
            </h2>
            <div className="space-y-4">
              {(backendForecast?.decisions || []).map((insight, index) => (
                <motion.div
                  key={insight.id}
                  initial={{ opacity: 0, x: -20 }}
                  animate={{ opacity: 1, x: 0 }}
                  transition={{ delay: index * 0.1 }}
                >
                  <Card
                    hover
                    className={`
                      relative overflow-hidden cursor-pointer
                      ${insight.priority === 'high' ? 'border-l-4 border-l-red-500' :
                        insight.priority === 'medium' ? 'border-l-4 border-l-amber-500' :
                        'border-l-4 border-l-slate-500'}
                    `}
                  >
                    <div className="flex items-start gap-4">
                      <div className={`
                        p-2 rounded-lg shrink-0
                        ${insight.priority === 'high' ? 'bg-red-500/20 text-red-400' :
                          insight.priority === 'medium' ? 'bg-amber-500/20 text-amber-400' :
                          'bg-slate-500/20 text-slate-400'}
                      `}>
                        {insight.priority === 'high' ? (
                          <AlertTriangle className="w-5 h-5" />
                        ) : insight.priority === 'medium' ? (
                          <Target className="w-5 h-5" />
                        ) : (
                          <Clock className="w-5 h-5" />
                        )}
                      </div>

                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2 mb-1">
                          <Badge
                            variant={
                              insight.priority === 'high' ? 'error' :
                              insight.priority === 'medium' ? 'warning' : 'info'
                            }
                            size="sm"
                          >
                            {insight.priority} priority
                          </Badge>
                        </div>
                        <h3 className="font-semibold text-white">{insight.title}</h3>
                        <p className="mt-1 text-sm text-slate-400">{insight.description}</p>

                        <div className="mt-4 pt-4 border-t border-space-700">
                          <p className="text-xs text-slate-500 mb-1">Recommended Action</p>
                          <p className="text-sm text-indigo-300 font-medium">{insight.action}</p>
                        </div>

                        <div className="mt-3 flex items-center justify-between">
                          <p className="text-xs text-slate-500">
                            Expected: {insight.expectedImpact}
                          </p>
                          <Button variant="ghost" size="sm" icon={ChevronRight}>
                            Details
                          </Button>
                        </div>
                      </div>
                    </div>
                  </Card>
                </motion.div>
              ))}
            </div>
          </div>

          {/* Prediction Details */}
          <div>
            <h2 className="text-lg font-semibold text-white mb-4">Upcoming Predictions</h2>
            <Card>
              <div className="space-y-4">
                {/* Table Header */}
                <div className="grid grid-cols-4 gap-4 px-4 py-2 border-b border-space-700">
                  <span className="text-xs font-medium text-slate-500 uppercase">Time</span>
                  <span className="text-xs font-medium text-slate-500 uppercase text-right">Forecast</span>
                  <span className="text-xs font-medium text-slate-500 uppercase text-right">Range</span>
                  <span className="text-xs font-medium text-slate-500 uppercase text-right">Trend</span>
                </div>

                {/* Predictions */}
                {[
                  { time: '2024-05-16 09:00', forecast: 47890, range: '46.2K - 49.5K', trend: 'up' },
                  { time: '2024-05-16 12:00', forecast: 52100, range: '50.8K - 53.4K', trend: 'up' },
                  { time: '2024-05-16 15:00', forecast: 54890, range: '53.1K - 56.7K', trend: 'up' },
                  { time: '2024-05-16 18:00', forecast: 58200, range: '56.5K - 59.9K', trend: 'up' },
                  { time: '2024-05-16 21:00', forecast: 51200, range: '49.8K - 52.6K', trend: 'down' },
                  { time: '2024-05-17 00:00', forecast: 43200, range: '42.1K - 44.5K', trend: 'down' },
                ].map((prediction, index) => (
                  <motion.div
                    key={prediction.time}
                    initial={{ opacity: 0, y: 10 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ delay: index * 0.05 }}
                    className="grid grid-cols-4 gap-4 px-4 py-3 hover:bg-space-700/50 rounded-lg transition-colors"
                  >
                    <div className="flex items-center gap-2">
                      <Clock className="w-3.5 h-3.5 text-slate-500" />
                      <span className="text-sm text-slate-300">{prediction.time.split(' ')[1]}</span>
                    </div>
                    <span className="text-sm font-mono text-white text-right">
                      {prediction.forecast.toLocaleString()}
                    </span>
                    <span className="text-sm text-slate-500 text-right">
                      {prediction.range}
                    </span>
                    <div className="flex items-center justify-end gap-1">
                      {prediction.trend === 'up' ? (
                        <ArrowUpRight className="w-4 h-4 text-emerald-400" />
                      ) : (
                        <ArrowDownRight className="w-4 h-4 text-red-400" />
                      )}
                    </div>
                  </motion.div>
                ))}
              </div>
            </Card>

            {/* Summary Stats */}
            <div className="grid grid-cols-2 gap-4 mt-6">
              <Card className="text-center">
                <Calendar className="w-6 h-6 text-indigo-400 mx-auto mb-2" />
                <p className="text-2xl font-bold text-white font-mono">94.5%</p>
                <p className="text-xs text-slate-400">Forecast Accuracy</p>
              </Card>
              <Card className="text-center">
                <Target className="w-6 h-6 text-cyan-400 mx-auto mb-2" />
                <p className="text-2xl font-bold text-white font-mono">±3.2%</p>
                <p className="text-xs text-slate-400">Confidence Interval</p>
              </Card>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
