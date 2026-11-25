import os
import uuid
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.core.deps import log_audit, require_permissions
from app.db.session import get_db
from app.detection.unified_risk.risk_engine import run_unified_risk_scoring
from app.models.entities import (
    Account,
    Alert,
    AuditLog,
    Bank,
    CaseEvidence,
    CaseNote,
    InvestigationCase,
    User,
)
from app.reports.pdf_generator import REPORTS_DIR, generate_pdf_report
from app.schemas.common import (
    AlertAssignRequest,
    AlertUpdateRequest,
    BankConfigUpdateRequest,
    CaseCreateRequest,
    CaseEvidenceCreateRequest,
    CaseNoteCreateRequest,
    CaseUpdateRequest,
    ConvertAlertToCaseRequest,
    ReportGenerateRequest,
)

router = APIRouter(tags=["Alerts, Cases, Reports & Audit"])

# In-memory registry of generated report metadata (backed by actual PDF files on disk)
_GENERATED_REPORTS: Dict[str, Dict[str, Any]] = {}


@router.get("/alerts")
def list_alerts(
    severity: Optional[str] = Query(default=None),
    category: Optional[str] = Query(default=None),
    status_filter: Optional[str] = Query(default=None, alias="status"),
    current_user: User = Depends(require_permissions("alerts:read")),
    db: Session = Depends(get_db),
):
    q = db.query(Alert).filter(Alert.bank_id == current_user.bank_id)
    if severity:
        q = q.filter(Alert.severity == severity)
    if category:
        q = q.filter(Alert.category == category)
    if status_filter:
        q = q.filter(Alert.status == status_filter)
    rows = q.order_by(Alert.risk_score.desc(), Alert.created_at.desc()).all()

    user_map = {u.id: u.full_name for u in db.query(User).filter(User.bank_id == current_user.bank_id).all()}
    acc_map = {a.id: a.account_number for a in db.query(Account).filter(Account.bank_id == current_user.bank_id).all()}

    return {
        "alerts": [
            {
                "id": a.id,
                "title": a.title,
                "category": a.category,
                "severity": a.severity,
                "status": a.status,
                "risk_score": a.risk_score,
                "transaction_id": a.transaction_id,
                "account_id": a.account_id,
                "account_number": acc_map.get(a.account_id, a.account_id),
                "assigned_to": a.assigned_to,
                "assigned_to_name": user_map.get(a.assigned_to) if a.assigned_to else None,
                "resolution_reason": a.resolution_reason,
                "supporting_evidence": a.supporting_evidence,
                "created_at": a.created_at.isoformat(),
            }
            for a in rows
        ]
    }


@router.get("/alerts/{alert_id}")
def get_alert(
    alert_id: str,
    current_user: User = Depends(require_permissions("alerts:read")),
    db: Session = Depends(get_db),
):
    a = db.query(Alert).filter(Alert.bank_id == current_user.bank_id, Alert.id == alert_id).first()
    if not a:
        raise HTTPException(status_code=404, detail="Alert not found")
    return {
        "id": a.id,
        "title": a.title,
        "category": a.category,
        "severity": a.severity,
        "status": a.status,
        "risk_score": a.risk_score,
        "transaction_id": a.transaction_id,
        "account_id": a.account_id,
        "assigned_to": a.assigned_to,
        "resolution_reason": a.resolution_reason,
        "supporting_evidence": a.supporting_evidence,
        "created_at": a.created_at.isoformat(),
    }


@router.patch("/alerts/{alert_id}")
def update_alert(
    alert_id: str,
    payload: AlertUpdateRequest,
    request: Request,
    current_user: User = Depends(require_permissions("alerts:write")),
    db: Session = Depends(get_db),
):
    a = db.query(Alert).filter(Alert.bank_id == current_user.bank_id, Alert.id == alert_id).first()
    if not a:
        raise HTTPException(status_code=404, detail="Alert not found")

    if payload.status in ("resolved", "dismissed") and not (payload.resolution_reason and payload.resolution_reason.strip()):
        raise HTTPException(status_code=400, detail="A mandatory resolution_reason is required when resolving or dismissing an alert")

    if payload.status:
        a.status = payload.status
    if payload.resolution_reason is not None:
        a.resolution_reason = payload.resolution_reason.strip()
    db.commit()

    log_audit(
        db, current_user, "alert.update", "alert", a.id,
        {"status": a.status, "reason": a.resolution_reason}, request=request
    )
    return {"id": a.id, "status": a.status, "resolution_reason": a.resolution_reason}


