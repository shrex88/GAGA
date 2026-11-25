from datetime import datetime
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.core.deps import log_audit, require_permissions
from app.db.session import get_db
from app.detection.aml.aml_engine import run_aml_detection
from app.detection.fraud.fraud_engine import run_fraud_detection
from app.detection.unified_risk.risk_engine import generate_xai_explanation, run_unified_risk_scoring
from app.graph.graph_service import graph_service
from app.models.entities import Account, DetectionFinding, RiskAssessment, Transaction, User

router = APIRouter(tags=["Transactions, Detection & Graph"])


@router.get("/transactions")
def list_transactions(
    search: Optional[str] = Query(default=None),
    status_filter: Optional[str] = Query(default=None, alias="status"),
    risk_category: Optional[str] = Query(default=None),
    min_amount: Optional[float] = Query(default=None),
    max_amount: Optional[float] = Query(default=None),
    start_date: Optional[datetime] = Query(default=None),
    end_date: Optional[datetime] = Query(default=None),
    sort_by: str = Query(default="timestamp"),
    sort_dir: str = Query(default="desc"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=200),
    current_user: User = Depends(require_permissions("transactions:read")),
    db: Session = Depends(get_db),
):
    bank_id = current_user.bank_id
    acc_map = {
        a.id: a.account_number
        for a in db.query(Account).filter(Account.bank_id == bank_id).all()
    }
    rev_acc = {v: k for k, v in acc_map.items()}

    q = db.query(Transaction).filter(Transaction.bank_id == bank_id)

    if search:
        s = search.strip()
        matching_acc_ids = [aid for anum, aid in rev_acc.items() if s.lower() in anum.lower()]
        conds = [Transaction.transaction_ref.ilike(f"%{s}%"), Transaction.id.ilike(f"%{s}%")]
        if matching_acc_ids:
            conds.append(Transaction.source_account_id.in_(matching_acc_ids))
            conds.append(Transaction.destination_account_id.in_(matching_acc_ids))
        q = q.filter(or_(*conds))

    if status_filter:
        q = q.filter(Transaction.transaction_status == status_filter)
    if risk_category:
        q = q.filter(Transaction.risk_category == risk_category)
    if min_amount is not None:
        q = q.filter(Transaction.amount >= min_amount)
    if max_amount is not None:
        q = q.filter(Transaction.amount <= max_amount)
    if start_date:
        q = q.filter(Transaction.timestamp >= start_date)
    if end_date:
        q = q.filter(Transaction.timestamp <= end_date)

    sort_col = {
        "timestamp": Transaction.timestamp,
        "amount": Transaction.amount,
        "risk_score": Transaction.risk_score,
    }.get(sort_by, Transaction.timestamp)
    q = q.order_by(sort_col.desc() if sort_dir == "desc" else sort_col.asc())

    total = q.count()
    items = q.offset((page - 1) * page_size).limit(page_size).all()

    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "items": [
            {
                "id": t.id,
                "transaction_ref": t.transaction_ref,
                "source_account_id": t.source_account_id,
                "source_account": acc_map.get(t.source_account_id, t.source_account_id),
                "destination_account_id": t.destination_account_id,
                "destination_account": acc_map.get(t.destination_account_id, t.destination_account_id),
                "amount": t.amount,
                "currency": t.currency,
                "timestamp": t.timestamp.isoformat(),
                "transaction_type": t.transaction_type,
                "transaction_status": t.transaction_status,
                "channel": t.channel,
                "risk_score": t.risk_score,
                "risk_category": t.risk_category,
                "is_flagged": t.is_flagged,
                "is_synthetic": t.is_synthetic,
            }
            for t in items
        ],
    }


