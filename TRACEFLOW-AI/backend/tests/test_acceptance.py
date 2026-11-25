import io
import os
import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


def _login(client: TestClient, email: str, password: str) -> str:
    res = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert res.status_code == 200, res.text
    return res.json()["access_token"]


def test_01_authentication_and_me(client):
    token = _login(client, "admin@traceflow.ai", "TraceflowDemo@2026!")
    me = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200
    assert me.json()["email"] == "admin@traceflow.ai"
    assert "bank_admin" in me.json()["roles"]

    bad = client.post("/api/v1/auth/login", json={"email": "admin@traceflow.ai", "password": "wrong_password"})
    assert bad.status_code == 401


def test_02_dataset_upload_1000_csv(client):
    token = _login(client, "fraud@traceflow.ai", "TraceflowDemo@2026!")
    headers = {"Authorization": f"Bearer {token}"}

    # Generate 1,000-row CSV in memory
    lines = ["transaction_id,source_account_id,destination_account_id,amount,currency,timestamp,transaction_type,transaction_status"]
    for i in range(1000):
        lines.append(f"TEST-CSV-{i:05d},CSV-A-{i%20},CSV-B-{(i+1)%20},{100 + (i % 500)},USD,2026-11-20T10:00:00Z,transfer,completed")
    csv_bytes = "\n".join(lines).encode("utf-8")

    res = client.post(
        "/api/v1/datasets/upload",
        headers=headers,
        files={"file": ("test_1000.csv", io.BytesIO(csv_bytes), "text/csv")},
        data={"run_analysis": "true"},
    )
    assert res.status_code == 201, res.text
    imp = res.json()["import_result"]
    assert imp["total_rows"] == 1000
    assert imp["accepted_rows"] == 1000
    assert imp["rejected_rows"] == 0


def test_03_transaction_explorer_search_and_filter(client):
    token = _login(client, "fraud@traceflow.ai", "TraceflowDemo@2026!")
    headers = {"Authorization": f"Bearer {token}"}

    res = client.get("/api/v1/transactions", headers=headers, params={"page": 1, "page_size": 10})
    assert res.status_code == 200
    data = res.json()
    assert data["total"] >= 1000
    assert len(data["items"]) == 10

    # Search for imported CSV transaction
    s_res = client.get("/api/v1/transactions", headers=headers, params={"search": "TEST-CSV-00001"})
    assert s_res.status_code == 200
    assert s_res.json()["total"] >= 1


def test_04_and_05_graph_and_aml_circular_detection(client):
    token = _login(client, "aml@traceflow.ai", "TraceflowDemo@2026!")
    headers = {"Authorization": f"Bearer {token}"}

    aml_res = client.get("/api/v1/aml/findings", headers=headers)
    assert aml_res.status_code == 200
    findings = aml_res.json()["findings"]
    assert len(findings) > 0
    circular = [f for f in findings if f["finding_type"] == "circular_transfers"]
    assert len(circular) > 0
    assert len(circular[0]["graph_path"]) >= 4

    acc_id = circular[0]["account_id"]
    g_res = client.get(f"/api/v1/graph/account/{acc_id}", headers=headers, params={"hops": 3})
    assert g_res.status_code == 200
    assert g_res.json()["found"] is True
    assert len(g_res.json()["nodes"]) >= 3
    assert len(g_res.json()["cycles"]) >= 1

    trace_res = client.get(f"/api/v1/graph/trace/{acc_id}", headers=headers, params={"max_hops": 4})
    assert trace_res.status_code == 200
    assert len(trace_res.json()["paths"]) >= 1


def test_06_fraud_detection_and_explanation(client):
    token = _login(client, "fraud@traceflow.ai", "TraceflowDemo@2026!")
    headers = {"Authorization": f"Bearer {token}"}

    res = client.get("/api/v1/fraud/findings", headers=headers)
    assert res.status_code == 200
    findings = res.json()["findings"]
    assert len(findings) > 0
    assert findings[0]["explanation"]
    assert len(findings[0]["evidence_indicators"]) >= 1