@router.post("/alerts/{alert_id}/assign")
def assign_alert(
    alert_id: str,
    payload: AlertAssignRequest,
    request: Request,
    current_user: User = Depends(require_permissions("alerts:write")),
    db: Session = Depends(get_db),
):
    a = db.query(Alert).filter(Alert.bank_id == current_user.bank_id, Alert.id == alert_id).first()
    if not a:
        raise HTTPException(status_code=404, detail="Alert not found")
    assignee = db.query(User).filter(User.bank_id == current_user.bank_id, User.id == payload.assigned_to).first()
    if not assignee:
        raise HTTPException(status_code=404, detail="Assignee user not found in bank")
    a.assigned_to = assignee.id
    if a.status == "open":
        a.status = "under_review"
    db.commit()
    log_audit(db, current_user, "alert.assign", "alert", a.id, {"assigned_to": assignee.id}, request=request)
    return {"id": a.id, "assigned_to": assignee.id, "assigned_to_name": assignee.full_name, "status": a.status}


@router.post("/alerts/{alert_id}/convert-to-case", status_code=status.HTTP_201_CREATED)
def convert_alert_to_case(
    alert_id: str,
    payload: ConvertAlertToCaseRequest,
    request: Request,
    current_user: User = Depends(require_permissions("cases:write")),
    db: Session = Depends(get_db),
):
    a = db.query(Alert).filter(Alert.bank_id == current_user.bank_id, Alert.id == alert_id).first()
    if not a:
        raise HTTPException(status_code=404, detail="Alert not found")

    case_id = f"case_{uuid.uuid4().hex[:12]}"
    case_num = f"TF-{uuid.uuid4().hex[:6].upper()}"
    ev = a.supporting_evidence or {}

    case_obj = InvestigationCase(
        id=case_id,
        bank_id=current_user.bank_id,
        case_number=case_num,
        title=payload.title or f"Investigation: {a.title}",
        description=ev.get("explanation", "Escalated from alert for full investigation."),
        priority=payload.priority,
        status="Open",
        assigned_to=a.assigned_to or current_user.id,
        created_by=current_user.id,
        alert_id=a.id,
        related_account_ids=[a.account_id] if a.account_id else [],
        related_transaction_ids=[a.transaction_id] if a.transaction_id else [],
        ai_summary=ev.get("explanation", ""),
    )
    db.add(case_obj)
    db.flush()

    db.add(
        CaseEvidence(
            id=f"ev_{uuid.uuid4().hex[:12]}",
            case_id=case_id,
            evidence_type="alert_snapshot",
            title=f"Initial Alert Evidence ({a.category.upper()})",
            payload=ev,
            added_by=current_user.id,
        )
    )
    a.status = "escalated"
    db.commit()

    log_audit(db, current_user, "alert.convert_to_case", "case", case_id, {"alert_id": a.id}, request=request)
    return {"case_id": case_id, "case_number": case_num, "status": case_obj.status}


@router.post("/cases", status_code=status.HTTP_201_CREATED)
def create_case(
    payload: CaseCreateRequest,
    request: Request,
    current_user: User = Depends(require_permissions("cases:write")),
    db: Session = Depends(get_db),
):
    case_id = f"case_{uuid.uuid4().hex[:12]}"
    case_num = f"TF-{uuid.uuid4().hex[:6].upper()}"
    c = InvestigationCase(
        id=case_id,
        bank_id=current_user.bank_id,
        case_number=case_num,
        title=payload.title,
        description=payload.description,
        priority=payload.priority,
        status="Open",
        assigned_to=current_user.id,
        created_by=current_user.id,
        alert_id=payload.alert_id,
        related_account_ids=payload.related_account_ids,
        related_transaction_ids=payload.related_transaction_ids,
        ai_summary="Case created for analyst investigation. Algorithmic indicators require human review.",
    )
    db.add(c)
    db.commit()
    log_audit(db, current_user, "case.create", "case", case_id, {"case_number": case_num}, request=request)
    return {"id": c.id, "case_number": c.case_number, "status": c.status}


@router.get("/cases")
def list_cases(
    status_filter: Optional[str] = Query(default=None, alias="status"),
    current_user: User = Depends(require_permissions("cases:read")),
    db: Session = Depends(get_db),
):
    q = db.query(InvestigationCase).filter(InvestigationCase.bank_id == current_user.bank_id)
    if status_filter:
        q = q.filter(InvestigationCase.status == status_filter)
    rows = q.order_by(InvestigationCase.updated_at.desc()).all()
    user_map = {u.id: u.full_name for u in db.query(User).filter(User.bank_id == current_user.bank_id).all()}

    return {
        "cases": [
            {
                "id": c.id,
                "case_number": c.case_number,
                "title": c.title,
                "priority": c.priority,
                "status": c.status,
                "assigned_to": c.assigned_to,
                "assigned_to_name": user_map.get(c.assigned_to) if c.assigned_to else None,
                "related_account_ids": c.related_account_ids,
                "related_transaction_ids": c.related_transaction_ids,
                "created_at": c.created_at.isoformat(),
                "updated_at": c.updated_at.isoformat(),
            }
            for c in rows
        ]
    }


