from __future__ import annotations

import logging

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import Response

from .database import SessionLocal
from .models import AuditLog, User


logger = logging.getLogger(__name__)


class AuditMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        should_audit = request.method in {"POST", "PUT", "PATCH", "DELETE"}
        response: Response | None = None
        status_code = 500
        try:
            response = await call_next(request)
            status_code = response.status_code
            return response
        finally:
            if should_audit:
                actor: User | None = getattr(request.state, "current_user", None)
                try:
                    with SessionLocal() as db:
                        db.add(
                            AuditLog(
                                actor_id=actor.id if actor and actor.id else None,
                                actor_role=actor.role.value if actor else "anonymous",
                                action=f"{request.method} {request.url.path}",
                                method=request.method,
                                path=request.url.path[:500],
                                status_code=status_code,
                                ip_address=(request.client.host if request.client else "")[:80],
                                user_agent=request.headers.get("user-agent", "")[:500],
                            )
                        )
                        db.commit()
                except Exception:
                    logger.exception("Failed to persist audit event")
