import uuid
from collections import defaultdict
from typing import Any, Dict, List
import networkx as nx
from sqlalchemy.orm import Session

from app.graph.graph_service import graph_service
from app.models.entities import (
    Account,
    Alert,
    Bank,
    DetectionFinding,
    RiskAssessment,
    Transaction,
)


def classify_risk(score: float, thresholds: Dict[str, int]) -> str:
    low_max = int(thresholds.get("low_max", 29))
    mod_max = int(thresholds.get("moderate_max", 49))
    high_max = int(thresholds.get("high_max", 74))
    if score <= low_max:
        return "Low"
    if score <= mod_max:
        return "Moderate"
    if score <= high_max:
        return "High"
    return "Critical"


def run_unified_risk_scoring(db: Session, bank_id: str) -> Dict[str, Any]:
    """
    Combine independent Fraud and AML findings with Network centrality risk
    into transparent 0-100 risk scores for Transactions and Accounts,
    record RiskAssessment history, and generate Alerts for High/Critical items.
    """
    bank = db.query(Bank).filter(Bank.id == bank_id).first()
    cfg = bank.config if (bank and bank.config) else {}
    weights = cfg.get("scoring_weights", {"fraud_weight": 0.40, "aml_weight": 0.40, "network_weight": 0.20})
    thresholds = cfg.get("risk_thresholds", {"low_max": 29, "moderate_max": 49, "high_max": 74})

    w_fraud = float(weights.get("fraud_weight", 0.40))
    w_aml = float(weights.get("aml_weight", 0.40))
    w_net = float(weights.get("network_weight", 0.20))
    w_sum = max(w_fraud + w_aml + w_net, 1e-6)
    w_fraud, w_aml, w_net = w_fraud / w_sum, w_aml / w_sum, w_net / w_sum

    findings = db.query(DetectionFinding).filter(DetectionFinding.bank_id == bank_id).all()
    txs = db.query(Transaction).filter(Transaction.bank_id == bank_id).all()
    accounts = db.query(Account).filter(Account.bank_id == bank_id).all()

    # Build graph for network centrality contribution
    G, _ = graph_service.build_networkx_graph(db, bank_id)
    simple_di = nx.DiGraph(G)
    try:
        pr = nx.pagerank(simple_di) if len(simple_di) > 0 else {}
    except Exception:
        pr = {}
    max_pr = max(pr.values(), default=1e-6) or 1e-6

    tx_fraud: Dict[str, List[DetectionFinding]] = defaultdict(list)
    tx_aml: Dict[str, List[DetectionFinding]] = defaultdict(list)
    acc_fraud: Dict[str, List[DetectionFinding]] = defaultdict(list)
    acc_aml: Dict[str, List[DetectionFinding]] = defaultdict(list)

    for f in findings:
        if f.engine == "fraud":
            if f.transaction_id:
                tx_fraud[f.transaction_id].append(f)
            if f.account_id:
                acc_fraud[f.account_id].append(f)
        elif f.engine == "aml":
            if f.transaction_id:
                tx_aml[f.transaction_id].append(f)
            for acc_id in (f.graph_path or ([f.account_id] if f.account_id else [])):
                if acc_id:
                    acc_aml[acc_id].append(f)

    assessments: List[RiskAssessment] = []
    alerts_to_create: List[Alert] = []
    existing_alert_keys = {
        (a.category, a.transaction_id, a.account_id, a.finding_id)
        for a in db.query(Alert).filter(Alert.bank_id == bank_id).all()
    }

    # Score transactions
    flagged_tx_count = 0
    for tx in txs:
        f_score = max((f.risk_score for f in tx_fraud.get(tx.id, [])), default=0.0)
        a_score = max((f.risk_score for f in tx_aml.get(tx.id, [])), default=0.0)
        net_raw = ((pr.get(tx.source_account_id, 0.0) + pr.get(tx.destination_account_id, 0.0)) / (2.0 * max_pr)) * 100.0
        n_score = min(100.0, net_raw)

        # If either engine strongly flagged it, ensure combined score reflects severity
        weighted = w_fraud * f_score + w_aml * a_score + w_net * n_score
        peak = max(f_score, a_score)
        combined = min(100.0, max(weighted, peak * 0.85 if peak >= 60.0 else weighted))

        cat = classify_risk(combined, thresholds)
        tx.risk_score = round(combined, 2)
        tx.risk_category = cat
        tx.is_flagged = combined >= (thresholds.get("moderate_max", 49) + 1)
        if tx.is_flagged:
            flagged_tx_count += 1

        if combined >= 30.0:
            factors = []
            if f_score > 0:
                factors.append(f"Fraud Engine: {f_score:.1f}/100 (weight {w_fraud:.0%})")
            if a_score > 0:
                factors.append(f"AML Engine: {a_score:.1f}/100 (weight {w_aml:.0%})")
            factors.append(f"Network Centrality: {n_score:.1f}/100 (weight {w_net:.0%})")

            assessments.append(
                RiskAssessment(
                    id=f"rsk_{uuid.uuid4().hex[:14]}",
                    bank_id=bank_id,
                    entity_type="transaction",
                    entity_id=tx.id,
                    fraud_risk=round(f_score, 2),
                    aml_risk=round(a_score, 2),
                    network_risk=round(n_score, 2),
                    combined_risk=round(combined, 2),
                    risk_category=cat,
                    contributing_factors=factors,
                    weights_used={"fraud": w_fraud, "aml": w_aml, "network": w_net},
                    explanation=f"Combined risk {combined:.1f}/100 ({cat}): " + "; ".join(factors),
                )
            )

    # Score accounts
    high_risk_accounts = 0
    for acc in accounts:
        f_score = max((f.risk_score for f in acc_fraud.get(acc.id, [])), default=0.0)
        a_score = max((f.risk_score for f in acc_aml.get(acc.id, [])), default=0.0)
        n_score = min(100.0, (pr.get(acc.id, 0.0) / max_pr) * 100.0)
        weighted = w_fraud * f_score + w_aml * a_score + w_net * n_score
        peak = max(f_score, a_score)
        combined = min(100.0, max(weighted, peak * 0.85 if peak >= 60.0 else weighted))
        cat = classify_risk(combined, thresholds)

        acc.risk_score = round(combined, 2)
        acc.risk_category = cat
        if cat in ("High", "Critical"):
            high_risk_accounts += 1

        if combined >= 30.0:
            factors = []
            if f_score > 0:
                factors.append(f"Fraud findings peak: {f_score:.1f}/100")
            if a_score > 0:
                factors.append(f"AML network/rule peak: {a_score:.1f}/100")
            factors.append(f"Graph PageRank centrality: {n_score:.1f}/100")
            assessments.append(
                RiskAssessment(
                    id=f"rsk_{uuid.uuid4().hex[:14]}",
                    bank_id=bank_id,
                    entity_type="account",
                    entity_id=acc.id,
                    fraud_risk=round(f_score, 2),
                    aml_risk=round(a_score, 2),
                    network_risk=round(n_score, 2),
                    combined_risk=round(combined, 2),
                    risk_category=cat,
                    contributing_factors=factors,
                    weights_used={"fraud": w_fraud, "aml": w_aml, "network": w_net},
                    explanation=f"Account {acc.account_number} combined risk {combined:.1f}/100 ({cat}).",
                )
            )

    # Generate Alerts from high-severity findings
    for f in findings:
        if f.risk_score >= 60.0:
            key = (f.engine, f.transaction_id, f.account_id, f.id)
            if key in existing_alert_keys:
                continue
            existing_alert_keys.add(key)
            sev = classify_risk(f.risk_score, thresholds)
            alerts_to_create.append(
                Alert(
                    id=f"alt_{uuid.uuid4().hex[:14]}",
                    bank_id=bank_id,
                    title=f"{f.engine.upper()}: {f.finding_type.replace('_', ' ').title()}",
                    category=f.engine,
                    severity=sev,
                    status="open",
                    risk_score=f.risk_score,
                    transaction_id=f.transaction_id,
                    account_id=f.account_id,
                    finding_id=f.id,
                    supporting_evidence={
                        "algorithm": f.algorithm,
                        "model_version": f.model_version,
                        "indicators": f.evidence_indicators,
                        "graph_path": f.graph_path,
                        "explanation": f.explanation,
                    },
                )
            )

    if assessments:
        db.bulk_save_objects(assessments)
    if alerts_to_create:
        db.bulk_save_objects(alerts_to_create)
    db.commit()

    return {
        "transactions_scored": len(txs),
        "flagged_transactions": flagged_tx_count,
        "accounts_scored": len(accounts),
        "high_risk_accounts": high_risk_accounts,
        "alerts_generated": len(alerts_to_create),
        "risk_assessments_recorded": len(assessments),
    }


