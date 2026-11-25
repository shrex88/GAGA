import uuid
from typing import List
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import func
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.deps import get_current_user, get_user_permissions, log_audit, require_permissions
from app.core.security import create_access_token, hash_password, verify_password
from app.db.session import get_db
from app.models.entities import Role, User, UserRole
from app.schemas.common import LoginRequest, RegisterRequest, TokenResponse, UserOut

router = APIRouter(prefix="/auth", tags=["Authentication"])


def _to_user_out(db: Session, user: User) -> UserOut:
    perms = sorted(get_user_permissions(db, user))
    return UserOut(
        id=user.id,
        bank_id=user.bank_id,
        email=user.email,
        full_name=user.full_name,
        roles=[r.name for r in user.roles],
        permissions=perms,
        is_active=user.is_active,
    )


@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest, request: Request, db: Session = Depends(get_db)):
    norm_email = payload.email.strip().lower()
    try:
        user = db.query(User).filter(func.lower(User.email) == norm_email).first()
    except SQLAlchemyError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database service unavailable. Please try again later.",
        )

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="No account found for the provided email address.",
        )
    if not verify_password(payload.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect password. Please check your credentials.",
        )
    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="User account is disabled")

    token = create_access_token({"sub": user.id, "bank_id": user.bank_id, "roles": [r.name for r in user.roles]})
    log_audit(db, user, "user.login", "user", user.id, {"email": user.email}, request=request)
    return TokenResponse(access_token=token, user=_to_user_out(db, user))


@router.post("/register", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def register(
    payload: RegisterRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permissions("users:manage")),
):
    norm_email = payload.email.strip().lower()
    if db.query(User).filter(func.lower(User.email) == norm_email).first():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already registered")

    role = db.query(Role).filter(Role.name == payload.role_name).first()
    if not role:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Unknown role: {payload.role_name}")

    # Enforce bank-level scoping: admin creates users within their own bank
    target_bank = current_user.bank_id

    user = User(
        id=f"usr_{uuid.uuid4().hex[:12]}",
        bank_id=target_bank,
        email=norm_email,
        full_name=payload.full_name,
        password_hash=hash_password(payload.password),
        is_active=True,
    )
    db.add(user)
    db.flush()
    db.add(UserRole(user_id=user.id, role_id=role.id))
    db.commit()
    db.refresh(user)

    log_audit(db, current_user, "user.register", "user", user.id, {"role": payload.role_name}, request=request)
    return _to_user_out(db, user)


@router.get("/me", response_model=UserOut)
def get_me(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return _to_user_out(db, current_user)


@router.get("/users", response_model=List[UserOut])
def list_bank_users(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    users = db.query(User).filter(User.bank_id == current_user.bank_id).all()
    return [_to_user_out(db, u) for u in users]