@router.get("/transactions/{tx_id}")
def get_transaction_detail(
    tx_id: str,
    current_user: User = Depends(require_permissions("transactions:read")),
    db: Session = Depends(get_db),
):
    bank_id = current_user.bank_id
    t = db.query(Transaction).filter(
        Transaction.bank_id == bank_id,
        (Transaction.id == tx_id) | (Transaction.transaction_ref == tx_id),
    ).first()
    if not t:
        raise HTTPException(status_code=404, detail="Transaction not found")

    src = db.query(Account).filter(Account.id == t.source_account_id).first()
    dst = db.query(Account).filter(Account.id == t.destination_account_id).first()
    findings = db.query(DetectionFinding).filter(
        DetectionFinding.bank_id == bank_id, DetectionFinding.transaction_id == t.id
    ).all()
    xai = generate_xai_explanation(db, bank_id, "transaction", t.id)

    return {
        "transaction": {
            "id": t.id,
            "transaction_ref": t.transaction_ref,
            "source_account_id": t.source_account_id,
            "source_account": src.account_number if src else t.source_account_id,
            "destination_account_id": t.destination_account_id,
            "destination_account": dst.account_number if dst else t.destination_account_id,
            "amount": t.amount,
            "currency": t.currency,
            "timestamp": t.timestamp.isoformat(),
            "transaction_type": t.transaction_type,
            "transaction_status": t.transaction_status,
            "channel": t.channel,
            "beneficiary_ref": t.beneficiary_ref,
            "location_ref": t.location_ref,
            "risk_score": t.risk_score,
            "risk_category": t.risk_category,
            "is_flagged": t.is_flagged,
            "is_synthetic": t.is_synthetic,
        },
        "findings": [
            {
                "id": f.id,
                "engine": f.engine,
                "finding_type": f.finding_type,
                "algorithm": f.algorithm,
                "model_version": f.model_version,
                "risk_score": f.risk_score,
                "evidence_indicators": f.evidence_indicators,
                "explanation": f.explanation,
                "shap_values": f.shap_values,
                "detected_at": f.detected_at.isoformat(),
            }
            for f in findings
        ],
        "xai_explanation": xai,
    }


@router.get("/transactions/{tx_id}/related")
def get_related_transactions(
    tx_id: str,
    current_user: User = Depends(require_permissions("transactions:read")),
    db: Session = Depends(get_db),
):
    bank_id = current_user.bank_id
    t = db.query(Transaction).filter(Transaction.bank_id == bank_id, Transaction.id == tx_id).first()
    if not t:
        raise HTTPException(status_code=404, detail="Transaction not found")
    related = (
        db.query(Transaction)
        .filter(
            Transaction.bank_id == bank_id,
            Transaction.id != t.id,
            or_(
                Transaction.source_account_id == t.source_account_id,
                Transaction.destination_account_id == t.destination_account_id,
                Transaction.source_account_id == t.destination_account_id,
            ),
        )
        .order_by(Transaction.timestamp.desc())
        .limit(20)
        .all()
    )
    return {
        "related_transactions": [
            {
                "id": r.id,
                "transaction_ref": r.transaction_ref,
                "amount": r.amount,
                "currency": r.currency,
                "timestamp": r.timestamp.isoformat(),
                "risk_score": r.risk_score,
                "risk_category": r.risk_category,
            }
            for r in related
        ]
    }


@router.get("/fraud/findings")
def list_fraud_findings(
    current_user: User = Depends(require_permissions("fraud:read")),
    db: Session = Depends(get_db),
):
    return _list_findings_by_engine(db, current_user.bank_id, "fraud")


@router.get("/fraud/findings/{finding_id}")
def get_fraud_finding(
    finding_id: str,
    current_user: User = Depends(require_permissions("fraud:read")),
    db: Session = Depends(get_db),
):
    return _get_finding_detail(db, current_user.bank_id, "fraud", finding_id)


@router.post("/fraud/analyse")
def trigger_fraud_analysis(
    request: Request,
    current_user: User = Depends(require_permissions("fraud:analyse")),
    db: Session = Depends(get_db),
):
    res = run_fraud_detection(db, current_user.bank_id)
    risk_res = run_unified_risk_scoring(db, current_user.bank_id)
    log_audit(db, current_user, "fraud.analyse", "engine", "fraud", res, request=request)
    return {"fraud": res, "unified_risk": risk_res}