def generate_xai_explanation(db: Session, bank_id: str, entity_type: str, entity_id: str) -> Dict[str, Any]:
    """Deterministic, evidence-grounded Explainable AI summary for a transaction or account."""
    if entity_type == "transaction":
        tx = db.query(Transaction).filter(Transaction.bank_id == bank_id, Transaction.id == entity_id).first()
        if not tx:
            return {"found": False}
        findings = db.query(DetectionFinding).filter(
            DetectionFinding.bank_id == bank_id, DetectionFinding.transaction_id == tx.id
        ).all()
        actions = [
            "Verify customer authorization and device fingerprint for this transfer.",
            "Inspect source and destination account 30-day behavioral baselines.",
        ]
        if any(f.engine == "aml" for f in findings):
            actions.append("Trace 3-hop fund flow in Transaction Graph Explorer to check for layering or cycles.")
        return {
            "found": True,
            "entity_type": "transaction",
            "entity_id": tx.id,
            "risk_score": tx.risk_score,
            "risk_category": tx.risk_category,
            "findings_count": len(findings),
            "contributing_factors": [
                {"engine": f.engine, "type": f.finding_type, "score": f.risk_score, "indicators": f.evidence_indicators, "shap": f.shap_values}
                for f in findings
            ],
            "recommended_actions": actions,
            "summary": (
                f"Transaction {tx.transaction_ref} (${tx.amount:,.2f} {tx.currency}) carries a "
                f"{tx.risk_category} risk score ({tx.risk_score:.1f}/100) based on {len(findings)} analytical finding(s)."
            ),
        }

    acc = db.query(Account).filter(Account.bank_id == bank_id, Account.id == entity_id).first()
    if not acc:
        return {"found": False}
    findings = db.query(DetectionFinding).filter(
        DetectionFinding.bank_id == bank_id, DetectionFinding.account_id == acc.id
    ).all()
    return {
        "found": True,
        "entity_type": "account",
        "entity_id": acc.id,
        "account_number": acc.account_number,
        "risk_score": acc.risk_score,
        "risk_category": acc.risk_category,
        "findings_count": len(findings),
        "contributing_factors": [
            {"engine": f.engine, "type": f.finding_type, "score": f.risk_score, "indicators": f.evidence_indicators}
            for f in findings
        ],
        "recommended_actions": [
            "Review KYC profile and beneficial ownership.",
            "Inspect multi-hop incoming and outgoing counterparties in Transaction Graph.",
            "Escalate to investigation case if patterns remain unexplained after customer outreach.",
        ],
        "summary": (
            f"Account {acc.account_number} is rated {acc.risk_category} ({acc.risk_score:.1f}/100) "
            f"with {len(findings)} associated detection indicator(s)."
        ),
    }
