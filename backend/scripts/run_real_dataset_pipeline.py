import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
load_dotenv(ROOT / ".env")
if os.getenv("KAGGLE_API_KEY") and not os.getenv("KAGGLE_KEY"):
    os.environ["KAGGLE_KEY"] = os.getenv("KAGGLE_API_KEY", "")

from app.core.schemas import PipelineRunRequest
from app.services.dataset_store import DataSourceError, DatasetStoreService
from app.services.eda import AutoEDAService
from app.services.evidence_store import EDAEvidenceStore
from app.services.intelligence import DatasetIntelligenceService
from app.services.monitoring import MonitoringService
from app.services.pipeline import PipelineService


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run local parallel batched EDA and ML pipeline execution."
    )
    source_group = parser.add_mutually_exclusive_group(required=True)
    source_group.add_argument(
        "--dataset-ref",
        help="Kaggle dataset reference in owner/slug form.",
    )
    source_group.add_argument(
        "--csv-path",
        help="Local CSV path.",
    )
    parser.add_argument(
        "--dataset-id",
        help="Optional dataset id override. Defaults to owner--slug for Kaggle refs or CSV filename for local files.",
    )
    parser.add_argument(
        "--target-column",
        help="Optional target column override for the ML pipeline.",
    )
    parser.add_argument(
        "--model",
        choices=["auto", "ARIMA", "XGBoost", "LSTM"],
        default="auto",
        help="Model override. Default uses EDA-driven model selection.",
    )
    parser.add_argument(
        "--horizon",
        type=int,
        default=14,
        help="Forecast horizon used by the pipeline request.",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=max(2, min((os.cpu_count() or 4), 8)),
        help="Parallel worker count for batched column profiling.",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=8,
        help="Column batch size used by parallel EDA.",
    )
    parser.add_argument(
        "--output",
        help="Optional output path for the JSON report. Defaults to storage/test_runs/<timestamp>_<dataset>.json",
    )
    return parser.parse_args()


def dataset_id_from_ref(dataset_ref: str) -> str:
    owner, slug = dataset_ref.split("/", 1)
    return f"{owner}--{slug}"


def dataset_id_from_csv(csv_path: str) -> str:
    return Path(csv_path).stem


def default_output_path(dataset_id: str) -> Path:
    safe_name = dataset_id.replace("/", "__")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    target_dir = ROOT / "storage" / "test_runs"
    target_dir.mkdir(parents=True, exist_ok=True)
    return target_dir / f"{stamp}_{safe_name}.json"


def load_dataframe(args: argparse.Namespace, dataset_id: str) -> tuple[pd.DataFrame, str]:
    if args.csv_path:
        csv_path = Path(args.csv_path)
        if not csv_path.exists():
            raise SystemExit(f"CSV path not found: {csv_path}")
        try:
            return pd.read_csv(csv_path), f"local-csv:{csv_path}"
        except UnicodeDecodeError:
            return pd.read_csv(csv_path, encoding="latin-1"), f"local-csv:{csv_path}"

    dataset_store = DatasetStoreService()
    fallback_profile = AutoEDAService(workers=1, batch_size=1).profile_catalog_dataset(dataset_id)
    try:
        return dataset_store.load_training_frame(
            dataset_id=dataset_id,
            profile=fallback_profile,
            source_ref=args.dataset_ref,
            require_real=True,
        )
    except DataSourceError as exc:
        raise SystemExit(f"Dataset load failed: {exc}") from exc


def main() -> None:
    args = parse_args()
    dataset_id = args.dataset_id or (
        dataset_id_from_csv(args.csv_path) if args.csv_path else dataset_id_from_ref(args.dataset_ref)
    )

    eda_service = AutoEDAService(workers=args.workers, batch_size=args.batch_size)
    evidence_store = EDAEvidenceStore()
    intelligence_service = DatasetIntelligenceService()
    pipeline_service = PipelineService()
    monitoring_service = MonitoringService()

    print(
        f"Loading dataset `{dataset_id}` "
        f"with workers={args.workers} batch_size={args.batch_size}..."
    )
    dataframe, data_source = load_dataframe(args, dataset_id)
    print(f"Loaded dataframe from {data_source} with shape={dataframe.shape}")

    eda_start = time.perf_counter()
    profile = eda_service.profile_dataframe(dataset_id, dataframe)
    profile.summary["dataSource"] = data_source
    if args.dataset_ref:
        profile.summary["sourceRef"] = args.dataset_ref
    profile.evidence_refs = evidence_store.persist(profile)
    profile.insights = intelligence_service.explain(profile)
    profile.decisions = [
        "Accepted dataset for local parallel EDA processing.",
        "Generated batched column profiling and downstream forecasting intelligence.",
        "Prepared the profiled dataset for direct ML pipeline execution.",
    ]
    eda_seconds = round(time.perf_counter() - eda_start, 2)

    print(
        "EDA complete: "
        f"rows={profile.summary.get('rows')} "
        f"columns={profile.summary.get('columns')} "
        f"time={eda_seconds}s"
    )

    pipeline_start = time.perf_counter()
    pipeline_result = pipeline_service.run_on_dataframe(
        PipelineRunRequest(
            dataset_id=dataset_id,
            source_ref=args.dataset_ref,
            target_column=args.target_column,
            horizon=args.horizon,
            model_override=args.model,
        ),
        profile,
        dataframe,
        data_source,
    )
    monitoring_service.record_pipeline_run(pipeline_result)
    pipeline_seconds = round(time.perf_counter() - pipeline_start, 2)

    output_path = Path(args.output) if args.output else default_output_path(dataset_id)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    report = {
        "dataset": {
            "dataset_id": dataset_id,
            "dataset_ref": args.dataset_ref,
            "csv_path": args.csv_path,
            "data_source": data_source,
            "shape": {"rows": int(dataframe.shape[0]), "columns": int(dataframe.shape[1])},
        },
        "execution": {
            "workers": args.workers,
            "batch_size": args.batch_size,
            "eda_seconds": eda_seconds,
            "pipeline_seconds": pipeline_seconds,
        },
        "eda": {
            "title": profile.title,
            "summary": profile.summary,
            "time_series": profile.time_series,
            "validation": profile.validation,
            "forecastability": profile.forecastability,
            "quality_intelligence": profile.quality_intelligence,
            "strategy_recommendation": profile.strategy_recommendation,
            "eda_trace": profile.eda_trace,
            "evidence_refs": profile.evidence_refs,
            "decisions": profile.decisions,
        },
        "pipeline": pipeline_result.model_dump(),
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }

    output_path.write_text(json.dumps(report, indent=2), encoding="utf-8")

    print("Pipeline complete.")
    print(f"Selected model: {pipeline_result.selected_model}")
    print(f"Metrics: {pipeline_result.metrics}")
    print(f"EDA time: {eda_seconds}s | Pipeline time: {pipeline_seconds}s")
    print(f"Report saved to: {output_path}")


if __name__ == "__main__":
    main()
