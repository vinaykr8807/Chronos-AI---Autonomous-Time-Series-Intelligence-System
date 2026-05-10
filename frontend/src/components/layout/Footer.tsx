import { Activity } from 'lucide-react';

export function Footer() {
  return (
    <footer className="border-t border-space-600 bg-space-900/50">
      <div className="max-w-7xl mx-auto px-6 py-6">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2 text-sm text-slate-500">
            <Activity className="w-4 h-4" />
            <span>© 2026 Chronos AI. All rights reserved.</span>
          </div>
          <div className="flex items-center gap-4">
            <span className="text-xs text-slate-600">System Status: Operational</span>
            <span className="text-xs text-slate-600">v1.0.0</span>
          </div>
        </div>
      </div>
    </footer>
  );
}
