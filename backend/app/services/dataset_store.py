from __future__ import annotations

import io
import hashlib
import os
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd

from app.core.config import settings
from app.core.schemas import DatasetProfile


class DataSourceError(RuntimeError):
    pass


class DatasetStoreService:
    _frame_cache: dict[str, pd.DataFrame] = {}

    def __init__(self) -> None:
        self._dataset_dir = settings.storage_dir / "datasets"
        self._dataset_dir.mkdir(parents=True, exist_ok=True)

    def load_training_frame(
        self,
        dataset_id: str,
        profile: DatasetProfile,
        source_ref: str | None = None,
        require_real: bool = False,
    ) -> tuple[pd.DataFrame, str]:
        resolved_ref = source_ref or self._infer_ref(dataset_id)
        if resolved_ref:
            dataframe = self._download_kaggle_dataset(resolved_ref)
            if dataframe is not None:
                return dataframe, f"kaggle:{resolved_ref}"
            if require_real:
                raise DataSourceError(
                    f"Real dataset `{resolved_ref}` could not be loaded. "
                    "Check Kaggle credentials, dataset availability, and cached archive integrity."
                )
        elif require_real:
            raise DataSourceError(f"Dataset `{dataset_id}` does not include a real data source reference.")
        return self._synthetic_frame(profile), "synthetic-profile"

    def preview_rows(
        self,
        dataset_id: str,
        profile: DatasetProfile,
        page: int = 1,
        page_size: int = 25,
        source_ref: str | None = None,
    ) -> tuple[list[dict[str, object]], list[str], int, str]:
        dataframe, source = self.load_training_frame(dataset_id, profile, source_ref)
        normalized = dataframe.copy()
        for column in normalized.columns:
            if pd.api.types.is_datetime64_any_dtype(normalized[column]):
                normalized[column] = normalized[column].astype(str)
            elif normalized[column].dtype == "object":
                normalized[column] = normalized[column].where(normalized[column].notna(), None)

        total_rows = int(len(normalized))
        safe_page = max(page, 1)
        safe_page_size = max(1, min(page_size, 100))
        start = (safe_page - 1) * safe_page_size
        end = start + safe_page_size
        page_frame = normalized.iloc[start:end].replace({np.nan: None})
        rows = page_frame.to_dict(orient="records")
        return rows, [str(column) for column in normalized.columns], total_rows, source

    def _download_kaggle_dataset(self, ref: str) -> pd.DataFrame | None:
        cached = self._frame_cache.get(ref)
        if cached is not None:
            return cached.copy()

        # Check all known local folder patterns for this ref before hitting Kaggle API
        slug = ref.replace("/", "__")
        slug_dash = ref.replace("/", "--")
        candidate_dirs = [
            self._dataset_dir / slug,
            self._dataset_dir / slug_dash,
        ]
        # Also scan storage/datasets for any folder whose name starts with the owner prefix
        owner = ref.split("/")[0] if "/" in ref else ""
        if owner and self._dataset_dir.exists():
            for folder in self._dataset_dir.iterdir():
                if folder.is_dir() and folder.name.startswith(owner) and folder not in candidate_dirs:
                    candidate_dirs.append(folder)

        for cache_path in candidate_dirs:
            csv_path = self._preferred_csv(cache_path)
            if csv_path is not None:
                try:
                    try:
                        dataframe = pd.read_csv(csv_path)
                    except UnicodeDecodeError:
                        dataframe = pd.read_csv(csv_path, encoding="latin-1")
                    self._frame_cache[ref] = dataframe
                    return dataframe.copy()
                except Exception:
                    continue

        kaggle_username = settings.kaggle_username or os.getenv("KAGGLE_USERNAME")
        kaggle_key = settings.kaggle_key or settings.kaggle_api_key or os.getenv("KAGGLE_KEY") or os.getenv("KAGGLE_API_KEY")
        if not kaggle_username or not kaggle_key:
            return None
        os.environ.setdefault("KAGGLE_USERNAME", kaggle_username)
        os.environ.setdefault("KAGGLE_KEY", kaggle_key)

        cache_path = self._dataset_dir / slug
        csv_path = self._preferred_csv(cache_path)
        if csv_path is None:
            try:
                from kaggle.api.kaggle_api_extended import KaggleApi

                cache_path.mkdir(parents=True, exist_ok=True)
                api = KaggleApi()
                api.authenticate()
                archive = api.dataset_download_files(ref, path=str(cache_path), force=False, quiet=True)
                zip_target = self._resolve_zip(cache_path, archive)
                if zip_target and zip_target.exists():
                    if not self._extract_zip(zip_target, cache_path):
                        archive = api.dataset_download_files(ref, path=str(cache_path), force=True, quiet=True)
                        zip_target = self._resolve_zip(cache_path, archive)
                        if not zip_target or not self._extract_zip(zip_target, cache_path):
                            return None
                csv_path = self._preferred_csv(cache_path)
            except Exception:
                return None
        if csv_path is None:
            return None
        try:
            dataframe = pd.read_csv(csv_path)
        except UnicodeDecodeError:
            dataframe = pd.read_csv(csv_path, encoding="latin-1")
        except Exception:
            return None
        self._frame_cache[ref] = dataframe
        return dataframe.copy()

    def _resolve_zip(self, cache_path: Path, archive: object) -> Path | None:
        if isinstance(archive, (str, Path)):
            candidate = Path(archive)
            if candidate.exists():
                return candidate
        zip_files = sorted(cache_path.glob("*.zip"), key=lambda item: item.stat().st_size, reverse=True)
        return zip_files[0] if zip_files else None

    def _preferred_csv(self, cache_path: Path) -> Path | None:
        csv_files = sorted(cache_path.rglob("*.csv"), key=lambda item: item.stat().st_size, reverse=True)
        return csv_files[0] if csv_files else None

    def _extract_zip(self, zip_target: Path, cache_path: Path) -> bool:
        try:
            with zipfile.ZipFile(zip_target, "r") as zf:
                if zf.testzip() is not None:
                    return False
                zf.extractall(cache_path)
            return True
        except zipfile.BadZipFile:
            return False

    def _infer_ref(self, dataset_id: str) -> str | None:
        if "--" in dataset_id:
            owner, slug = dataset_id.split("--", 1)
            if owner and slug:
                return f"{owner}/{slug}"
        # Check if a local cached folder exists for this dataset_id
        candidate = self._dataset_dir / dataset_id.replace("/", "__")
        if candidate.exists() and self._preferred_csv(candidate) is not None:
            # Reconstruct ref from folder name if it looks like owner__slug
            parts = dataset_id.replace("__", "/").split("/")
            if len(parts) == 2 and parts[0] and parts[1]:
                return f"{parts[0]}/{parts[1]}"
        return None

    def _synthetic_frame(self, profile: DatasetProfile) -> pd.DataFrame:
        rows = min(max(int(profile.summary.get("rows", 2400) or 2400), 600), 5000)
        rng = np.random.default_rng(self._stable_seed(profile.dataset_id))
        timestamps = pd.date_range("2021-01-01", periods=rows, freq="h")
        trend = np.linspace(0, rows * 0.4, rows)
        seasonal_day = np.sin(np.arange(rows) / 24 * 2 * np.pi) * 1200
        seasonal_week = np.sin(np.arange(rows) / 168 * 2 * np.pi) * 2400
        temperature = 24 + np.sin(np.arange(rows) / 24 * 2 * np.pi) * 9 + rng.normal(0, 1.5, rows)
        target = 42000 + trend + seasonal_day + seasonal_week + temperature * 110 + rng.normal(0, 320, rows)
        return pd.DataFrame(
            {
                "timestamp": timestamps,
                "target_value": target,
                "temperature": temperature,
                "segment": rng.choice(["residential", "commercial", "industrial"], size=rows, p=[0.45, 0.35, 0.2]),
            }
        )

    def _stable_seed(self, value: str) -> int:
        digest = hashlib.sha256(value.encode("utf-8")).digest()
        return int.from_bytes(digest[:4], "little")
