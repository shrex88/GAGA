import uuid
from collections import defaultdict
from datetime import timedelta
from typing import Any, Dict, List
import networkx as nx
from sqlalchemy.orm import Session

from app.graph.graph_service import graph_service
from app.models.entities import Account, Bank, DetectionFinding, Transaction


def run_aml_detection(db: Session, bank_id: str) -> Dict[str, Any]:
    """
    Execute the AML Detection Pipeline using NetworkX graph analytics & configurable rules:
    A. Circular transaction flows (cycles up to max_cycle_hops)
    B. Multi-hop layering-like sequences (3-5 hop chains with sequential timestamps)
    C. Potential structuring indicators (multiple transfers just below reporting threshold)
    D. Rapid pass-through / mule-account indicators
    E. Unusual fan-in / fan-out network hubs

    All findings represent risk indicators warranting investigator review, not proof of criminal activity.
    """
    bank = db.query(Bank).filter(Bank.id == bank_id).first()
    cfg = (bank.config or {}).get("aml_thresholds", {}) if bank else {}

    struct_min = float(cfg.get("structuring_min", 8500.0))
    struct_max = float(cfg.get("structuring_max", 9999.0))
    struct_count = int(cfg.get("structuring_count", 3))
    struct_hours = int(cfg.get("structuring_window_hours", 48))
    rapid_hours = int(cfg.get("rapid_passthrough_hours", 4))
    rapid_ratio = float(cfg.get("rapid_passthrough_ratio", 0.80))
    fan_in_thresh = int(cfg.get("fan_in_threshold", 5))
    fan_out_thresh = int(cfg.get("fan_out_threshold", 5))
    max_cycle_hops = int(cfg.get("max_cycle_hops", 5))

    txs = (
        db.query(Transaction)
        .filter(Transaction.bank_id == bank_id)
        .order_by(Transaction.timestamp.asc())
        .all()
    )
    if not txs:
        return {"findings_created": 0, "transactions_scanned": 0}

    db.query(DetectionFinding).filter(
        DetectionFinding.bank_id == bank_id,
        DetectionFinding.engine == "aml",
    ).delete(synchronize_session=False)

    G, accounts = graph_service.build_networkx_graph(db, bank_id)
    simple_di = nx.DiGraph(G)

    findings: List[DetectionFinding] = []
    seen_signatures = set()

    def acc_num(acc_id: str) -> str:
        return accounts[acc_id].account_number if acc_id in accounts else acc_id

    # A. Circular Transaction Flows
    try:
        # Filter to edges with meaningful volume (>= $2,000) to avoid noise cycles
        high_val_di = nx.DiGraph()
        for u, v, data in G.edges(data=True):
            if data.get("amount", 0.0) >= 2000.0:
                high_val_di.add_edge(u, v)

        for cyc in nx.simple_cycles(high_val_di):
            if 3 <= len(cyc) <= max_cycle_hops:
                sig = ("cycle", tuple(sorted(cyc)))
                if sig in seen_signatures:
                    continue
                seen_signatures.add(sig)

                path_nums = [acc_num(n) for n in cyc] + [acc_num(cyc[0])]
                # Find first edge transaction for reference
                first_edge = G.get_edge_data(cyc[0], cyc[1]) or {}
                first_tx_id = next(iter(first_edge.keys()), None)

                findings.append(
                    DetectionFinding(
                        id=f"fnd_{uuid.uuid4().hex[:14]}",
                        bank_id=bank_id,
                        engine="aml",
                        finding_type="circular_transfers",
                        transaction_id=first_tx_id,
                        account_id=cyc[0],
                        algorithm="NetworkX Bounded Cycle Detection",
                        model_version="aml-graph-v1.0",
                        risk_score=86.0,
                        evidence_indicators=[
                            f"Circular fund path of {len(cyc)} hops detected",
                            f"Path: {' -> '.join(path_nums)}",
                        ],
                        graph_path=cyc + [cyc[0]],
                        explanation=(
                            f"Potential circular transaction flow identified across {len(cyc)} accounts "
                            f"({' -> '.join(path_nums)}). Funds appear to return to an earlier account. "
                            f"This pattern is a risk indicator warranting AML review, not proof of criminal activity."
                        ),
                    )
                )
                if len([f for f in findings if f.finding_type == "circular_transfers"]) >= 15:
                    break
    except Exception:
        pass

    # B. Multi-hop Layering-like Sequences (temporal chains of length 4-5 with high value)
    tx_by_src: Dict[str, List[Transaction]] = defaultdict(list)
    tx_by_dst: Dict[str, List[Transaction]] = defaultdict(list)
    for tx in txs:
        tx_by_src[tx.source_account_id].append(tx)
        tx_by_dst[tx.destination_account_id].append(tx)

    for tx in txs:
        if tx.amount < 15000.0:
            continue
        # Trace forward 3..5 hops within 6 hours where each hop retains >= 75% of prior amount
        chain_accounts = [tx.source_account_id, tx.destination_account_id]
        chain_txs = [tx]
        curr_acc = tx.destination_account_id
        curr_ts = tx.timestamp
        curr_amt = tx.amount

        for _ in range(4):
            candidates = [
                nxt for nxt in tx_by_src.get(curr_acc, [])
                if nxt.destination_account_id not in chain_accounts
                and timedelta(minutes=1) <= (nxt.timestamp - curr_ts) <= timedelta(hours=4)
                and 0.70 * curr_amt <= nxt.amount <= 1.15 * curr_amt
            ]
            if not candidates:
                break
            nxt = candidates[0]
            chain_accounts.append(nxt.destination_account_id)
            chain_txs.append(nxt)
            curr_acc = nxt.destination_account_id
            curr_ts = nxt.timestamp
            curr_amt = nxt.amount

        if len(chain_accounts) >= 5:
            sig = ("layering", tuple(chain_accounts[:5]))
            if sig not in seen_signatures:
                seen_signatures.add(sig)
                path_nums = [acc_num(a) for a in chain_accounts]
                findings.append(
                    DetectionFinding(
                        id=f"fnd_{uuid.uuid4().hex[:14]}",
                        bank_id=bank_id,
                        engine="aml",
                        finding_type="potential_layering",
                        transaction_id=chain_txs[0].id,
                        account_id=chain_accounts[0],
                        algorithm="Temporal Multi-Hop Chain Traversal",
                        model_version="aml-graph-v1.0",
                        risk_score=82.0,
                        evidence_indicators=[
                            f"{len(chain_txs)}-hop sequential transfer chain within short window",
                            f"Initial amount ${tx.amount:,.2f} -> Final hop ${curr_amt:,.2f}",
                            f"Chain: {' -> '.join(path_nums)}",
                        ],
                        graph_path=chain_accounts,
                        explanation=(
                            f"Potential multi-hop layering indicator: funds moved sequentially across "
                            f"{len(chain_accounts)} accounts ({' -> '.join(path_nums)}) retaining ~"
                            f"{(curr_amt / max(tx.amount, 1.0)) * 100:.0f}% of value. Requires investigator verification."
                        ),
                    )
                )

    # C. Structuring Indicators (multiple transactions just under $10k in configurable window)
    for src_id, list_tx in tx_by_src.items():
        near_thresh = [t for t in list_tx if struct_min <= t.amount <= struct_max]
        if len(near_thresh) >= struct_count:
            near_thresh.sort(key=lambda t: t.timestamp)
            for i in range(len(near_thresh)):
                window_txs = [
                    t for t in near_thresh[i:]
                    if (t.timestamp - near_thresh[i].timestamp) <= timedelta(hours=struct_hours)
                ]
                if len(window_txs) >= struct_count:
                    sig = ("structuring", src_id)
                    if sig not in seen_signatures:
                        seen_signatures.add(sig)
                        total_amt = sum(t.amount for t in window_txs)
                        findings.append(
                            DetectionFinding(
                                id=f"fnd_{uuid.uuid4().hex[:14]}",
                                bank_id=bank_id,
                                engine="aml",
                                finding_type="structuring_indicator",
                                transaction_id=window_txs[0].id,
                                account_id=src_id,
                                algorithm="Time-Window Threshold Aggregation",
                                model_version="aml-graph-v1.0",
                                risk_score=78.0,
                                evidence_indicators=[
                                    f"{len(window_txs)} transfers between ${struct_min:,.0f} and ${struct_max:,.0f} within {struct_hours}h",
                                    f"Aggregate volume: ${total_amt:,.2f}",
                                ],
                                graph_path=[src_id] + [t.destination_account_id for t in window_txs[:5]],
                                explanation=(
                                    f"Account {acc_num(src_id)} executed {len(window_txs)} transfers totaling "
                                    f"${total_amt:,.2f}, each just below the $10,000 reporting threshold within {struct_hours} hours. "
                                    f"This is a structuring risk indicator for compliance review."
                                ),
                            )
                        )
                    break

    # D. Rapid Pass-Through / Mule Account Indicators
    for acc_id in accounts:
        inflows = [t for t in tx_by_dst.get(acc_id, []) if t.amount >= 5000.0]
        outflows = [t for t in tx_by_src.get(acc_id, []) if t.amount >= 5000.0]
        if not inflows or not outflows:
            continue
        for out_tx in outflows:
            recent_in = [
                in_tx for in_tx in inflows
                if timedelta(minutes=1) <= (out_tx.timestamp - in_tx.timestamp) <= timedelta(hours=rapid_hours)
            ]
            in_sum = sum(t.amount for t in recent_in)
            if in_sum > 0 and (out_tx.amount / in_sum) >= rapid_ratio and out_tx.amount >= 15000.0:
                sig = ("passthrough", acc_id)
                if sig not in seen_signatures:
                    seen_signatures.add(sig)
                    findings.append(
                        DetectionFinding(
                            id=f"fnd_{uuid.uuid4().hex[:14]}",
                            bank_id=bank_id,
                            engine="aml",
                            finding_type="rapid_passthrough_mule",
                            transaction_id=out_tx.id,
                            account_id=acc_id,
                            algorithm="Rapid Inflow-Outflow Velocity Ratio",
                            model_version="aml-graph-v1.0",
                            risk_score=80.0,
                            evidence_indicators=[
                                f"Inflow ${in_sum:,.2f} followed by ${out_tx.amount:,.2f} outflow within {rapid_hours}h",
                                f"Pass-through ratio: {(out_tx.amount / in_sum) * 100:.1f}%",
                            ],
                            graph_path=[recent_in[0].source_account_id, acc_id, out_tx.destination_account_id],
                            explanation=(
                                f"Account {acc_num(acc_id)} exhibited rapid pass-through behavior: "
                                f"received ${in_sum:,.2f} and transferred out ${out_tx.amount:,.2f} within {rapid_hours} hours "
                                f"(mule-account risk indicator)."
                            ),
                        )
                    )
                break

    # E. Unusual Fan-In and Fan-Out Network Hubs
    for acc_id in simple_di.nodes():
        in_deg = simple_di.in_degree(acc_id)
        out_deg = simple_di.out_degree(acc_id)
        if in_deg >= fan_in_thresh and out_deg >= fan_out_thresh:
            sig = ("fan_in_out", acc_id)
            if sig not in seen_signatures:
                seen_signatures.add(sig)
                findings.append(
                    DetectionFinding(
                        id=f"fnd_{uuid.uuid4().hex[:14]}",
                        bank_id=bank_id,
                        engine="aml",
                        finding_type="fan_in_fan_out_hub",
                        transaction_id=(tx_by_src.get(acc_id) or tx_by_dst.get(acc_id) or [None])[0].id
                        if (tx_by_src.get(acc_id) or tx_by_dst.get(acc_id)) else None,
                        account_id=acc_id,
                        algorithm="Graph Degree & Centrality Analysis",
                        model_version="aml-graph-v1.0",
                        risk_score=74.0,
                        evidence_indicators=[
                            f"High fan-in ({in_deg} distinct senders) and fan-out ({out_deg} distinct recipients)",
                        ],
                        graph_path=[acc_id],
                        explanation=(
                            f"Account {acc_num(acc_id)} acts as a high-degree network hub "
                            f"({in_deg} incoming counterparties, {out_deg} outgoing counterparties). "
                            f"May indicate aggregation/distribution activity requiring due diligence."
                        ),
                    )
                )

    if findings:
        db.bulk_save_objects(findings)
    db.commit()

    return {
        "findings_created": len(findings),
        "transactions_scanned": len(txs),
        "model_version": "aml-graph-v1.0",
    }
