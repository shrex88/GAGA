import csv
import io
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from dateutil import parser as date_parser
from sqlalchemy.orm import Session

from app.models.entities import Account, Customer, Dataset, Transaction

VALID_CURRENCIES = {"USD", "EUR", "GBP", "CAD", "SGD", "CHF", "AUD", "JPY", "INR"}
REQUIRED_FIELDS = [
    "transaction_id",
    "source_account_id",
    "destination_account_id",
    "amount",
    "currency",
    "timestamp",
    "transaction_type",
    "transaction_status",
]


def preview_csv_bytes(content: bytes, limit: int = 10) -> Dict[str, Any]:
    """Parse CSV header and sample rows for preview and column mapping."""
    text = content.decode("utf-8-sig", errors="replace")
    reader = csv.DictReader(io.StringIO(text))
    headers = reader.fieldnames or []
    rows = []
    total = 0
    for row in reader:
        total += 1
        if len(rows) < limit:
            rows.append(row)
    return {
        "headers": headers,
        "preview_rows": rows,
        "total_rows_detected": total,
        "required_fields": REQUIRED_FIELDS,
    }


def import_csv_transactions(
    db: Session,
    bank_id: str,
    filename: str,
    content: bytes,
    user_id: Optional[str] = None,
    column_mapping: Optional[Dict[str, str]] = None,
    dataset_name: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Validate and import transactions from CSV bytes.
    Never silently discards rejected rows; returns a full validation & error report.
    """
    text = content.decode("utf-8-sig", errors="replace")
    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames:
        raise ValueError("CSV file has no header row.")

    mapping = column_mapping or {}

    def get_col(row: Dict[str, Any], canonical: str) -> Optional[str]:
        mapped_name = mapping.get(canonical, canonical)
        val = row.get(mapped_name)
        return val.strip() if isinstance(val, str) else val

    dataset_id = f"ds_{uuid.uuid4().hex[:12]}"
    dataset = Dataset(
        id=dataset_id,
        bank_id=bank_id,
        data_source_id="ds_csv_001",
        name=dataset_name or f"CSV Import: {filename}",
        filename=filename,
        status="validated",
        column_mapping=mapping,
        is_synthetic=True,
        uploaded_by=user_id,
    )
    db.add(dataset)
    db.flush()

    # Preload existing accounts and transaction refs for this bank
    existing_accounts = {
        a.account_number: a
        for a in db.query(Account).filter(Account.bank_id == bank_id).all()
    }
    existing_tx_refs = {
        row[0]
        for row in db.query(Transaction.transaction_ref)
        .filter(Transaction.bank_id == bank_id)
        .all()
    }

    def get_or_create_account(acc_num: str, currency: str) -> Account:
        if acc_num in existing_accounts:
            return existing_accounts[acc_num]
        cust = Customer(
            id=f"cust_{uuid.uuid4().hex[:12]}",
            bank_id=bank_id,
            customer_ref=f"CUST-{acc_num}",
            full_name=f"Imported Holder ({acc_num})",
            segment="retail",
            kyc_status="pending_review",
            country="US",
            is_synthetic=True,
        )
        db.add(cust)
        acc = Account(
            id=f"acc_{uuid.uuid4().hex[:12]}",
            bank_id=bank_id,
            customer_id=cust.id,
            account_number=acc_num,
            account_type="checking",
            currency=currency,
            balance=25000.0,
            status="active",
            is_synthetic=True,
        )
        db.add(acc)
        existing_accounts[acc_num] = acc
        return acc

    total_rows = 0
    accepted_rows = 0
    rejected_rows = 0
    duplicate_rows = 0
    error_report: List[Dict[str, Any]] = []
    seen_in_file = set()
    to_insert: List[Transaction] = []

    for idx, row in enumerate(reader, start=2):
        total_rows += 1
        tx_ref = get_col(row, "transaction_id")
        src_num = get_col(row, "source_account_id")
        dst_num = get_col(row, "destination_account_id")
        amt_raw = get_col(row, "amount")
        currency = (get_col(row, "currency") or "").upper()
        ts_raw = get_col(row, "timestamp")
        tx_type = (get_col(row, "transaction_type") or "transfer").lower()
        tx_status = (get_col(row, "transaction_status") or "completed").lower()

        if not tx_ref or not src_num or not dst_num or not amt_raw or not ts_raw:
            rejected_rows += 1
            error_report.append({"row": idx, "transaction_id": tx_ref, "error": "Missing required field(s)"})
            continue

        if src_num == dst_num:
            rejected_rows += 1
            error_report.append({"row": idx, "transaction_id": tx_ref, "error": "Source and destination accounts cannot be identical"})
            continue

        if tx_ref in existing_tx_refs or tx_ref in seen_in_file:
            duplicate_rows += 1
            rejected_rows += 1
            error_report.append({"row": idx, "transaction_id": tx_ref, "error": "Duplicate transaction_id"})
            continue

        try:
            amount = float(amt_raw)
        except ValueError:
            rejected_rows += 1
            error_report.append({"row": idx, "transaction_id": tx_ref, "error": f"Invalid numeric amount: {amt_raw}"})
            continue

        if amount <= 0:
            rejected_rows += 1
            error_report.append({"row": idx, "transaction_id": tx_ref, "error": f"Non-positive amount rejected: {amount}"})
            continue

        if currency not in VALID_CURRENCIES:
            rejected_rows += 1
            error_report.append({"row": idx, "transaction_id": tx_ref, "error": f"Unsupported currency: {currency}"})
            continue

        try:
            ts = date_parser.parse(ts_raw)
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
        except Exception:
            rejected_rows += 1
            error_report.append({"row": idx, "transaction_id": tx_ref, "error": f"Invalid timestamp format: {ts_raw}"})
            continue

        seen_in_file.add(tx_ref)
        src_acc = get_or_create_account(src_num, currency)
        dst_acc = get_or_create_account(dst_num, currency)

        to_insert.append(
            Transaction(
                id=f"tx_{uuid.uuid4().hex[:14]}",
                bank_id=bank_id,
                dataset_id=dataset_id,
                transaction_ref=tx_ref,
                source_account_id=src_acc.id,
                destination_account_id=dst_acc.id,
                amount=round(amount, 2),
                currency=currency,
                timestamp=ts,
                transaction_type=tx_type,
                transaction_status=tx_status,
                channel=get_col(row, "channel") or "csv_batch",
                device_id=get_col(row, "device_id"),
                beneficiary_ref=get_col(row, "beneficiary_ref") or f"BEN-{dst_num}",
                location_ref=get_col(row, "location_ref"),
                metadata_json={"imported_from": filename},
                is_synthetic=True,
            )
        )
        accepted_rows += 1

    db.flush()
    if to_insert:
        db.bulk_save_objects(to_insert)

    dataset.total_rows = total_rows
    dataset.accepted_rows = accepted_rows
    dataset.rejected_rows = rejected_rows
    dataset.duplicate_rows = duplicate_rows
    dataset.error_report = error_report[:500]  # cap stored error rows
    dataset.status = "imported" if accepted_rows > 0 else "failed"
    db.commit()

    return {
        "dataset_id": dataset_id,
        "filename": filename,
        "status": dataset.status,
        "total_rows": total_rows,
        "accepted_rows": accepted_rows,
        "rejected_rows": rejected_rows,
        "duplicate_rows": duplicate_rows,
        "error_report": error_report[:100],
    }
