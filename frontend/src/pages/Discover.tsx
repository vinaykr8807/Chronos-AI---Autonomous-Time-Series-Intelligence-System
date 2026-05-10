import { useState, useEffect, useMemo } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { motion } from 'framer-motion';
import {
  Search,
  Filter,
  X,
  Database,
  Clock,
  Hash,
  AlertCircle,
  CheckCircle2,
  SlidersHorizontal,
} from 'lucide-react';
import { Button, Card, StatusBadge, Input, Skeleton } from '../components/common';
import { type Dataset } from '../data/mockData';
import { searchDatasets } from '../lib/api';

const domains = [
  { id: 'all', label: 'All Domains' },
  { id: 'energy', label: 'Energy' },
  { id: 'traffic', label: 'Traffic' },
  { id: 'sales', label: 'Sales' },
  { id: 'finance', label: 'Finance' },
  { id: 'iot', label: 'IoT' },
];

const domainColors: Record<string, string> = {
  energy: 'from-amber-500 to-orange-500',
  traffic: 'from-blue-500 to-cyan-500',
  sales: 'from-emerald-500 to-teal-500',
  finance: 'from-purple-500 to-pink-500',
  iot: 'from-indigo-500 to-violet-500',
};

function DatasetCard({ dataset, index }: { dataset: Dataset; index: number }) {
  const navigate = useNavigate();
  const visibleTags = (dataset.tags || []).map((tag) => tag.trim()).filter(Boolean);
  const hasRowCount = dataset.rowCount > 0;
  const hasTimeRangeEnd = !Number.isNaN(new Date(dataset.timeRange.end).getTime());
  const sourceLabel = dataset.ref ? `Real source: ${dataset.ref}` : 'No real source ref';
  const rowCountLabel = hasRowCount ? `${dataset.rowCount.toLocaleString()} rows` : sourceLabel;
  const profileLabel = hasTimeRangeEnd
    ? String(new Date(dataset.timeRange.end).getFullYear())
    : dataset.validationSummary
      ? (dataset.isTimeSeriesValidated ? 'TS candidate' : 'Needs profiling')
      : 'Ready to profile';
  const relevancePercent = Math.max(1, Math.round((dataset.relevanceScore || 0) * 100));
  const datasetTarget = dataset.ref
    ? `/dataset/${dataset.id}?ref=${encodeURIComponent(dataset.ref || '')}`
    : `/dataset/${dataset.id}`;

  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3, delay: index * 0.05 }}
      whileHover={{ y: -4 }}
      onClick={() => dataset.ref && navigate(datasetTarget)}
      className={`group ${dataset.ref ? 'cursor-pointer' : 'cursor-not-allowed opacity-60'}`}
    >
      <Card hover glow="primary" className="h-full">
        {/* Header */}
        <div className="flex items-start justify-between mb-4">
          <div className={`p-2 rounded-lg bg-gradient-to-br ${domainColors[dataset.domain] || domainColors.general || 'from-slate-500 to-slate-600'}`}>
            <Database className="w-5 h-5 text-white" />
          </div>
          <div className="flex items-center gap-2">
            {dataset.isTimeSeriesValidated && (
              <StatusBadge status="validated" />
            )}
          </div>
        </div>

        {/* Content */}
        <h3 className="text-lg font-semibold text-white mb-2 group-hover:text-indigo-300 transition-colors">
          {dataset.title}
        </h3>
        <p className="text-sm text-slate-400 mb-4 line-clamp-2">
          {dataset.description}
        </p>

        {/* Tags */}
        {visibleTags.length > 0 && (
          <div className="flex flex-wrap gap-2 mb-4">
            {visibleTags.slice(0, 3).map((tag) => (
            <span
              key={tag}
              className="px-2 py-0.5 text-xs rounded-full bg-space-700 text-slate-400"
            >
              {tag}
            </span>
            ))}
            {visibleTags.length > 3 && (
              <span className="px-2 py-0.5 text-xs rounded-full bg-space-700 text-slate-500">
                +{visibleTags.length - 3}
              </span>
            )}
          </div>
        )}

        {/* Stats */}
        <div className="grid grid-cols-2 gap-4 py-3 border-t border-space-700">
          <div className="flex items-center gap-1.5 text-xs text-slate-400">
            <Hash className="w-3.5 h-3.5" />
            <span>{rowCountLabel}</span>
          </div>
          <div className="flex items-center gap-1.5 text-xs text-slate-400">
            <Clock className="w-3.5 h-3.5" />
            <span>{profileLabel}</span>
          </div>
          {dataset.missingPercent > 0 && (
            <div className="flex items-center gap-1.5 text-xs text-amber-400 col-span-2">
              <AlertCircle className="w-3.5 h-3.5" />
              <span>{dataset.missingPercent}% missing</span>
            </div>
          )}
        </div>

        {/* Relevance Score */}
        <div className="flex items-center justify-between mt-4 pt-4 border-t border-space-700">
          <div className="flex flex-col">
            <span className="text-xs text-slate-500">Relevance Score</span>
            {dataset.validationSummary && (
              <span className="text-[11px] text-slate-600">{dataset.validationSummary}</span>
            )}
          </div>
          <div className="flex items-center gap-2">
            <div className="w-20 h-1.5 bg-space-700 rounded-full overflow-hidden">
              <motion.div
                initial={{ width: 0 }}
                animate={{ width: `${relevancePercent}%` }}
                transition={{ duration: 0.5, delay: index * 0.1 }}
                className="h-full bg-gradient-to-r from-indigo-500 to-cyan-400 rounded-full"
              />
            </div>
            <span className="text-xs font-mono text-indigo-400">
              {relevancePercent}%
            </span>
          </div>
        </div>

        <button
          type="button"
          onClick={(event) => {
            event.stopPropagation();
            navigate(datasetTarget);
          }}
          className="mt-4 flex h-9 w-full items-center justify-center gap-2 rounded-md border border-indigo-500/30 bg-indigo-500/10 px-3 text-sm font-medium text-indigo-200 transition-colors hover:border-indigo-400/60 hover:bg-indigo-500/20"
        >
          <CheckCircle2 className="h-4 w-4" />
          Run EDA First
        </button>
      </Card>
    </motion.div>
  );
}

