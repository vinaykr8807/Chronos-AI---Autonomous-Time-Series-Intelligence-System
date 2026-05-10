from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import numpy as np

from app.core.config import settings
from app.core.schemas import DatasetProfile


class EDAEvidenceStore:
    """Persist deterministic EDA evidence before any LLM explanation is allowed."""

    def __init__(self) -> None:
        self._store_dir = settings.storage_dir / "eda_evidence"
        self._store_dir.mkdir(parents=True, exist_ok=True)
        self._model = None

    def persist(self, profile: DatasetProfile) -> dict[str, object]:
        evidence = self._evidence_payload(profile)
        evidence_id = self._evidence_id(profile.dataset_id, evidence)
        json_path = self._store_dir / f"{evidence_id}.json"
        faiss_path = self._store_dir / f"{evidence_id}.faiss"
        metadata_path = self._store_dir / f"{evidence_id}.meta.json"

        json_path.write_text(json.dumps(evidence, indent=2, default=str), encoding="utf-8")
        embedding_backend, dimension = self._write_faiss_index(evidence, faiss_path)

        metadata = {
            "evidenceId": evidence_id,
            "jsonPath": str(json_path),
            "faissPath": str(faiss_path),
            "embeddingBackend": embedding_backend,
            "embeddingDimension": dimension,
            "chunkCount": len(evidence["chunks"]),
            "llmGate": "ready" if faiss_path.exists() else "blocked",
        }
        metadata_path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")
        return metadata

    def clear(self) -> int:
        removed = 0
        for path in self._store_dir.glob("*"):
            if path.is_file() and path.suffix in {".json", ".faiss"}:
                path.unlink()
                removed += 1
        return removed

    def _evidence_payload(self, profile: DatasetProfile) -> dict[str, Any]:
        target = (profile.structural_intelligence or {}).get("targetColumn") or profile.validation.get("recommendedTarget")
        chunks = [
            {
                "kind": "dataset_summary",
                "text": (
                    f"{profile.title}; dataset_id={profile.dataset_id}; rows={profile.summary.get('rows')}; "
                    f"columns={profile.summary.get('columns')}; missing={profile.summary.get('missingPercent')}%; "
                    f"dataset_type={(profile.structural_intelligence or {}).get('datasetType')}; target={target}; "
                    f"time_column={(profile.structural_intelligence or {}).get('timeColumn')}"
                ),
            },
            {
                "kind": "quality",
                "text": json.dumps(profile.quality_intelligence, default=str),
            },
            {
                "kind": "forecastability",
                "text": json.dumps(profile.forecastability, default=str),
            },
            {
                "kind": "strategy",
                "text": json.dumps(profile.strategy_recommendation, default=str),
            },
            {
                "kind": "feature_intelligence",
                "text": json.dumps(profile.feature_intelligence, default=str),
            },
        ]
        for item in profile.eda_trace:
            chunks.append({"kind": str(item.get("stage", "eda_trace")), "text": json.dumps(item, default=str)})
        for column in profile.columns:
            payload = {
                "name": column.name,
                "type": column.type,
                "missingPercent": column.missingPercent,
                "uniqueValues": column.uniqueValues,
                "min": column.min,
                "max": column.max,
                "mean": column.mean,
                "median": column.median,
                "std": column.std,
                "outlierPercent": column.outlierPercent,
                "topValues": column.topValues,
                "role": (profile.structural_intelligence.get("columnRoles", {}) if profile.structural_intelligence else {}).get(column.name),
            }
            chunks.append({"kind": "column_profile", "text": json.dumps(payload, default=str)})

        return {
            "datasetId": profile.dataset_id,
            "title": profile.title,
            "summary": profile.summary,
            "timeSeries": profile.time_series,
            "validation": profile.validation,
            "structuralIntelligence": profile.structural_intelligence,
            "forecastability": profile.forecastability,
            "temporalBehavior": profile.temporal_behavior,
            "qualityIntelligence": profile.quality_intelligence,
            "featureIntelligence": profile.feature_intelligence,
            "strategyRecommendation": profile.strategy_recommendation,
            "semanticUnderstanding": profile.semantic_understanding,
            "edaTrace": profile.eda_trace,
            "chunks": chunks,
        }

    def _write_faiss_index(self, evidence: dict[str, Any], faiss_path: Path) -> tuple[str, int]:
        import faiss

        texts = [str(chunk["text"]) for chunk in evidence["chunks"]]
        vectors, backend = self._embed(texts)
        index = faiss.IndexFlatIP(vectors.shape[1])
        index.add(vectors)
        faiss.write_index(index, str(faiss_path))
        return backend, int(vectors.shape[1])

    def _embed(self, texts: list[str]) -> tuple[np.ndarray, str]:
        try:
            from sentence_transformers import SentenceTransformer

            if self._model is None:
                self._model = SentenceTransformer("all-MiniLM-L6-v2", local_files_only=True)
            vectors = np.asarray(self._model.encode(texts, normalize_embeddings=True), dtype="float32")
            return vectors, "sentence-transformers/all-MiniLM-L6-v2"
        except Exception:
            vectors = np.vstack([self._hash_embedding(text) for text in texts]).astype("float32")
            norms = np.linalg.norm(vectors, axis=1, keepdims=True)
            vectors = vectors / np.maximum(norms, 1e-8)
            return vectors, "hashing-fallback"

    def _hash_embedding(self, text: str, dimensions: int = 384) -> np.ndarray:
        vector = np.zeros(dimensions, dtype=np.float32)
        for token in text.lower().replace("_", " ").split():
            digest = hashlib.sha256(token.encode("utf-8")).digest()
            index = int.from_bytes(digest[:4], "little") % dimensions
            sign = 1.0 if digest[4] % 2 == 0 else -1.0
            vector[index] += sign
        return vector

    def _evidence_id(self, dataset_id: str, evidence: dict[str, Any]) -> str:
        raw = json.dumps(
            {
                "datasetId": dataset_id,
                "summary": evidence.get("summary", {}),
                "validation": evidence.get("validation", {}),
                "strategyRecommendation": evidence.get("strategyRecommendation", {}),
            },
            sort_keys=True,
            default=str,
        )
        digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]
        safe_dataset = dataset_id.replace("/", "__").replace("\\", "__").replace(":", "_")
        return f"{safe_dataset}-{digest}"