def test_07_unified_risk_intelligence(client):
    token = _login(client, "admin@traceflow.ai", "TraceflowDemo@2026!")
    headers = {"Authorization": f"Bearer {token}"}

    res = client.get("/api/v1/risk/accounts", headers=headers)
    assert res.status_code == 200
    accs = res.json()["accounts"]
    assert len(accs) > 0
    assert any(a["risk_category"] in ("High", "Critical") for a in accs)


def test_08_and_09_investigation_workflow_and_pdf_report(client):
    token = _login(client, "aml@traceflow.ai", "TraceflowDemo@2026!")
    headers = {"Authorization": f"Bearer {token}"}

    alerts_res = client.get("/api/v1/alerts", headers=headers)
    assert alerts_res.status_code == 200
    alerts = alerts_res.json()["alerts"]
    assert len(alerts) > 0
    alert_id = alerts[0]["id"]

    # Convert alert to case
    conv = client.post(
        f"/api/v1/alerts/{alert_id}/convert-to-case",
        headers=headers,
        json={"priority": "Critical"},
    )
    assert conv.status_code == 201
    case_id = conv.json()["case_id"]

    # Add note
    note = client.post(
        f"/api/v1/cases/{case_id}/notes",
        headers=headers,
        json={"content": "Verified circular pattern across 4 accounts.", "is_conclusion": True},
    )
    assert note.status_code == 201

    # Add evidence
    ev = client.post(
        f"/api/v1/cases/{case_id}/evidence",
        headers=headers,
        json={"evidence_type": "graph_snapshot", "title": "Cycle Graph", "payload": {"hops": 4}},
    )
    assert ev.status_code == 201

    # Change status
    upd = client.patch(f"/api/v1/cases/{case_id}", headers=headers, json={"status": "Under Investigation"})
    assert upd.status_code == 200
    assert upd.json()["status"] == "Under Investigation"

    # Generate & download PDF report
    rep = client.post("/api/v1/reports/generate", headers=headers, json={"case_id": case_id})
    assert rep.status_code == 201
    report_id = rep.json()["report_id"]

    dl = client.get(f"/api/v1/reports/{report_id}/download", headers=headers)
    assert dl.status_code == 200
    assert dl.headers["content-type"] == "application/pdf"
    assert dl.content[:4] == b"%PDF"


def test_11_permissions_and_tenant_isolation(client):
    # Auditor cannot trigger fraud analysis or modify alerts
    auditor_token = _login(client, "auditor@traceflow.ai", "TraceflowDemo@2026!")
    aud_headers = {"Authorization": f"Bearer {auditor_token}"}
    r_deny = client.post("/api/v1/fraud/analyse", headers=aud_headers)
    assert r_deny.status_code == 403

    # Meridian Partner Bank (bank_002) admin must see 0 bank_001 transactions
    meridian_token = _login(client, "admin@meridian.bank", "TraceflowDemo@2026!")
    m_headers = {"Authorization": f"Bearer {meridian_token}"}
    m_txs = client.get("/api/v1/transactions", headers=m_headers)
    assert m_txs.status_code == 200
    assert m_txs.json()["total"] == 0


def test_12_error_handling_invalid_csv_and_unauth(client):
    # Unauthenticated request
    unauth = client.get("/api/v1/transactions")
    assert unauth.status_code == 401

    # Invalid CSV rows (negative amount, bad currency, missing fields)
    token = _login(client, "admin@traceflow.ai", "TraceflowDemo@2026!")
    headers = {"Authorization": f"Bearer {token}"}
    bad_csv = (
        "transaction_id,source_account_id,destination_account_id,amount,currency,timestamp,transaction_type,transaction_status\n"
        "BAD-1,A1,A2,-500,USD,2026-11-20T10:00:00Z,transfer,completed\n"
        "BAD-2,A1,A2,100,XYZ,2026-11-20T10:00:00Z,transfer,completed\n"
    ).encode("utf-8")
    res = client.post(
        "/api/v1/datasets/upload",
        headers=headers,
        files={"file": ("bad.csv", io.BytesIO(bad_csv), "text/csv")},
        data={"run_analysis": "false"},
    )
    assert res.status_code == 201
    imp = res.json()["import_result"]
    assert imp["accepted_rows"] == 0
    assert imp["rejected_rows"] == 2
    assert len(imp["error_report"]) == 2
