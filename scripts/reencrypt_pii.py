"""Rewrite existing PII through the encrypted SQLAlchemy column types."""

from sqlalchemy import select
from sqlalchemy.orm.attributes import flag_modified

from hr_agent.config import get_settings
from hr_agent.crypto import pii_hash
from hr_agent.database import SessionLocal, init_db
from hr_agent.models import (
    Candidate,
    Employee,
    HRRequest,
    InterviewNotification,
    OffboardingCase,
    PerformanceReview,
    User,
)


def main() -> None:
    if not get_settings().data_encryption_key:
        raise SystemExit("请先配置 HR_DATA_ENCRYPTION_KEY")
    init_db()
    rewritten = 0
    with SessionLocal() as db:
        field_map = {
            Candidate: ("name", "email", "phone", "resume_text", "strengths", "gaps", "recommendation"),
            Employee: ("name", "email"),
            HRRequest: ("content", "result"),
            PerformanceReview: ("goals", "manager_feedback", "development_plan"),
            OffboardingCase: ("reason",),
            InterviewNotification: ("recipient", "content"),
            User: ("email", "full_name"),
        }
        for model, fields in field_map.items():
            for record in db.scalars(select(model)):
                for field in fields:
                    flag_modified(record, field)
                if isinstance(record, Employee):
                    record.email_hash = pii_hash(record.email)
                if isinstance(record, User):
                    record.email_hash = pii_hash(record.email)
                rewritten += 1
        db.commit()
    print(f"PII re-encryption complete: {rewritten} records")


if __name__ == "__main__":
    main()
