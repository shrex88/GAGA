import os
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from app.api.v1 import (
    routes_auth,
    routes_dashboard_data,
    routes_investigations,
    routes_transactions_detection,
)
from app.core.config import get_settings
from app.db.seed import seed_initial_data
from app.db.session import Base, SessionLocal, engine
from app.detection.aml.aml_engine import run_aml_detection
from app.detection.fraud.fraud_engine import run_fraud_detection
from app.detection.unified_risk.risk_engine import run_unified_risk_scoring
from app.graph.graph_service import graph_service
from app.ingestion.synthetic_generator import export_sample_csv, generate_synthetic_dataset
from app.models.entities import Transaction

settings = get_settings()
limiter = Limiter(key_func=get_remote_address)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Initialize schema & seed demo users/banks
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        seed_initial_data(db)
        # Auto-seed initial 1,000 synthetic transactions if database is empty
        if db.query(Transaction).filter(Transaction.bank_id == "bank_001").count() == 0:
            generate_synthetic_dataset(db, bank_id="bank_001", count=1000, seed=42)
            run_fraud_detection(db, "bank_001")
            run_aml_detection(db, "bank_001")
            run_unified_risk_scoring(db, "bank_001")
            graph_service.sync_bank_graph_to_neo4j(db, "bank_001")

        # Ensure sample CSV exists for Data Management testing
        sample_csv_path = os.path.abspath(
            os.path.join(os.path.dirname(__file__), "..", "..", "..", "data", "samples", "synthetic_sample_1000.csv")
        )
        if not os.path.exists(sample_csv_path):
            export_sample_csv(sample_csv_path, count=1000, seed=77)
    finally:
        db.close()
    yield


app = FastAPI(
    title="TRACEFLOW AI",
    description="AI-Powered Financial Crime & Transaction Intelligence Platform",
    version="1.0.0",
    lifespan=lifespan,
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_origin_regex=r"http://(localhost|127\.0\.0\.1):[0-9]+",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error", "error_type": type(exc).__name__},
    )


@app.get("/health")
@app.get(f"{settings.API_V1_PREFIX}/health")
def health_check():
    db_ok = False
    db_error = None
    db = SessionLocal()
    try:
        db.execute(text("SELECT 1"))
        db_ok = True
    except Exception as exc:
        db_error = type(exc).__name__
    finally:
        db.close()

    return {
        "status": "ok" if db_ok else "degraded",
        "service": settings.APP_NAME,
        "auth_mode": settings.APP_AUTH_MODE,
        "database": {"connected": db_ok, "error": db_error},
        "graph": graph_service.status(),
    }


app.include_router(routes_auth.router, prefix=settings.API_V1_PREFIX)
app.include_router(routes_dashboard_data.router, prefix=settings.API_V1_PREFIX)
app.include_router(routes_transactions_detection.router, prefix=settings.API_V1_PREFIX)
app.include_router(routes_investigations.router, prefix=settings.API_V1_PREFIX)
