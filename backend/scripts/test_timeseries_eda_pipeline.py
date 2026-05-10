from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.core.schemas import PipelineRunRequest
from app.services.eda import AutoEDAService
from app.services.pipeline import PipelineService


DEFAULT_CSV = ROOT / "storage" / "datasets" / "datasetengineer__southern-california-energy-consumption" / "electricity_consumption_optimization_dataset.csv"
DEFAULT_DATASET_ID = "datasetengineer--southern-california-energy-consumption"
DEFAULT_TARGET = "Energy Consumption (kWh)"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Fresh time-series EDA + ML pipeline test without persisted EDA evidence."
    )
    parser.add_argument("--csv-path", default=str(DEFAULT_CSV), help="Time-series CSV path to test.")
    parser.add_argument("--dataset-id", default=DEFAULT_DATASET_ID, help="Dataset id used in profile/pipeline output.")
    parser.add_argument("--target-column", default=DEFAULT_TARGET, help="Target column for model training.")
    parser.add_argument("--model", choices=["auto", "ARIMA", "XGBoost", "LSTM"], default="auto", help="Model override.")
    parser.add_argument("--horizon", type=int, default=14, help="Forecast horizon for the pipeline request.")
    parser.add_argument("--workers", type=int, default=4, help="Parallel EDA worker count.")
    parser.add_argument("--batch-size", type=int, default=8, help="Column batch size for EDA profiling.")
    parser.add_argument("--max-rows", type=int, default=0, help="Optional row cap for fast local testing. Use 0 for all rows.")
    parser.add_argument("--output", help="Optional JSON report path.")
    return parser.parse_args()


def read_csv(path: Path) -> pd.DataFrame:
    try:
        return pd.read_csv(path)
    except UnicodeDecodeError:
        return pd.read_csv(path, encoding="latin-1")


def default_output_path(dataset_id: str) -> Path:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    target_dir = ROOT / "storage" / "test_runs"
    target_dir.mkdir(parents=True, exist_ok=True)
    return target_dir / f"{stamp}_{dataset_id}_fresh_timeseries_test.json"


def main() -> None:
    args = parse_args()
    csv_path = Path(args.csv_path)
    if not csv_path.exists():
        raise SystemExit(f"CSV path not found: {csv_path}")

    print("Available parameters:")
    print("  --csv-path       CSV file to test")
    print("  --dataset-id     dataset id used by backend services")
    print("  --target-column  target column for ML training")
    print("  --model          auto, ARIMA, XGBoost, or LSTM")
    print("  --horizon        forecast horizon")
    print("  --workers        parallel EDA worker count")
    print("  --batch-size     EDA column batch size")
    print("  --max-rows       optional fast-test row cap; 0 means full dataset")
    print()

    dataframe = read_csv(csv_path)
    if args.max_rows and args.max_rows > 0:
        dataframe = dataframe.head(args.max_rows).copy()

    print(f"Dataset: {args.dataset_id}")
    print(f"CSV: {csv_path}")
    print(f"Shape: {dataframe.shape[0]:,} rows x {dataframe.shape[1]:,} columns")
    print(f"Target override: {args.target_column}")

    eda_service = AutoEDAService(workers=args.workers, batch_size=args.batch_size)
    pipeline_service = PipelineService()

    eda_started = time.perf_counter()
    profile = eda_service.profile_dataframe(args.dataset_id, dataframe)
    profile.summary["dataSource"] = f"local-csv:{csv_path}"
    profile.summary["realDataLoaded"] = True
    profile.summary["profileCacheHit"] = False
    profile.evidence_refs = {
        "llmGate": "not_used",
        "reason": "Fresh pipeline test does not persist or reuse EDA evidence.",
    }
    eda_seconds = round(time.perf_counter() - eda_started, 2)

    print("\nEDA result:")
    print(f"  rows: {profile.summary.get('rows')}")
    print(f"  columns: {profile.summary.get('columns')}")
    print(f"  missingPercent: {profile.summary.get('missingPercent')}")
    print(f"  timeSeriesValidated: {profile.summary.get('timeSeriesValidated')}")
    print(f"  timeColumn: {profile.time_series.get('timeColumn')}")
    print(f"  frequency: {profile.time_series.get('frequency')}")
    print(f"  recommendedTarget: {profile.validation.get('recommendedTarget')}")
    print(f"  requestedTarget: {args.target_column}")
    print(f"  forecastability: {profile.forecastability.get('score')} ({profile.forecastability.get('grade')})")
    print(f"  EDA recommended model: {profile.strategy_recommendation.get('recommendedModelFamily')}")
    print(f"  EDA seconds: {eda_seconds}")

    pipeline_started = time.perf_counter()
    pipeline_result = pipeline_service.run_on_dataframe(
        PipelineRunRequest(
            dataset_id=args.dataset_id,
            source_ref=None,
            target_column=args.target_column,
            horizon=args.horizon,
            model_override=args.model,
        ),
        profile,
        dataframe,
        f"local-csv:{csv_path}",
    )
    pipeline_seconds = round(time.perf_counter() - pipeline_started, 2)

    print("\nPipeline result:")
    print(f"  selectedModel: {pipeline_result.selected_model}")
    print(f"  metrics: {pipeline_result.metrics}")
    print(f"  trainRows: {pipeline_result.sandbox.get('trainRows')}")
    print(f"  testRows: {pipeline_result.sandbox.get('testRows')}")
    print(f"  featureCount: {pipeline_result.sandbox.get('featureCount')}")
    print(f"  targetColumn: {pipeline_result.sandbox.get('targetColumn')}")
    print(f"  pipeline seconds: {pipeline_seconds}")
    print("  cleaning transformations:")
    for item in pipeline_result.preprocessing_report.get("transformationsApplied", []):
        print(f"    - {item}")

    report = {
        "dataset": {
            "datasetId": args.dataset_id,
            "csvPath": str(csv_path),
            "shape": {"rows": int(dataframe.shape[0]), "columns": int(dataframe.shape[1])},
            "targetColumn": args.target_column,
        },
        "parameters": {
            "model": args.model,
            "horizon": args.horizon,
            "workers": args.workers,
            "batchSize": args.batch_size,
            "maxRows": args.max_rows,
        },
        "eda": {
            "seconds": eda_seconds,
            "summary": profile.summary,
            "timeSeries": profile.time_series,
            "validation": profile.validation,
            "forecastability": profile.forecastability,
            "qualityIntelligence": profile.quality_intelligence,
            "featureIntelligence": profile.feature_intelligence,
            "strategyRecommendation": profile.strategy_recommendation,
            "semanticUnderstanding": profile.semantic_understanding,
            "edaTrace": profile.eda_trace,
            "evidenceRefs": profile.evidence_refs,
        },
        "pipeline": pipeline_result.model_dump(),
        "generatedAt": datetime.now(timezone.utc).isoformat(),
    }

    output_path = Path(args.output) if args.output else default_output_path(args.dataset_id)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    print(f"\nReport saved to: {output_path}")


if __name__ == "__main__":
    main()
