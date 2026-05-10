import { useMemo } from 'react';
import type { CorrelationDataPoint } from '../../data/mockData';

interface CorrelationHeatmapProps {
  data: CorrelationDataPoint[];
  height?: number;
}

function shortLabel(name: string, maxLen = 14): string {
  if (name.length <= maxLen) return name;
  // Keep last meaningful segment after last underscore if it fits
  const parts = name.split('_');
  if (parts.length > 1) {
    const last = parts[parts.length - 1];
    const secondLast = parts[parts.length - 2];
    const combined = `${secondLast}_${last}`;
    if (combined.length <= maxLen) return `…${combined}`;
    if (last.length <= maxLen) return `…${last}`;
  }
  return `${name.slice(0, maxLen - 1)}…`;
}

function correlationColor(value: number): string {
  // Continuous scale: pink (-1) → dark (0) → cyan (+1)
  const abs = Math.abs(value);
  if (value >= 0) {
    const alpha = 0.15 + abs * 0.75;
    return `rgba(34, 211, 238, ${alpha.toFixed(2)})`;
  } else {
    const alpha = 0.15 + abs * 0.75;
    return `rgba(244, 114, 182, ${alpha.toFixed(2)})`;
  }
}

function textColor(value: number): string {
  return Math.abs(value) > 0.4 ? '#ffffff' : '#94a3b8';
}

export function CorrelationHeatmap({ data, height = 420 }: CorrelationHeatmapProps) {
  const features = useMemo(() => {
    const seen = new Set<string>();
    data.forEach((d) => { seen.add(d.feature1); seen.add(d.feature2); });
    return Array.from(seen);
  }, [data]);

  const matrix = useMemo(() => {
    const mat: Record<string, Record<string, number>> = {};
    features.forEach((f1) => {
      mat[f1] = {};
      features.forEach((f2) => {
        if (f1 === f2) {
          mat[f1][f2] = 1;
        } else {
          const found = data.find(
            (d) => (d.feature1 === f1 && d.feature2 === f2) || (d.feature1 === f2 && d.feature2 === f1)
          );
          mat[f1][f2] = found?.correlation ?? 0;
        }
      });
    });
    return mat;
  }, [data, features]);

  if (features.length === 0) {
    return (
      <div className="flex items-center justify-center h-40 text-slate-400 text-sm">
        No correlation data available for this dataset.
      </div>
    );
  }

  // Adaptive cell size: fit within available width, min 44px max 72px
  const n = features.length;
  const ROW_LABEL_W = 130;
  const HEADER_H = 80;
  const cellSize = Math.max(44, Math.min(72, Math.floor((560 - ROW_LABEL_W) / n)));

  return (
    <div className="overflow-auto">
      <div className="inline-block min-w-full">
        {/* Column headers — rotated 45° */}
        <div className="flex" style={{ marginLeft: ROW_LABEL_W, height: HEADER_H }}>
          {features.map((f) => (
            <div
              key={f}
              style={{ width: cellSize, minWidth: cellSize }}
              className="relative flex items-end justify-center pb-1"
            >
              <div
                className="absolute bottom-1 text-xs text-slate-300 font-medium whitespace-nowrap"
                style={{
                  transform: 'rotate(-45deg)',
                  transformOrigin: 'bottom center',
                  maxWidth: 110,
                  overflow: 'hidden',
                  textOverflow: 'ellipsis',
                }}
                title={f}
              >
                {shortLabel(f, 16)}
              </div>
            </div>
          ))}
        </div>

        {/* Matrix rows */}
        <div>
          {features.map((rowF) => (
            <div key={rowF} className="flex items-center">
              {/* Row label */}
              <div
                className="text-xs text-slate-300 font-medium text-right pr-3 shrink-0 truncate"
                style={{ width: ROW_LABEL_W }}
                title={rowF}
              >
                {shortLabel(rowF, 18)}
              </div>

              {/* Cells */}
              {features.map((colF) => {
                const val = matrix[rowF]?.[colF] ?? 0;
                return (
                  <div
                    key={colF}
                    className="flex items-center justify-center border border-space-900 transition-opacity hover:opacity-80 cursor-default"
                    style={{
                      width: cellSize,
                      minWidth: cellSize,
                      height: cellSize,
                      backgroundColor: correlationColor(val),
                    }}
                    title={`${rowF} × ${colF}: ${val.toFixed(3)}`}
                  >
                    <span
                      className="text-xs font-mono font-semibold select-none"
                      style={{ color: textColor(val), fontSize: cellSize < 52 ? 10 : 12 }}
                    >
                      {val.toFixed(2)}
                    </span>
                  </div>
                );
              })}
            </div>
          ))}
        </div>

        {/* Legend */}
        <div className="flex items-center justify-center mt-5 gap-3">
          <div className="flex items-center gap-1.5">
            <div className="w-3 h-3 rounded-sm" style={{ backgroundColor: 'rgba(244,114,182,0.9)' }} />
            <span className="text-xs text-slate-400">Strong negative</span>
          </div>
          <div
            className="w-28 h-3 rounded"
            style={{ background: 'linear-gradient(to right, rgba(244,114,182,0.9), #1e2433, rgba(34,211,238,0.9))' }}
          />
          <div className="flex items-center gap-1.5">
            <div className="w-3 h-3 rounded-sm" style={{ backgroundColor: 'rgba(34,211,238,0.9)' }} />
            <span className="text-xs text-slate-400">Strong positive</span>
          </div>
        </div>
      </div>
    </div>
  );
}
