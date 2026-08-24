from datetime import date, datetime, timezone
from enum import Enum
from typing import Any

from sqlalchemy import Date, DateTime, Enum as SqlEnum, Float, ForeignKey, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from .crypto import EncryptedJSON, EncryptedText
from .database import Base


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class RecruitmentStatus(str, Enum):
    PENDING_APPROVAL = "pending_approval"
    PUBLISHED = "published"
    INTERVIEWING = "interviewing"
    OFFERED = "offered"
    TALENT_POOL = "talent_pool"


class CandidateStatus(str, Enum):
    SCREENED = "screened"
    INTERVIEW = "interview"
    HUMAN_REVIEW = "human_review"
    REJECTED = "rejected"
    OFFERED = "offered"
    TALENT_POOL = "talent_pool"


class NotificationChannel(str, Enum):
    EMAIL = "email"
    SMS = "sms"


class NotificationStatus(str, Enum):
    PENDING_CONFIGURATION = "pending_configuration"
    SCHEDULED = "scheduled"
    SENDING = "sending"
    SENT = "sent"
    FAILED = "failed"


class UserRole(str, Enum):
    ADMIN = "admin"
    HR = "hr"
    RECRUITER = "recruiter"
    VIEWER = "viewer"


class EmployeeStatus(str, Enum):
    ONBOARDING = "onboarding"
    ACTIVE = "active"
    IMPROVEMENT = "improvement"
    OFFBOARDING = "offboarding"
    EXITED = "exited"


class RequestStatus(str, Enum):
    COMPLETED = "completed"
    PENDING_APPROVAL = "pending_approval"
    PENDING_REVIEW = "pending_review"
    APPROVED = "approved"
    REJECTED = "rejected"


class JobRequisition(Base):
    __tablename__ = "job_requisitions"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(120))
    department: Mapped[str] = mapped_column(String(120), index=True)
    headcount: Mapped[int] = mapped_column(Integer, default=1)
    salary: Mapped[str] = mapped_column(String(120), default="面议")
    education: Mapped[str] = mapped_column(String(80), default="不限")
    experience: Mapped[str] = mapped_column(String(80), default="不限")
    responsibilities: Mapped[list[str]] = mapped_column(JSON, default=list)
    required_skills: Mapped[list[str]] = mapped_column(JSON, default=list)
    job_profile: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    status: Mapped[RecruitmentStatus] = mapped_column(
        SqlEnum(RecruitmentStatus), default=RecruitmentStatus.PENDING_APPROVAL
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class Candidate(Base):
    __tablename__ = "candidates"

    id: Mapped[int] = mapped_column(primary_key=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("job_requisitions.id"), index=True)
    name: Mapped[str] = mapped_column(EncryptedText())
    email: Mapped[str] = mapped_column(EncryptedText())
    phone: Mapped[str] = mapped_column(EncryptedText(), default="")
    resume_text: Mapped[str] = mapped_column(EncryptedText())
    score: Mapped[float] = mapped_column(Float)
    strengths: Mapped[list[str]] = mapped_column(EncryptedJSON(), default=list)
    gaps: Mapped[list[str]] = mapped_column(EncryptedJSON(), default=list)
    recommendation: Mapped[str] = mapped_column(EncryptedText())
    status: Mapped[CandidateStatus] = mapped_column(SqlEnum(CandidateStatus))
    selection_rank: Mapped[int | None] = mapped_column(Integer, nullable=True)
    selected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class InterviewNotification(Base):
    __tablename__ = "interview_notifications"
    __table_args__ = (UniqueConstraint("candidate_id", "channel", name="uq_candidate_notification_channel"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    candidate_id: Mapped[int] = mapped_column(ForeignKey("candidates.id"), index=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("job_requisitions.id"), index=True)
    channel: Mapped[NotificationChannel] = mapped_column(SqlEnum(NotificationChannel))
    recipient: Mapped[str] = mapped_column(EncryptedText())
    subject: Mapped[str] = mapped_column(String(255), default="面试通知")
    content: Mapped[str] = mapped_column(EncryptedText())
    scheduled_for: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    status: Mapped[NotificationStatus] = mapped_column(SqlEnum(NotificationStatus), index=True)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error: Mapped[str] = mapped_column(Text, default="")
    task_id: Mapped[str | None] = mapped_column(String(80), nullable=True, index=True)
    attempt_count: Mapped[int] = mapped_column(Integer, default=0)
    claimed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class Employee(Base):
    __tablename__ = "employees"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(EncryptedText())
    email: Mapped[str] = mapped_column(EncryptedText())
    email_hash: Mapped[str | None] = mapped_column(String(64), unique=True, index=True, nullable=True)
    department: Mapped[str] = mapped_column(String(120), index=True)
    position: Mapped[str] = mapped_column(String(120))
    start_date: Mapped[date] = mapped_column(Date)
    status: Mapped[EmployeeStatus] = mapped_column(SqlEnum(EmployeeStatus), default=EmployeeStatus.ONBOARDING)
    onboarding_tasks: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class HRRequest(Base):
    __tablename__ = "hr_requests"

    id: Mapped[int] = mapped_column(primary_key=True)
    employee_id: Mapped[int | None] = mapped_column(ForeignKey("employees.id"), nullable=True, index=True)
    request_type: Mapped[str] = mapped_column(String(60), index=True)
    content: Mapped[str] = mapped_column(EncryptedText())
    result: Mapped[dict[str, Any]] = mapped_column(EncryptedJSON(), default=dict)
    status: Mapped[RequestStatus] = mapped_column(SqlEnum(RequestStatus))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class PerformanceReview(Base):
    __tablename__ = "performance_reviews"

    id: Mapped[int] = mapped_column(primary_key=True)
    employee_id: Mapped[int] = mapped_column(ForeignKey("employees.id"), index=True)
    cycle: Mapped[str] = mapped_column(String(80))
    goals: Mapped[list[str]] = mapped_column(EncryptedJSON(), default=list)
    score: Mapped[float] = mapped_column(Float)
    manager_feedback: Mapped[str] = mapped_column(EncryptedText(), default="")
    development_plan: Mapped[dict[str, Any]] = mapped_column(EncryptedJSON(), default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class OffboardingCase(Base):
    __tablename__ = "offboarding_cases"

    id: Mapped[int] = mapped_column(primary_key=True)
    employee_id: Mapped[int] = mapped_column(ForeignKey("employees.id"), index=True)
    reason: Mapped[str] = mapped_column(EncryptedText())
    last_working_day: Mapped[date | None] = mapped_column(Date, nullable=True)
    handover_items: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    status: Mapped[RequestStatus] = mapped_column(SqlEnum(RequestStatus), default=RequestStatus.PENDING_APPROVAL)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(EncryptedText())
    email_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    full_name: Mapped[str] = mapped_column(EncryptedText())
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[UserRole] = mapped_column(SqlEnum(UserRole), index=True)
    is_active: Mapped[bool] = mapped_column(default=True, index=True)
    failed_login_attempts: Mapped[int] = mapped_column(Integer, default=0)
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    actor_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    actor_role: Mapped[str] = mapped_column(String(40), default="anonymous")
    action: Mapped[str] = mapped_column(String(120), index=True)
    method: Mapped[str] = mapped_column(String(10))
    path: Mapped[str] = mapped_column(String(500), index=True)
    status_code: Mapped[int] = mapped_column(Integer)
    ip_address: Mapped[str] = mapped_column(String(80), default="")
    user_agent: Mapped[str] = mapped_column(String(500), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, index=True)
