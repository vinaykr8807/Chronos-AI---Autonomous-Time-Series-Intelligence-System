from concurrent.futures import ThreadPoolExecutor, TimeoutError

from app.core.config import settings
from app.core.schemas import DatasetProfile


class DatasetIntelligenceService:
    """Uses an LLM for explanation only; core ML decisions stay deterministic."""

    _executor = ThreadPoolExecutor(max_workers=2)
    _timeout_seconds = 25.0

    def explain(self, profile: DatasetProfile) -> str:
        fallback = self._fallback_report(profile)
        if (profile.evidence_refs or {}).get("llmGate") != "ready":
            return fallback
        if not settings.groq_api_key:
            return fallback
        try:
            future = self._executor.submit(self._remote_explain, profile)
            return future.result(timeout=self._timeout_seconds) or fallback
        except TimeoutError:
            return fallback
        except Exception:
            return fallback

    def _remote_explain(self, profile: DatasetProfile) -> str:
        from groq import Groq

        forecastability = profile.forecastability or {}
        strategy = profile.strategy_recommendation or {}
        quality = profile.quality_intelligence or {}
        temporal = profile.temporal_behavior or {}
        feature_intel = profile.feature_intelligence or {}
        semantic = profile.semantic_understanding or {}
        structural = profile.structural_intelligence or {}
        evidence = profile.evidence_refs or {}
        eda_trace = profile.eda_trace or []
        has_time = bool(profile.time_series.get("valid"))
        dataset_type = "time-series" if has_time else "cross-sectional (no time index)"

        column_summary = []
        for col in profile.columns[:14]:
            entry = f"- {col.name} ({col.type}): missing={col.missingPercent}%"
            if col.type == "numeric":
                entry += f", mean={col.mean}, std={col.std}, min={col.min}, max={col.max}, outliers={col.outlierPercent}%"
            elif col.type == "categorical":
                entry += f", unique={col.uniqueValues}, top={col.topValues[:3]}"
            column_summary.append(entry)

        strong_signals = [
            f"{s['feature']}({s.get('associationMethod','pearson')}={s['sameTimeCorrelation']})"
            for s in (feature_intel.get("predictiveSignals") or [])
            if max(float(s.get("sameTimeCorrelation", 0)), float(s.get("lagInfluence", 0))) >= 0.06
        ]

        # Build sections dynamically based on dataset type
        if has_time:
            analysis_sections = (
                "1) Dataset overview and domain context, "
                "2) Data quality (missing values, trust score, anomalies, drift), "
                "3) Time-series characteristics (frequency, seasonality, stationarity, periodicity, regime changes), "
                "4) Forecastability analysis with specific scores and risks, "
                "5) Feature analysis (strong predictors, redundant features, leakage risks), "
                "6) Recommended modeling strategy with justification."
            )
        else:
            analysis_sections = (
                "1) Dataset overview and domain context (this is a cross-sectional dataset, NOT time-series), "
                "2) Data quality (missing values, trust score, outliers, distribution shape), "
                "3) Feature analysis (which features are strong predictors of the target, association strengths, redundancy), "
                "4) Target variable analysis (distribution, skewness, outlier rate), "
                "5) Recommended modeling strategy (regression/classification, validation approach, preprocessing), "
                "6) Business insights specific to this domain and dataset."
            )

        user_content = (
            f"Dataset: {profile.title}\n"
            f"Dataset type: {dataset_type}\n"
            f"Domain: {semantic.get('inferredDomain')} | Use case: {semantic.get('likelyUseCase')}\n"
            f"Business meaning: {semantic.get('businessMeaning')}\n"
            f"Shape: {profile.summary.get('rows'):,} rows x {profile.summary.get('columns')} columns\n"
            f"Missing: {profile.summary.get('missingPercent')}% | Trust score: {quality.get('trustScore')}\n"
            + (
                f"Time column: {profile.time_series.get('timeColumn')} | Frequency: {profile.time_series.get('frequency')} | Consistency: {profile.time_series.get('consistencyScore')}\n"
                f"Periodicity: {temporal.get('periodicity')} | Drift score: {temporal.get('driftScore')} | Anomalies: {len(temporal.get('anomalies') or [])} | Regime changes: {len(temporal.get('regimeChanges') or [])}\n"
                f"Temporal interpretation: {temporal.get('interpretation')}\n"
                if has_time else
                f"Distribution shape: {temporal.get('distributionShape')} | Skewness: {temporal.get('skewness')} | Outlier count: {temporal.get('outlierCount')}\n"
                f"Target interpretation: {temporal.get('interpretation')}\n"
            )
            + f"Forecastability/predictability score: {forecastability.get('score')} ({forecastability.get('grade')})\n"
            + (f"Seasonality: {forecastability.get('seasonalityStrength')} | Noise ratio: {forecastability.get('noiseRatio')} | Trend: {forecastability.get('trendConsistency')}\n" if has_time else "")
            + f"Forecastability reasons: {forecastability.get('reasons')}\n"
            + f"Forecastability risks: {forecastability.get('risks')}\n"
            + f"Target column: {structural.get('targetColumn')} | {semantic.get('targetMeaning')}\n"
            + f"Strong predictive signals: {strong_signals[:8]}\n"
            + f"Redundant features: {[r['features'] for r in (feature_intel.get('redundantFeatures') or [])[:3]]}\n"
            + f"Leakage warnings: {feature_intel.get('leakageWarnings')}\n"
            + f"Recommended model: {strategy.get('recommendedModelFamily')} | Confidence: {strategy.get('confidence')}\n"
            + f"Strategy reason: {strategy.get('reason')}\n"
            + f"Preprocessing plan: {strategy.get('preprocessingPlan')}\n"
            + f"EDA evidence store: id={evidence.get('evidenceId')} chunks={evidence.get('chunkCount')} embedding={evidence.get('embeddingBackend')} faiss={evidence.get('faissPath')}\n"
            + f"Deterministic EDA trace: {eda_trace}\n"
            + f"Column profiles:\n" + "\n".join(column_summary)
        )

        client = Groq(api_key=settings.groq_api_key)
        response = client.chat.completions.create(
            model=settings.groq_model,
            messages=[
                {
                    "role": "system",
                    "content": (
                        f"You are a senior data scientist writing a professional dataset intelligence report for a {dataset_type} dataset. "
                        "You are only allowed to use the deterministic EDA evidence supplied by the backend. "
                        "Do not override the target column, dataset type, model strategy, or quality conclusions. "
                        f"Write a structured analysis covering: {analysis_sections} "
                        "Be specific; use the actual column names, numbers, and scores provided. "
                        "Do not invent training results or metrics. "
                        "Do not use bullet points. Write in clear, dense paragraphs."
                    ),
                },
                {"role": "user", "content": user_content},
            ],
            temperature=0.15,
            max_tokens=950,
        )
        return response.choices[0].message.content or ""

    def _fallback_report(self, profile: DatasetProfile) -> str:
        numeric = [col.name for col in profile.columns if col.type == "numeric"]
        categorical = [col.name for col in profile.columns if col.type == "categorical"]
        datetime_cols = [col.name for col in profile.columns if col.type == "datetime"]
        missing = float(profile.summary.get("missingPercent", 0) or 0)
        rows = int(profile.summary.get("rows", 0) or 0)
        cols = int(profile.summary.get("columns", 0) or 0)
        forecastability = profile.forecastability or {}
        strategy = profile.strategy_recommendation or {}
        semantic = profile.semantic_understanding or {}
        quality = profile.quality_intelligence or {}
        temporal = profile.temporal_behavior or {}
        feature_intel = profile.feature_intelligence or {}
        time_series = profile.time_series or {}
        has_time = bool(time_series.get("valid"))

        fc_score = forecastability.get("score", "N/A")
        fc_grade = forecastability.get("grade", "unknown")
        trust = float(quality.get("trustScore") or 0)
        model = strategy.get("recommendedModelFamily", "XGBoost")
        model_reason = strategy.get("reason", "")
        domain = semantic.get("inferredDomain", "general")
        use_case = semantic.get("likelyUseCase", "predictive modeling")
        target = (profile.structural_intelligence or {}).get("targetColumn") or profile.validation.get("recommendedTarget")
        preprocessing = strategy.get("preprocessingPlan") or []
        fc_reasons = forecastability.get("reasons") or []
        fc_risks = forecastability.get("risks") or []
        strong_signals = [
            f"{s['feature']}" for s in (feature_intel.get("predictiveSignals") or [])
            if max(float(s.get("sameTimeCorrelation", 0)), float(s.get("lagInfluence", 0))) >= 0.06
        ]
        redundant = feature_intel.get("redundantFeatures") or []
        leakage = feature_intel.get("leakageWarnings") or []

        parts = []

        # Overview
        dataset_type = "time-series" if has_time else "cross-sectional"
        parts.append(
            f"{profile.title} is a {domain} {dataset_type} dataset with {rows:,} rows and {cols} columns, "
            f"suited for {use_case}. {semantic.get('businessMeaning', '')}"
        )

        # Column breakdown
        col_parts = []
        if datetime_cols:
            col_parts.append(f"{len(datetime_cols)} datetime: {', '.join(datetime_cols[:3])}")
        if numeric:
            col_parts.append(f"{len(numeric)} numeric: {', '.join(numeric[:5])}")
        if categorical:
            col_parts.append(f"{len(categorical)} categorical: {', '.join(categorical[:4])}")
        if col_parts:
            parts.append("Columns: " + "; ".join(col_parts) + ".")

        # Data quality
        quality_note = quality.get("missingPattern", f"{missing:.1f}% missing values")
        parts.append(f"Data quality: trust score {trust:.0f}/100. {quality_note}")
        if leakage and leakage != ["No obvious leakage columns detected by naming analysis."]:
            parts.append(f"Leakage risk: {'; '.join(str(w) for w in leakage[:2])}.")

        # Time-series or cross-sectional specific section
        if has_time:
            ts_col = time_series.get("timeColumn")
            freq = time_series.get("frequency", "unknown")
            consistency = float(time_series.get("consistencyScore") or 0)
            drift = float(temporal.get("driftScore") or 0)
            anomaly_count = len(temporal.get("anomalies") or [])
            seasonality = float(forecastability.get("seasonalityStrength") or 0)
            noise = float(forecastability.get("noiseRatio") or 0)
            parts.append(
                f"Time-series: column `{ts_col}`, frequency {freq}, interval consistency {consistency:.2f}. "
                f"Periodicity: {temporal.get('periodicity', 'undetermined')}. Drift score: {drift:.3f}."
            )
            if anomaly_count > 0:
                parts.append(f"{anomaly_count} temporal anomalies detected (|z| > 3).")
            parts.append(
                f"Forecastability: {fc_score} ({fc_grade}). Seasonality {seasonality:.3f}, noise ratio {noise:.3f}."
            )
            if fc_reasons:
                parts.append(" ".join(str(r) for r in fc_reasons[:2]))
            if fc_risks and fc_risks != ["No major forecastability blockers detected."]:
                parts.append("Risks: " + " ".join(str(r) for r in fc_risks[:2]))
        else:
            dist_shape = temporal.get("distributionShape", "unknown")
            outlier_count = temporal.get("outlierCount", 0)
            skew = temporal.get("skewness", 0)
            parts.append(
                f"Cross-sectional dataset with no time index. Target `{target}` distribution is {dist_shape} "
                f"(skewness {skew:.2f}), with {outlier_count:,} outliers."
            )
            parts.append(
                f"Predictability score: {fc_score} ({fc_grade}). "
                + (" ".join(str(r) for r in fc_reasons[:2]) if fc_reasons else "")
            )

        # Feature intelligence
        if strong_signals:
            parts.append(f"Top predictive features: {', '.join(strong_signals[:6])}.")
        if redundant:
            pairs = ["+".join(r["features"]) for r in redundant[:2]]
            parts.append(f"Redundant pairs (corr > 0.92): {', '.join(pairs)}.")

        # Strategy
        validation = "walk-forward temporal holdout" if has_time else "stratified k-fold cross-validation"
        parts.append(
            f"Recommended model: {model}. {model_reason} "
            f"Preprocessing: {', '.join(preprocessing)}. "
            f"Validate with {validation}."
        )

        if profile.eda_trace:
            trace_names = [str(step.get("stage")) for step in profile.eda_trace[:8]]
            evidence = profile.evidence_refs or {}
            parts.append(
                f"EDA evidence trace completed before explanation: {', '.join(trace_names)}. "
                f"Evidence store status: {evidence.get('llmGate', 'not indexed')}."
            )

        return " ".join(parts)
