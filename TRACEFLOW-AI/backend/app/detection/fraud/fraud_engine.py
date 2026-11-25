import os
import uuid
from collections import defaultdict
from datetime import timedelta
from typing import Any, Dict, List
import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest
from sqlalchemy.orm import Session

from app.models.entities import Account, DetectionFinding, ModelVersion, Transaction

FEATURE_NAMES = [
    "amount",
    "log_amount",
    "amount_zscore",
    "ratio_to_account_avg",
    "tx_velocity_1h",
    "tx_velocity_24h",
    "is_night_utc",
    "beneficiary_novelty",
    "is_wire_or_api",
]


def _extract_fraud_features(txs: List[Transaction]) -> pd.DataFrame:
    """Compute per-transaction behavioral & statistical features without using ground-truth labels."""
    by_src: Dict[str, List[Transaction]] = defaultdict(list)
    for tx in txs:
        by_src[tx.source_account_id].append(tx)

    for src_id in by_src:
        by_src[src_id].sort(key=lambda t: t.timestamp)

    # Precompute per-account stats & seen beneficiaries
    acc_stats: Dict[str, Dict[str, float]] = {}
    for src_id, list_tx in by_src.items():
        amts = [float(t.amount) for t in list_tx]
        mean_a = float(np.mean(amts)) if amts else 0.0
        std_a = float(np.std(amts)) if len(amts) > 1 else max(mean_a * 0.25, 1.0)
        acc_stats[src_id] = {"mean": mean_a, "std": max(std_a, 1.0)}

    seen_beneficiaries: Dict[str, set] = defaultdict(set)
    rows = []

    # Sort all chronologically to compute novelty & rolling velocities accurately
    sorted_txs = sorted(txs, key=lambda t: t.timestamp)
    tx_history_times: Dict[str, List[Any]] = defaultdict(list)

    for tx in sorted_txs:
        src = tx.source_account_id
        amt = float(tx.amount)
        stats = acc_stats[src]
        zscore = (amt - stats["mean"]) / stats["std"]
        ratio_avg = amt / max(stats["mean"], 1.0)

        # Rolling velocity counts
        ts = tx.timestamp
        hist = tx_history_times[src]
        v1h = sum(1 for prev_ts in hist if (ts - prev_ts) <= timedelta(hours=1))
        v24h = sum(1 for prev_ts in hist if (ts - prev_ts) <= timedelta(hours=24))
        hist.append(ts)

        ben_key = tx.beneficiary_ref or tx.destination_account_id
        is_novel_ben = 1.0 if ben_key not in seen_beneficiaries[src] else 0.0
        seen_beneficiaries[src].add(ben_key)

        hour = ts.hour
        is_night = 1.0 if (hour >= 0 and hour <= 5) else 0.0
        is_wire_api = 1.0 if (tx.transaction_type == "wire" or tx.channel == "api_gateway") else 0.0

        rows.append({
            "tx_id": tx.id,
            "amount": amt,
            "log_amount": float(np.log1p(amt)),
            "amount_zscore": float(zscore),
            "ratio_to_account_avg": float(ratio_avg),
            "tx_velocity_1h": float(v1h),
            "tx_velocity_24h": float(v24h),
            "is_night_utc": is_night,
            "beneficiary_novelty": is_novel_ben,
            "is_wire_or_api": is_wire_api,
        })

    return pd.DataFrame(rows)


