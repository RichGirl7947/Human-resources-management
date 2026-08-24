from abc import ABC, abstractmethod
from collections.abc import Mapping
from typing import Any

from .schemas import AgentResult


class BaseAgent(ABC):
    name: str
    description: str

    @abstractmethod
    def execute(self, payload: Mapping[str, Any]) -> AgentResult:
        raise NotImplementedError


class JobProfileAgent(BaseAgent):
    name = "job_profile"
    description = "根据用人需求生成结构化职位画像"

    def execute(self, payload: Mapping[str, Any]) -> AgentResult:
        skills = [str(item).strip() for item in payload.get("required_skills", []) if str(item).strip()]
        responsibilities = [str(item).strip() for item in payload.get("responsibilities", []) if str(item).strip()]
        profile = {
            "position": payload["title"],
            "department": payload["department"],
            "salary": payload.get("salary", "面议"),
            "education": payload.get("education", "不限"),
            "experience": payload.get("experience", "不限"),
            "mission": f"在{payload['department']}承担{payload['title']}岗位职责并交付可衡量成果",
            "core_responsibilities": responsibilities,
            "must_have_skills": skills,
            "screening_questions": [f"请说明你在{skill}方面最有代表性的项目经验" for skill in skills[:4]],
            "success_metrics": ["试用期目标完成率", "关键交付按期率", "团队协作反馈"],
        }
        return AgentResult(
            agent=self.name,
            summary=f"已生成 {payload['title']} 职位画像，等待用人需求审批",
            data=profile,
            human_review_required=True,
            trace=["读取岗位职责", "归纳必备技能", "生成筛选问题", "提交人工审批"],
        )


class ResumeScreeningAgent(BaseAgent):
    name = "resume_screening"
    description = "按职位技能要求对简历做可解释匹配"

    def execute(self, payload: Mapping[str, Any]) -> AgentResult:
        resume = str(payload["resume_text"]).casefold()
        title = str(payload["title"]).casefold()
        skills = [str(skill).strip() for skill in payload.get("required_skills", []) if str(skill).strip()]
        matched = [skill for skill in skills if skill.casefold() in resume]
        gaps = [skill for skill in skills if skill not in matched]
        skill_score = (len(matched) / len(skills) * 80) if skills else 40
        title_score = 20 if title in resume else 10
        score = round(min(skill_score + title_score, 100), 1)
        if score >= 75:
            recommendation, status = "建议进入面试，由招聘人员确认", "interview"
        elif score >= 50:
            recommendation, status = "建议人工复核后决定", "human_review"
        else:
            recommendation, status = "匹配度较低，可进入人才库", "rejected"
        return AgentResult(
            agent=self.name,
            summary=recommendation,
            data={
                "score": score,
                "matched_skills": matched,
                "skill_gaps": gaps,
                "recommended_status": status,
            },
            human_review_required=True,
            trace=["标准化简历文本", "匹配职位技能", "计算可解释分数", "提交招聘人员确认"],
        )


class OnboardingAgent(BaseAgent):
    name = "onboarding"
    description = "生成入职任务和新员工引导清单"

    def execute(self, payload: Mapping[str, Any]) -> AgentResult:
        tasks = [
            {"owner": "HR", "task": "核验身份、学历与合同资料", "required": True},
            {"owner": "IT", "task": "创建账号并配置办公设备", "required": True},
            {"owner": "直属经理", "task": "确认导师与试用期目标", "required": True},
            {"owner": "新员工", "task": "完成制度与安全培训", "required": True},
            {"owner": "HR Agent", "task": "发送首周日程与政策入口", "required": True},
        ]
        return AgentResult(
            agent=self.name,
            summary=f"已为 {payload['name']} 生成入职任务",
            data={"tasks": tasks, "position": payload["position"], "department": payload["department"]},
            human_review_required=True,
            trace=["读取员工与岗位信息", "生成跨部门任务", "等待资料核验"],
        )


