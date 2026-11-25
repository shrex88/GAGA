import os
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from reportlab.lib import colors
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
from sqlalchemy.orm import Session

from app.models.entities import (
    Account,
    CaseEvidence,
    CaseNote,
    DetectionFinding,
    InvestigationCase,
    Transaction,
)

REPORTS_DIR = os.path.join(os.getcwd(), "generated_reports")


def generate_pdf_report(
    db: Session,
    bank_id: str,
    case_id: Optional[str] = None,
    account_id: Optional[str] = None,
    title: Optional[str] = None,
) -> Dict[str, Any]:
    """Generate a downloadable PDF report using actual case, account, and transaction evidence."""
    os.makedirs(REPORTS_DIR, exist_ok=True)
    report_id = f"rep_{uuid.uuid4().hex[:12]}"
    filename = f"TRACEFLOW_Report_{report_id}.pdf"
    filepath = os.path.join(REPORTS_DIR, filename)

    case_obj = None
    if case_id:
        case_obj = db.query(InvestigationCase).filter(
            InvestigationCase.bank_id == bank_id, InvestigationCase.id == case_id
        ).first()

    acc_ids: List[str] = list(case_obj.related_account_ids) if (case_obj and case_obj.related_account_ids) else []
    tx_ids: List[str] = list(case_obj.related_transaction_ids) if (case_obj and case_obj.related_transaction_ids) else []
    if account_id and account_id not in acc_ids:
        acc_ids.append(account_id)

    accounts = db.query(Account).filter(Account.bank_id == bank_id, Account.id.in_(acc_ids)).all() if acc_ids else []
    txs = db.query(Transaction).filter(Transaction.bank_id == bank_id, Transaction.id.in_(tx_ids)).all() if tx_ids else []
    if not txs and acc_ids:
        txs = (
            db.query(Transaction)
            .filter(
                Transaction.bank_id == bank_id,
                (Transaction.source_account_id.in_(acc_ids)) | (Transaction.destination_account_id.in_(acc_ids)),
            )
            .order_by(Transaction.timestamp.desc())
            .limit(20)
            .all()
        )

    findings = []
    if acc_ids or tx_ids:
        q = db.query(DetectionFinding).filter(DetectionFinding.bank_id == bank_id)
        if tx_ids and acc_ids:
            q = q.filter((DetectionFinding.transaction_id.in_(tx_ids)) | (DetectionFinding.account_id.in_(acc_ids)))
        elif acc_ids:
            q = q.filter(DetectionFinding.account_id.in_(acc_ids))
        elif tx_ids:
            q = q.filter(DetectionFinding.transaction_id.in_(tx_ids))
        findings = q.limit(20).all()

    notes = db.query(CaseNote).filter(CaseNote.case_id == case_obj.id).order_by(CaseNote.created_at.asc()).all() if case_obj else []
    evidences = db.query(CaseEvidence).filter(CaseEvidence.case_id == case_obj.id).all() if case_obj else []

    doc = SimpleDocTemplate(filepath, pagesize=LETTER, rightMargin=40, leftMargin=40, topMargin=40, bottomMargin=40)
    styles = getSampleStyleSheet()
    h1 = ParagraphStyle("H1", parent=styles["Heading1"], textColor=colors.HexColor("#0f172a"), fontSize=18, spaceAfter=8)
    h2 = ParagraphStyle("H2", parent=styles["Heading2"], textColor=colors.HexColor("#1e3a8a"), fontSize=13, spaceBefore=12, spaceAfter=6)
    body = styles["BodyText"]

    story = []
    report_title = title or (f"Investigation Report: {case_obj.case_number} - {case_obj.title}" if case_obj else "TRACEFLOW AI Financial Crime Intelligence Report")
    story.append(Paragraph("TRACEFLOW AI — Financial Crime Intelligence Report", h1))
    story.append(Paragraph(f"<b>Report Title:</b> {report_title}", body))
    story.append(Paragraph(f"<b>Generated At:</b> {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}", body))
    story.append(Paragraph("<b>Notice:</b> Algorithmic indicators are statistical/graph risk signals and do not constitute legal proof of criminal activity.", body))
    story.append(Spacer(1, 10))

    if case_obj:
        story.append(Paragraph("1. Investigation Status & Overview", h2))
        story.append(Paragraph(f"<b>Case Number:</b> {case_obj.case_number} | <b>Status:</b> {case_obj.status} | <b>Priority:</b> {case_obj.priority}", body))
        story.append(Paragraph(f"<b>Description:</b> {case_obj.description or 'N/A'}", body))
        if case_obj.ai_summary:
            story.append(Paragraph(f"<b>Algorithmic AI Summary (Non-Legal):</b> {case_obj.ai_summary}", body))

    story.append(Paragraph("2. Monitored Accounts & Risk Summary", h2))
    if accounts:
        acc_data = [["Account Number", "Type", "Balance", "Risk Score", "Category"]]
        for a in accounts:
            acc_data.append([a.account_number, a.account_type, f"${a.balance:,.2f}", f"{a.risk_score:.1f}", a.risk_category])
        t = Table(acc_data, repeatRows=1)
        t.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1e293b")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
            ("FONTSIZE", (0, 0), (-1, -1), 9),
        ]))
        story.append(t)
    else:
        story.append(Paragraph("No specific accounts linked.", body))

    story.append(Paragraph("3. Transaction References", h2))
    if txs:
        tx_data = [["Transaction Ref", "Amount", "Currency", "Type", "Timestamp", "Risk"]]
        for tx in txs[:15]:
            tx_data.append([
                tx.transaction_ref,
                f"${tx.amount:,.2f}",
                tx.currency,
                tx.transaction_type,
                tx.timestamp.strftime("%Y-%m-%d %H:%M"),
                f"{tx.risk_score:.1f} ({tx.risk_category})",
            ])
        t2 = Table(tx_data, repeatRows=1)
        t2.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1e293b")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
            ("FONTSIZE", (0, 0), (-1, -1), 8),
        ]))
        story.append(t2)
    else:
        story.append(Paragraph("No transaction records linked.", body))

    story.append(Paragraph("4. Algorithmic Detection Findings & AI Explanation", h2))
    if findings:
        for f in findings[:10]:
            story.append(Paragraph(
                f"• <b>[{f.engine.upper()}] {f.finding_type.replace('_', ' ').title()}</b> "
                f"(Score: {f.risk_score:.1f}/100, Algorithm: {f.algorithm}): {f.explanation}",
                body,
            ))
            story.append(Spacer(1, 4))
    else:
        story.append(Paragraph("No algorithmic findings recorded for the selected scope.", body))

    story.append(Paragraph("5. Analyst Comments & Conclusions (Human Review)", h2))
    if notes:
        for n in notes:
            label = "ANALYST CONCLUSION" if n.is_conclusion else "INVESTIGATOR NOTE"
            story.append(Paragraph(f"• <b>[{label}]</b> ({n.created_at.strftime('%Y-%m-%d %H:%M')}): {n.content}", body))
            story.append(Spacer(1, 3))
    else:
        story.append(Paragraph("No analyst notes or conclusions recorded yet.", body))

    if evidences:
        story.append(Paragraph("6. Attached Case Evidence Items", h2))
        for ev in evidences:
            story.append(Paragraph(f"• <b>{ev.title}</b> ({ev.evidence_type})", body))

    doc.build(story)
    return {
        "report_id": report_id,
        "filename": filename,
        "filepath": filepath,
        "title": report_title,
        "case_id": case_id,
        "account_id": account_id,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
