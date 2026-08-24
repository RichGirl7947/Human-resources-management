from fastapi.testclient import TestClient

from hr_agent.main import app


ADMIN_EMAIL = "test-admin@example.com"
ADMIN_PASSWORD = "StrongTestPassword2026"


def authenticate(client: TestClient) -> None:
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
    assert response.status_code in {200, 201}
    client.headers["Authorization"] = f"Bearer {response.json()['access_token']}"


def test_employee_lifecycle_api():
    with TestClient(app) as client:
        authenticate(client)
        assert client.get("/health").json()["status"] == "ok"
        chain_status = client.get("/api/v1/langchain/status")
        assert chain_status.status_code == 200
        assert chain_status.json()["framework"] == "LangChain"
        assert len(chain_status.json()["tools"]) == 7

        job = client.post(
            "/api/v1/recruitment/requisitions",
            json={
                "title": "Python 后端工程师",
                "department": "研发中心",
                "headcount": 1,
                "salary": "20K-30K·14薪",
                "education": "本科",
                "experience": "3-5年",
                "responsibilities": ["开发 HR Agent"],
                "required_skills": ["Python", "FastAPI", "SQLAlchemy", "pytest"],
            },
        )
        assert job.status_code == 201
        job_id = job.json()["id"]
        assert job.json()["status"] == "pending_approval"
        assert job.json()["salary"] == "20K-30K·14薪"
        assert job.json()["education"] == "本科"
        assert job.json()["experience"] == "3-5年"
        assert job.json()["job_profile"]["salary"] == "20K-30K·14薪"

        approved = client.post(f"/api/v1/recruitment/requisitions/{job_id}/approve")
        assert approved.json()["status"] == "published"

        candidate = client.post(
            f"/api/v1/recruitment/requisitions/{job_id}/candidates",
            json={
                "name": "张三",
                "email": "zhangsan@example.com",
                "phone": "13800000001",
                "resume_text": "Python 后端工程师，熟悉 FastAPI、SQLAlchemy 和 pytest，拥有五年项目经验。",
            },
        )
        assert candidate.status_code == 201
        assert candidate.json()["status"] == "screened"
        candidate_id = candidate.json()["id"]
        selection = client.post(f"/api/v1/recruitment/requisitions/{job_id}/finalize-screening")
        assert selection.status_code == 200
        assert selection.json()["selected_count"] == 1
        assert selection.json()["selected_candidates"][0]["status"] == "interview"
        assert len(selection.json()["notifications"]) == 2
        decision = client.post(
            f"/api/v1/recruitment/candidates/{candidate_id}/decision",
            json={"approved": True, "comment": "通过面试"},
        )
        assert decision.json()["status"] == "offered"

        employee = client.post(
            "/api/v1/onboarding/employees",
            json={
                "name": "张三",
                "email": "zhangsan@example.com",
                "department": "研发中心",
                "position": "Python 后端工程师",
                "start_date": "2026-09-01",
            },
        )
        assert employee.status_code == 201
        employee_id = employee.json()["id"]
        assert len(employee.json()["onboarding_tasks"]) >= 4
        completed_onboarding = client.post(f"/api/v1/onboarding/employees/{employee_id}/complete")
        assert completed_onboarding.json()["status"] == "active"

        answer = client.post(
            "/api/v1/hr/ask",
            json={"employee_id": employee_id, "question": "年假如何申请？"},
        )
        assert answer.status_code == 201
        assert answer.json()["status"] == "completed"

        workflow = client.post(
            "/api/v1/hr/workflows",
            json={"employee_id": employee_id, "content": "申请下周五休假一天"},
        )
        assert workflow.json()["request_type"] == "leave"
        assert workflow.json()["status"] == "pending_approval"
        workflow_id = workflow.json()["id"]
        workflow_decision = client.post(
            f"/api/v1/hr/requests/{workflow_id}/decision",
            json={"approved": True, "comment": "同意休假"},
        )
        assert workflow_decision.json()["status"] == "approved"

        review = client.post(
            "/api/v1/performance/reviews",
            json={
                "employee_id": employee_id,
                "cycle": "2026-H2",
                "goals": ["上线招聘 Agent"],
                "score": 4.2,
                "manager_feedback": "交付稳定",
            },
        )
        assert review.status_code == 201
        assert review.json()["development_plan"]["category"] == "high_performance"

        offboarding = client.post(
            "/api/v1/offboarding",
            json={
                "employee_id": employee_id,
                "reason": "个人职业发展",
                "last_working_day": "2027-03-31",
            },
        )
        assert offboarding.status_code == 201
        assert offboarding.json()["status"] == "pending_approval"
        case_id = offboarding.json()["id"]
        offboarding_decision = client.post(
            f"/api/v1/offboarding/{case_id}/decision",
            json={"approved": True, "comment": "完成交接后离职"},
        )
        assert offboarding_decision.json()["status"] == "approved"
        completed_offboarding = client.post(f"/api/v1/offboarding/{case_id}/complete")
        assert completed_offboarding.json()["status"] == "completed"

        dashboard = client.get("/api/v1/dashboard")
        assert dashboard.status_code == 200
        assert dashboard.json()["employees"] == 1
        assert dashboard.json()["offboarding_cases"] == 1


def test_ai_shortlist_selects_top_five_and_schedules_two_channel_notifications():
    with TestClient(app) as client:
        authenticate(client)
        job = client.post(
            "/api/v1/recruitment/requisitions",
            json={
                "title": "AI 应用工程师",
                "department": "智能应用部",
                "headcount": 2,
                "responsibilities": ["开发企业 AI 应用"],
                "required_skills": ["Python", "LangChain", "FastAPI", "SQLAlchemy"],
            },
        ).json()
        client.post(f"/api/v1/recruitment/requisitions/{job['id']}/approve")
        for index in range(6):
            response = client.post(
                f"/api/v1/recruitment/requisitions/{job['id']}/candidates",
                json={
                    "name": f"候选人{index + 1}",
                    "email": f"candidate{index + 1}@example.com",
                    "phone": f"138000000{index + 1:02d}",
                    "resume_text": (
                        "拥有 Python、LangChain、FastAPI、SQLAlchemy 企业项目经验，"
                        f"负责过 {index + 1} 个 AI 应用项目。"
                    ),
                },
            )
            assert response.status_code == 201
            assert response.json()["status"] == "screened"

        result = client.post(
            f"/api/v1/recruitment/requisitions/{job['id']}/finalize-screening"
        )
        assert result.status_code == 200
        body = result.json()
        assert body["selected_count"] == 5
        assert [item["selection_rank"] for item in body["selected_candidates"]] == [1, 2, 3, 4, 5]
        assert all(item["status"] == "interview" for item in body["selected_candidates"])
        assert len(body["notifications"]) == 10
        assert {item["channel"] for item in body["notifications"]} == {"email", "sms"}
        assert all(item["status"] == "pending_configuration" for item in body["notifications"])

        all_candidates = client.get(
            f"/api/v1/recruitment/candidates?job_id={job['id']}"
        ).json()
        assert sum(item["status"] == "interview" for item in all_candidates) == 5
        assert sum(item["status"] == "talent_pool" for item in all_candidates) == 1

        repeated = client.post(
            f"/api/v1/recruitment/requisitions/{job['id']}/finalize-screening"
        )
        assert repeated.status_code == 200
        assert len(repeated.json()["notifications"]) == 10