@router.get("/aml/findings")
def list_aml_findings(
    current_user: User = Depends(require_permissions("aml:read")),
    db: Session = Depends(get_db),
):
    return _list_findings_by_engine(db, current_user.bank_id, "aml")


@router.get("/aml/findings/{finding_id}")
def get_aml_finding(
    finding_id: str,
    current_user: User = Depends(require_permissions("aml:read")),
    db: Session = Depends(get_db),
):
    return _get_finding_detail(db, current_user.bank_id, "aml", finding_id)


@router.post("/aml/analyse")
def trigger_aml_analysis(
    request: Request,
    current_user: User = Depends(require_permissions("aml:analyse")),
    db: Session = Depends(get_db),
):
    res = run_aml_detection(db, current_user.bank_id)
    risk_res = run_unified_risk_scoring(db, current_user.bank_id)
    log_audit(db, current_user, "aml.analyse", "engine", "aml", res, request=request)
    return {"aml": res, "unified_risk": risk_res}


def _list_findings_by_engine(db: Session, bank_id: str, engine: str):
    acc_map = {a.id: a.account_number for a in db.query(Account).filter(Account.bank_id == bank_id).all()}
    rows = (
        db.query(DetectionFinding)
        .filter(DetectionFinding.bank_id == bank_id, DetectionFinding.engine == engine)
        .order_by(DetectionFinding.risk_score.desc(), DetectionFinding.detected_at.desc())
        .all()
    )
    return {
        "findings": [
            {
                "id": f.id,
                "engine": f.engine,
                "finding_type": f.finding_type,
                "transaction_id": f.transaction_id,
                "account_id": f.account_id,
                "account_number": acc_map.get(f.account_id, f.account_id),
                "algorithm": f.algorithm,
                "model_version": f.model_version,
                "risk_score": f.risk_score,
                "evidence_indicators": f.evidence_indicators,
                "graph_path": [acc_map.get(a, a) for a in (f.graph_path or [])],
                "explanation": f.explanation,
                "shap_values": f.shap_values,
                "detected_at": f.detected_at.isoformat(),
            }
            for f in rows
        ]
    }


def _get_finding_detail(db: Session, bank_id: str, engine: str, finding_id: str):
    f = db.query(DetectionFinding).filter(
        DetectionFinding.bank_id == bank_id,
        DetectionFinding.engine == engine,
        DetectionFinding.id == finding_id,
    ).first()
    if not f:
        raise HTTPException(status_code=404, detail="Finding not found")
    return {
        "id": f.id,
        "engine": f.engine,
        "finding_type": f.finding_type,
        "transaction_id": f.transaction_id,
        "account_id": f.account_id,
        "algorithm": f.algorithm,
        "model_version": f.model_version,
        "risk_score": f.risk_score,
        "evidence_indicators": f.evidence_indicators,
        "graph_path": f.graph_path,
        "explanation": f.explanation,
        "shap_values": f.shap_values,
        "detected_at": f.detected_at.isoformat(),
    }


@router.get("/graph/account/{account_id}")
def get_account_graph(
    account_id: str,
    hops: int = Query(default=2, ge=1, le=5),
    min_amount: Optional[float] = Query(default=None),
    start_date: Optional[datetime] = Query(default=None),
    end_date: Optional[datetime] = Query(default=None),
    current_user: User = Depends(require_permissions("graph:read")),
    db: Session = Depends(get_db),
):
    res = graph_service.get_account_network(
        db, current_user.bank_id, account_id, hops=hops, min_amount=min_amount, start_date=start_date, end_date=end_date
    )
    if not res["found"]:
        raise HTTPException(status_code=404, detail="Account not found in bank scope")
    return res


@router.get("/graph/trace/{account_id}")
def trace_account_funds(
    account_id: str,
    max_hops: int = Query(default=4, ge=2, le=5),
    current_user: User = Depends(require_permissions("graph:read")),
    db: Session = Depends(get_db),
):
    res = graph_service.trace_fund_paths(db, current_user.bank_id, account_id, max_hops=max_hops)
    if not res["found"]:
        raise HTTPException(status_code=404, detail="Account not found")
    return res


