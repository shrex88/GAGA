import json
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional
from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, UploadFile, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.deps import log_audit, require_permissions
from app.db.session import get_db
from app.detection.aml.aml_engine import run_aml_detection
from app.detection.fraud.fraud_engine import run_fraud_detection
from app.detection.unified_risk.risk_engine import run_unified_risk_scoring
from app.graph.graph_service import graph_service
from app.ingestion.csv_importer import import_csv_transactions, preview_csv_bytes
from app.ingestion.synthetic_generator import generate_synthetic_dataset
from app.models.entities import (
    Account,
    Alert,
    Dataset,
    DetectionFinding,
    InvestigationCase,
    Transaction,
    User,
)
from app.schemas.common import SeedSyntheticRequest

settings = get_settings()
router = APIRouter(tags=["Dashboard & Datasets"])


@router.get("/dashboard/summary")
def dashboard_summary(
    days: int = Query(default=30, ge=1, le=365),
    current_user: User = Depends(require_permissions("dashboard:read")),
    db: Session = Depends(get_db),
):
    bank_id = current_user.bank_id
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)

    tx_q = db.query(Transaction).filter(Transaction.bank_id == bank_id, Transaction.timestamp >= cutoff)
    total_transactions = tx_q.count()
    suspicious_transactions = tx_q.filter(Transaction.is_flagged == True).count()
    avg_risk = db.query(func.avg(Transaction.risk_score)).filter(
        Transaction.bank_id == bank_id, Transaction.timestamp >= cutoff
    ).scalar() or 0.0

    total_accounts = db.query(Account).filter(Account.bank_id == bank_id).count()
    high_risk_accounts = db.query(Account).filter(
        Account.bank_id == bank_id, Account.risk_category.in_(["High", "Critical"])
    ).count()

    fraud_alerts = db.query(Alert).filter(
        Alert.bank_id == bank_id, Alert.category == "fraud", Alert.status.in_(["open", "under_review", "escalated"])
    ).count()
    aml_alerts = db.query(Alert).filter(
        Alert.bank_id == bank_id, Alert.category == "aml", Alert.status.in_(["open", "under_review", "escalated"])
    ).count()
    active_cases = db.query(InvestigationCase).filter(
        InvestigationCase.bank_id == bank_id,
        InvestigationCase.status.in_(["Open", "Under Investigation", "Escalated"]),
    ).count()

    recent_suspicious = (
        db.query(Transaction)
        .filter(Transaction.bank_id == bank_id, Transaction.is_flagged == True)
        .order_by(Transaction.risk_score.desc(), Transaction.timestamp.desc())
        .limit(8)
        .all()
    )
    acc_map = {
        a.id: a.account_number
        for a in db.query(Account).filter(Account.bank_id == bank_id).all()
    }
    high_risk_acc_rows = (
        db.query(Account)
        .filter(Account.bank_id == bank_id)
        .order_by(Account.risk_score.desc())
        .limit(8)
        .all()
    )

    return {
        "kpis": {
            "total_transactions": total_transactions,
            "total_accounts": total_accounts,
            "suspicious_transactions": suspicious_transactions,
            "fraud_alerts": fraud_alerts,
            "aml_alerts": aml_alerts,
            "high_risk_accounts": high_risk_accounts,
            "active_cases": active_cases,
            "avg_risk_score": round(float(avg_risk), 2),
        },
        "recent_suspicious": [
            {
                "id": t.id,
                "transaction_ref": t.transaction_ref,
                "source_account": acc_map.get(t.source_account_id, t.source_account_id),
                "destination_account": acc_map.get(t.destination_account_id, t.destination_account_id),
                "amount": t.amount,
                "currency": t.currency,
                "timestamp": t.timestamp.isoformat(),
                "risk_score": t.risk_score,
                "risk_category": t.risk_category,
            }
            for t in recent_suspicious
        ],
        "high_risk_accounts_list": [
            {
                "id": a.id,
                "account_number": a.account_number,
                "account_type": a.account_type,
                "balance": a.balance,
                "risk_score": a.risk_score,
                "risk_category": a.risk_category,
            }
            for a in high_risk_acc_rows
        ],
        "graph_status": graph_service.status(),
        "is_synthetic_demo": True,
    }