@router.get("/cases/{case_id}")
def get_case_detail(
    case_id: str,
    current_user: User = Depends(require_permissions("cases:read")),
    db: Session = Depends(get_db),
):
    c = db.query(InvestigationCase).filter(
        InvestigationCase.bank_id == current_user.bank_id, InvestigationCase.id == case_id
    ).first()
    if not c:
        raise HTTPException(status_code=404, detail="Case not found")

    notes = db.query(CaseNote).filter(CaseNote.case_id == c.id).order_by(CaseNote.created_at.asc()).all()
    evidences = db.query(CaseEvidence).filter(CaseEvidence.case_id == c.id).order_by(CaseEvidence.created_at.asc()).all()
    user_map = {u.id: u.full_name for u in db.query(User).filter(User.bank_id == current_user.bank_id).all()}

    return {
        "case": {
            "id": c.id,
            "case_number": c.case_number,
            "title": c.title,
            "description": c.description,
            "priority": c.priority,
            "status": c.status,
            "assigned_to": c.assigned_to,
            "assigned_to_name": user_map.get(c.assigned_to) if c.assigned_to else None,
            "related_account_ids": c.related_account_ids,
            "related_transaction_ids": c.related_transaction_ids,
            "ai_summary": c.ai_summary,
            "created_at": c.created_at.isoformat(),
            "updated_at": c.updated_at.isoformat(),
        },
        "notes": [
            {
                "id": n.id,
                "author_name": user_map.get(n.author_id, "Analyst"),
                "content": n.content,
                "is_conclusion": n.is_conclusion,
                "created_at": n.created_at.isoformat(),
            }
            for n in notes
        ],
        "evidence": [
            {
                "id": e.id,
                "evidence_type": e.evidence_type,
                "title": e.title,
                "payload": e.payload,
                "created_at": e.created_at.isoformat(),
            }
            for e in evidences
        ],
    }


@router.patch("/cases/{case_id}")
def update_case(
    case_id: str,
    payload: CaseUpdateRequest,
    request: Request,
    current_user: User = Depends(require_permissions("cases:write")),
    db: Session = Depends(get_db),
):
    c = db.query(InvestigationCase).filter(
        InvestigationCase.bank_id == current_user.bank_id, InvestigationCase.id == case_id
    ).first()
    if not c:
        raise HTTPException(status_code=404, detail="Case not found")
    valid_statuses = {"Open", "Under Investigation", "Escalated", "Resolved", "Closed"}
    if payload.status and payload.status not in valid_statuses:
        raise HTTPException(status_code=400, detail=f"Invalid status. Must be one of {sorted(valid_statuses)}")
    if payload.status:
        c.status = payload.status
    if payload.priority:
        c.priority = payload.priority
    if payload.assigned_to:
        c.assigned_to = payload.assigned_to
    if payload.title:
        c.title = payload.title
    if payload.description is not None:
        c.description = payload.description
    db.commit()
    log_audit(db, current_user, "case.update", "case", c.id, {"status": c.status, "priority": c.priority}, request=request)
    return {"id": c.id, "status": c.status, "priority": c.priority}


@router.post("/cases/{case_id}/notes", status_code=status.HTTP_201_CREATED)
def add_case_note(
    case_id: str,
    payload: CaseNoteCreateRequest,
    request: Request,
    current_user: User = Depends(require_permissions("cases:write")),
    db: Session = Depends(get_db),
):
    c = db.query(InvestigationCase).filter(
        InvestigationCase.bank_id == current_user.bank_id, InvestigationCase.id == case_id
    ).first()
    if not c:
        raise HTTPException(status_code=404, detail="Case not found")
    note = CaseNote(
        id=f"note_{uuid.uuid4().hex[:12]}",
        case_id=c.id,
        author_id=current_user.id,
        content=payload.content,
        is_conclusion=payload.is_conclusion,
    )
    db.add(note)
    db.commit()
    log_audit(db, current_user, "case.add_note", "case", c.id, {"is_conclusion": payload.is_conclusion}, request=request)
    return {"id": note.id, "content": note.content, "created_at": note.created_at.isoformat()}


