# Autonomous Time-Series Intelligence Backend

FastAPI backend for dataset discovery, automated EDA, dataset intelligence, adaptive pipeline orchestration, forecasting, and monitoring.

## Run

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

The frontend can call it through Vite's `/api` proxy.

## Real EDA and Real Training

For Kaggle-backed datasets such as `owner--dataset-slug`, the backend now requires a real dataset load for:

- dataset profiling / EDA
- raw-row preview
- forecasting
- pipeline training

Pipeline training now uses the generated EDA profile to select a suitable model family automatically:

- `ARIMA` for stable, lower-noise, readable univariate temporal signals
- `XGBoost` for richer lag and exogenous-feature setups
- `LSTM` only when the sequence is long, high-quality, and the local runtime actually has PyTorch available

If the backend cannot load the real dataset, it returns a clear API error instead of silently switching to synthetic data.

Set these values in `.env` before running Kaggle-backed analysis:

```env
KAGGLE_USERNAME=your_kaggle_username
KAGGLE_API_KEY=your_kaggle_api_key
BACKEND_CORS_ORIGINS=http://localhost:5173,http://127.0.0.1:5173
```

Notes:

- Demo catalog datasets like `energy-001` still use the fast synthetic/catalog path by design.
- If a cached Kaggle zip is corrupt, the loader will try to re-download it when valid Kaggle credentials are present.

## Local Parallel EDA Runner

To run real EDA and the ML pipeline locally, use:

```powershell
cd backend
python scripts/run_real_dataset_pipeline.py --dataset-ref owner/dataset-slug
```

Kaggle example:

```powershell
python scripts/run_real_dataset_pipeline.py --dataset-ref datasetengineer/southern-california-energy-consumption
```

Local CSV example:

```powershell
python scripts/run_real_dataset_pipeline.py --csv-path .\storage\datasets\my_dataset.csv
```

What the script does:

- loads a Kaggle dataset or local CSV
- runs EDA with parallel batched column profiling
- runs the ML pipeline on the same in-memory dataframe
- writes a JSON report to `storage/test_runs/`

Useful flags:

- `--workers 6`
- `--batch-size 10`
- `--model auto|ARIMA|XGBoost|LSTM`
- `--target-column your_column`
- `--horizon 14`
- `--output .\storage\test_runs\custom-report.json`

## Architecture

- `api`: REST routes only; no business logic.
- `services`: discovery, EDA, LLM intelligence, pipeline, forecasting, monitoring.
- `agents`: deterministic orchestration layer that coordinates workflow decisions.
- `core`: config, schemas, lightweight persistence helpers.
- `storage`: generated FAISS indexes, cached datasets, and metric logs.
