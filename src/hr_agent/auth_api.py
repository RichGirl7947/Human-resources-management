from __future__ import annotations

import secrets
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .auth import (
    authenticate_user,
    create_access_token,
    find_user_by_email,
    get_current_user,
    hash_password,
    require_roles,
)
from .config import get_settings
from .crypto import pii_hash
from .database import get_db
from .models import AuditLog, User, UserRole
from .schemas import (
    AuditLogRead,
    AuthResponse,
    BootstrapRequest,
    LoginRequest,
    UserCreate,
    UserRead,
)


router = APIRouter(prefix="/api/v1")
DbSession = Annotated[Session, Depends(get_db)]


def _create_user(payload: UserCreate, db: Session, role: UserRole | None = None) -> User:
    if find_user_by_email(db, payload.email):
        raise HTTPException(status_code=409, detail="该工号已存在用户")
    user = User(
        email=payload.email.strip(),
        email_hash=pii_hash(payload.email),
        full_name=payload.full_name.strip(),
        password_hash=hash_password(payload.password),
        role=role or payload.role,
        is_active=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@router.get("/auth/bootstrap-status", tags=["auth"])
def bootstrap_status(db: DbSession) -> dict[str, bool]:
    settings = get_settings()
    return {
        "required": int(db.scalar(select(func.count()).select_from(User)) or 0) == 0,
        "token_required": settings.environment == "production",
    }


@router.post("/auth/bootstrap", response_model=AuthResponse, status_code=status.HTTP_201_CREATED, tags=["auth"])
def bootstrap_admin(payload: BootstrapRequest, request: Request, db: DbSession) -> AuthResponse:
    if int(db.scalar(select(func.count()).select_from(User)) or 0):
        raise HTTPException(status_code=409, detail="系统已经完成管理员初始化")
    settings = get_settings()
    if settings.environment == "production":
        if not settings.bootstrap_token or not secrets.compare_digest(
            payload.bootstrap_token, settings.bootstrap_token
        ):
            raise HTTPException(status_code=403, detail="初始化令牌无效")
    user = _create_user(payload, db, UserRole.ADMIN)
    request.state.current_user = user
    token, expires_at = create_access_token(user)
    return AuthResponse(access_token=token, expires_at=expires_at, user=user)


@router.post("/auth/login", response_model=AuthResponse, tags=["auth"])
def login(payload: LoginRequest, request: Request, db: DbSession) -> AuthResponse:
    user = authenticate_user(db, payload.email, payload.password)
    if not user:
        raise HTTPException(status_code=401, detail="工号或密码错误")
    request.state.current_user = user
    token, expires_at = create_access_token(user)
    return AuthResponse(access_token=token, expires_at=expires_at, user=user)


@router.get("/auth/me", response_model=UserRead, tags=["auth"])
def current_user(user: Annotated[User, Depends(get_current_user)]) -> User:
    return user


@router.get(
    "/admin/users",
    response_model=list[UserRead],
    dependencies=[Depends(require_roles(UserRole.ADMIN))],
    tags=["admin"],
)
def list_users(db: DbSession) -> list[User]:
    return list(db.scalars(select(User).order_by(User.created_at.desc())))


@router.post(
    "/admin/users",
    response_model=UserRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_roles(UserRole.ADMIN))],
    tags=["admin"],
)
def create_user(payload: UserCreate, db: DbSession) -> User:
    return _create_user(payload, db)


@router.post(
    "/admin/users/{user_id}/toggle",
    response_model=UserRead,
    dependencies=[Depends(require_roles(UserRole.ADMIN))],
    tags=["admin"],
)
def toggle_user(user_id: int, db: DbSession, actor: Annotated[User, Depends(get_current_user)]) -> User:
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")
    if user.id == actor.id:
        raise HTTPException(status_code=409, detail="不能停用当前登录账号")
    user.is_active = not user.is_active
    db.commit()
    db.refresh(user)
    return user


@router.get(
    "/admin/audit-logs",
    response_model=list[AuditLogRead],
    dependencies=[Depends(require_roles(UserRole.ADMIN))],
    tags=["admin"],
)
def list_audit_logs(db: DbSession, limit: int = 100) -> list[AuditLog]:
    safe_limit = min(max(limit, 1), 500)
    return list(db.scalars(select(AuditLog).order_by(AuditLog.created_at.desc()).limit(safe_limit)))