@router.post("/cases/{case_id}/evidence", status_code=status.HTTP_201_CREATED)
def add_case_evidence(
    case_id: str,
    payload: CaseEvidenceCreateRequest,
    request: Request,
    current_user: User = Depends(require_permissions("cases:write")),
    db: Session = Depends(get_db),
):
    c = db.query(InvestigationCase).filter(
        InvestigationCase.bank_id == current_user.bank_id, InvestigationCase.id == case_id
    ).first()
    if not c:
        raise HTTPException(status_code=404, detail="Case not found")
    ev = CaseEvidence(
        id=f"ev_{uuid.uuid4().hex[:12]}",
        case_id=c.id,
        evidence_type=payload.evidence_type,
        title=payload.title,
        payload=payload.payload,
        added_by=current_user.id,
    )
    db.add(ev)
    db.commit()
    log_audit(db, current_user, "case.add_evidence", "case", c.id, {"title": payload.title}, request=request)
    return {"id": ev.id, "title": ev.title, "created_at": ev.created_at.isoformat()}


@router.post("/reports/generate", status_code=status.HTTP_201_CREATED)
def create_report(
    payload: ReportGenerateRequest,
    request: Request,
    current_user: User = Depends(require_permissions("reports:write")),
    db: Session = Depends(get_db),
):
    meta = generate_pdf_report(
        db=db,
        bank_id=current_user.bank_id,
        case_id=payload.case_id,
        account_id=payload.account_id,
        title=payload.title,
    )
    meta["bank_id"] = current_user.bank_id
    _GENERATED_REPORTS[meta["report_id"]] = meta
    log_audit(db, current_user, "report.generate", "report", meta["report_id"], {"filename": meta["filename"]}, request=request)
    return {
        "report_id": meta["report_id"],
        "filename": meta["filename"],
        "title": meta["title"],
        "generated_at": meta["generated_at"],
    }


@router.get("/reports")
def list_reports(current_user: User = Depends(require_permissions("reports:read"))):
    items = [
        {k: v for k, v in r.items() if k != "filepath"}
        for r in _GENERATED_REPORTS.values()
        if r.get("bank_id") == current_user.bank_id
    ]
    return {"reports": sorted(items, key=lambda x: x["generated_at"], reverse=True)}


@router.get("/reports/{report_id}/download")
def download_report(
    report_id: str,
    current_user: User = Depends(require_permissions("reports:read")),
):
    meta = _GENERATED_REPORTS.get(report_id)
    if not meta or meta.get("bank_id") != current_user.bank_id:
        raise HTTPException(status_code=404, detail="Report not found")
    if not os.path.exists(meta["filepath"]):
        raise HTTPException(status_code=404, detail="Report PDF file missing on disk")
    return FileResponse(meta["filepath"], media_type="application/pdf", filename=meta["filename"])


@router.get("/audit/logs")
def list_audit_logs(
    limit: int = Query(default=100, ge=1, le=500),
    current_user: User = Depends(require_permissions("audit:read")),
    db: Session = Depends(get_db),
):
    rows = (
        db.query(AuditLog)
        .filter(AuditLog.bank_id == current_user.bank_id)
        .order_by(AuditLog.created_at.desc())
        .limit(limit)
        .all()
    )
    return {
        "logs": [
            {
                "id": r.id,
                "user_email": r.user_email,
                "action": r.action,
                "resource_type": r.resource_type,
                "resource_id": r.resource_id,
                "details": r.details,
                "ip_address": r.ip_address,
                "created_at": r.created_at.isoformat(),
            }
            for r in rows
        ]
    }


@router.get("/settings/bank-config")
def get_bank_config(
    current_user: User = Depends(require_permissions("settings:read")),
    db: Session = Depends(get_db),
):
    bank = db.query(Bank).filter(Bank.id == current_user.bank_id).first()
    if not bank:
        raise HTTPException(status_code=404, detail="Bank not found")
    return {"bank_id": bank.id, "bank_name": bank.name, "config": bank.config}


@router.patch("/settings/bank-config")
def update_bank_config(
    payload: BankConfigUpdateRequest,
    request: Request,
    current_user: User = Depends(require_permissions("settings:write")),
    db: Session = Depends(get_db),
):
    bank = db.query(Bank).filter(Bank.id == current_user.bank_id).first()
    if not bank:
        raise HTTPException(status_code=404, detail="Bank not found")
    cfg = dict(bank.config or {})
    if payload.scoring_weights:
        cfg["scoring_weights"] = payload.scoring_weights
    if payload.risk_thresholds:
        cfg["risk_thresholds"] = payload.risk_thresholds
    if payload.aml_thresholds:
        cfg["aml_thresholds"] = payload.aml_thresholds
    bank.config = cfg
    db.commit()

    # Recompute unified risk scores with updated weights/thresholds
    run_unified_risk_scoring(db, current_user.bank_id)
    log_audit(db, current_user, "settings.update", "bank", bank.id, {"updated_keys": list(cfg.keys())}, request=request)
    return {"bank_id": bank.id, "config": bank.config}
