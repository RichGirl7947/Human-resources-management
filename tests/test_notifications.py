from datetime import timedelta

from hr_agent.database import SessionLocal
from hr_agent.models import (
    Candidate,
    CandidateStatus,
    InterviewNotification,
    JobRequisition,
    NotificationChannel,
    NotificationStatus,
    RecruitmentStatus,
    utc_now,
)
from hr_agent.notifications import deliver_notification


def test_notification_delivery_is_idempotent(monkeypatch):
    calls: list[int] = []
    monkeypatch.setattr("hr_agent.notifications.channel_configured", lambda *args: True)
    monkeypatch.setattr("hr_agent.notifications._send_email", lambda item, settings: calls.append(item.id))

    with SessionLocal() as db:
        job = JobRequisition(
            title="通知测试职位",
            department="测试部",
            headcount=1,
            responsibilities=["测试"],
            required_skills=["Python"],
            status=RecruitmentStatus.INTERVIEWING,
        )
        db.add(job)
        db.flush()
        candidate = Candidate(
            job_id=job.id,
            name="通知候选人",
            email="notice@example.com",
            phone="13800009999",
            resume_text="用于可靠消息队列测试的候选人简历文本。",
            score=90,
            strengths=["Python"],
            gaps=[],
            recommendation="进入面试",
            status=CandidateStatus.INTERVIEW,
        )
        db.add(candidate)
        db.flush()
        notification = InterviewNotification(
            candidate_id=candidate.id,
            job_id=job.id,
            channel=NotificationChannel.EMAIL,
            recipient=candidate.email,
            subject="面试通知",
            content="测试通知",
            scheduled_for=utc_now() - timedelta(minutes=1),
            status=NotificationStatus.SCHEDULED,
        )
        db.add(notification)
        db.commit()
        db.refresh(notification)

        first = deliver_notification(db, notification.id)
        second = deliver_notification(db, notification.id)
        assert first == NotificationStatus.SENT
        assert second is None
        assert calls == [notification.id]
        assert notification.attempt_count == 1