@router.get("/graph/network/{account_id}")
def get_network_alias(
    account_id: str,
    hops: int = Query(default=3, ge=1, le=5),
    current_user: User = Depends(require_permissions("graph:read")),
    db: Session = Depends(get_db),
):
    res = graph_service.get_account_network(db, current_user.bank_id, account_id, hops=hops)
    if not res["found"]:
        raise HTTPException(status_code=404, detail="Account not found")
    return res


@router.get("/risk/accounts")
def list_account_risks(
    current_user: User = Depends(require_permissions("risk:read")),
    db: Session = Depends(get_db),
):
    bank_id = current_user.bank_id
    accounts = db.query(Account).filter(Account.bank_id == bank_id).order_by(Account.risk_score.desc()).limit(100).all()
    latest_assess = {}
    for ra in (
        db.query(RiskAssessment)
        .filter(RiskAssessment.bank_id == bank_id, RiskAssessment.entity_type == "account")
        .order_by(RiskAssessment.assessed_at.desc())
        .all()
    ):
        if ra.entity_id not in latest_assess:
            latest_assess[ra.entity_id] = ra

    return {
        "accounts": [
            {
                "id": a.id,
                "account_number": a.account_number,
                "account_type": a.account_type,
                "balance": a.balance,
                "risk_score": a.risk_score,
                "risk_category": a.risk_category,
                "fraud_risk": latest_assess[a.id].fraud_risk if a.id in latest_assess else 0.0,
                "aml_risk": latest_assess[a.id].aml_risk if a.id in latest_assess else 0.0,
                "network_risk": latest_assess[a.id].network_risk if a.id in latest_assess else 0.0,
                "contributing_factors": latest_assess[a.id].contributing_factors if a.id in latest_assess else [],
            }
            for a in accounts
        ]
    }


@router.get("/risk/transactions")
def list_transaction_risks(
    current_user: User = Depends(require_permissions("risk:read")),
    db: Session = Depends(get_db),
):
    bank_id = current_user.bank_id
    txs = db.query(Transaction).filter(Transaction.bank_id == bank_id).order_by(Transaction.risk_score.desc()).limit(100).all()
    return {
        "transactions": [
            {
                "id": t.id,
                "transaction_ref": t.transaction_ref,
                "amount": t.amount,
                "currency": t.currency,
                "risk_score": t.risk_score,
                "risk_category": t.risk_category,
                "timestamp": t.timestamp.isoformat(),
            }
            for t in txs
        ]
    }


@router.get("/risk/summary")
def get_risk_summary(
    current_user: User = Depends(require_permissions("risk:read")),
    db: Session = Depends(get_db),
):
    bank_id = current_user.bank_id
    total_acc = db.query(Account).filter(Account.bank_id == bank_id).count()
    critical_acc = db.query(Account).filter(Account.bank_id == bank_id, Account.risk_category == "Critical").count()
    high_acc = db.query(Account).filter(Account.bank_id == bank_id, Account.risk_category == "High").count()
    history = (
        db.query(RiskAssessment)
        .filter(RiskAssessment.bank_id == bank_id)
        .order_by(RiskAssessment.assessed_at.desc())
        .limit(20)
        .all()
    )
    return {
        "total_accounts": total_acc,
        "critical_accounts": critical_acc,
        "high_accounts": high_acc,
        "recent_assessments": [
            {
                "id": h.id,
                "entity_type": h.entity_type,
                "entity_id": h.entity_id,
                "fraud_risk": h.fraud_risk,
                "aml_risk": h.aml_risk,
                "network_risk": h.network_risk,
                "combined_risk": h.combined_risk,
                "risk_category": h.risk_category,
                "contributing_factors": h.contributing_factors,
                "assessed_at": h.assessed_at.isoformat(),
            }
            for h in history
        ],
    }
