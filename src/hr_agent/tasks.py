from __future__ import annotations

from datetime import datetime, timedelta, timezone
import logging

from celery import Celery
from sqlalchemy import select

from .config import get_settings
from .database import SessionLocal
from .models import InterviewNotification, NotificationStatus
from .notifications import NotificationDeliveryError, deliver_notification


logger = logging.getLogger(__name__)
settings = get_settings()
celery_app = Celery(
    "hr_agent",
    broker=settings.celery_broker_url or "memory://",
    backend=settings.celery_result_backend or settings.celery_broker_url or "cache+memory://",
)
celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    broker_transport_options={"visibility_timeout": 3600},
    beat_schedule={
        "sweep-due-interview-notifications": {
            "task": "hr_agent.sweep_due_interview_notifications",
            "schedule": 60.0,
        }
    },
)


@celery_app.task(bind=True, name="hr_agent.deliver_interview_notification", max_retries=8)
def deliver_interview_notification(self: object, notification_id: int) -> str:
    try:
        with SessionLocal() as db:
            outcome = deliver_notification(
                db, notification_id, settings=settings, raise_on_failure=True
            )
            return outcome.value if outcome else "already_processed"
    except NotificationDeliveryError as exc:
        retries = int(getattr(self.request, "retries", 0))
        countdown = min(60 * (2**retries), 3600)
        raise self.retry(exc=exc, countdown=countdown)


def enqueue_interview_notification(notification_id: int, eta: datetime) -> str | None:
    if not settings.celery_broker_url:
        return None
    result = deliver_interview_notification.apply_async(args=[notification_id], eta=eta)
    with SessionLocal() as db:
        notification = db.get(InterviewNotification, notification_id)
        if notification:
            notification.task_id = result.id
            db.commit()
    return result.id


@celery_app.task(name="hr_agent.sweep_due_interview_notifications")
def sweep_due_interview_notifications() -> int:
    now = datetime.now(timezone.utc)
    stale_before = now - timedelta(minutes=10)
    with SessionLocal() as db:
        ids = list(
            db.scalars(
                select(InterviewNotification.id).where(
                    InterviewNotification.scheduled_for <= now,
                    (
                        InterviewNotification.status.in_(
                            [
                                NotificationStatus.SCHEDULED,
                                NotificationStatus.PENDING_CONFIGURATION,
                                NotificationStatus.FAILED,
                            ]
                        )
                        | (
                            (InterviewNotification.status == NotificationStatus.SENDING)
                            & (InterviewNotification.claimed_at <= stale_before)
                        )
                    ),
                )
            )
        )
    for notification_id in ids:
        deliver_interview_notification.delay(notification_id)
    return len(ids)
