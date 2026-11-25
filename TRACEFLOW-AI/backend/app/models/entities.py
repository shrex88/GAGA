from datetime import datetime, timezone
from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship
from app.db.session import Base


def utcnow():
    return datetime.now(timezone.utc)


class Bank(Base):
    __tablename__ = "banks"

    id = Column(String(64), primary_key=True)
    name = Column(String(200), nullable=False)
    code = Column(String(32), unique=True, nullable=False)
    country = Column(String(64), default="US", nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    config = Column(JSON, default=dict, nullable=False)
    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)


class Role(Base):
    __tablename__ = "roles"

    id = Column(String(64), primary_key=True)
    name = Column(String(64), unique=True, nullable=False)
    description = Column(Text, default="", nullable=False)


class Permission(Base):
    __tablename__ = "permissions"

    id = Column(String(64), primary_key=True)
    code = Column(String(128), unique=True, nullable=False)
    description = Column(Text, default="", nullable=False)


class RolePermission(Base):
    __tablename__ = "role_permissions"
    __table_args__ = (UniqueConstraint("role_id", "permission_id", name="uq_role_perm"),)

    id = Column(Integer, primary_key=True, autoincrement=True)
    role_id = Column(String(64), ForeignKey("roles.id", ondelete="CASCADE"), nullable=False)
    permission_id = Column(String(64), ForeignKey("permissions.id", ondelete="CASCADE"), nullable=False)


class User(Base):
    __tablename__ = "users"

    id = Column(String(64), primary_key=True)
    bank_id = Column(String(64), ForeignKey("banks.id", ondelete="CASCADE"), nullable=False, index=True)
    email = Column(String(255), unique=True, nullable=False, index=True)
    full_name = Column(String(200), nullable=False)
    password_hash = Column(String(512), nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)

    bank = relationship("Bank")
    roles = relationship("Role", secondary="user_roles", lazy="joined")


class UserRole(Base):
    __tablename__ = "user_roles"
    __table_args__ = (UniqueConstraint("user_id", "role_id", name="uq_user_role"),)

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String(64), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    role_id = Column(String(64), ForeignKey("roles.id", ondelete="CASCADE"), nullable=False)


class Customer(Base):
    __tablename__ = "customers"
    __table_args__ = (UniqueConstraint("bank_id", "customer_ref", name="uq_bank_customer_ref"),)

    id = Column(String(64), primary_key=True)
    bank_id = Column(String(64), ForeignKey("banks.id", ondelete="CASCADE"), nullable=False, index=True)
    customer_ref = Column(String(128), nullable=False, index=True)
    full_name = Column(String(200), nullable=False)
    segment = Column(String(64), default="retail", nullable=False)
    kyc_status = Column(String(32), default="verified", nullable=False)
    country = Column(String(64), default="US", nullable=False)
    is_synthetic = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)


class Account(Base):
    __tablename__ = "accounts"
    __table_args__ = (UniqueConstraint("bank_id", "account_number", name="uq_bank_account_num"),)

    id = Column(String(64), primary_key=True)
    bank_id = Column(String(64), ForeignKey("banks.id", ondelete="CASCADE"), nullable=False, index=True)
    customer_id = Column(String(64), ForeignKey("customers.id", ondelete="SET NULL"), nullable=True, index=True)
    account_number = Column(String(128), nullable=False, index=True)
    account_type = Column(String(64), default="checking", nullable=False)
    currency = Column(String(8), default="USD", nullable=False)
    balance = Column(Float, default=0.0, nullable=False)
    status = Column(String(32), default="active", nullable=False)
    risk_score = Column(Float, default=0.0, nullable=False)
    risk_category = Column(String(32), default="Low", nullable=False)
    is_synthetic = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)

    customer = relationship("Customer")


class DataSource(Base):
    __tablename__ = "data_sources"

    id = Column(String(64), primary_key=True)
    bank_id = Column(String(64), ForeignKey("banks.id", ondelete="CASCADE"), nullable=False, index=True)
    name = Column(String(128), nullable=False)
    source_type = Column(String(64), nullable=False)  # synthetic, csv_upload, bank_api
    status = Column(String(32), default="active", nullable=False)
    config = Column(JSON, default=dict, nullable=False)
    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)


