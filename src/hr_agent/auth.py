from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timedelta, timezone
import secrets
from typing import Annotated

import jwt
from fastapi import Depends, HTTPException, Request, Security, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pwdlib import PasswordHash
from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import get_settings
from .crypto import pii_hash
from .database import get_db
from .models import User, UserRole, utc_now


password_hash = PasswordHash.recommended()
bearer_scheme = HTTPBearer(auto_error=False, scheme_name="HRAccessToken")
_development_secret = secrets.token_urlsafe(48)
DbSession = Annotated[Session, Depends(get_db)]


def _jwt_secret() -> str:
    settings = get_settings()
    if settings.jwt_secret:
        return settings.jwt_secret
    if settings.environment == "production":
        raise RuntimeError("生产环境必须配置 HR_JWT_SECRET")
    return _development_secret


def validate_production_settings() -> None:
    settings = get_settings()
    if settings.environment != "production":
        return
    missing: list[str] = []
    if not settings.jwt_secret or len(settings.jwt_secret) < 32:
        missing.append("HR_JWT_SECRET（至少32字符）")
    if not settings.data_encryption_key:
        missing.append("HR_DATA_ENCRYPTION_KEY")
    if not settings.database_url.startswith("postgresql"):
        missing.append("HR_DATABASE_URL（PostgreSQL）")
    if not settings.celery_broker_url:
        missing.append("HR_CELERY_BROKER_URL")
    if missing:
        raise RuntimeError("生产配置不完整：" + "、".join(missing))


def hash_password(password: str) -> str:
    return password_hash.hash(password)


def verify_password(password: str, encoded: str) -> bool:
    return password_hash.verify(password, encoded)


def create_access_token(user: User) -> tuple[str, datetime]:
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=get_settings().access_token_minutes)
    payload = {
        "sub": str(user.id),
        "role": user.role.value,
        "iat": datetime.now(timezone.utc),
        "exp": expires_at,
        "type": "access",
    }
    return jwt.encode(payload, _jwt_secret(), algorithm="HS256"), expires_at


def _unauthorized(detail: str = "登录已失效，请重新登录") -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detail,
        headers={"WWW-Authenticate": "Bearer"},
    )


def get_current_user(
    request: Request,
    db: DbSession,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Security(bearer_scheme)],
) -> User:
    settings = get_settings()
    if not settings.auth_required:
        user = User(
            id=0,
            email="development@localhost",
            email_hash="development",
            full_name="Development Admin",
            password_hash="",
            role=UserRole.ADMIN,
            is_active=True,
        )
        request.state.current_user = user
        return user
    if not credentials or credentials.scheme.casefold() != "bearer":
        raise _unauthorized("请先登录")
    try:
        payload = jwt.decode(credentials.credentials, _jwt_secret(), algorithms=["HS256"])
        if payload.get("type") != "access":
            raise _unauthorized()
        user_id = int(payload["sub"])
    except (jwt.InvalidTokenError, KeyError, TypeError, ValueError) as exc:
        raise _unauthorized() from exc
    user = db.get(User, user_id)
    if not user or not user.is_active:
        raise _unauthorized("账号不存在或已停用")
    request.state.current_user = user
    return user


def require_roles(*roles: UserRole) -> Callable[..., User]:
    allowed = set(roles)

    def dependency(user: Annotated[User, Depends(get_current_user)]) -> User:
        if user.role not in allowed:
            raise HTTPException(status_code=403, detail="当前角色没有执行此操作的权限")
        return user

    return dependency


def authorize_api(
    request: Request, user: Annotated[User, Depends(get_current_user)]
) -> User:
    if request.method in {"GET", "HEAD", "OPTIONS"}:
        return user
    path = request.url.path
    if path.endswith("/recruitment/interview-notifications/dispatch"):
        allowed = {UserRole.ADMIN}
    elif "/recruitment/" in path:
        allowed = {UserRole.ADMIN, UserRole.HR, UserRole.RECRUITER}
    else:
        allowed = {UserRole.ADMIN, UserRole.HR}
    if user.role not in allowed:
        raise HTTPException(status_code=403, detail="当前角色没有执行此操作的权限")
    return user


def find_user_by_email(db: Session, email: str) -> User | None:
    return db.scalar(select(User).where(User.email_hash == pii_hash(email)))


def authenticate_user(db: Session, email: str, password: str) -> User | None:
    user = find_user_by_email(db, email)
    if not user or not user.is_active:
        return None
    now = utc_now()
    compare_now = now if user.locked_until is None or user.locked_until.tzinfo else now.replace(tzinfo=None)
    if user.locked_until and user.locked_until > compare_now:
        raise HTTPException(status_code=423, detail="登录失败次数过多，请15分钟后重试")
    if not verify_password(password, user.password_hash):
        user.failed_login_attempts += 1
        if user.failed_login_attempts >= 5:
            user.locked_until = now + timedelta(minutes=15)
            user.failed_login_attempts = 0
        db.commit()
        return None
    user.failed_login_attempts = 0
    user.locked_until = None
    user.last_login_at = now
    db.commit()
    db.refresh(user)
    return user
