from collections.abc import Generator

from sqlalchemy import create_engine, event, inspect, select, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from .config import get_settings


class Base(DeclarativeBase):
    pass


settings = get_settings()
connect_args = {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}
engine = create_engine(settings.database_url, connect_args=connect_args, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


if engine.dialect.name == "sqlite":
    @event.listens_for(engine, "connect")
    def _enable_sqlite_foreign_keys(dbapi_connection: object, _: object) -> None:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


def init_db() -> None:
    from . import models  # noqa: F401

    if settings.environment == "production":
        return
    Base.metadata.create_all(bind=engine)
    if engine.dialect.name == "sqlite":
        requisition_columns = {
            str(column["name"]) for column in inspect(engine).get_columns("job_requisitions")
        }
        requisition_additions = {
            "salary": "VARCHAR(120) NOT NULL DEFAULT '面议'",
            "education": "VARCHAR(80) NOT NULL DEFAULT '不限'",
            "experience": "VARCHAR(80) NOT NULL DEFAULT '不限'",
        }
        candidate_columns = {
            str(column["name"]) for column in inspect(engine).get_columns("candidates")
        }
        candidate_additions = {
            "phone": "VARCHAR(40) NOT NULL DEFAULT ''",
            "selection_rank": "INTEGER",
            "selected_at": "DATETIME",
        }
        employee_columns = {
            str(column["name"]) for column in inspect(engine).get_columns("employees")
        }
        employee_additions = {"email_hash": "VARCHAR(64)"}
        notification_columns = {
            str(column["name"]) for column in inspect(engine).get_columns("interview_notifications")
        }
        notification_additions = {
            "task_id": "VARCHAR(80)",
            "attempt_count": "INTEGER NOT NULL DEFAULT 0",
            "claimed_at": "DATETIME",
        }
        with engine.begin() as connection:
            for column_name, definition in requisition_additions.items():
                if column_name not in requisition_columns:
                    connection.execute(
                        text(f"ALTER TABLE job_requisitions ADD COLUMN {column_name} {definition}")
                    )
            for column_name, definition in candidate_additions.items():
                if column_name not in candidate_columns:
                    connection.execute(
                        text(f"ALTER TABLE candidates ADD COLUMN {column_name} {definition}")
                    )
            for column_name, definition in employee_additions.items():
                if column_name not in employee_columns:
                    connection.execute(
                        text(f"ALTER TABLE employees ADD COLUMN {column_name} {definition}")
                    )
            for column_name, definition in notification_additions.items():
                if column_name not in notification_columns:
                    connection.execute(
                        text(f"ALTER TABLE interview_notifications ADD COLUMN {column_name} {definition}")
                    )
            connection.execute(
                text("CREATE UNIQUE INDEX IF NOT EXISTS ix_employees_email_hash ON employees (email_hash)")
            )
        from .crypto import pii_hash
        from .models import Employee

        with SessionLocal() as session:
            employees = list(session.scalars(select(Employee).where(Employee.email_hash.is_(None))))
            for employee in employees:
                employee.email_hash = pii_hash(employee.email)
            session.commit()


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
