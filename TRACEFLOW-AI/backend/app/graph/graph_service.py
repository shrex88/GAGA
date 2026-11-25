from datetime import datetime
from typing import Any, Dict, List, Optional, Set, Tuple
import networkx as nx
from neo4j import GraphDatabase
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.entities import Account, Customer, Transaction

settings = get_settings()


class GraphIntelligenceService:
    """
    Transaction Graph Intelligence supporting Neo4j (primary graph store when available)
    and NetworkX (deterministic analytical fallback derived from PostgreSQL/SQLite).
    """

    def __init__(self) -> None:
        self._driver = None
        self._neo4j_available = False
        self._check_neo4j()

    def _check_neo4j(self) -> None:
        if not settings.NEO4J_URI:
            self._neo4j_available = False
            return
        try:
            driver = GraphDatabase.driver(
                settings.NEO4J_URI,
                auth=(settings.NEO4J_USER, settings.NEO4J_PASSWORD),
                connection_timeout=1.5,
            )
            driver.verify_connectivity()
            self._driver = driver
            self._neo4j_available = True
        except Exception:
            self._driver = None
            self._neo4j_available = False

    def status(self) -> Dict[str, Any]:
        return {
            "neo4j_connected": self._neo4j_available,
            "backend_mode": "neo4j" if self._neo4j_available else "networkx_fallback",
            "uri": settings.NEO4J_URI if self._neo4j_available else None,
        }

    def sync_bank_graph_to_neo4j(self, db: Session, bank_id: str) -> Dict[str, Any]:
        """Synchronize authoritative relational accounts & transactions into Neo4j."""
        if not self._neo4j_available or not self._driver:
            return {"synced": False, "mode": "networkx_fallback"}

        accounts = db.query(Account).filter(Account.bank_id == bank_id).all()
        txs = db.query(Transaction).filter(Transaction.bank_id == bank_id).all()

        with self._driver.session() as session:
            for acc in accounts:
                session.run(
                    """
                    MERGE (a:Account {id: $id, bank_id: $bank_id})
                    SET a.account_number = $account_number,
                        a.risk_score = $risk_score,
                        a.risk_category = $risk_category,
                        a.account_type = $account_type
                    """,
                    id=acc.id,
                    bank_id=bank_id,
                    account_number=acc.account_number,
                    risk_score=acc.risk_score,
                    risk_category=acc.risk_category,
                    account_type=acc.account_type,
                )
            for tx in txs:
                session.run(
                    """
                    MATCH (s:Account {id: $src_id, bank_id: $bank_id})
                    MATCH (d:Account {id: $dst_id, bank_id: $bank_id})
                    MERGE (s)-[r:TRANSFERRED_TO {transaction_id: $tx_id}]->(d)
                    SET r.transaction_ref = $tx_ref,
                        r.amount = $amount,
                        r.currency = $currency,
                        r.timestamp = $timestamp,
                        r.risk_score = $risk_score
                    """,
                    src_id=tx.source_account_id,
                    dst_id=tx.destination_account_id,
                    bank_id=bank_id,
                    tx_id=tx.id,
                    tx_ref=tx.transaction_ref,
                    amount=float(tx.amount),
                    currency=tx.currency,
                    timestamp=tx.timestamp.isoformat(),
                    risk_score=float(tx.risk_score),
                )
        return {"synced": True, "mode": "neo4j", "accounts": len(accounts), "edges": len(txs)}

    def build_networkx_graph(
        self,
        db: Session,
        bank_id: str,
        min_amount: Optional[float] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
    ) -> Tuple[nx.MultiDiGraph, Dict[str, Account]]:
        """Build a directed multigraph from the authoritative SQL transaction store."""
        accounts = {
            a.id: a
            for a in db.query(Account).filter(Account.bank_id == bank_id).all()
        }
        query = db.query(Transaction).filter(Transaction.bank_id == bank_id)
        if min_amount is not None:
            query = query.filter(Transaction.amount >= min_amount)
        if start_date is not None:
            query = query.filter(Transaction.timestamp >= start_date)
        if end_date is not None:
            query = query.filter(Transaction.timestamp <= end_date)

        txs = query.all()
        G = nx.MultiDiGraph()
        for acc_id, acc in accounts.items():
            G.add_node(
                acc_id,
                account_number=acc.account_number,
                account_type=acc.account_type,
                risk_score=acc.risk_score,
                risk_category=acc.risk_category,
                balance=acc.balance,
                currency=acc.currency,
            )

        for tx in txs:
            G.add_edge(
                tx.source_account_id,
                tx.destination_account_id,
                key=tx.id,
                transaction_id=tx.id,
                transaction_ref=tx.transaction_ref,
                amount=float(tx.amount),
                currency=tx.currency,
                timestamp=tx.timestamp.isoformat(),
                risk_score=float(tx.risk_score),
                risk_category=tx.risk_category,
                is_flagged=bool(tx.is_flagged),
                transaction_type=tx.transaction_type,
            )
        return G, accounts

    def get_account_network(
        self,
        db: Session,
        bank_id: str,
        account_id_or_number: str,
        hops: int = 2,
        min_amount: Optional[float] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
    ) -> Dict[str, Any]:
        """Extract an N-hop ego network (2 to 5 hops) around an account for Cytoscape.js."""
        hops = max(1, min(5, hops))
        acc = (
            db.query(Account)
            .filter(
                Account.bank_id == bank_id,
                (Account.id == account_id_or_number) | (Account.account_number == account_id_or_number),
            )
            .first()
        )
        if not acc:
            return {"found": False, "nodes": [], "edges": [], "cycles": [], "stats": {}}

        G, accounts = self.build_networkx_graph(
            db, bank_id, min_amount=min_amount, start_date=start_date, end_date=end_date
        )

        # Undirected BFS up to `hops` to collect neighborhood
        undirected = G.to_undirected()
        visited: Set[str] = {acc.id}
        frontier: Set[str] = {acc.id}
        for _ in range(hops):
            next_frontier: Set[str] = set()
            for node in frontier:
                if node in undirected:
                    for nbr in undirected.neighbors(node):
                        if nbr not in visited:
                            visited.add(nbr)
                            next_frontier.add(nbr)
            frontier = next_frontier
            if not frontier or len(visited) > 120:
                break

        subG = G.subgraph(visited).copy()

        # Detect cycles within this subgraph (up to 5 hops)
        simple_di = nx.DiGraph()
        for u, v, data in subG.edges(data=True):
            simple_di.add_edge(u, v)

        cycles: List[List[str]] = []
        try:
            for cyc in nx.simple_cycles(simple_di, length_bound=5):
                if 2 <= len(cyc) <= 5 and acc.id in cyc:
                    cycles.append(cyc)
                    if len(cycles) >= 10:
                        break
        except Exception:
            pass

        cycle_nodes = {n for c in cycles for n in c}

        nodes = []
        for nid in subG.nodes():
            a = accounts.get(nid)
            if not a:
                continue
            nodes.append({
                "data": {
                    "id": a.id,
                    "label": a.account_number,
                    "account_number": a.account_number,
                    "account_type": a.account_type,
                    "risk_score": round(a.risk_score, 2),
                    "risk_category": a.risk_category,
                    "balance": round(a.balance, 2),
                    "is_center": a.id == acc.id,
                    "in_cycle": a.id in cycle_nodes,
                    "in_degree": subG.in_degree(nid),
                    "out_degree": subG.out_degree(nid),
                }
            })

        edges = []
        for u, v, key, data in subG.edges(keys=True, data=True):
            is_cycle_edge = (u in cycle_nodes and v in cycle_nodes and any(
                u in c and v in c for c in cycles
            ))
            edges.append({
                "data": {
                    "id": data["transaction_id"],
                    "source": u,
                    "target": v,
                    "label": f"${data['amount']:,.0f}",
                    "transaction_ref": data["transaction_ref"],
                    "amount": data["amount"],
                    "currency": data["currency"],
                    "timestamp": data["timestamp"],
                    "risk_score": round(data["risk_score"], 2),
                    "is_flagged": data["is_flagged"] or is_cycle_edge,
                    "is_cycle_edge": is_cycle_edge,
                    "transaction_type": data["transaction_type"],
                }
            })

        return {
            "found": True,
            "center_account_id": acc.id,
            "center_account_number": acc.account_number,
            "hops": hops,
            "backend_mode": "neo4j" if self._neo4j_available else "networkx_fallback",
            "nodes": nodes,
            "edges": edges,
            "cycles": [
                [accounts[n].account_number for n in c if n in accounts]
                for c in cycles
            ],
            "stats": {
                "node_count": len(nodes),
                "edge_count": len(edges),
                "cycles_detected": len(cycles),
            },
        }

    def trace_fund_paths(
        self,
        db: Session,
        bank_id: str,
        source_account_id_or_number: str,
        max_hops: int = 4,
    ) -> Dict[str, Any]:
        """Trace outgoing multi-hop fund movement paths from a source account."""
        max_hops = max(2, min(5, max_hops))
        acc = (
            db.query(Account)
            .filter(
                Account.bank_id == bank_id,
                (Account.id == source_account_id_or_number) | (Account.account_number == source_account_id_or_number),
            )
            .first()
        )
        if not acc:
            return {"found": False, "paths": []}

        G, accounts = self.build_networkx_graph(db, bank_id)
        simple_di = nx.DiGraph(G)

        paths: List[Dict[str, Any]] = []
        # BFS/DFS paths of length 2..max_hops
        def dfs(curr: str, path: List[str], total_amt: float):
            if len(paths) >= 25:
                return
            if len(path) > 1:
                paths.append({
                    "hops": len(path) - 1,
                    "account_ids": list(path),
                    "account_numbers": [accounts[n].account_number for n in path if n in accounts],
                    "min_hop_amount": round(total_amt, 2),
                })
            if len(path) - 1 >= max_hops:
                return
            for nbr in simple_di.successors(curr):
                if nbr not in path or (nbr == acc.id and len(path) >= 3):
                    edge_data = G.get_edge_data(curr, nbr) or {}
                    max_e = max((d.get("amount", 0.0) for d in edge_data.values()), default=0.0)
                    next_amt = max_e if total_amt == 0.0 else min(total_amt, max_e)
                    if nbr == acc.id:
                        paths.append({
                            "hops": len(path),
                            "account_ids": list(path) + [nbr],
                            "account_numbers": [accounts[n].account_number for n in (list(path) + [nbr]) if n in accounts],
                            "min_hop_amount": round(next_amt, 2),
                            "is_cycle": True,
                        })
                    else:
                        dfs(nbr, path + [nbr], next_amt)

        dfs(acc.id, [acc.id], 0.0)
        return {
            "found": True,
            "source_account_id": acc.id,
            "source_account_number": acc.account_number,
            "max_hops": max_hops,
            "paths": sorted(paths, key=lambda p: (-p["hops"], -p["min_hop_amount"]))[:20],
        }


graph_service = GraphIntelligenceService()
