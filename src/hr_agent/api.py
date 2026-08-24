from datetime import timedelta
import logging
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .agents import AGENTS
from .auth import authorize_api
from .crypto import pii_hash
from .database import get_db
from .langchain_runtime import (
    get_langchain_runtime,
    get_langchain_status,
    get_langchain_supervisor,
)
from .models import (
    Candidate,
    CandidateStatus,
    Employee,
    EmployeeStatus,
    HRRequest,
    InterviewNotification,
    JobRequisition,
    NotificationChannel,
    OffboardingCase,
    PerformanceReview,
    RecruitmentStatus,
    RequestStatus,
    utc_now,
)
from .notifications import dispatch_due_notifications, initial_notification_status
from .schemas import (
    ApprovalDecision,
    CandidateCreate,
    CandidateRead,
    EmployeeOnboardCreate,
    EmployeeRead,
    HRRequestRead,
    InterviewNotificationRead,
    InterviewSelectionRead,
    JobRequisitionCreate,
    JobRequisitionRead,
    LangChainChatRequest,
    LangChainChatResponse,
    LangChainStatus,
    OffboardingCreate,
    OffboardingRead,
    PerformanceReviewCreate,
    PerformanceReviewRead,
    PolicyQuestion,
    WorkflowCreate,
)
from .tasks import enqueue_interview_notification


router = APIRouter(prefix="/api/v1", dependencies=[Depends(authorize_api)])
DbSession = Annotated[Session, Depends(get_db)]
logger = logging.getLogger(__name__)


def require_employee(db: Session, employee_id: int) -> Employee:
    employee = db.get(Employee, employee_id)
    if not employee:
        raise HTTPException(status_code=404, detail="员工不存在")
    return employee


@router.get("/agents", tags=["system"])
def list_agents() -> list[dict[str, str]]:
    return [{"name": agent.name, "description": agent.description} for agent in AGENTS.values()]


@router.get("/langchain/status", response_model=LangChainStatus, tags=["langchain"])
def langchain_status() -> LangChainStatus:
    return get_langchain_status()


@router.post("/langchain/chat", response_model=LangChainChatResponse, tags=["langchain"])
def langchain_chat(payload: LangChainChatRequest) -> LangChainChatResponse:
    supervisor = get_langchain_supervisor()
    if supervisor is None:
        raise HTTPException(
            status_code=503,
            detail="LangChain LCEL 已启用；如需 Supervisor 对话，请配置模型 Provider、API Key、模型名和 Base URL。",
        )
    try:
        return supervisor.invoke(payload.message, payload.thread_id)
    except Exception as exc:
        if (
            "Authentication" in exc.__class__.__name__
            or getattr(exc, "status_code", None) in {401, 403}
            or "invalid_api_key" in str(exc)
        ):
            raise HTTPException(
                status_code=502,
                detail="模型认证失败，请在本机更新当前 Provider 对应的 API Key，并确认 Key 与 Base URL 属于同一地域。",
            ) from exc
        raise HTTPException(
            status_code=502,
            detail="LangChain Supervisor 调用失败，请检查模型配置和服务日志。",
        ) from exc


@router.get("/recruitment/requisitions", response_model=list[JobRequisitionRead], tags=["recruitment"])
def list_requisitions(db: DbSession) -> list[JobRequisition]:
    return list(db.scalars(select(JobRequisition).order_by(JobRequisition.created_at.desc())))


@router.get("/recruitment/candidates", response_model=list[CandidateRead], tags=["recruitment"])
def list_candidates(db: DbSession, job_id: int | None = None) -> list[Candidate]:
    query = select(Candidate).order_by(Candidate.created_at.desc())
    if job_id is not None:
        query = query.where(Candidate.job_id == job_id)
    return list(db.scalars(query))