@router.get("/dashboard/trends")
def dashboard_trends(
    days: int = Query(default=30, ge=1, le=365),
    current_user: User = Depends(require_permissions("dashboard:read")),
    db: Session = Depends(get_db),
):
    bank_id = current_user.bank_id
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    txs = (
        db.query(Transaction)
        .filter(Transaction.bank_id == bank_id, Transaction.timestamp >= cutoff)
        .order_by(Transaction.timestamp.asc())
        .all()
    )
    findings = db.query(DetectionFinding).filter(DetectionFinding.bank_id == bank_id).all()
    tx_engines: Dict[str, set] = {}
    for f in findings:
        if f.transaction_id:
            tx_engines.setdefault(f.transaction_id, set()).add(f.engine)

    buckets: Dict[str, Dict[str, Any]] = {}
    for t in txs:
        day_key = t.timestamp.strftime("%Y-%m-%d")
        if day_key not in buckets:
            buckets[day_key] = {"date": day_key, "volume": 0.0, "count": 0, "fraud_count": 0, "aml_count": 0}
        buckets[day_key]["volume"] += float(t.amount)
        buckets[day_key]["count"] += 1
        engs = tx_engines.get(t.id, set())
        if "fraud" in engs:
            buckets[day_key]["fraud_count"] += 1
        if "aml" in engs:
            buckets[day_key]["aml_count"] += 1

    series = sorted(buckets.values(), key=lambda x: x["date"])
    for item in series:
        item["volume"] = round(item["volume"], 2)
    return {"trends": series}


@router.get("/dashboard/risk-distribution")
def dashboard_risk_distribution(
    current_user: User = Depends(require_permissions("dashboard:read")),
    db: Session = Depends(get_db),
):
    bank_id = current_user.bank_id
    categories = ["Low", "Moderate", "High", "Critical"]
    tx_counts = {c: 0 for c in categories}
    acc_counts = {c: 0 for c in categories}

    for cat, cnt in (
        db.query(Transaction.risk_category, func.count(Transaction.id))
        .filter(Transaction.bank_id == bank_id)
        .group_by(Transaction.risk_category)
        .all()
    ):
        tx_counts[cat] = cnt

    for cat, cnt in (
        db.query(Account.risk_category, func.count(Account.id))
        .filter(Account.bank_id == bank_id)
        .group_by(Account.risk_category)
        .all()
    ):
        acc_counts[cat] = cnt

    return {
        "distribution": [
            {"category": c, "transactions": tx_counts[c], "accounts": acc_counts[c]}
            for c in categories
        ]
    }


@router.post("/datasets/preview")
async def preview_dataset_csv(
    file: UploadFile = File(...),
    current_user: User = Depends(require_permissions("datasets:write")),
):
    content = await file.read()
    max_bytes = settings.MAX_UPLOAD_MB * 1024 * 1024
    if len(content) > max_bytes:
        raise HTTPException(status_code=413, detail=f"File exceeds {settings.MAX_UPLOAD_MB} MB limit")
    return preview_csv_bytes(content)