def run_fraud_detection(db: Session, bank_id: str) -> Dict[str, Any]:
    """
    Execute the Fraud Detection Pipeline:
    1. Isolation Forest unsupervised anomaly detection.
    2. Statistical behavioral profiling (amount z-score, velocity burst, odd-hour & novel beneficiary).
    3. Feature-attribution explanation for each flagged transaction.
    """
    txs = db.query(Transaction).filter(Transaction.bank_id == bank_id).all()
    if not txs:
        return {"findings_created": 0, "transactions_scanned": 0, "model_version": "iforest-v1.0"}

    # Clear previous fraud findings for this bank before fresh analysis
    db.query(DetectionFinding).filter(
        DetectionFinding.bank_id == bank_id,
        DetectionFinding.engine == "fraud",
    ).delete(synchronize_session=False)

    df = _extract_fraud_features(txs)
    tx_map = {t.id: t for t in txs}

    X = df[FEATURE_NAMES].values
    contamination = min(0.08, max(0.01, 15.0 / len(df)))
    iso_model = IsolationForest(
        n_estimators=150,
        contamination=contamination,
        random_state=42,
    )
    preds = iso_model.fit_predict(X)
    raw_scores = -iso_model.decision_function(X)  # higher = more anomalous

    # Normalize anomaly score to 0-100
    min_s, max_s = float(np.min(raw_scores)), float(np.max(raw_scores))
    span = max(max_s - min_s, 1e-6)
    norm_scores = ((raw_scores - min_s) / span) * 100.0

    # Persist model version metadata
    os.makedirs("models", exist_ok=True)
    artifact_path = os.path.join("models", f"iforest_{bank_id}.joblib")
    joblib.dump(iso_model, artifact_path)

    model_ver = ModelVersion(
        id=f"mv_{uuid.uuid4().hex[:12]}",
        name="TraceFlow Isolation Forest Fraud Detector",
        engine_type="fraud",
        version="1.0.0",
        algorithm="IsolationForest + BehavioralZScore",
        metrics={
            "samples_evaluated": len(df),
            "contamination": round(contamination, 4),
            "anomalies_predicted": int(np.sum(preds == -1)),
        },
        artifact_path=artifact_path,
        is_active=True,
    )
    db.add(model_ver)

    findings: List[DetectionFinding] = []
    # Compute global feature means for deterministic attribution
    col_means = df[FEATURE_NAMES].mean()
    col_stds = df[FEATURE_NAMES].std().replace(0, 1.0)

    for idx, row in df.iterrows():
        tx_id = row["tx_id"]
        tx = tx_map[tx_id]
        iso_score = float(norm_scores[idx])
        is_iso_anomaly = int(preds[idx]) == -1

        indicators: List[str] = []
        rule_boost = 0.0

        if row["amount_zscore"] >= 2.8 or row["ratio_to_account_avg"] >= 8.0:
            indicators.append(
                f"Unusual transaction amount (${row['amount']:,.2f}, {row['ratio_to_account_avg']:.1f}x account mean)"
            )
            rule_boost += 25.0

        if row["tx_velocity_1h"] >= 4:
            indicators.append(
                f"High short-term velocity ({int(row['tx_velocity_1h'])} transfers in 1 hour)"
            )
            rule_boost += 22.0

        if row["beneficiary_novelty"] == 1.0 and row["amount"] >= 10000.0:
            indicators.append("First-time / novel beneficiary receiving high-value transfer")
            rule_boost += 15.0

        if row["is_night_utc"] == 1.0 and row["amount"] >= 8000.0:
            indicators.append("Off-hours high-value activity (00:00–05:59 UTC)")
            rule_boost += 10.0

        if tx.device_id and ("NEW" in tx.device_id or "UNRECOGNIZED" in tx.device_id):
            indicators.append(f"Unrecognized or newly observed device ({tx.device_id})")
            rule_boost += 12.0

        combined_fraud_score = min(100.0, max(iso_score, iso_score * 0.65 + rule_boost))

        if is_iso_anomaly or combined_fraud_score >= 58.0 or len(indicators) >= 2:
            if not indicators:
                indicators.append("Multivariate behavioral deviation detected by Isolation Forest")

            # Compute normalized feature contributions (pseudo-SHAP z-deviation)
            feature_contrib = {}
            for fname in FEATURE_NAMES:
                z = (float(row[fname]) - float(col_means[fname])) / float(col_stds[fname])
                feature_contrib[fname] = round(z, 3)

            finding_type = "unusual_amount"
            if row["tx_velocity_1h"] >= 4:
                finding_type = "abnormal_velocity"
            elif tx.device_id and ("NEW" in tx.device_id or "UNRECOGNIZED" in tx.device_id):
                finding_type = "account_takeover_indicator"
            elif row["beneficiary_novelty"] == 1.0 and row["amount"] >= 10000.0:
                finding_type = "suspicious_beneficiary"

            explanation = (
                f"Transaction {tx.transaction_ref} (${tx.amount:,.2f}) flagged with fraud risk score "
                f"{combined_fraud_score:.1f}/100. Indicators: {'; '.join(indicators)}. "
                f"Note: This score reflects statistical anomaly deviation, not a calibrated probability of fraud."
            )

            findings.append(
                DetectionFinding(
                    id=f"fnd_{uuid.uuid4().hex[:14]}",
                    bank_id=bank_id,
                    engine="fraud",
                    finding_type=finding_type,
                    transaction_id=tx.id,
                    account_id=tx.source_account_id,
                    algorithm="IsolationForest + BehavioralProfiling",
                    model_version="iforest-v1.0.0",
                    risk_score=round(combined_fraud_score, 2),
                    evidence_indicators=indicators,
                    graph_path=[tx.source_account_id, tx.destination_account_id],
                    explanation=explanation,
                    shap_values=feature_contrib,
                )
            )

    if findings:
        db.bulk_save_objects(findings)
    db.commit()

    return {
        "findings_created": len(findings),
        "transactions_scanned": len(txs),
        "model_version": "iforest-v1.0.0",
        "artifact_path": artifact_path,
    }