@router.get(
    "/recruitment/interview-notifications",
    response_model=list[InterviewNotificationRead],
    tags=["recruitment"],
)
def list_interview_notifications(
    db: DbSession, job_id: int | None = None
) -> list[InterviewNotification]:
    query = select(InterviewNotification).order_by(
        InterviewNotification.scheduled_for.desc(), InterviewNotification.id
    )
    if job_id is not None:
        query = query.where(InterviewNotification.job_id == job_id)
    return list(db.scalars(query))


@router.post(
    "/recruitment/requisitions",
    response_model=JobRequisitionRead,
    status_code=status.HTTP_201_CREATED,
    tags=["recruitment"],
)
def create_requisition(payload: JobRequisitionCreate, db: DbSession) -> JobRequisition:
    result = get_langchain_runtime().invoke("job_profile", payload.model_dump())
    record = JobRequisition(
        **payload.model_dump(),
        job_profile=result.data,
        status=RecruitmentStatus.PENDING_APPROVAL,
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return record


@router.post("/recruitment/requisitions/{job_id}/approve", response_model=JobRequisitionRead, tags=["recruitment"])
def approve_requisition(job_id: int, db: DbSession) -> JobRequisition:
    record = db.get(JobRequisition, job_id)
    if not record:
        raise HTTPException(status_code=404, detail="招聘需求不存在")
    record.status = RecruitmentStatus.PUBLISHED
    db.commit()
    db.refresh(record)
    return record


@router.post(
    "/recruitment/requisitions/{job_id}/candidates",
    response_model=CandidateRead,
    status_code=status.HTTP_201_CREATED,
    tags=["recruitment"],
)
def screen_candidate(job_id: int, payload: CandidateCreate, db: DbSession) -> Candidate:
    job = db.get(JobRequisition, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="招聘需求不存在")
    result = get_langchain_runtime().invoke(
        "resume_screening",
        {
            "title": job.title,
            "required_skills": job.required_skills,
            "resume_text": payload.resume_text,
        }
    )
    record = Candidate(
        job_id=job.id,
        **payload.model_dump(),
        score=result.data["score"],
        strengths=result.data["matched_skills"],
        gaps=result.data["skill_gaps"],
        recommendation=result.summary,
        status=CandidateStatus.SCREENED,
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return record


@router.post(
    "/recruitment/requisitions/{job_id}/finalize-screening",
    response_model=InterviewSelectionRead,
    tags=["recruitment"],
)
def finalize_screening(job_id: int, db: DbSession) -> InterviewSelectionRead:
    job = db.get(JobRequisition, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="招聘职位不存在")
    candidates = list(
        db.scalars(
            select(Candidate)
            .where(Candidate.job_id == job_id)
            .order_by(Candidate.score.desc(), Candidate.created_at, Candidate.id)
        )
    )
    if not candidates:
        raise HTTPException(status_code=409, detail="该职位还没有已筛选的候选人")

    existing_notifications = list(
        db.scalars(
            select(InterviewNotification)
            .where(InterviewNotification.job_id == job_id)
            .order_by(InterviewNotification.id)
        )
    )
    if existing_notifications:
        selected = sorted(
            (item for item in candidates if item.selection_rank is not None),
            key=lambda item: item.selection_rank or 999,
        )
        return InterviewSelectionRead(
            job_id=job_id,
            selected_count=len(selected),
            selected_candidates=selected,
            notifications=existing_notifications,
            scheduled_for=min(item.scheduled_for for item in existing_notifications),
        )

    selected = candidates[:5]
    selected_ids = {item.id for item in selected}
    selected_at = utc_now()
    # Send on the next day, leaving a full-day buffer inside the user's two-day SLA.
    scheduled_for = selected_at + timedelta(hours=24)
    for rank, candidate in enumerate(selected, start=1):
        candidate.status = CandidateStatus.INTERVIEW
        candidate.selection_rank = rank
        candidate.selected_at = selected_at
    for candidate in candidates:
        if candidate.id not in selected_ids and candidate.status != CandidateStatus.OFFERED:
            candidate.status = CandidateStatus.TALENT_POOL
            candidate.selection_rank = None
            candidate.selected_at = None

    notifications: list[InterviewNotification] = []
    for candidate in selected:
        email_content = (
            f"{candidate.name}，您好：\n\n"
            f"您的简历已通过 AI 初筛，现邀请您参加“{job.title}”职位面试。"
            "具体面试时间与形式将由 HR 与您确认，请留意后续联系。\n\n"
            f"招聘团队\n{job.department}"
        )
        sms_content = (
            f"【HR面试通知】{candidate.name}您好，您的简历已进入“{job.title}”职位面试环节，"
            "具体安排将由HR与您确认，请留意邮件和电话。"
        )
        channel_payloads = [
            (NotificationChannel.EMAIL, candidate.email, f"“{job.title}”职位面试通知", email_content),
            (NotificationChannel.SMS, candidate.phone, "面试通知", sms_content),
        ]
        for channel, recipient, subject, content in channel_payloads:
            if not recipient:
                continue
            notification = InterviewNotification(
                candidate_id=candidate.id,
                job_id=job.id,
                channel=channel,
                recipient=recipient,
                subject=subject,
                content=content,
                scheduled_for=scheduled_for,
                status=initial_notification_status(channel),
            )
            db.add(notification)
            notifications.append(notification)
    job.status = RecruitmentStatus.INTERVIEWING
    db.commit()
    for candidate in selected:
        db.refresh(candidate)
    for notification in notifications:
        db.refresh(notification)
        try:
            enqueue_interview_notification(notification.id, notification.scheduled_for)
        except Exception:
            logger.exception("Failed to enqueue interview notification %s", notification.id)
    return InterviewSelectionRead(
        job_id=job_id,
        selected_count=len(selected),
        selected_candidates=selected,
        notifications=notifications,
        scheduled_for=scheduled_for,
    )


@router.post("/recruitment/interview-notifications/dispatch", tags=["recruitment"])
def dispatch_interview_notifications(db: DbSession) -> dict[str, int]:
    return dispatch_due_notifications(db)


@router.post("/recruitment/candidates/{candidate_id}/decision", response_model=CandidateRead, tags=["recruitment"])
def decide_candidate(candidate_id: int, payload: ApprovalDecision, db: DbSession) -> Candidate:
    candidate = db.get(Candidate, candidate_id)
    if not candidate:
        raise HTTPException(status_code=404, detail="候选人不存在")
    job = db.get(JobRequisition, candidate.job_id)
    if payload.approved:
        candidate.status = CandidateStatus.OFFERED
        if job:
            job.status = RecruitmentStatus.OFFERED
    else:
        candidate.status = CandidateStatus.TALENT_POOL
    db.commit()
    db.refresh(candidate)
    return candidate


@router.post(
    "/onboarding/employees",
    response_model=EmployeeRead,
    status_code=status.HTTP_201_CREATED,
    tags=["onboarding"],
)
def onboard_employee(payload: EmployeeOnboardCreate, db: DbSession) -> Employee:
    email_hash = pii_hash(payload.email)
    existing = db.scalar(select(Employee).where(Employee.email_hash == email_hash))
    if existing:
        raise HTTPException(status_code=409, detail="该邮箱已存在员工档案")
    result = get_langchain_runtime().invoke("onboarding", payload.model_dump())
    employee = Employee(
        **payload.model_dump(),
        email_hash=email_hash,
        status=EmployeeStatus.ONBOARDING,
        onboarding_tasks=result.data["tasks"],
    )
    db.add(employee)
    db.commit()
    db.refresh(employee)
    return employee


@router.post("/onboarding/employees/{employee_id}/complete", response_model=EmployeeRead, tags=["onboarding"])
def complete_onboarding(employee_id: int, db: DbSession) -> Employee:
    employee = require_employee(db, employee_id)
    if employee.status != EmployeeStatus.ONBOARDING:
        raise HTTPException(status_code=409, detail="员工当前不处于入职阶段")
    employee.status = EmployeeStatus.ACTIVE
    db.commit()
    db.refresh(employee)
    return employee


@router.get("/employees", response_model=list[EmployeeRead], tags=["onboarding"])
def list_employees(db: DbSession) -> list[Employee]:
    return list(db.scalars(select(Employee).order_by(Employee.created_at.desc())))


@router.post("/hr/ask", response_model=HRRequestRead, status_code=status.HTTP_201_CREATED, tags=["employee-service"])
def ask_policy(payload: PolicyQuestion, db: DbSession) -> HRRequest:
    if payload.employee_id is not None:
        require_employee(db, payload.employee_id)
    result = get_langchain_runtime().invoke("policy_qa", payload.model_dump())
    record = HRRequest(
        employee_id=payload.employee_id,
        request_type="policy_question",
        content=payload.question,
        result=result.model_dump(),
        status=RequestStatus.PENDING_REVIEW if result.human_review_required else RequestStatus.COMPLETED,
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return record


@router.post(
    "/hr/workflows",
    response_model=HRRequestRead,
    status_code=status.HTTP_201_CREATED,
    tags=["employee-service"],
)
def create_workflow(payload: WorkflowCreate, db: DbSession) -> HRRequest:
    if payload.employee_id is not None:
        require_employee(db, payload.employee_id)
    result = get_langchain_runtime().invoke("workflow_router", payload.model_dump())
    record = HRRequest(
        employee_id=payload.employee_id,
        request_type=result.data["category"],
        content=payload.content,
        result=result.model_dump(),
        status=RequestStatus.PENDING_APPROVAL,
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return record


@router.post("/hr/requests/{request_id}/decision", response_model=HRRequestRead, tags=["employee-service"])
def decide_hr_request(request_id: int, payload: ApprovalDecision, db: DbSession) -> HRRequest:
    record = db.get(HRRequest, request_id)
    if not record:
        raise HTTPException(status_code=404, detail="HR 请求不存在")
    if record.status not in {RequestStatus.PENDING_APPROVAL, RequestStatus.PENDING_REVIEW}:
        raise HTTPException(status_code=409, detail="该请求已处理")
    record.status = RequestStatus.APPROVED if payload.approved else RequestStatus.REJECTED
    result = dict(record.result)
    result["human_decision"] = {"approved": payload.approved, "comment": payload.comment}
    record.result = result
    db.commit()
    db.refresh(record)
    return record


@router.get("/hr/requests", response_model=list[HRRequestRead], tags=["employee-service"])
def list_hr_requests(db: DbSession) -> list[HRRequest]:
    return list(db.scalars(select(HRRequest).order_by(HRRequest.created_at.desc())))


@router.post(
    "/performance/reviews",
    response_model=PerformanceReviewRead,
    status_code=status.HTTP_201_CREATED,
    tags=["performance"],
)
def create_performance_review(payload: PerformanceReviewCreate, db: DbSession) -> PerformanceReview:
    employee = require_employee(db, payload.employee_id)
    result = get_langchain_runtime().invoke("performance_coach", payload.model_dump())
    record = PerformanceReview(**payload.model_dump(), development_plan=result.data)
    if result.data["category"] == "improvement":
        employee.status = EmployeeStatus.IMPROVEMENT
    elif employee.status == EmployeeStatus.ONBOARDING:
        employee.status = EmployeeStatus.ACTIVE
    db.add(record)
    db.commit()
    db.refresh(record)
    return record


@router.get("/performance/reviews", response_model=list[PerformanceReviewRead], tags=["performance"])
def list_performance_reviews(db: DbSession) -> list[PerformanceReview]:
    return list(db.scalars(select(PerformanceReview).order_by(PerformanceReview.created_at.desc())))


@router.post(
    "/offboarding",
    response_model=OffboardingRead,
    status_code=status.HTTP_201_CREATED,
    tags=["offboarding"],
)
def start_offboarding(payload: OffboardingCreate, db: DbSession) -> OffboardingCase:
    employee = require_employee(db, payload.employee_id)
    result = get_langchain_runtime().invoke("offboarding", payload.model_dump())
    record = OffboardingCase(
        **payload.model_dump(),
        handover_items=result.data["handover_items"],
        status=RequestStatus.PENDING_APPROVAL,
    )
    employee.status = EmployeeStatus.OFFBOARDING
    db.add(record)
    db.commit()
    db.refresh(record)
    return record


@router.post("/offboarding/{case_id}/decision", response_model=OffboardingRead, tags=["offboarding"])
def decide_offboarding(case_id: int, payload: ApprovalDecision, db: DbSession) -> OffboardingCase:
    record = db.get(OffboardingCase, case_id)
    if not record:
        raise HTTPException(status_code=404, detail="离职申请不存在")
    if record.status != RequestStatus.PENDING_APPROVAL:
        raise HTTPException(status_code=409, detail="离职申请已处理")
    employee = require_employee(db, record.employee_id)
    record.status = RequestStatus.APPROVED if payload.approved else RequestStatus.REJECTED
    employee.status = EmployeeStatus.OFFBOARDING if payload.approved else EmployeeStatus.ACTIVE
    db.commit()
    db.refresh(record)
    return record


@router.post("/offboarding/{case_id}/complete", response_model=OffboardingRead, tags=["offboarding"])
def complete_offboarding(case_id: int, db: DbSession) -> OffboardingCase:
    record = db.get(OffboardingCase, case_id)
    if not record:
        raise HTTPException(status_code=404, detail="离职申请不存在")
    if record.status != RequestStatus.APPROVED:
        raise HTTPException(status_code=409, detail="离职申请尚未批准")
    employee = require_employee(db, record.employee_id)
    record.status = RequestStatus.COMPLETED
    employee.status = EmployeeStatus.EXITED
    db.commit()
    db.refresh(record)
    return record


@router.get("/offboarding", response_model=list[OffboardingRead], tags=["offboarding"])
def list_offboarding_cases(db: DbSession) -> list[OffboardingCase]:
    return list(db.scalars(select(OffboardingCase).order_by(OffboardingCase.created_at.desc())))


@router.get("/dashboard", tags=["analytics"])
def dashboard(db: DbSession) -> dict[str, Any]:
    def count(model: type[Any]) -> int:
        return int(db.scalar(select(func.count()).select_from(model)) or 0)

    pending_requests = int(
        db.scalar(
            select(func.count())
            .select_from(HRRequest)
            .where(HRRequest.status.in_([RequestStatus.PENDING_APPROVAL, RequestStatus.PENDING_REVIEW]))
        )
        or 0
    )
    pending_requisitions = int(
        db.scalar(
            select(func.count())
            .select_from(JobRequisition)
            .where(JobRequisition.status == RecruitmentStatus.PENDING_APPROVAL)
        )
        or 0
    )
    pending_candidates = int(
        db.scalar(
            select(func.count())
            .select_from(Candidate)
            .where(Candidate.status.in_([CandidateStatus.INTERVIEW, CandidateStatus.HUMAN_REVIEW]))
        )
        or 0
    )
    pending_offboarding = int(
        db.scalar(
            select(func.count())
            .select_from(OffboardingCase)
            .where(OffboardingCase.status == RequestStatus.PENDING_APPROVAL)
        )
        or 0
    )
    return {
        "requisitions": count(JobRequisition),
        "candidates": count(Candidate),
        "employees": count(Employee),
        "hr_requests": count(HRRequest),
        "pending_human_actions": (
            pending_requests + pending_requisitions + pending_candidates + pending_offboarding
        ),
        "performance_reviews": count(PerformanceReview),
        "offboarding_cases": count(OffboardingCase),
    }
