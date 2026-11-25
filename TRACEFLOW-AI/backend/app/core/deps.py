import uuid
from typing import Any, Dict, List, Optional, Set
import jwt
from fastapi import Depends, Header, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.security import decode_access_token
from app.db.session import get_db
from app.models.entities import AuditLog, Permission, Role, RolePermission, User

settings = get_settings()
bearer_scheme = HTTPBearer(auto_error=False)

DEMO_ROLE_EMAILS = {
    "bank_admin": "admin@traceflow.ai",
    "fraud_analyst": "fraud@traceflow.ai",
    "aml_investigator": "aml@traceflow.ai",
    "auditor": "auditor@traceflow.ai",
}


def get_user_permissions(db: Session, user: User) -> Set[str]:
    role_ids = [r.id for r in user.roles]
    if not role_ids:
        return set()
    rows = (
        db.query(Permission.code)
        .join(RolePermission, RolePermission.permission_id == Permission.id)
        .filter(RolePermission.role_id.in_(role_ids))
        .all()
    )
    return {row[0] for row in rows}


def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
    x_demo_role: Optional[str] = Header(default=None, alias="X-Demo-Role"),
    db: Session = Depends(get_db),
) -> User:
    # 1. If a Bearer token is supplied, always validate it
    if credentials and credentials.scheme.lower() == "bearer":
        try:
            payload = decode_access_token(credentials.credentials)
            user_id: str = payload.get("sub")
            if not user_id:
                raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token payload")
        except jwt.ExpiredSignatureError:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Session expired. Please sign in again.")
        except Exception:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid authentication token")

        user = db.query(User).filter(User.id == user_id, User.is_active == True).first()
        if not user:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found or inactive")
        return user

    # 2. In local development demo mode (APP_AUTH_MODE=demo), allow direct access with local demo identity
    if settings.APP_AUTH_MODE.lower() == "demo" and settings.APP_ENV.lower() == "development":
        demo_email = DEMO_ROLE_EMAILS.get((x_demo_role or "bank_admin").lower(), "admin@traceflow.ai")
        demo_user = db.query(User).filter(User.email == demo_email, User.is_active == True).first()
        if demo_user:
            return demo_user

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Missing or invalid authentication credentials",
    )


def require_permissions(*required: str):
    def _checker(
        current_user: User = Depends(get_current_user),
        db: Session = Depends(get_db),
    ) -> User:
        perms = get_user_permissions(db, current_user)
        missing = [p for p in required if p not in perms]
        if missing:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Insufficient permissions: missing {', '.join(missing)}",
            )
        return current_user

    return _checker


def require_roles(*allowed_roles: str):
    def _checker(current_user: User = Depends(get_current_user)) -> User:
        user_roles = {r.name for r in current_user.roles}
        if not user_roles.intersection(set(allowed_roles)):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Role required: one of {', '.join(allowed_roles)}",
            )
        return current_user

    return _checker


def log_audit(
    db: Session,
    user: Optional[User],
    action: str,
    resource_type: str,
    resource_id: Optional[str] = None,
    details: Optional[Dict[str, Any]] = None,
    bank_id: Optional[str] = None,
    request: Optional[Request] = None,
) -> None:
    """Record an immutable audit log entry without storing raw sensitive PII."""
    entry = AuditLog(
        id=f"aud_{uuid.uuid4().hex[:16]}",
        bank_id=bank_id or (user.bank_id if user else "bank_001"),
        user_id=user.id if user else None,
        user_email=user.email if user else None,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        details=details or {},
        ip_address=request.client.host if (request and request.client) else None,
    )
    db.add(entry)
    db.commit()