function DatasetCardSkeleton() {
  return (
    <Card className="h-full">
      <div className="flex items-start justify-between mb-4">
        <Skeleton className="w-10 h-10 rounded-lg" />
        <Skeleton className="w-20 h-5 rounded-full" />
      </div>
      <Skeleton className="w-3/4 h-6 rounded mb-2" />
      <Skeleton className="w-full h-16 rounded mb-4" />
      <div className="flex gap-2 mb-4">
        <Skeleton className="w-16 h-5 rounded-full" />
        <Skeleton className="w-20 h-5 rounded-full" />
        <Skeleton className="w-12 h-5 rounded-full" />
      </div>
      <div className="flex items-center gap-4 py-3 border-t border-space-700">
        <Skeleton className="w-16 h-4 rounded" />
        <Skeleton className="w-16 h-4 rounded" />
      </div>
      <div className="flex items-center justify-between mt-4 pt-4 border-t border-space-700">
        <Skeleton className="w-24 h-4 rounded" />
        <Skeleton className="w-20 h-4 rounded" />
      </div>
    </Card>
  );
}

export function Discover() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const [searchQuery, setSearchQuery] = useState(searchParams.get('q') || '');
  const [selectedDomain, setSelectedDomain] = useState('all');
  const [showValidatedOnly, setShowValidatedOnly] = useState(false);
  const [isLoading, setIsLoading] = useState(true);
  const [showFilters, setShowFilters] = useState(false);
  const [datasetResults, setDatasetResults] = useState<Dataset[]>([]);

  useEffect(() => {
    let cancelled = false;
    setIsLoading(true);
    searchDatasets(searchQuery, selectedDomain, showValidatedOnly)
      .then((response) => {
        if (!cancelled) {
          setDatasetResults(response.results.filter((dataset) => Boolean(dataset.ref)));
        }
      })
      .catch(() => {
        if (!cancelled) {
          setDatasetResults([]);
        }
      })
      .finally(() => {
        if (!cancelled) {
          setIsLoading(false);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [searchQuery, selectedDomain, showValidatedOnly]);

  const filteredDatasets = useMemo(() => {
    let filtered = datasetResults;

    if (searchQuery) {
      const query = searchQuery.toLowerCase();
      filtered = filtered.filter(
        (d) =>
          d.title.toLowerCase().includes(query) ||
          d.description.toLowerCase().includes(query) ||
          d.tags.some((t) => t.trim().toLowerCase().includes(query))
      );
    }

    if (selectedDomain !== 'all') {
      filtered = filtered.filter((d) => d.domain === selectedDomain);
    }

    if (showValidatedOnly) {
      filtered = filtered.filter((d) => d.isTimeSeriesValidated);
    }

    return filtered;
  }, [datasetResults, searchQuery, selectedDomain, showValidatedOnly]);

  const handleSearch = (query: string) => {
    setSearchQuery(query);
    navigate(`/discover?q=${encodeURIComponent(query)}`, { replace: true });
  };

  return (
    <div className="min-h-[calc(100vh-4rem)]">
      {/* Header */}
      <div className="border-b border-space-600 bg-space-900/50">
        <div className="max-w-7xl mx-auto px-6 py-6 lg:px-8">
          <div className="flex flex-col md:flex-row md:items-center gap-4">
            <div className="flex-1">
              <h1 className="text-2xl font-bold text-white">Dataset Discovery</h1>
              <p className="mt-1 text-sm text-slate-400">
                Find and explore time-series datasets across multiple domains
              </p>
            </div>
            <div className="flex items-center gap-3">
              <div className="relative flex-1 md:flex-none md:w-80">
                <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-500" />
                <input
                  type="text"
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  onKeyDown={(e) => e.key === 'Enter' && handleSearch(searchQuery)}
                  placeholder="Search datasets..."
                  className="w-full bg-space-800 border border-space-600 rounded-lg pl-10 pr-4 py-2 text-sm text-white placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-indigo-500"
                />
                {searchQuery && (
                  <button
                    onClick={() => setSearchQuery('')}
                    className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-500 hover:text-slate-300"
                  >
                    <X className="w-4 h-4" />
                  </button>
                )}
              </div>
              <Button
                variant={showFilters ? 'primary' : 'secondary'}
                icon={SlidersHorizontal}
                onClick={() => setShowFilters(!showFilters)}
              >
                Filters
              </Button>
            </div>
          </div>
        </div>
      </div>

      <div className="max-w-7xl mx-auto px-6 py-8 lg:px-8">
        <div className="flex flex-col lg:flex-row gap-8">
          {/* Sidebar Filters */}
          <motion.aside
            initial={{ opacity: 0, x: -20 }}
            animate={{ opacity: 1, x: 0 }}
            className={`lg:w-64 shrink-0 ${showFilters ? 'block' : 'hidden lg:block'}`}
          >
            <Card padding="md" className="sticky top-24">
              <div className="flex items-center gap-2 mb-6">
                <Filter className="w-4 h-4 text-indigo-400" />
                <h3 className="font-semibold text-white">Filters</h3>
              </div>

              {/* Domain Filter */}
              <div className="mb-6">
                <label className="text-sm font-medium text-slate-300 mb-3 block">
                  Domain
                </label>
                <div className="space-y-2">
                  {domains.map((domain) => (
                    <button
                      key={domain.id}
                      onClick={() => setSelectedDomain(domain.id)}
                      className={`
                        w-full flex items-center gap-3 px-3 py-2 rounded-lg text-sm transition-colors
                        ${selectedDomain === domain.id
                          ? 'bg-indigo-500/20 text-indigo-300'
                          : 'text-slate-400 hover:bg-space-700 hover:text-white'
                        }
                      `}
                    >
                      <span
                        className={`
                          w-2 h-2 rounded-full
                          ${selectedDomain === domain.id ? 'bg-indigo-400' : 'bg-space-600'}
                        `}
                      />
                      {domain.label}
                    </button>
                  ))}
                </div>
              </div>

              {/* Validation Filter */}
              <div className="mb-6">
                <label className="flex items-center gap-3 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={showValidatedOnly}
                    onChange={(e) => setShowValidatedOnly(e.target.checked)}
                    className="w-4 h-4 rounded border-space-600 bg-space-800 text-indigo-500 focus:ring-indigo-500 focus:ring-offset-space-900"
                  />
                  <span className="text-sm text-slate-300">
                    Time-series validated only
                  </span>
                </label>
              </div>

              {/* Reset Button */}
              <Button
                variant="ghost"
                onClick={() => {
                  setSelectedDomain('all');
                  setShowValidatedOnly(false);
                  setSearchQuery('');
                }}
                className="w-full"
              >
                Reset Filters
              </Button>
            </Card>
          </motion.aside>

          {/* Dataset Grid */}
          <div className="flex-1">
            {/* Results Info */}
            <div className="flex items-center justify-between mb-6">
              <p className="text-sm text-slate-400">
                Showing <span className="text-white font-medium">{filteredDatasets.length}</span> datasets
                {searchQuery && (
                  <span>
                    {' '}for "<span className="text-indigo-400">{searchQuery}</span>"
                  </span>
                )}
              </p>
            </div>

            {/* Grid */}
            {isLoading ? (
              <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-6">
                {Array.from({ length: 6 }).map((_, i) => (
                  <DatasetCardSkeleton key={i} />
                ))}
              </div>
            ) : filteredDatasets.length > 0 ? (
              <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-6">
                {filteredDatasets.map((dataset, index) => (
                  <DatasetCard key={dataset.id} dataset={dataset} index={index} />
                ))}
              </div>
            ) : (
              <div className="flex flex-col items-center justify-center py-20">
                <div className="p-4 rounded-full bg-space-800 mb-4">
                  <Search className="w-8 h-8 text-slate-500" />
                </div>
                <h3 className="text-lg font-semibold text-white mb-2">
                  No datasets found
                </h3>
                <p className="text-sm text-slate-400 mb-4">
                  Try adjusting your search or filters
                </p>
                <Button
                  variant="secondary"
                  onClick={() => {
                    setSelectedDomain('all');
                    setShowValidatedOnly(false);
                    setSearchQuery('');
                  }}
                >
                  Clear all filters
                </Button>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
