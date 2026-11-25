from datetime import datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, EmailStr, Field


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=6)


class RegisterRequest(BaseModel):
    email: EmailStr
    full_name: str = Field(min_length=2, max_length=200)
    password: str = Field(min_length=8)
    role_name: str = Field(default="fraud_analyst")
    bank_id: str = Field(default="bank_001")


class UserOut(BaseModel):
    id: str
    bank_id: str
    email: str
    full_name: str
    roles: List[str]
    permissions: List[str]
    is_active: bool


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut


class SeedSyntheticRequest(BaseModel):
    count: int = Field(default=1000, ge=100, le=20000)
    seed: int = Field(default=42)
    run_analysis: bool = Field(default=True)
    name: Optional[str] = None


class AlertUpdateRequest(BaseModel):
    status: Optional[str] = None  # open, under_review, resolved, dismissed, escalated
    resolution_reason: Optional[str] = None


class AlertAssignRequest(BaseModel):
    assigned_to: str


class ConvertAlertToCaseRequest(BaseModel):
    title: Optional[str] = None
    priority: str = "High"


class CaseCreateRequest(BaseModel):
    title: str = Field(min_length=3, max_length=255)
    description: str = ""
    priority: str = "High"
    alert_id: Optional[str] = None
    related_account_ids: List[str] = Field(default_factory=list)
    related_transaction_ids: List[str] = Field(default_factory=list)


class CaseUpdateRequest(BaseModel):
    status: Optional[str] = None
    priority: Optional[str] = None
    assigned_to: Optional[str] = None
    title: Optional[str] = None
    description: Optional[str] = None


class CaseNoteCreateRequest(BaseModel):
    content: str = Field(min_length=2)
    is_conclusion: bool = False


class CaseEvidenceCreateRequest(BaseModel):
    evidence_type: str = Field(default="finding")
    title: str = Field(min_length=2, max_length=255)
    payload: Dict[str, Any] = Field(default_factory=dict)


class ReportGenerateRequest(BaseModel):
    case_id: Optional[str] = None
    account_id: Optional[str] = None
    title: Optional[str] = None


class BankConfigUpdateRequest(BaseModel):
    scoring_weights: Optional[Dict[str, float]] = None
    risk_thresholds: Optional[Dict[str, int]] = None
    aml_thresholds: Optional[Dict[str, Any]] = None
