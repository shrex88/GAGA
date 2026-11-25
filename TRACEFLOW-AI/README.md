# TRACEFLOW AI — AI-Powered Financial Crime & Transaction Intelligence Platform

**Tagline:** *Follow the Money. Reveal the Pattern. Protect the Financial System.*

TRACEFLOW AI is an end-to-end FinTech financial crime intelligence prototype combining:
1. **Fraud Detection Engine** (Scikit-learn Isolation Forest + statistical behavioral profiling + velocity & device indicators)
2. **AML Detection Engine** (NetworkX / Neo4j graph-based cycle detection, multi-hop layering, structuring, rapid pass-through/mule detection, fan-in/fan-out hubs)
3. **Interactive Transaction Graph** (Cytoscape.js + Neo4j / NetworkX fallback, 2–5 hop traversal, cycle highlighting, fund tracing)
4. **Unified Risk Intelligence & Explainable AI** (Configurable 0–100 scoring, risk history, deterministic evidence-grounded explanations)
5. **Investigation & Case Management** (Alerts triage, case lifecycle, analyst notes/conclusions, evidence attachment, ReportLab PDF export)
6. **Security & Multi-Tenant RBAC** (JWT + Argon2 password hashing, bank-level isolation, audit logs, CSV formula injection protection)

---

## Demo Login Credentials (Seeded)

| Role | Email | Password | Bank Scope |
| :--- | :--- | :--- | :--- |
| **Bank Admin** | `admin@traceflow.ai` | `TraceflowDemo@2026!` | `bank_001` |
| **Fraud Analyst** | `fraud@traceflow.ai` | `TraceflowDemo@2026!` | `bank_001` |
| **AML Investigator** | `aml@traceflow.ai` | `TraceflowDemo@2026!` | `bank_001` |
| **Auditor** | `auditor@traceflow.ai` | `TraceflowDemo@2026!` | `bank_001` |
| **Partner Bank Admin** | `admin@meridian.bank` | `TraceflowDemo@2026!` | `bank_002` |

---

## Local Startup Instructions

### 1. Backend (FastAPI)
```bash
cd TRACEFLOW-AI/backend
.venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```
On first startup, the backend automatically initializes the database schema, seeds the demo banks/users/roles, generates 1,000 synthetic banking transactions with 9 scenarios, runs the Fraud, AML, and Unified Risk engines, and writes `data/samples/synthetic_sample_1000.csv`.

### 2. Frontend (React + Vite)
```bash
cd TRACEFLOW-AI/frontend
npm run dev
```
Open `http://localhost:5173` in your browser.

### 3. Docker Compose (PostgreSQL + Neo4j + Redis + Backend + Frontend)
```bash
cd TRACEFLOW-AI
docker compose up --build
```

---

## Running Tests
```bash
cd TRACEFLOW-AI/backend
.venv/bin/pytest -v tests/test_acceptance.py
```

---

## Architecture & Notes
- **Relational Store:** PostgreSQL (via `DATABASE_URL`) or SQLite (`traceflow.db`) for zero-dependency local runs.
- **Graph Store:** Neo4j (`NEO4J_URI`) with automatic NetworkX analytical fallback when Neo4j is not running locally.
- **Synthetic Data Disclaimer:** All seeded and generated demonstration data is synthetic (`is_synthetic=True`). Algorithmic findings are risk indicators for human review, not legal proof of criminal activity.