@router.post("/datasets/upload", status_code=status.HTTP_201_CREATED)
async def upload_dataset_csv(
    request: Request,
    file: UploadFile = File(...),
    column_mapping: Optional[str] = Form(default=None),
    dataset_name: Optional[str] = Form(default=None),
    run_analysis: bool = Form(default=True),
    current_user: User = Depends(require_permissions("datasets:write")),
    db: Session = Depends(get_db),
):
    if not file.filename or not file.filename.lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail="Only .csv files are supported")

    content = await file.read()
    max_bytes = settings.MAX_UPLOAD_MB * 1024 * 1024
    if len(content) > max_bytes:
        raise HTTPException(status_code=413, detail=f"File exceeds {settings.MAX_UPLOAD_MB} MB limit")

    mapping_dict = None
    if column_mapping:
        try:
            mapping_dict = json.loads(column_mapping)
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid JSON in column_mapping")

    try:
        result = import_csv_transactions(
            db=db,
            bank_id=current_user.bank_id,
            filename=file.filename,
            content=content,
            user_id=current_user.id,
            column_mapping=mapping_dict,
            dataset_name=dataset_name,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    analysis_summary = None
    if run_analysis and result["accepted_rows"] > 0:
        analysis_summary = _run_full_pipeline(db, current_user.bank_id, result["dataset_id"])

    log_audit(
        db, current_user, "dataset.upload", "dataset", result["dataset_id"],
        {"accepted": result["accepted_rows"], "rejected": result["rejected_rows"]}, request=request
    )
    return {"import_result": result, "analysis": analysis_summary}


@router.post("/datasets/seed-synthetic", status_code=status.HTTP_201_CREATED)
def seed_synthetic(
    payload: SeedSyntheticRequest,
    request: Request,
    current_user: User = Depends(require_permissions("datasets:write")),
    db: Session = Depends(get_db),
):
    gen_res = generate_synthetic_dataset(
        db=db,
        bank_id=current_user.bank_id,
        count=payload.count,
        seed=payload.seed,
        user_id=current_user.id,
        name=payload.name,
    )
    analysis = None
    if payload.run_analysis:
        analysis = _run_full_pipeline(db, current_user.bank_id, gen_res["dataset_id"])

    log_audit(
        db, current_user, "dataset.seed_synthetic", "dataset", gen_res["dataset_id"],
        {"count": payload.count, "seed": payload.seed}, request=request
    )
    return {"dataset": gen_res, "analysis": analysis}


@router.get("/datasets")
def list_datasets(
    current_user: User = Depends(require_permissions("datasets:read")),
    db: Session = Depends(get_db),
):
    rows = (
        db.query(Dataset)
        .filter(Dataset.bank_id == current_user.bank_id)
        .order_by(Dataset.created_at.desc())
        .all()
    )
    return {
        "datasets": [
            {
                "id": d.id,
                "name": d.name,
                "filename": d.filename,
                "status": d.status,
                "total_rows": d.total_rows,
                "accepted_rows": d.accepted_rows,
                "rejected_rows": d.rejected_rows,
                "duplicate_rows": d.duplicate_rows,
                "is_synthetic": d.is_synthetic,
                "created_at": d.created_at.isoformat(),
                "analysed_at": d.analysed_at.isoformat() if d.analysed_at else None,
            }
            for d in rows
        ]
    }


@router.get("/datasets/{dataset_id}")
def get_dataset(
    dataset_id: str,
    current_user: User = Depends(require_permissions("datasets:read")),
    db: Session = Depends(get_db),
):
    d = db.query(Dataset).filter(Dataset.bank_id == current_user.bank_id, Dataset.id == dataset_id).first()
    if not d:
        raise HTTPException(status_code=404, detail="Dataset not found")
    return {
        "id": d.id,
        "name": d.name,
        "filename": d.filename,
        "status": d.status,
        "total_rows": d.total_rows,
        "accepted_rows": d.accepted_rows,
        "rejected_rows": d.rejected_rows,
        "duplicate_rows": d.duplicate_rows,
        "error_report": d.error_report,
        "column_mapping": d.column_mapping,
        "is_synthetic": d.is_synthetic,
        "created_at": d.created_at.isoformat(),
        "analysed_at": d.analysed_at.isoformat() if d.analysed_at else None,
    }


@router.post("/datasets/{dataset_id}/analyse")
def analyse_dataset(
    dataset_id: str,
    request: Request,
    current_user: User = Depends(require_permissions("datasets:write")),
    db: Session = Depends(get_db),
):
    d = db.query(Dataset).filter(Dataset.bank_id == current_user.bank_id, Dataset.id == dataset_id).first()
    if not d:
        raise HTTPException(status_code=404, detail="Dataset not found")

    res = _run_full_pipeline(db, current_user.bank_id, dataset_id)
    log_audit(db, current_user, "dataset.analyse", "dataset", dataset_id, res, request=request)
    return res


def _run_full_pipeline(db: Session, bank_id: str, dataset_id: Optional[str] = None) -> Dict[str, Any]:
    fraud_res = run_fraud_detection(db, bank_id)
    aml_res = run_aml_detection(db, bank_id)
    risk_res = run_unified_risk_scoring(db, bank_id)
    neo4j_sync = graph_service.sync_bank_graph_to_neo4j(db, bank_id)

    if dataset_id:
        ds = db.query(Dataset).filter(Dataset.id == dataset_id).first()
        if ds:
            ds.status = "analysed"
            ds.analysed_at = datetime.now(timezone.utc)
            db.commit()

    return {
        "fraud": fraud_res,
        "aml": aml_res,
        "unified_risk": risk_res,
        "graph_sync": neo4j_sync,
    }
