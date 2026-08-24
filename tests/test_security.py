from fastapi.testclient import TestClient
from sqlalchemy import select, text

from hr_agent.database import SessionLocal, engine
from hr_agent.main import app
from hr_agent.models import User


ADMIN_EMAIL = "test-admin@example.com"
ADMIN_PASSWORD = "StrongTestPassword2026"


def admin_client() -> TestClient:
    client = TestClient(app)
    client.__enter__()
    if client.get("/api/v1/auth/bootstrap-status").json()["required"]:
        response = client.post(
            "/api/v1/auth/bootstrap",
            json={
                "email": ADMIN_EMAIL,
                "full_name": "测试管理员",
                "password": ADMIN_PASSWORD,
                "role": "admin",
                "bootstrap_token": "",
            },
        )
    else:
        response = client.post(
            "/api/v1/auth/login",
            json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
        )
    client.headers["Authorization"] = f"Bearer {response.json()['access_token']}"
    return client


def test_auth_roles_encryption_audit_and_security_headers():
    client = admin_client()
    try:
        recruiter = client.post(
            "/api/v1/admin/users",
            json={
                "email": "recruiter@example.com",
                "full_name": "招聘专员",
                "password": "RecruiterPassword2026",
                "role": "recruiter",
            },
        )
        assert recruiter.status_code == 201
        login = client.post(
            "/api/v1/auth/login",
            json={"email": "recruiter@example.com", "password": "RecruiterPassword2026"},
        )
        recruiter_headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
        allowed = client.post(
            "/api/v1/recruitment/requisitions",
            headers=recruiter_headers,
            json={
                "title": "安全测试工程师",
                "department": "质量部",
                "responsibilities": ["安全测试"],
                "required_skills": ["Python"],
            },
        )
        assert allowed.status_code == 201
        forbidden = client.post(
            "/api/v1/onboarding/employees",
            headers=recruiter_headers,
            json={
                "name": "无权限用户",
                "email": "denied@example.com",
                "department": "质量部",
                "position": "测试",
                "start_date": "2026-09-01",
            },
        )
        assert forbidden.status_code == 403

        with SessionLocal() as db:
            user = next(item for item in db.scalars(select(User)) if item.full_name == "招聘专员")
            assert user is not None
            assert user.password_hash.startswith("$argon2")
        with engine.connect() as connection:
            stored_email, stored_name = connection.execute(
                text("SELECT email, full_name FROM users WHERE email_hash = :email_hash"),
                {"email_hash": user.email_hash},
            ).one()
            assert stored_email.startswith("enc:v1:")
            assert stored_name.startswith("enc:v1:")

        logs = client.get("/api/v1/admin/audit-logs").json()
        assert any(item["path"] == "/api/v1/admin/users" for item in logs)
        root = client.get("/")
        assert root.headers["x-content-type-options"] == "nosniff"
        assert "default-src 'self'" in root.headers["content-security-policy"]
    finally:
        client.__exit__(None, None, None)
