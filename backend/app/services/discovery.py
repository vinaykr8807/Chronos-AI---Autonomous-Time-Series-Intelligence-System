from __future__ import annotations

import json
import math
import os
import re
from collections import Counter
from pathlib import Path

from app.core.config import settings
from app.core.schemas import DatasetResult, DatasetSearchResponse, Domain, SearchRequest
from app.services.catalog import CATALOG


class DatasetDiscoveryService:
    """Semantic dataset discovery with FAISS-backed persistence and Kaggle integration."""

    def __init__(self) -> None:
        self._model = None
        self._faiss_index = None
        self._last_engine = "tfidf-fallback"
        self._cache_dir = settings.storage_dir / "discovery"
        self._cache_dir.mkdir(parents=True, exist_ok=True)
        self._catalog_store = self._cache_dir / "catalog.json"
        self._faiss_store = self._cache_dir / "catalog.faiss"
        self._catalog = self._build_catalog()
        self._persist_catalog_metadata()

    def search(self, payload: SearchRequest) -> DatasetSearchResponse:
        candidates = self._merge_results(self._catalog, self._fetch_kaggle(payload))
        filtered = [
            dataset for dataset in candidates
            if (payload.domain in (None, "general") or dataset.domain == payload.domain)
            and (not payload.time_series_only or dataset.isTimeSeriesValidated)
        ]
        ranked = self._rank(payload.query, filtered)[: payload.limit]
        return DatasetSearchResponse(
            query=payload.query,
            results=ranked,
            engine=self._last_engine,
            retrieval={
                "indexType": "faiss" if self._faiss_index is not None else "in-memory",
                "candidateCount": len(candidates),
                "filteredCount": len(filtered),
                "embeddingModel": "all-MiniLM-L6-v2" if self._model else "tfidf-fallback",
                "persistedIndex": self._faiss_store.exists(),
            },
        )

    def _fetch_kaggle(self, payload: SearchRequest) -> list[DatasetResult]:
        kaggle_username = settings.kaggle_username or os.getenv("KAGGLE_USERNAME")
        kaggle_key = settings.kaggle_key or settings.kaggle_api_key or os.getenv("KAGGLE_KEY") or os.getenv("KAGGLE_API_KEY")
        if not kaggle_username or not kaggle_key:
            return []
        try:
            os.environ.setdefault("KAGGLE_USERNAME", kaggle_username)
            os.environ.setdefault("KAGGLE_KEY", kaggle_key)
            from kaggle.api.kaggle_api_extended import KaggleApi

            api = KaggleApi()
            api.authenticate()
            datasets = api.dataset_list(search=payload.query, max_size=None, file_type="csv", sort_by="hottest")
            results: list[DatasetResult] = []
            for item in datasets[: payload.limit]:
                title = getattr(item, "title", None) or getattr(item, "ref", "Kaggle Dataset")
                description = getattr(item, "subtitle", "") or f"Kaggle dataset: {title}"
                tags = self._tag_names(getattr(item, "tags", []))
                is_ts = self._looks_time_series(title, description, tags)
                results.append(
                    DatasetResult(
                        id=getattr(item, "ref", title).replace("/", "--"),
                        title=title,
                        description=description,
                        domain=self._infer_domain(" ".join([title, *tags])),
                        tags=tags or [payload.query or "time-series"],
                        relevanceScore=0.75,
                        semanticScore=0.75,
                        isTimeSeriesValidated=is_ts,
                        rowCount=0,
                        columnCount=0,
                        timeRange={"start": "unknown", "end": "unknown"},
                        missingPercent=0,
                        source="kaggle",
                        ref=getattr(item, "ref", None),
                        validationSummary="Metadata suggests a temporal forecasting candidate." if is_ts else "Metadata requires deeper validation before forecasting use.",
                    )
                )
            return results
        except Exception:
            return []

    def _rank(self, query: str, datasets: list[DatasetResult]) -> list[DatasetResult]:
        if not query.strip():
            return datasets
        try:
            return self._rank_with_embeddings(query, datasets)
        except Exception:
            return self._rank_with_tfidf(query, datasets)

    def _rank_with_embeddings(self, query: str, datasets: list[DatasetResult]) -> list[DatasetResult]:
        import faiss
        import numpy as np
        from sentence_transformers import SentenceTransformer

        self._last_engine = "sentence-transformers/faiss" if datasets == self._catalog else "sentence-transformers/ephemeral-faiss"
        if self._model is None:
            try:
                self._model = SentenceTransformer("all-MiniLM-L6-v2", local_files_only=True)
            except Exception:
                self._model = SentenceTransformer("all-MiniLM-L6-v2")
        docs = [self._text(dataset) for dataset in datasets]
        query_matrix = np.asarray(self._model.encode([query], normalize_embeddings=True), dtype="float32")
        doc_matrix = np.asarray(self._model.encode(docs, normalize_embeddings=True), dtype="float32")

        if datasets == self._catalog:
            self._load_or_build_catalog_index(doc_matrix)
            index = self._faiss_index
        else:
            index = faiss.IndexFlatIP(doc_matrix.shape[1])
            index.add(doc_matrix)

        scores, indices = index.search(query_matrix, len(datasets))
        ranked: list[DatasetResult] = []
        for score, idx in zip(scores[0], indices[0]):
            dataset = datasets[int(idx)]
            semantic = round(max(float(score), 0.01), 3)
            ranked.append(dataset.model_copy(update={"relevanceScore": semantic, "semanticScore": semantic}))
        return ranked

    def _rank_with_tfidf(self, query: str, datasets: list[DatasetResult]) -> list[DatasetResult]:
        self._last_engine = "tfidf-fallback"
        docs = [self._text(dataset) for dataset in datasets]
        tokens = [self._tokens(doc) for doc in docs]
        query_tokens = self._tokens(query)
        df = Counter(token for doc in tokens for token in set(doc))
        scores = []
        for dataset, doc_tokens in zip(datasets, tokens):
            tf = Counter(doc_tokens)
            score = 0.0
            for token in query_tokens:
                if token in tf:
                    score += (1 + math.log(tf[token])) * math.log((1 + len(docs)) / (1 + df[token]) + 1)
            normalized = round(min(0.99, 0.55 + score / max(len(df), 1)), 3)
            scores.append(dataset.model_copy(update={"relevanceScore": normalized, "semanticScore": normalized}))
        return sorted(scores, key=lambda item: item.relevanceScore, reverse=True)

    def _load_or_build_catalog_index(self, doc_matrix) -> None:
        import faiss

        if self._faiss_index is not None:
            return
        if self._faiss_store.exists():
            index = faiss.read_index(str(self._faiss_store))
            if index.ntotal == len(self._catalog):
                self._faiss_index = index
                return
        index = faiss.IndexFlatIP(doc_matrix.shape[1])
        index.add(doc_matrix)
        faiss.write_index(index, str(self._faiss_store))
        self._faiss_index = index

    def _persist_catalog_metadata(self) -> None:
        self._catalog_store.write_text(json.dumps([item.model_dump() for item in self._catalog], indent=2), encoding="utf-8")

    def _text(self, dataset: DatasetResult) -> str:
        return f"{dataset.title} {dataset.description} {' '.join(dataset.tags)} {dataset.domain}"

    def _tokens(self, text: str) -> list[str]:
        return [token.strip(".,:;()[]").lower() for token in text.split() if len(token.strip()) > 2]

    def _infer_domain(self, text: str):
        text = text.lower()
        domain_signals: dict[Domain, list[str]] = {
            "finance": ["finance", "financial", "stock", "price", "gold", "market", "trading"],
            "sales": [
                "sales", "store", "retail", "truck", "supply", "chain", "inventory",
                "transaction", "e-commerce", "commerce",
            ],
            "traffic": ["traffic", "vehicle", "mobility", "highway", "congestion", "forecast", "weather"],
            "energy": [
                "energy", "electric", "eletric", "electricity", "eergy", "power", "load",
                "demand", "consumption", "efficiency",
            ],
            "iot": [
                "iot", "sensor", "industrial", "machine", "manufacturing", "health",
                "social", "happiness", "mental",
            ],
        }
        scores = {
            domain: sum(1 for signal in signals if signal in text)
            for domain, signals in domain_signals.items()
        }
        best_domain, best_score = max(scores.items(), key=lambda item: item[1])
        if best_score > 0:
            return best_domain
        return "general"

    def _build_catalog(self) -> list[DatasetResult]:
        real_catalog = [
            dataset for dataset in CATALOG
            if dataset.ref or dataset.source in {"kaggle", "local-storage"}
        ]
        return self._merge_results(self._local_storage_datasets(), real_catalog)

    def _merge_results(self, *groups: list[DatasetResult]) -> list[DatasetResult]:
        merged: dict[str, DatasetResult] = {}
        for group in groups:
            for dataset in group:
                existing = merged.get(dataset.id)
                if existing is None or (not existing.ref and dataset.ref):
                    merged[dataset.id] = dataset
        return list(merged.values())

    def _local_storage_datasets(self) -> list[DatasetResult]:
        datasets: list[DatasetResult] = []
        for dataset_dir in self._dataset_roots():
            for folder in sorted(dataset_dir.iterdir()):
                if not folder.is_dir():
                    continue
                csv_path = self._preferred_csv(folder)
                if csv_path is None:
                    continue
                datasets.append(self._dataset_from_csv_folder(folder, csv_path))
        return datasets

    def _dataset_roots(self) -> list[Path]:
        roots = [
            settings.storage_dir / "datasets",
            Path(__file__).resolve().parents[2] / "storage" / "datasets",
            Path.cwd() / "backend" / "storage" / "datasets",
        ]
        unique: list[Path] = []
        seen: set[Path] = set()
        for root in roots:
            resolved = root.resolve()
            if resolved.exists() and resolved not in seen:
                unique.append(resolved)
                seen.add(resolved)
        return unique

    def _dataset_from_csv_folder(self, folder: Path, csv_path: Path) -> DatasetResult:
        owner, slug = self._owner_slug(folder.name)
        dataset_id = f"{owner}--{slug}" if owner and slug else folder.name
        ref = f"{owner}/{slug}" if owner and slug else None
        title = self._title_from_slug(slug or folder.name)
        headers, row_count = self._csv_shape(csv_path)
        text = " ".join([folder.name, csv_path.name, title, *headers])
        domain = self._infer_domain(text)
        tags = self._tags_from_text(text, domain)
        return DatasetResult(
            id=dataset_id,
            title=title,
            description=f"Cached local dataset from storage/datasets with primary file `{csv_path.name}`.",
            domain=domain,
            tags=tags,
            relevanceScore=0.86,
            semanticScore=0.86,
            isTimeSeriesValidated=self._looks_time_series(title, csv_path.name, tags + headers),
            rowCount=row_count,
            columnCount=len(headers),
            timeRange={"start": "unknown", "end": "unknown"},
            missingPercent=0,
            source="local-storage",
            ref=ref,
            validationSummary="Available from local storage; run EDA to validate forecasting readiness.",
        )

    def _owner_slug(self, folder_name: str) -> tuple[str | None, str | None]:
        if "__" in folder_name:
            owner, slug = folder_name.split("__", 1)
            return owner, slug
        if "--" in folder_name:
            owner, slug = folder_name.split("--", 1)
            return owner, slug
        return None, folder_name

    def _title_from_slug(self, slug: str) -> str:
        words = re.split(r"[-_]+", slug)
        return " ".join(word.capitalize() for word in words if word)

    def _preferred_csv(self, cache_path: Path) -> Path | None:
        csv_files = sorted(cache_path.rglob("*.csv"), key=lambda item: item.stat().st_size, reverse=True)
        return csv_files[0] if csv_files else None

    def _csv_shape(self, csv_path: Path) -> tuple[list[str], int]:
        headers: list[str] = []
        row_count = 0
        try:
            with csv_path.open("r", encoding="utf-8", errors="replace", newline="") as handle:
                first_line = handle.readline()
                headers = [value.strip() for value in first_line.split(",") if value.strip()]
                row_count = sum(1 for _ in handle)
        except Exception:
            return [], 0
        return headers, row_count

    def _tags_from_text(self, text: str, domain: Domain) -> list[str]:
        tokens = []
        for token in self._tokens(text):
            normalized = token.replace("_", "-")
            if normalized not in tokens:
                tokens.append(normalized)
        return [domain, *tokens[:5]]

    def _tag_names(self, tags: object) -> list[str]:
        names: list[str] = []
        for tag in list(tags or [])[:6]:
            if isinstance(tag, dict):
                value = tag.get("name") or tag.get("ref")
            else:
                value = getattr(tag, "name", None) or getattr(tag, "ref", None) or str(tag)
            normalized = str(value).strip() if value else ""
            if normalized:
                names.append(normalized)
        return names

    def _looks_time_series(self, title: str, description: str, tags: list[str]) -> bool:
        text = " ".join([title, description, *tags]).lower()
        signals = ["time series", "forecast", "hourly", "daily", "monthly", "demand", "load", "weather"]
        return any(signal in text for signal in signals)
