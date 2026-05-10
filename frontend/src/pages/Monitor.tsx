import { useEffect, useState, useMemo } from 'react';
import { motion } from 'framer-motion';
import {
  Activity,
  Cpu,
  RefreshCw,
  AlertTriangle,
  Info,
  CheckCircle,
  XCircle,
  TrendingUp,
  TrendingDown,
  Clock,
  ChevronDown,
  Bell,
  Settings,
  Target,
} from 'lucide-react';
import { Card, Badge } from '../components/common';
import { SimpleLineChart } from '../components/charts';
import { getMonitorSnapshot } from '../lib/api';

const timeRangeOptions = [
  { id: '1h', label: '1 Hour' },
  { id: '24h', label: '24 Hours' },
  { id: '7d', label: '7 Days' },
  { id: '30d', label: '30 Days' },
];

const alertIcons = {
  drift: AlertTriangle,
  info: Info,
  warning: AlertTriangle,
  error: XCircle,
};

const alertColors = {
  drift: 'from-amber-500 to-orange-500',
  info: 'from-blue-500 to-cyan-500',
  warning: 'from-amber-500 to-yellow-500',
  error: 'from-red-500 to-pink-500',
};

export function Monitor() {
  const [selectedRange, setSelectedRange] = useState('7d');
  const [expandedAlert, setExpandedAlert] = useState<string | null>(null);
  const [snapshot, setSnapshot] = useState<Awaited<ReturnType<typeof getMonitorSnapshot>> | null>(null);

  useEffect(() => {
    getMonitorSnapshot()
      .then(setSnapshot)
      .catch(() => setSnapshot(null));
  }, []);

  const performanceData = useMemo(() => {
    if (snapshot?.performance.length) {
      return snapshot.performance;
    }
    return [];
  }, [snapshot]);

  const alerts = snapshot?.alerts || [];
  const kpis = snapshot?.kpis || {
    modelAccuracy: 0,
    retrainingCycles: 0,
    driftScore: 0,
    uptime: 0,
  };
  const unacknowledgedAlerts = alerts.filter((a) => !a.acknowledged);

  return (
    <div className="min-h-[calc(100vh-4rem)]">
      {/* Header */}
      <div className="border-b border-space-600 bg-space-900/50">
        <div className="max-w-7xl mx-auto px-6 py-4 lg:px-8">
          <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
            <div className="flex items-center gap-3">
              <h1 className="text-2xl font-bold text-white">System Monitor</h1>
              {unacknowledgedAlerts.length > 0 && (
                <Badge variant="warning" pulse>
                  {unacknowledgedAlerts.length} new alert{unacknowledgedAlerts.length > 1 ? 's' : ''}
                </Badge>
              )}
            </div>
            <div className="flex items-center gap-3">
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
      </div>

      <div className="max-w-7xl mx-auto px-6 py-6 lg:px-8">
        {/* KPI Cards */}
        <div className="grid md:grid-cols-2 lg:grid-cols-4 gap-4 mb-8">
          {[
            {
              icon: Target,
              label: 'Model Accuracy',
              value: `${kpis.modelAccuracy}%`,
              trend: 'up',
              trendValue: '+2.3%',
              color: 'from-emerald-500 to-teal-500',
            },
            {
              icon: RefreshCw,
              label: 'Retraining Cycles',
              value: kpis.retrainingCycles,
              trend: 'neutral',
              trendValue: 'This month',
              color: 'from-blue-500 to-indigo-500',
            },
            {
              icon: Activity,
              label: 'Drift Score',
              value: kpis.driftScore.toFixed(2),
              trend: 'down',
              trendValue: '-0.05',
              color: 'from-amber-500 to-orange-500',
            },
            {
              icon: Cpu,
              label: 'System Uptime',
              value: `${kpis.uptime}%`,
              trend: 'neutral',
              trendValue: 'Last 30 days',
              color: 'from-purple-500 to-pink-500',
            },
          ].map((kpi, index) => (
            <motion.div
              key={kpi.label}
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: index * 0.1 }}
            >
              <Card className="relative overflow-hidden">
                <div className={`absolute top-0 left-0 w-full h-1 bg-gradient-to-r ${kpi.color}`} />
                <div className="flex items-start justify-between">
                  <div className={`p-2 rounded-lg bg-gradient-to-br ${kpi.color}`}>
                    <kpi.icon className="w-5 h-5 text-white" />
                  </div>
                  <div className={`flex items-center gap-1 text-xs ${
                    kpi.trend === 'up' ? 'text-emerald-400' :
                    kpi.trend === 'down' ? 'text-red-400' : 'text-slate-400'
                  }`}>
                    {kpi.trend === 'up' ? (
                      <TrendingUp className="w-3 h-3" />
                    ) : kpi.trend === 'down' ? (
                      <TrendingDown className="w-3 h-3" />
                    ) : null}
                    {kpi.trendValue}
                  </div>
                </div>
                <div className="mt-4">
                  <p className="text-sm text-slate-400">{kpi.label}</p>
                  <p className="mt-1 text-3xl font-bold text-white font-mono">{kpi.value}</p>
                </div>
              </Card>
            </motion.div>
          ))}
        </div>

        {/* Performance Charts */}
        <div className="grid lg:grid-cols-2 gap-6 mb-8">
          <Card>
            <h3 className="text-lg font-semibold text-white mb-4">Model Accuracy Over Time</h3>
            <SimpleLineChart
              data={performanceData}
              dataKey="accuracy"
              color="#10b981"
              height={250}
            />
          </Card>
          <Card>
            <h3 className="text-lg font-semibold text-white mb-4">Data Drift Score</h3>
            <SimpleLineChart
              data={performanceData}
              dataKey="drift"
              color="#f59e0b"
              height={250}
            />
          </Card>
        </div>

        {/* Alert Feed */}
        <div className="grid lg:grid-cols-3 gap-6">
          <div className="lg:col-span-2">
            <h2 className="text-lg font-semibold text-white mb-4 flex items-center gap-2">
              <Bell className="w-5 h-5 text-slate-400" />
              Alert Feed
            </h2>
            <div className="space-y-3">
              {alerts.map((alert, index) => {
                const Icon = alertIcons[alert.type];
                const isExpanded = expandedAlert === alert.id;

                return (
                  <motion.div
                    key={alert.id}
                    initial={{ opacity: 0, y: 10 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ delay: index * 0.05 }}
                  >
                    <Card
                      hover
                      className={`
                        cursor-pointer transition-all
                        ${!alert.acknowledged ? 'border-l-4 border-l-indigo-500' : 'opacity-60'}
                      `}
                      onClick={() => setExpandedAlert(isExpanded ? null : alert.id)}
                    >
                      <div className="flex items-start gap-4">
                        <div className={`p-2 rounded-lg bg-gradient-to-br ${alertColors[alert.type]}`}>
                          <Icon className="w-4 h-4 text-white" />
                        </div>

                        <div className="flex-1 min-w-0">
                          <div className="flex items-center justify-between">
                            <div className="flex items-center gap-2">
                              <h4 className="font-medium text-white">{alert.title}</h4>
                              <Badge
                                variant={
                                  alert.type === 'drift' ? 'warning' :
                                  alert.type === 'error' ? 'error' :
                                  alert.type === 'warning' ? 'warning' : 'info'
                                }
                                size="sm"
                              >
                                {alert.type}
                              </Badge>
                            </div>
                            <div className="flex items-center gap-2">
                              <span className="text-xs text-slate-500">
                                {new Date(alert.timestamp).toLocaleString()}
                              </span>
                              <ChevronDown
                                className={`w-4 h-4 text-slate-500 transition-transform ${
                                  isExpanded ? 'rotate-180' : ''
                                }`}
                              />
                            </div>
                          </div>

                          <p className="mt-1 text-sm text-slate-400">{alert.message}</p>

                          {isExpanded && (
                            <motion.div
                              initial={{ opacity: 0, height: 0 }}
                              animate={{ opacity: 1, height: 'auto' }}
                              className="mt-4 pt-4 border-t border-space-700 flex items-center gap-3"
                            >
                              {alert.acknowledged ? (
                                <div className="flex items-center gap-2 text-sm text-emerald-400">
                                  <CheckCircle className="w-4 h-4" />
                                  Acknowledged
                                </div>
                              ) : (
                                <button className="px-3 py-1.5 text-sm font-medium rounded-lg bg-indigo-500/20 text-indigo-300 hover:bg-indigo-500/30 transition-colors">
                                  Acknowledge
                                </button>
                              )}
                              <button className="px-3 py-1.5 text-sm font-medium text-slate-400 hover:text-white transition-colors">
                                View Details
                              </button>
                            </motion.div>
                          )}
                        </div>
                      </div>
                    </Card>
                  </motion.div>
                );
              })}
            </div>
          </div>

          {/* System Status Sidebar */}
          <div>
            <h2 className="text-lg font-semibold text-white mb-4">System Health</h2>
            <Card>
              <div className="space-y-4">
                {/* Status Items */}
                {[
                  { label: 'API Gateway', status: 'healthy', latency: '12ms' },
                  { label: 'Database', status: 'healthy', latency: '8ms' },
                  { label: 'Model Service', status: 'healthy', latency: '45ms' },
                  { label: 'Data Pipeline', status: 'healthy', latency: '120ms' },
                  { label: 'Alert System', status: 'healthy', latency: '5ms' },
                ].map((item) => (
                  <div
                    key={item.label}
                    className="flex items-center justify-between py-2 border-b border-space-700/50 last:border-0"
                  >
                    <div className="flex items-center gap-2">
                      <span
                        className={`w-2 h-2 rounded-full ${
                          item.status === 'healthy' ? 'bg-emerald-400' : 'bg-red-400'
                        }`}
                      />
                      <span className="text-sm text-slate-300">{item.label}</span>
                    </div>
                    <div className="flex items-center gap-3">
                      <span className="text-xs text-slate-500">Latency: {item.latency}</span>
                      <Badge
                        variant={item.status === 'healthy' ? 'success' : 'error'}
                        size="sm"
                      >
                        {item.status}
                      </Badge>
                    </div>
                  </div>
                ))}
              </div>
            </Card>

            {/* Recent Activity */}
            <div className="mt-6">
              <h3 className="text-lg font-semibold text-white mb-4">Recent Activity</h3>
              <Card>
                <div className="space-y-3">
                  {snapshot?.recent_runs && snapshot.recent_runs.length > 0 ? (
                    snapshot.recent_runs.map((run: any, index: number) => (
                      <div
                        key={run.run_id || index}
                        className="flex items-center gap-3 py-2 border-b border-space-700/50 last:border-0"
                      >
                        <div className="p-1.5 rounded bg-space-700">
                          <Activity className="w-3.5 h-3.5 text-slate-400" />
                        </div>
                        <div className="flex-1">
                          <p className="text-sm text-slate-300">
                            {run.selected_model} run for {run.dataset_id}
                          </p>
                          <p className="text-xs text-slate-500">
                            {run.timestamp ? new Date(run.timestamp).toLocaleString() : 'Recent'}
                          </p>
                        </div>
                      </div>
                    ))
                  ) : (
                    [
                      { action: 'System online', time: 'Just now', icon: Activity },
                      { action: 'Monitoring initialized', time: 'Just now', icon: Settings },
                    ].map((activity, index) => (
                      <div
                        key={index}
                        className="flex items-center gap-3 py-2 border-b border-space-700/50 last:border-0"
                      >
                        <div className="p-1.5 rounded bg-space-700">
                          <activity.icon className="w-3.5 h-3.5 text-slate-400" />
                        </div>
                        <div className="flex-1">
                          <p className="text-sm text-slate-300">{activity.action}</p>
                          <p className="text-xs text-slate-500">{activity.time}</p>
                        </div>
                      </div>
                    ))
                  )}
                </div>
              </Card>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
