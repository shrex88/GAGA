import csv
import os
import random
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple
from sqlalchemy.orm import Session

from app.models.entities import Account, Customer, Dataset, Transaction

FIRST_NAMES = [
    "James", "Olivia", "Liam", "Emma", "Noah", "Ava", "Ethan", "Sophia",
    "Mason", "Isabella", "Lucas", "Mia", "Logan", "Charlotte", "Daniel", "Amelia",
    "Henry", "Harper", "Sebastian", "Evelyn", "Mateo", "Aria", "Jack", "Chloe",
]
LAST_NAMES = [
    "Morgan", "Vance", "Patel", "Chen", "Mercer", "Sterling", "Kowalski", "Santos",
    "Nakamura", "Lindqvist", "Okafor", "Alvarez", "Bennett", "Hayes", "Fletcher", "Rossi",
]
COUNTRIES = ["US", "UK", "CA", "DE", "SG", "CH"]
CHANNELS = ["online", "mobile_app", "wire_desk", "api_gateway"]
CURRENCIES = ["USD", "USD", "USD", "USD", "EUR", "GBP"]


def generate_synthetic_dataset(
    db: Session,
    bank_id: str,
    count: int = 1000,
    seed: int = 42,
    user_id: Optional[str] = None,
    name: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Generate a reproducible synthetic banking dataset with normal activity and
    8 distinct financial-crime scenarios (plus normal baseline = 9 scenarios).
    All generated records are explicitly marked is_synthetic=True.
    """
    rng = random.Random(seed)
    now = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
    run_tag = uuid.uuid4().hex[:6].upper()

    dataset_id = f"ds_{uuid.uuid4().hex[:12]}"
    dataset_name = name or f"Synthetic Banking Dataset ({count} tx, seed={seed})"
    dataset = Dataset(
        id=dataset_id,
        bank_id=bank_id,
        data_source_id="ds_synthetic_001",
        name=dataset_name,
        filename=f"synthetic_{count}_seed{seed}.csv",
        status="imported",
        total_rows=count,
        accepted_rows=count,
        rejected_rows=0,
        duplicate_rows=0,
        is_synthetic=True,
        uploaded_by=user_id,
    )
    db.add(dataset)
    db.flush()

    # Create customers & accounts (scale with transaction count)
    num_accounts = max(45, min(250, count // 15))
    accounts: List[Account] = []
    for i in range(num_accounts):
        cust_ref = f"CUST-{run_tag}-{i+1:04d}"
        acc_num = f"ACC-{run_tag}-{1000 + i}"
        cust = Customer(
            id=f"cust_{uuid.uuid4().hex[:12]}",
            bank_id=bank_id,
            customer_ref=cust_ref,
            full_name=f"{rng.choice(FIRST_NAMES)} {rng.choice(LAST_NAMES)}",
            segment=rng.choice(["retail", "retail", "commercial", "private_wealth"]),
            kyc_status=rng.choice(["verified", "verified", "verified", "enhanced_due_diligence"]),
            country=rng.choice(COUNTRIES),
            is_synthetic=True,
        )
        db.add(cust)
        acc = Account(
            id=f"acc_{uuid.uuid4().hex[:12]}",
            bank_id=bank_id,
            customer_id=cust.id,
            account_number=acc_num,
            account_type=rng.choice(["checking", "checking", "savings", "business"]),
            currency="USD",
            balance=round(rng.uniform(5000.0, 250000.0), 2),
            status="active",
            is_synthetic=True,
        )
        db.add(acc)
        accounts.append(acc)
    db.flush()

    tx_rows: List[Transaction] = []
    tx_counter = 1

    def make_tx(
        src: Account,
        dst: Account,
        amount: float,
        ts: datetime,
        scenario: str,
        tx_type: str = "transfer",
        channel: Optional[str] = None,
        device_id: Optional[str] = None,
        beneficiary_ref: Optional[str] = None,
        currency: str = "USD",
    ) -> Transaction:
        nonlocal tx_counter
        tx_ref = f"TX-{run_tag}-{tx_counter:06d}"
        tx_counter += 1
        return Transaction(
            id=f"tx_{uuid.uuid4().hex[:14]}",
            bank_id=bank_id,
            dataset_id=dataset_id,
            transaction_ref=tx_ref,
            source_account_id=src.id,
            destination_account_id=dst.id,
            amount=round(amount, 2),
            currency=currency,
            timestamp=ts,
            transaction_type=tx_type,
            transaction_status="completed",
            channel=channel or rng.choice(CHANNELS),
            device_id=device_id or f"DEV-{rng.randint(100, 999)}",
            beneficiary_ref=beneficiary_ref or f"BEN-{dst.account_number}",
            location_ref=rng.choice(["NY-US", "LDN-UK", "SG-SG", "TOR-CA", "FRA-DE"]),
            metadata_json={"synthetic": True, "seed": seed},
            scenario_label=scenario,
            is_synthetic=True,
        )

    # 1. Circular transaction network (A -> B -> C -> D -> A)
    c_nodes = accounts[0:4]
    base_ts = now - timedelta(days=2, hours=6)
    cycle_amt = 46500.0
    for idx in range(4):
        src = c_nodes[idx]
        dst = c_nodes[(idx + 1) % 4]
        tx_rows.append(
            make_tx(
                src, dst,
                cycle_amt - idx * 350.0,
                base_ts + timedelta(minutes=25 * idx),
                scenario="circular_network",
                tx_type="wire",
                channel="wire_desk",
            )
        )

    # 2. Multi-hop layering-like sequence (5 hops)
    layer_nodes = accounts[4:10]
    layer_ts = now - timedelta(days=3, hours=10)
    layer_amt = 78000.0
    for idx in range(5):
        tx_rows.append(
            make_tx(
                layer_nodes[idx],
                layer_nodes[idx + 1],
                layer_amt * (0.97 ** idx),
                layer_ts + timedelta(minutes=40 * idx),
                scenario="multi_hop_layering",
                tx_type="wire",
            )
        )

    # 3. Potential structuring scenario (multiple tx just under $10,000 threshold)
    struct_src = accounts[10]
    struct_dsts = accounts[11:16]
    struct_ts = now - timedelta(days=1, hours=14)
    for idx, dst in enumerate(struct_dsts):
        tx_rows.append(
            make_tx(
                struct_src,
                dst,
                rng.uniform(9150.0, 9880.0),
                struct_ts + timedelta(hours=2 * idx),
                scenario="structuring",
                tx_type="ach",
            )
        )

    # 4. Rapid pass-through (mule account)
    mule_in_srcs = accounts[16:18]
    mule_hub = accounts[18]
    mule_out_dst = accounts[19]
    mule_ts = now - timedelta(days=1, hours=5)
    tx_rows.append(make_tx(mule_in_srcs[0], mule_hub, 22000.0, mule_ts, scenario="rapid_passthrough", tx_type="wire"))
    tx_rows.append(make_tx(mule_in_srcs[1], mule_hub, 18500.0, mule_ts + timedelta(minutes=10), scenario="rapid_passthrough", tx_type="wire"))
    tx_rows.append(make_tx(mule_hub, mule_out_dst, 39200.0, mule_ts + timedelta(minutes=28), scenario="rapid_passthrough", tx_type="wire"))

    # 5. Fan-in and fan-out activity
    fan_sources = accounts[20:26]
    fan_hub = accounts[26]
    fan_targets = accounts[27:33]
    fan_ts = now - timedelta(days=4, hours=3)
    for i, s in enumerate(fan_sources):
        tx_rows.append(make_tx(s, fan_hub, rng.uniform(4200.0, 7800.0), fan_ts + timedelta(minutes=12 * i), scenario="fan_in_fan_out", tx_type="transfer"))
    for i, t in enumerate(fan_targets):
        tx_rows.append(make_tx(fan_hub, t, rng.uniform(4000.0, 7500.0), fan_ts + timedelta(hours=2, minutes=15 * i), scenario="fan_in_fan_out", tx_type="transfer"))

    # 6. Unusual transaction amount anomalies (establish baseline first, then spike)
    anom_acc = accounts[33]
    for i in range(12):
        dst = accounts[34 + (i % 4)]
        tx_rows.append(make_tx(anom_acc, dst, rng.uniform(180.0, 620.0), now - timedelta(days=14 - i), scenario="normal", tx_type="payment"))
    # Spike!
    tx_rows.append(
        make_tx(
            anom_acc,
            accounts[38],
            64500.0,
            now - timedelta(hours=6),
            scenario="unusual_amount",
            tx_type="wire",
            channel="api_gateway",
            device_id="DEV-NEW-9991",
        )
    )

    # 7. Unusual transaction frequency burst
    burst_acc = accounts[39]
    burst_ts = now - timedelta(hours=9)
    for i in range(10):
        tx_rows.append(
            make_tx(
                burst_acc,
                accounts[40 + (i % 4)],
                rng.uniform(1400.0, 2900.0),
                burst_ts + timedelta(minutes=2 * i),
                scenario="unusual_frequency",
                tx_type="transfer",
                device_id="DEV-BURST-77",
            )
        )

    # 8. Suspicious beneficiary activity (offshore/high-risk beneficiary at odd hours)
    ben_src = accounts[44 % len(accounts)]
    ben_dst = accounts[0]
    odd_ts = (now - timedelta(days=1)).replace(hour=2, minute=15)
    for i in range(3):
        tx_rows.append(
            make_tx(
                ben_src,
                ben_dst,
                rng.uniform(14500.0, 19800.0),
                odd_ts + timedelta(minutes=18 * i),
                scenario="suspicious_beneficiary",
                tx_type="wire",
                beneficiary_ref=f"OFFSHORE-SHELL-{run_tag}-01",
                device_id="DEV-UNRECOGNIZED-01",
            )
        )

    # 9. Fill remaining count with normal legitimate transactions
    remaining = max(0, count - len(tx_rows))
    for _ in range(remaining):
        src, dst = rng.sample(accounts, 2)
        days_ago = rng.uniform(0.1, 28.0)
        ts = now - timedelta(days=days_ago)
        # Keep normal amounts mostly realistic log-normal-ish
        amt = round(min(4800.0, max(15.0, rng.lognormvariate(5.6, 0.85))), 2)
        tx_rows.append(
            make_tx(
                src,
                dst,
                amt,
                ts,
                scenario="normal",
                tx_type=rng.choice(["payment", "transfer", "ach", "card_settlement"]),
                currency=rng.choice(CURRENCIES),
            )
        )

    db.bulk_save_objects(tx_rows)
    db.commit()

    return {
        "dataset_id": dataset_id,
        "name": dataset_name,
        "accounts_created": len(accounts),
        "transactions_created": len(tx_rows),
        "seed": seed,
        "is_synthetic": True,
    }


def export_sample_csv(filepath: str, count: int = 1000, seed: int = 42) -> str:
    """Write a standalone synthetic CSV file for testing CSV upload workflows."""
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    rng = random.Random(seed)
    now = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
    accs = [f"CSV-ACC-{1000 + i}" for i in range(60)]

    with open(filepath, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([
            "transaction_id",
            "source_account_id",
            "destination_account_id",
            "amount",
            "currency",
            "timestamp",
            "transaction_type",
            "transaction_status",
            "channel",
            "beneficiary_ref",
        ])
        for i in range(count):
            src, dst = rng.sample(accs, 2)
            ts = (now - timedelta(hours=rng.randint(1, 500))).isoformat()
            amt = round(min(4500.0, max(20.0, rng.lognormvariate(5.5, 0.85))), 2)
            # Inject a few anomalies & cycle in the CSV sample
            if i in (10, 11, 12, 13):
                src, dst = accs[i - 10], accs[(i - 9) % 4]
                amt = 42000.0
                ts = (now - timedelta(hours=12) + timedelta(minutes=(i - 10) * 15)).isoformat()
            elif i == 50:
                amt = 72000.0
            writer.writerow([
                f"CSV-TX-{seed}-{i+1:05d}",
                src,
                dst,
                amt,
                "USD",
                ts,
                rng.choice(["transfer", "wire", "ach", "payment"]),
                "completed",
                rng.choice(["online", "mobile_app", "wire_desk"]),
                f"BEN-{dst}",
            ])
    return filepath
