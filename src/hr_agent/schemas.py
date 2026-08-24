from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from .models import (
    CandidateStatus,
    EmployeeStatus,
    NotificationChannel,
    NotificationStatus,
    RecruitmentStatus,
    RequestStatus,
    UserRole,
)


EMAIL_PATTERN = r"^[^@\s]+@[^@\s]+\.[^@\s]+$"
ACCOUNT_ID_PATTERN = r"^[A-Za-z0-9@._-]+$"
PHONE_PATTERN = r"^\+?[0-9 ()-]{6,40}$"


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class AgentResult(BaseModel):
    agent: str
    summary: str
    data: dict[str, Any] = Field(default_factory=dict)
    human_review_required: bool = False
    trace: list[str] = Field(default_factory=list)


class ApprovalDecision(BaseModel):
    approved: bool
    comment: str = Field(default="", max_length=1000)


class LangChainChatRequest(BaseModel):
    message: str = Field(min_length=2, max_length=4000)
    thread_id: str = Field(default="default", min_length=1, max_length=120)


class LangChainChatResponse(BaseModel):
    answer: str
    model: str
    tools: list[str]


class LangChainStatus(BaseModel):
    framework: str
    version: str
    runtime: str
    supervisor_enabled: bool
    provider: str | None
    model: str | None
    base_url: str | None
    api_key_configured: bool
    tools: list[str]


def _validate_password(value: str) -> str:
    if len(value) < 12 or not any(char.isupper() for char in value) or not any(
        char.islower() for char in value
    ) or not any(char.isdigit() for char in value):
        raise ValueError("密码至少12位，并包含大写字母、小写字母和数字")
    return value


class LoginRequest(BaseModel):
    # Keep the API field name for compatibility with existing clients and data,
    # while treating its value as the employee number used to sign in.
    email: str = Field(min_length=2, max_length=64, pattern=ACCOUNT_ID_PATTERN)
    password: str = Field(min_length=8, max_length=200)


class UserCreate(BaseModel):
    email: str = Field(min_length=2, max_length=64, pattern=ACCOUNT_ID_PATTERN)
    full_name: str = Field(min_length=2, max_length=120)
    password: str = Field(min_length=12, max_length=200)
    role: UserRole = UserRole.VIEWER

    _strong_password = field_validator("password")(_validate_password)


class BootstrapRequest(UserCreate):
    role: UserRole = UserRole.ADMIN
    bootstrap_token: str = Field(default="", max_length=500)


class UserRead(ORMModel):
    id: int
    email: str
    full_name: str
    role: UserRole
    is_active: bool
    last_login_at: datetime | None
    created_at: datetime


class AuthResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_at: datetime
    user: UserRead


class AuditLogRead(ORMModel):
    id: int
    actor_id: int | None
    actor_role: str
    action: str
    method: str
    path: str
    status_code: int
    ip_address: str
    user_agent: str
    created_at: datetime


class JobRequisitionCreate(BaseModel):
    title: str = Field(min_length=2, max_length=120)
    department: str = Field(min_length=2, max_length=120)
    headcount: int = Field(default=1, ge=1, le=100)
    salary: str = Field(default="面议", min_length=1, max_length=120)
    education: str = Field(default="不限", min_length=1, max_length=80)
    experience: str = Field(default="不限", min_length=1, max_length=80)
    responsibilities: list[str] = Field(min_length=1)
    required_skills: list[str] = Field(default_factory=list)


class JobRequisitionRead(ORMModel):
    id: int
    title: str
    department: str
    headcount: int
    salary: str
    education: str
    experience: str
    responsibilities: list[str]
    required_skills: list[str]
    job_profile: dict[str, Any]
    status: RecruitmentStatus
    created_at: datetime


class CandidateCreate(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    email: str = Field(min_length=5, max_length=255, pattern=EMAIL_PATTERN)
    phone: str = Field(min_length=6, max_length=40, pattern=PHONE_PATTERN)
    resume_text: str = Field(min_length=20)


class CandidateRead(ORMModel):
    id: int
    job_id: int
    name: str
    email: str
    phone: str
    score: float
    strengths: list[str]
    gaps: list[str]
    recommendation: str
    status: CandidateStatus
    selection_rank: int | None
    selected_at: datetime | None
    created_at: datetime


class InterviewNotificationRead(ORMModel):
    id: int
    candidate_id: int
    job_id: int
    channel: NotificationChannel
    recipient: str
    scheduled_for: datetime
    status: NotificationStatus
    sent_at: datetime | None
    error: str
    task_id: str | None
    attempt_count: int


class InterviewSelectionRead(BaseModel):
    job_id: int
    selected_count: int
    selected_candidates: list[CandidateRead]
    notifications: list[InterviewNotificationRead]
    scheduled_for: datetime | None


class EmployeeOnboardCreate(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    email: str = Field(min_length=5, max_length=255, pattern=EMAIL_PATTERN)
    department: str = Field(min_length=2, max_length=120)
    position: str = Field(min_length=2, max_length=120)
    start_date: date


class EmployeeRead(ORMModel):
    id: int
    name: str
    email: str
    department: str
    position: str
    start_date: date
    status: EmployeeStatus
    onboarding_tasks: list[dict[str, Any]]
    created_at: datetime


class PolicyQuestion(BaseModel):
    employee_id: int | None = None
    question: str = Field(min_length=2, max_length=1000)


class WorkflowCreate(BaseModel):
    employee_id: int | None = None
    content: str = Field(min_length=2, max_length=2000)


class HRRequestRead(ORMModel):
    id: int
    employee_id: int | None
    request_type: str
    content: str
    result: dict[str, Any]
    status: RequestStatus
    created_at: datetime


class PerformanceReviewCreate(BaseModel):
    employee_id: int
    cycle: str = Field(min_length=2, max_length=80)
    goals: list[str] = Field(min_length=1)
    score: float = Field(ge=1, le=5)
    manager_feedback: str = Field(default="", max_length=3000)


class PerformanceReviewRead(ORMModel):
    id: int
    employee_id: int
    cycle: str
    goals: list[str]
    score: float
    manager_feedback: str
    development_plan: dict[str, Any]
    created_at: datetime


class OffboardingCreate(BaseModel):
    employee_id: int
    reason: str = Field(min_length=2, max_length=2000)
    last_working_day: date | None = None


class OffboardingRead(ORMModel):
    id: int
    employee_id: int
    reason: str
    last_working_day: date | None
    handover_items: list[dict[str, Any]]
    status: RequestStatus
    created_at: datetime
