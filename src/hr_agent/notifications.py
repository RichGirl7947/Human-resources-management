from __future__ import annotations

from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
import json
import logging
import smtplib
from urllib.request import Request, urlopen

from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import Settings, get_settings
from .models import (
    InterviewNotification,
    NotificationChannel,
    NotificationStatus,
)


logger = logging.getLogger(__name__)


def channel_configured(channel: NotificationChannel, settings: Settings | None = None) -> bool:
    current = settings or get_settings()
    if channel == NotificationChannel.EMAIL:
        return bool(current.smtp_host and current.smtp_from)
    return bool(current.sms_webhook_url)


def initial_notification_status(
    channel: NotificationChannel, settings: Settings | None = None
) -> NotificationStatus:
    return (
        NotificationStatus.SCHEDULED
        if channel_configured(channel, settings)
        else NotificationStatus.PENDING_CONFIGURATION
    )


def _send_email(notification: InterviewNotification, settings: Settings) -> None:
    message = EmailMessage()
    message["Subject"] = notification.subject
    message["From"] = settings.smtp_from
    message["To"] = notification.recipient
    message["Message-ID"] = f"<hr-interview-{notification.id}@pulsehr.local>"
    message.set_content(notification.content)

    with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=20) as smtp:
        if settings.smtp_use_tls:
            smtp.starttls()
        if settings.smtp_username and settings.smtp_password:
            smtp.login(settings.smtp_username, settings.smtp_password)
        smtp.send_message(message)


def _send_sms(notification: InterviewNotification, settings: Settings) -> None:
    payload = json.dumps(
        {
            "phone": notification.recipient,
            "message": notification.content,
            "candidate_id": notification.candidate_id,
            "job_id": notification.job_id,
            "idempotency_key": f"interview-notification-{notification.id}",
        },
        ensure_ascii=False,
    ).encode("utf-8")
    request = Request(
        settings.sms_webhook_url,
        data=payload,
        headers={"Content-Type": "application/json; charset=utf-8"},
        method="POST",
    )
    with urlopen(request, timeout=20) as response:  # noqa: S310 - URL is explicitly configured by HR
        if response.status >= 300:
            raise RuntimeError(f"短信网关返回 HTTP {response.status}")


class NotificationDeliveryError(RuntimeError):
    pass


def deliver_notification(
    db: Session,
    notification_id: int,
    now: datetime | None = None,
    settings: Settings | None = None,
    raise_on_failure: bool = False,
) -> NotificationStatus | None:
    current = settings or get_settings()
    dispatch_time = now or datetime.now(timezone.utc)
    notification = db.scalar(
        select(InterviewNotification)
        .where(InterviewNotification.id == notification_id)
        .with_for_update(skip_locked=True)
    )
    if not notification or notification.status == NotificationStatus.SENT:
        return None
    if notification.status == NotificationStatus.SENDING:
        stale_before = dispatch_time - timedelta(minutes=10)
        claimed_at = notification.claimed_at
        comparable_stale = (
            stale_before if claimed_at is None or claimed_at.tzinfo else stale_before.replace(tzinfo=None)
        )
        if claimed_at and claimed_at > comparable_stale:
            return notification.status
    if not channel_configured(notification.channel, current):
        notification.status = NotificationStatus.PENDING_CONFIGURATION
        notification.error = "通知通道尚未配置"
        db.commit()
        return notification.status

    notification.status = NotificationStatus.SENDING
    notification.claimed_at = dispatch_time
    notification.attempt_count += 1
    notification.error = ""
    db.commit()
    try:
        if notification.channel == NotificationChannel.EMAIL:
            _send_email(notification, current)
        else:
            _send_sms(notification, current)
        notification.status = NotificationStatus.SENT
        notification.sent_at = dispatch_time
        notification.error = ""
        db.commit()
        return notification.status
    except Exception as exc:
        notification.status = NotificationStatus.FAILED
        notification.error = str(exc)[:1000]
        db.commit()
        logger.exception("Failed to send interview notification %s", notification.id)
        if raise_on_failure:
            raise NotificationDeliveryError(str(exc)) from exc
        return notification.status


def dispatch_due_notifications(
    db: Session, now: datetime | None = None, settings: Settings | None = None
) -> dict[str, int]:
    current = settings or get_settings()
    dispatch_time = now or datetime.now(timezone.utc)
    stale_before = dispatch_time - timedelta(minutes=10)
    notifications = list(
        db.scalars(
            select(InterviewNotification)
            .where(
                InterviewNotification.scheduled_for <= dispatch_time,
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
            .order_by(InterviewNotification.scheduled_for, InterviewNotification.id)
        )
    )
    result = {"processed": 0, "sent": 0, "pending_configuration": 0, "failed": 0}
    for notification in notifications:
        result["processed"] += 1
        outcome = deliver_notification(db, notification.id, dispatch_time, current)
        if outcome == NotificationStatus.PENDING_CONFIGURATION:
            result["pending_configuration"] += 1
        elif outcome == NotificationStatus.SENT:
            result["sent"] += 1
        elif outcome == NotificationStatus.FAILED:
            result["failed"] += 1
    return result