class Dataset(Base):
    __tablename__ = "datasets"

    id = Column(String(64), primary_key=True)
    bank_id = Column(String(64), ForeignKey("banks.id", ondelete="CASCADE"), nullable=False, index=True)
    data_source_id = Column(String(64), ForeignKey("data_sources.id", ondelete="SET NULL"), nullable=True)
    name = Column(String(200), nullable=False)
    filename = Column(String(255), nullable=True)
    status = Column(String(32), default="pending", nullable=False)  # pending, validated, imported, analysed, failed
    total_rows = Column(Integer, default=0, nullable=False)
    accepted_rows = Column(Integer, default=0, nullable=False)
    rejected_rows = Column(Integer, default=0, nullable=False)
    duplicate_rows = Column(Integer, default=0, nullable=False)
    error_report = Column(JSON, default=list, nullable=False)
    column_mapping = Column(JSON, default=dict, nullable=False)
    is_synthetic = Column(Boolean, default=True, nullable=False)
    uploaded_by = Column(String(64), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)
    analysed_at = Column(DateTime(timezone=True), nullable=True)


class Transaction(Base):
    __tablename__ = "transactions"
    __table_args__ = (
        UniqueConstraint("bank_id", "transaction_ref", name="uq_bank_tx_ref"),
        Index("ix_tx_bank_timestamp", "bank_id", "timestamp"),
        Index("ix_tx_src_dst", "source_account_id", "destination_account_id"),
    )

    id = Column(String(64), primary_key=True)
    bank_id = Column(String(64), ForeignKey("banks.id", ondelete="CASCADE"), nullable=False, index=True)
    dataset_id = Column(String(64), ForeignKey("datasets.id", ondelete="SET NULL"), nullable=True, index=True)
    transaction_ref = Column(String(128), nullable=False, index=True)
    source_account_id = Column(String(64), ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False, index=True)
    destination_account_id = Column(String(64), ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False, index=True)
    amount = Column(Float, nullable=False)
    currency = Column(String(8), default="USD", nullable=False)
    timestamp = Column(DateTime(timezone=True), nullable=False, index=True)
    transaction_type = Column(String(64), default="transfer", nullable=False)
    transaction_status = Column(String(32), default="completed", nullable=False)
    channel = Column(String(64), default="online", nullable=True)
    device_id = Column(String(128), nullable=True)
    beneficiary_ref = Column(String(128), nullable=True)
    location_ref = Column(String(128), nullable=True)
    metadata_json = Column(JSON, default=dict, nullable=False)
    risk_score = Column(Float, default=0.0, nullable=False)
    risk_category = Column(String(32), default="Low", nullable=False)
    is_flagged = Column(Boolean, default=False, nullable=False)
    scenario_label = Column(String(64), nullable=True)  # Ground truth for offline testing only
    is_synthetic = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)

    source_account = relationship("Account", foreign_keys=[source_account_id])
    destination_account = relationship("Account", foreign_keys=[destination_account_id])


class ModelVersion(Base):
    __tablename__ = "model_versions"

    id = Column(String(64), primary_key=True)
    name = Column(String(128), nullable=False)
    engine_type = Column(String(32), nullable=False)  # fraud, aml
    version = Column(String(32), nullable=False)
    algorithm = Column(String(128), nullable=False)
    metrics = Column(JSON, default=dict, nullable=False)
    artifact_path = Column(String(512), nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)


class DetectionFinding(Base):
    __tablename__ = "detection_findings"
    __table_args__ = (Index("ix_finding_bank_engine", "bank_id", "engine"),)

    id = Column(String(64), primary_key=True)
    bank_id = Column(String(64), ForeignKey("banks.id", ondelete="CASCADE"), nullable=False, index=True)
    engine = Column(String(32), nullable=False)  # fraud, aml
    finding_type = Column(String(128), nullable=False)
    transaction_id = Column(String(64), ForeignKey("transactions.id", ondelete="CASCADE"), nullable=True, index=True)
    account_id = Column(String(64), ForeignKey("accounts.id", ondelete="CASCADE"), nullable=True, index=True)
    algorithm = Column(String(128), nullable=False)
    model_version = Column(String(64), nullable=False)
    risk_score = Column(Float, nullable=False)
    evidence_indicators = Column(JSON, default=list, nullable=False)
    graph_path = Column(JSON, default=list, nullable=False)
    explanation = Column(Text, nullable=False)
    shap_values = Column(JSON, default=dict, nullable=False)
    detected_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)


