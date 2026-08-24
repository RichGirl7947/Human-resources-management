from hr_agent.agents import get_agent
from hr_agent.langchain_runtime import LANGCHAIN_TOOLS, get_langchain_runtime


def test_resume_screening_is_explainable():
    result = get_agent("resume_screening").execute(
        {
            "title": "Python 工程师",
            "required_skills": ["Python", "FastAPI", "SQLAlchemy", "pytest"],
            "resume_text": "Python 工程师，熟悉 FastAPI、SQLAlchemy 和 pytest。",
        }
    )
    assert result.data["score"] == 100
    assert result.data["skill_gaps"] == []
    assert result.human_review_required is True


def test_policy_qa_escalates_unknown_question():
    result = get_agent("policy_qa").execute({"question": "公司附近哪里适合团建？"})
    assert result.human_review_required is True
    assert result.data["confidence"] < 0.5


def test_workflow_router_builds_approval_chain():
    result = get_agent("workflow_router").execute({"content": "我要提交差旅费用报销"})
    assert result.data["category"] == "expense"
    assert result.data["approvers"] == ["直属经理", "财务"]


def test_langchain_runtime_routes_existing_agent():
    result = get_langchain_runtime().invoke("policy_qa", {"question": "年假如何申请？"})
    assert result.trace[0] == "LangChain LCEL 路由"
    assert result.data["confidence"] == 0.9


def test_langchain_exposes_seven_typed_tools():
    assert len(LANGCHAIN_TOOLS) == 7
    assert {item.name for item in LANGCHAIN_TOOLS} >= {"answer_hr_policy", "screen_resume", "route_hr_workflow"}
