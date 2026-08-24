"""LangChain 运行层：LCEL 调用链与可选的智能 Supervisor。"""

from collections.abc import Mapping
from functools import lru_cache
from importlib.metadata import version
import json
from typing import Any

from langchain.agents import create_agent
from langchain.tools import tool
from langchain_core.runnables import RunnableConfig, RunnableLambda
from langchain_openai import ChatOpenAI

from .agents import get_agent
from .config import Settings, get_langchain_api_key, get_settings
from .schemas import AgentResult, LangChainChatResponse, LangChainStatus


def _json_result(agent_name: str, payload: Mapping[str, Any]) -> str:
    result = get_agent(agent_name).execute(payload)
    return json.dumps(result.model_dump(), ensure_ascii=False)


@tool
def build_job_profile(
    title: str,
    department: str,
    responsibilities: list[str],
    required_skills: list[str],
    salary: str = "面议",
    education: str = "不限",
    experience: str = "不限",
) -> str:
    """根据职位、部门、薪资、学历、经验、岗位职责和技能要求生成职位画像。"""
    return _json_result(
        "job_profile",
        {
            "title": title,
            "department": department,
            "salary": salary,
            "education": education,
            "experience": experience,
            "responsibilities": responsibilities,
            "required_skills": required_skills,
        },
    )


@tool
def screen_resume(title: str, required_skills: list[str], resume_text: str) -> str:
    """按目标职位和必备技能筛选简历，返回可解释匹配分数；不得自行做最终录用决定。"""
    return _json_result(
        "resume_screening",
        {"title": title, "required_skills": required_skills, "resume_text": resume_text},
    )


@tool
def build_onboarding_plan(name: str, department: str, position: str) -> str:
    """为新员工生成 HR、IT、直属经理和员工本人的入职任务。"""
    return _json_result(
        "onboarding",
        {"name": name, "department": department, "position": position},
    )


@tool
def answer_hr_policy(question: str) -> str:
    """回答年假、病假、加班、报销、入职、转正或离职等 HR 政策问题。"""
    return _json_result("policy_qa", {"question": question})


@tool
def route_hr_workflow(content: str) -> str:
    """识别请假、报销、调岗、加班、离职或证明申请，并生成所需审批链。"""
    return _json_result("workflow_router", {"content": content})


@tool
def coach_performance(score: float, manager_feedback: str = "") -> str:
    """根据 1 到 5 分的绩效分数和经理反馈生成发展或改进建议。"""
    return _json_result(
        "performance_coach",
        {"score": score, "manager_feedback": manager_feedback},
    )


@tool
def build_offboarding_plan(reason: str) -> str:
    """根据离职原因生成跨部门工作交接、资产回收和结算清单。"""
    return _json_result("offboarding", {"reason": reason})


LANGCHAIN_TOOLS = [
    build_job_profile,
    screen_resume,
    build_onboarding_plan,
    answer_hr_policy,
    route_hr_workflow,
    coach_performance,
    build_offboarding_plan,
]

SYSTEM_PROMPT = """你是企业人力资源 Agent Supervisor。
你只能基于可用工具处理招聘、入职、员工服务、绩效发展和离职任务。
涉及录用、绩效定级、调岗、薪酬、纪律处分和离职审批时，必须明确提示需要人工确认，不能替代最终决策。
政策工具没有可靠答案时，应建议转 HR 人工服务台。回答使用简洁中文，并说明调用了哪个工具。"""


class LangChainRuntime:
    """为确定性业务 Agent 提供统一的 LCEL 路由、追踪标签和调用配置。"""

    def __init__(self) -> None:
        self._chain = RunnableLambda(self._dispatch).with_config(
            {"run_name": "hr_agent_lcel_router", "tags": ["hr", "human-in-the-loop"]}
        )

    @staticmethod
    def _dispatch(state: Mapping[str, Any]) -> AgentResult:
        result = get_agent(str(state["agent_name"])).execute(state["payload"])
        return result.model_copy(update={"trace": ["LangChain LCEL 路由", *result.trace]})

    def invoke(self, agent_name: str, payload: Mapping[str, Any]) -> AgentResult:
        config: RunnableConfig = {
            "run_name": f"hr_agent.{agent_name}",
            "tags": ["hr-agent", agent_name],
            "metadata": {"agent_name": agent_name, "human_review_policy": "required_when_flagged"},
        }
        return self._chain.invoke(
            {"agent_name": agent_name, "payload": dict(payload)},
            config=config,
        )

    @property
    def tool_names(self) -> list[str]:
        return [item.name for item in LANGCHAIN_TOOLS]


class LangChainSupervisor:
    """由配置的聊天模型驱动，自动选择 HR 工具的 LangChain Agent。"""

    def __init__(self, settings: Settings, api_key: str) -> None:
        if not settings.langchain_model or not settings.langchain_base_url:
            raise ValueError("LangChain 模型和 Base URL 必须同时配置")
        self.model = settings.langchain_model
        chat_model = ChatOpenAI(
            api_key=api_key,
            base_url=settings.langchain_base_url,
            model=settings.langchain_model,
        )
        self._agent = create_agent(
            model=chat_model,
            tools=LANGCHAIN_TOOLS,
            system_prompt=SYSTEM_PROMPT,
            name="hr_supervisor",
        )

    def invoke(self, message: str, thread_id: str = "default") -> LangChainChatResponse:
        result = self._agent.invoke(
            {"messages": [{"role": "user", "content": message}]},
            config={"configurable": {"thread_id": thread_id}},
        )
        final_message = result["messages"][-1]
        content = final_message.content
        if isinstance(content, list):
            answer = "\n".join(
                str(block.get("text", "")) if isinstance(block, dict) else str(block)
                for block in content
            ).strip()
        else:
            answer = str(content)
        return LangChainChatResponse(
            answer=answer,
            model=self.model,
            tools=[item.name for item in LANGCHAIN_TOOLS],
        )


@lru_cache
def get_langchain_runtime() -> LangChainRuntime:
    return LangChainRuntime()


@lru_cache
def get_langchain_supervisor() -> LangChainSupervisor | None:
    settings = get_settings()
    api_key = get_langchain_api_key(settings)
    if not api_key or not settings.langchain_model or not settings.langchain_base_url:
        return None
    return LangChainSupervisor(settings, api_key)


def get_langchain_status() -> LangChainStatus:
    settings = get_settings()
    api_key_configured = get_langchain_api_key(settings) is not None
    return LangChainStatus(
        framework="LangChain",
        version=version("langchain"),
        runtime="create_agent + LCEL",
        supervisor_enabled=(
            api_key_configured
            and settings.langchain_model is not None
            and settings.langchain_base_url is not None
        ),
        provider=settings.llm_provider,
        model=settings.langchain_model,
        base_url=settings.langchain_base_url,
        api_key_configured=api_key_configured,
        tools=[item.name for item in LANGCHAIN_TOOLS],
    )
