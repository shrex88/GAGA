from datetime import timedelta
import pytest
from fastapi.testclient import TestClient

from app.core import deps as core_deps
from app.core.config import get_settings
from app.core.security import create_access_token
from app.db.seed import seed_initial_data
from app.db.session import SessionLocal
from app.main import app
from app.models.entities import User

settings = get_settings()
DEMO_PWD = settings.DEMO_USER_PASSWORD


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


def test_health_endpoints_no_auth(client):
    for path in ["/health", "/api/v1/health"]:
        res = client.get(path)
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "ok"
        assert data["database"]["connected"] is True


def test_demo_mode_direct_access_without_token(client):
    """In APP_AUTH_MODE=demo, dashboard, transactions, fraud, AML, graph, alerts, cases, reports work without JWT."""
    assert settings.APP_AUTH_MODE == "demo"
    for endpoint in [
        "/api/v1/auth/me",
        "/api/v1/dashboard/summary",
        "/api/v1/transactions",
        "/api/v1/fraud/findings",
        "/api/v1/aml/findings",
        "/api/v1/risk/accounts",
        "/api/v1/alerts",
        "/api/v1/cases",
        "/api/v1/audit/logs",
        "/api/v1/settings/bank-config",
    ]:
        res = client.get(endpoint)
        assert res.status_code == 200, f"{endpoint} returned {res.status_code}: {res.text}"


@pytest.mark.parametrize(
    "email,expected_role",
    [
        ("admin@traceflow.ai", "bank_admin"),
        ("fraud@traceflow.ai", "fraud_analyst"),
        ("aml@traceflow.ai", "aml_investigator"),
        ("auditor@traceflow.ai", "auditor"),
        ("ADMIN@TRACEFLOW.AI", "bank_admin"),
    ],
)
def test_all_demo_accounts_login(client, email, expected_role):
    res = client.post("/api/v1/auth/login", json={"email": email, "password": DEMO_PWD})
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["access_token"]
    assert expected_role in body["user"]["roles"]


def test_incorrect_password_and_unknown_email(client):
    bad_pwd = client.post(
        "/api/v1/auth/login",
        json={"email": "admin@traceflow.ai", "password": "WrongPassword123!"},
    )
    assert bad_pwd.status_code == 401

    unknown = client.post(
        "/api/v1/auth/login",
        json={"email": "nobody@traceflow.ai", "password": DEMO_PWD},
    )
    assert unknown.status_code == 401


def test_duplicate_demo_user_prevention():
    db = SessionLocal()
    try:
        before_count = db.query(User).count()
        seed_initial_data(db)
        seed_initial_data(db)
        after_count = db.query(User).count()
        assert before_count == after_count
    finally:
        db.close()


def test_expired_and_invalid_jwt_rejection(client):
    expired_token = create_access_token(
        {"sub": "usr_admin_001", "bank_id": "bank_001"},
        expires_delta=timedelta(seconds=-10),
    )
    res_exp = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {expired_token}"})
    assert res_exp.status_code == 401
    assert "expired" in res_exp.json()["detail"].lower()

    res_bad = client.get("/api/v1/auth/me", headers={"Authorization": "Bearer not.a.valid.jwt"})
    assert res_bad.status_code == 401


def test_production_jwt_mode_blocks_unauthenticated(client, monkeypatch):
    """When APP_AUTH_MODE is set to 'jwt' (production), unauthenticated requests are rejected with 401."""
    monkeypatch.setattr(core_deps.settings, "APP_AUTH_MODE", "jwt")
    res = client.get("/api/v1/dashboard/summary")
    assert res.status_code == 401


def test_rbac_enforcement_with_jwt(client):
    fraud_tok = client.post(
        "/api/v1/auth/login", json={"email": "fraud@traceflow.ai", "password": DEMO_PWD}
    ).json()["access_token"]
    assert client.get("/api/v1/fraud/findings", headers={"Authorization": f"Bearer {fraud_tok}"}).status_code == 200
    assert client.get("/api/v1/audit/logs", headers={"Authorization": f"Bearer {fraud_tok}"}).status_code == 403

    aud_tok = client.post(
        "/api/v1/auth/login", json={"email": "auditor@traceflow.ai", "password": DEMO_PWD}
    ).json()["access_token"]
    assert client.get("/api/v1/audit/logs", headers={"Authorization": f"Bearer {aud_tok}"}).status_code == 200
    assert client.post("/api/v1/fraud/analyse", headers={"Authorization": f"Bearer {aud_tok}"}).status_code == 403