class RiskAssessment(Base):
    __tablename__ = "risk_assessments"
    __table_args__ = (Index("ix_risk_bank_entity", "bank_id", "entity_type", "entity_id"),)

    id = Column(String(64), primary_key=True)
    bank_id = Column(String(64), ForeignKey("banks.id", ondelete="CASCADE"), nullable=False, index=True)
    entity_type = Column(String(32), nullable=False)  # account, transaction
    entity_id = Column(String(64), nullable=False, index=True)
    fraud_risk = Column(Float, default=0.0, nullable=False)
    aml_risk = Column(Float, default=0.0, nullable=False)
    network_risk = Column(Float, default=0.0, nullable=False)
    combined_risk = Column(Float, default=0.0, nullable=False)
    risk_category = Column(String(32), default="Low", nullable=False)
    contributing_factors = Column(JSON, default=list, nullable=False)
    weights_used = Column(JSON, default=dict, nullable=False)
    explanation = Column(Text, default="", nullable=False)
    assessed_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)


class Alert(Base):
    __tablename__ = "alerts"
    __table_args__ = (Index("ix_alert_bank_status", "bank_id", "status"),)

    id = Column(String(64), primary_key=True)
    bank_id = Column(String(64), ForeignKey("banks.id", ondelete="CASCADE"), nullable=False, index=True)
    title = Column(String(255), nullable=False)
    category = Column(String(32), nullable=False)  # fraud, aml, unified
    severity = Column(String(32), nullable=False)  # Low, Moderate, High, Critical
    status = Column(String(32), default="open", nullable=False)  # open, under_review, resolved, dismissed, escalated
    risk_score = Column(Float, default=0.0, nullable=False)
    transaction_id = Column(String(64), ForeignKey("transactions.id", ondelete="SET NULL"), nullable=True)
    account_id = Column(String(64), ForeignKey("accounts.id", ondelete="SET NULL"), nullable=True)
    finding_id = Column(String(64), ForeignKey("detection_findings.id", ondelete="SET NULL"), nullable=True)
    assigned_to = Column(String(64), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    resolution_reason = Column(Text, nullable=True)
    supporting_evidence = Column(JSON, default=dict, nullable=False)
    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)


class InvestigationCase(Base):
    __tablename__ = "investigation_cases"

    id = Column(String(64), primary_key=True)
    bank_id = Column(String(64), ForeignKey("banks.id", ondelete="CASCADE"), nullable=False, index=True)
    case_number = Column(String(64), unique=True, nullable=False)
    title = Column(String(255), nullable=False)
    description = Column(Text, default="", nullable=False)
    priority = Column(String(32), default="High", nullable=False)  # Low, Medium, High, Critical
    status = Column(String(32), default="Open", nullable=False)  # Open, Under Investigation, Escalated, Resolved, Closed
    assigned_to = Column(String(64), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_by = Column(String(64), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    alert_id = Column(String(64), ForeignKey("alerts.id", ondelete="SET NULL"), nullable=True)
    related_account_ids = Column(JSON, default=list, nullable=False)
    related_transaction_ids = Column(JSON, default=list, nullable=False)
    ai_summary = Column(Text, default="", nullable=False)
    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)


class CaseEvidence(Base):
    __tablename__ = "case_evidence"

    id = Column(String(64), primary_key=True)
    case_id = Column(String(64), ForeignKey("investigation_cases.id", ondelete="CASCADE"), nullable=False, index=True)
    evidence_type = Column(String(64), nullable=False)  # transaction, graph_snapshot, finding, document
    title = Column(String(255), nullable=False)
    payload = Column(JSON, default=dict, nullable=False)
    added_by = Column(String(64), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)


class CaseNote(Base):
    __tablename__ = "case_notes"

    id = Column(String(64), primary_key=True)
    case_id = Column(String(64), ForeignKey("investigation_cases.id", ondelete="CASCADE"), nullable=False, index=True)
    author_id = Column(String(64), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    content = Column(Text, nullable=False)
    is_conclusion = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)


class AuditLog(Base):
    __tablename__ = "audit_logs"
    __table_args__ = (Index("ix_audit_bank_time", "bank_id", "created_at"),)

    id = Column(String(64), primary_key=True)
    bank_id = Column(String(64), ForeignKey("banks.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(String(64), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    user_email = Column(String(255), nullable=True)
    action = Column(String(128), nullable=False)
    resource_type = Column(String(64), nullable=False)
    resource_id = Column(String(64), nullable=True)
    details = Column(JSON, default=dict, nullable=False)
    ip_address = Column(String(64), nullable=True)
    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)
