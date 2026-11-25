import uuid
from sqlalchemy import func
from sqlalchemy.orm import Session
from app.core.config import get_settings
from app.core.security import hash_password
from app.models.entities import (
    Bank,
    DataSource,
    Permission,
    Role,
    RolePermission,
    User,
    UserRole,
)

settings = get_settings()

DEFAULT_BANK_CONFIG = {
    "scoring_weights": {
        "fraud_weight": 0.40,
        "aml_weight": 0.40,
        "network_weight": 0.20,
    },
    "risk_thresholds": {
        "low_max": 29,
        "moderate_max": 49,
        "high_max": 74,
    },
    "aml_thresholds": {
        "structuring_min": 8500.0,
        "structuring_max": 9999.0,
        "structuring_count": 3,
        "structuring_window_hours": 48,
        "rapid_passthrough_hours": 4,
        "rapid_passthrough_ratio": 0.80,
        "fan_in_threshold": 5,
        "fan_out_threshold": 5,
        "max_cycle_hops": 5,
    },
}

ROLE_PERMISSIONS = {
    "bank_admin": [
        "dashboard:read",
        "transactions:read",
        "fraud:read",
        "fraud:analyse",
        "aml:read",
        "aml:analyse",
        "graph:read",
        "risk:read",
        "alerts:read",
        "alerts:write",
        "cases:read",
        "cases:write",
        "datasets:read",
        "datasets:write",
        "reports:read",
        "reports:write",
        "audit:read",
        "settings:read",
        "settings:write",
        "users:manage",
    ],
    "fraud_analyst": [
        "dashboard:read",
        "transactions:read",
        "fraud:read",
        "fraud:analyse",
        "graph:read",
        "risk:read",
        "alerts:read",
        "alerts:write",
        "cases:read",
        "cases:write",
        "datasets:read",
        "datasets:write",
        "reports:read",
        "reports:write",
        "settings:read",
    ],
    "aml_investigator": [
        "dashboard:read",
        "transactions:read",
        "aml:read",
        "aml:analyse",
        "graph:read",
        "risk:read",
        "alerts:read",
        "alerts:write",
        "cases:read",
        "cases:write",
        "datasets:read",
        "datasets:write",
        "reports:read",
        "reports:write",
        "settings:read",
    ],
    "auditor": [
        "dashboard:read",
        "transactions:read",
        "fraud:read",
        "aml:read",
        "graph:read",
        "risk:read",
        "alerts:read",
        "cases:read",
        "datasets:read",
        "reports:read",
        "audit:read",
        "settings:read",
    ],
}


def seed_initial_data(db: Session, reset_demo_passwords: bool = False) -> None:
    """Idempotently seed banks, roles, permissions, and (in development) demo user accounts."""
    # 1. Banks
    banks = [
        {
            "id": "bank_001",
            "name": "TraceFlow Demo Bank",
            "code": "TFDB001",
            "country": "US",
            "config": DEFAULT_BANK_CONFIG,
        },
        {
            "id": "bank_002",
            "name": "Meridian Partner Bank",
            "code": "MPBK002",
            "country": "UK",
            "config": DEFAULT_BANK_CONFIG,
        },
    ]
    for b in banks:
        if not db.query(Bank).filter(Bank.id == b["id"]).first():
            db.add(Bank(**b))
    db.flush()

    # 2. Permissions
    all_perms = sorted({p for perms in ROLE_PERMISSIONS.values() for p in perms})
    perm_map = {}
    for code in all_perms:
        perm = db.query(Permission).filter(Permission.code == code).first()
        if not perm:
            perm = Permission(id=f"perm_{code.replace(':', '_')}", code=code, description=f"Permission {code}")
            db.add(perm)
        perm_map[code] = perm
    db.flush()

    # 3. Roles & RolePermissions
    role_map = {}
    for role_name, perms in ROLE_PERMISSIONS.items():
        role = db.query(Role).filter(Role.name == role_name).first()
        if not role:
            role = Role(
                id=f"role_{role_name}",
                name=role_name,
                description=f"{role_name.replace('_', ' ').title()} role",
            )
            db.add(role)
            db.flush()
        role_map[role_name] = role
        for code in perms:
            perm = perm_map[code]
            exists = (
                db.query(RolePermission)
                .filter(RolePermission.role_id == role.id, RolePermission.permission_id == perm.id)
                .first()
            )
            if not exists:
                db.add(RolePermission(role_id=role.id, permission_id=perm.id))
    db.flush()

    # 4. Demo Users (development environment only)
    if settings.APP_ENV.lower() == "development":
        demo_pwd = settings.DEMO_USER_PASSWORD
        demo_users = [
            ("usr_admin_001", "bank_001", "admin@traceflow.ai", "Elena Vance (Bank Admin)", demo_pwd, "bank_admin"),
            ("usr_fraud_001", "bank_001", "fraud@traceflow.ai", "Marcus Chen (Fraud Analyst)", demo_pwd, "fraud_analyst"),
            ("usr_aml_001", "bank_001", "aml@traceflow.ai", "Sophia Patel (AML Investigator)", demo_pwd, "aml_investigator"),
            ("usr_auditor_001", "bank_001", "auditor@traceflow.ai", "David Thorne (Auditor)", demo_pwd, "auditor"),
            ("usr_admin_002", "bank_002", "admin@meridian.bank", "Clara Sterling (Meridian Admin)", demo_pwd, "bank_admin"),
        ]
        for uid, bank_id, email, full_name, pwd, role_name in demo_users:
            norm_email = email.strip().lower()
            user = db.query(User).filter(func.lower(User.email) == norm_email).first()
            if not user:
                user = User(
                    id=uid,
                    bank_id=bank_id,
                    email=norm_email,
                    full_name=full_name,
                    password_hash=hash_password(pwd),
                    is_active=True,
                )
                db.add(user)
                db.flush()
                db.add(UserRole(user_id=user.id, role_id=role_map[role_name].id))
            else:
                if reset_demo_passwords:
                    user.password_hash = hash_password(pwd)
                    user.is_active = True
                role_obj = role_map[role_name]
                has_role = (
                    db.query(UserRole)
                    .filter(UserRole.user_id == user.id, UserRole.role_id == role_obj.id)
                    .first()
                )
                if not has_role:
                    db.add(UserRole(user_id=user.id, role_id=role_obj.id))

    # 5. Default Data Sources for bank_001
    for ds_id, name, stype in [
        ("ds_synthetic_001", "Synthetic Financial Crime Generator", "synthetic"),
        ("ds_csv_001", "CSV Batch Upload", "csv_upload"),
        ("ds_api_001", "Authorised Core Banking Feed (Future Interface)", "bank_api"),
    ]:
        if not db.query(DataSource).filter(DataSource.id == ds_id).first():
            db.add(
                DataSource(
                    id=ds_id,
                    bank_id="bank_001",
                    name=name,
                    source_type=stype,
                    status="active" if stype != "bank_api" else "configured_inactive",
                )
            )

    db.commit()
