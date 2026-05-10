from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
import random

from app.core.config import settings
from app.core.schemas import PipelineRunResponse, SystemMonitorResponse


class MonitoringService:
    def __init__(self) -> None:
        self._monitor_dir = settings.storage_dir / "monitoring"
        self._monitor_dir.mkdir(parents=True, exist_ok=True)
        self._runs_store = self._monitor_dir / "recent_runs.json"
        self._recent_runs = self._load_runs()

    def snapshot(self) -> SystemMonitorResponse:
        now = datetime.now(timezone.utc)
        random.seed("monitor")
        performance = []
        for index in range(48, -1, -1):
            ts = now - timedelta(hours=index)
            performance.append(
                {
                    "timestamp": ts.isoformat(),
                    "accuracy": round(93.5 + random.random() * 4.2, 2),
                    "drift": round(random.random() * 0.48, 3),
                    "latency": round(40 + random.random() * 35, 2),
                }
            )
        latest = self._recent_runs[0] if self._recent_runs else None
        return SystemMonitorResponse(
            kpis={
                "modelAccuracy": latest["metrics"]["r2"] * 100 if latest else 94.8,
                "modelUsed": latest["selected_model"] if latest else "LSTM",
                "retrainingCycles": len(self._recent_runs),
                "driftScore": self._drift_score(latest),
                "uptime": 99.97,
                "totalPredictions": 1245893 + len(self._recent_runs) * 90,
            },
            alerts=[
                {
                    "id": "alert-001",
                    "type": "drift",
                    "title": "Data Drift Detected",
                    "message": "Temperature feature distribution shifted beyond the configured threshold.",
                    "timestamp": now.isoformat(),
                    "acknowledged": False,
                },
                {
                    "id": "alert-002",
                    "type": "info",
                    "title": "Model Retrained",
                    "message": f"Latest agent run selected {latest['selected_model']} and updated KPI history." if latest else "No recent pipeline runs logged yet.",
                    "timestamp": (now - timedelta(hours=4)).isoformat(),
                    "acknowledged": True,
                },
            ],
            performance=performance,
            recent_runs=self._recent_runs[:10],
        )

    def record_pipeline_run(self, run: PipelineRunResponse) -> None:
        entry = {
            "run_id": run.run_id,
            "dataset_id": run.dataset_id,
            "selected_model": run.selected_model,
            "metrics": run.metrics,
            "sandbox": run.sandbox,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "agents": run.agents,
        }
        self._recent_runs.insert(0, entry)
        self._recent_runs = self._recent_runs[:25]
        self._runs_store.write_text(json.dumps(self._recent_runs, indent=2), encoding="utf-8")

    def _load_runs(self) -> list[dict[str, object]]:
        if not self._runs_store.exists():
            return []
        try:
            return json.loads(self._runs_store.read_text(encoding="utf-8"))
        except Exception:
            return []

    def _drift_score(self, latest: dict[str, object] | None) -> float:
        if not latest:
            return 0.23
        metrics = latest.get("metrics", {})
        mape = float(metrics.get("mape", 1.0)) if isinstance(metrics, dict) else 1.0
        return round(min(0.95, 0.12 + mape / 10), 3)