class PolicyQAAgent(BaseAgent):
    name = "policy_qa"
    description = "回答高频 HR 政策问题，低置信度时转人工"

    POLICIES = (
        ({"年假", "休假", "带薪假"}, "年假额度与司龄相关，请在考勤系统查看个人可用天数；申请需由直属经理审批。", "休假制度"),
        ({"病假", "生病", "医疗"}, "病假应及时提交申请；是否需要医疗证明及薪资计算方式以公司现行制度为准。", "考勤制度"),
        ({"加班", "调休"}, "加班需事前审批并保留记录；符合条件的加班可按公司制度安排调休或结算。", "加班管理制度"),
        ({"报销", "发票", "费用"}, "报销需提交合规票据、费用说明和对应审批记录，并按财务规定的时限发起。", "费用报销制度"),
        ({"离职", "辞职"}, "离职流程通常包含申请、审批、工作交接、资产归还和薪资结算，具体日期以审批结果为准。", "离职管理制度"),
        ({"入职", "试用期", "转正"}, "试用期目标由直属经理确认；转正需完成目标评估、经理评价和规定的审批流程。", "入职与转正制度"),
    )

    def execute(self, payload: Mapping[str, Any]) -> AgentResult:
        question = str(payload["question"])
        matches = []
        for keywords, answer, source in self.POLICIES:
            hit_count = sum(keyword in question for keyword in keywords)
            if hit_count:
                matches.append((hit_count, answer, source))
        if not matches:
            return AgentResult(
                agent=self.name,
                summary="未找到足够可靠的政策依据，已建议转 HR 人工处理",
                data={"answer": "该问题需要结合公司最新制度和个人情况判断，请提交 HR 人工服务单。", "confidence": 0.2},
                human_review_required=True,
                trace=["检索政策知识库", "未达到回答阈值", "转人工服务台"],
            )
        _, answer, source = max(matches, key=lambda item: item[0])
        return AgentResult(
            agent=self.name,
            summary="已根据政策知识库生成答复",
            data={"answer": answer, "source": source, "confidence": 0.9},
            human_review_required=False,
            trace=["识别问题意图", f"命中{source}", "生成带来源答复"],
        )


class WorkflowAgent(BaseAgent):
    name = "workflow_router"
    description = "识别 HR 服务类型并生成审批链"

    ROUTES = (
        (("请假", "休假"), "leave", ["直属经理"]),
        (("报销", "费用"), "expense", ["直属经理", "财务"]),
        (("调岗", "转岗"), "transfer", ["直属经理", "HRBP", "目标部门负责人"]),
        (("加班", "调休"), "overtime", ["直属经理"]),
        (("离职", "辞职"), "offboarding", ["直属经理", "HRBP"]),
        (("证明", "在职证明"), "certificate", ["HR 服务台"]),
    )

    def execute(self, payload: Mapping[str, Any]) -> AgentResult:
        content = str(payload["content"])
        category, approvers = "general", ["HR 服务台"]
        for keywords, route, route_approvers in self.ROUTES:
            if any(keyword in content for keyword in keywords):
                category, approvers = route, route_approvers
                break
        return AgentResult(
            agent=self.name,
            summary=f"已识别为 {category} 流程并生成审批链",
            data={"category": category, "approvers": approvers, "next_step": f"等待 {approvers[0]} 处理"},
            human_review_required=True,
            trace=["识别服务意图", "选择流程模板", "生成审批链", "等待人工审批"],
        )


class PerformanceAgent(BaseAgent):
    name = "performance_coach"
    description = "根据绩效结果生成发展建议或改进计划"

    def execute(self, payload: Mapping[str, Any]) -> AgentResult:
        score = float(payload["score"])
        feedback = str(payload.get("manager_feedback", "")).strip()
        if score >= 4:
            category = "high_performance"
            actions = ["安排高阶能力培训", "承担挑战性项目", "进入晋升或人才盘点讨论"]
        elif score >= 3:
            category = "meets_expectations"
            actions = ["巩固当前岗位能力", "选择一项关键技能提升", "下周期设置可量化进阶目标"]
        else:
            category = "improvement"
            actions = ["与经理确认差距事实", "制定 30/60/90 天改进目标", "每两周复盘进度并保留记录"]
        return AgentResult(
            agent=self.name,
            summary="已生成绩效发展建议，最终评审结论由经理和 HR 确认",
            data={"category": category, "actions": actions, "manager_feedback": feedback},
            human_review_required=True,
            trace=["读取绩效分数", "匹配发展策略", "生成行动建议", "提交人工确认"],
        )


class OffboardingAgent(BaseAgent):
    name = "offboarding"
    description = "生成离职交接与合规检查清单"

    def execute(self, payload: Mapping[str, Any]) -> AgentResult:
        items = [
            {"owner": "员工", "task": "完成工作、文档和客户事项交接"},
            {"owner": "直属经理", "task": "确认交接完整性与接收人"},
            {"owner": "IT", "task": "回收设备并按日期停用账号"},
            {"owner": "行政", "task": "回收门禁卡及其他公司资产"},
            {"owner": "HR", "task": "完成离职访谈、证明和档案更新"},
            {"owner": "薪酬", "task": "核对工资、假期和其他结算项"},
        ]
        return AgentResult(
            agent=self.name,
            summary="已生成离职交接清单，等待审批后执行",
            data={"handover_items": items, "reason": payload["reason"]},
            human_review_required=True,
            trace=["读取离职信息", "生成跨部门交接项", "等待离职审批"],
        )


AGENTS: dict[str, BaseAgent] = {
    agent.name: agent
    for agent in (
        JobProfileAgent(),
        ResumeScreeningAgent(),
        OnboardingAgent(),
        PolicyQAAgent(),
        WorkflowAgent(),
        PerformanceAgent(),
        OffboardingAgent(),
    )
}


def get_agent(name: str) -> BaseAgent:
    try:
        return AGENTS[name]
    except KeyError as exc:
        raise ValueError(f"未知 Agent: {name}") from exc
