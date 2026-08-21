"""M.Ber Task Planner (任務規劃器模組).

【新手教學 / 觀念解析】：
1. 什麼是 Planner（任務規劃器）？
   - Planner 是 Agent 接收到使用者自然語言後的第一道關卡。
   - 它的單一職責（Single Responsibility）：分析使用者的目標意圖（user_goal），
     並產出嚴格結構化的任務計畫（`TaskPlan`）。
   - 在 Phase 7 P7-05，Planner 正式感知 `memory_store` 本地記憶能力：
     能夠規劃直接記憶請求（如「記住我喜歡深色模式」），以及多步驟循序記憶工作流（如「先配電腦，然後記住配置」）。
"""

from abc import ABC, abstractmethod
import logging
from typing import Any, Dict, List, Optional, Set
import uuid
from pydantic import BaseModel, Field

from app.orchestration.models import ExecutionType, SubTask, TaskPlan

logger = logging.getLogger("mber.orchestration")

MAX_PLAN_TASKS = 5


class PlannedTask(BaseModel):
    """LLM Structured Output 產出之規劃子任務結構 (DTO)."""

    step_id: str = Field(
        default="step_1",
        description="符號化步驟識別碼 (例如 step_1, step_2)",
    )
    execution_type: ExecutionType = Field(
        ...,
        description="任務執行路由類型 (LOCAL / MCP / A2A)",
    )
    goal: str = Field(..., description="子任務目標描述")
    target: Optional[str] = Field(
        default=None,
        description="執行目標識別 (MCP 時為 tool/capability 名稱，A2A 時為 skill_id 或 agent 名稱，LOCAL 時為 local capability 如 'memory_store')",
    )
    parameters: Dict[str, Any] = Field(
        default_factory=dict,
        description="子任務執行參數",
    )
    depends_on: List[str] = Field(
        default_factory=list,
        description="所依賴之前置符號化步驟識別碼清單 (例如 ['step_1'])",
    )


class PlanStructuredOutput(BaseModel):
    """LLM Structured Output 封裝 (支援 1..N 個子任務，上限 5 個)."""

    tasks: List[PlannedTask] = Field(
        ...,
        min_length=1,
        max_length=MAX_PLAN_TASKS,
        description="規劃產出之子任務清單 (1~5 個)",
    )


class CapabilitySummary(BaseModel):
    """可用能力摘要 (Capability Awareness Snapshot)."""

    a2a_skills: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="已知可用 A2A 技能宣告 (id, name, description, tags)",
    )
    mcp_tools: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="可用 MCP 工具清單 (name, description)",
    )
    local_capabilities: List[str] = Field(
        default_factory=lambda: ["memory_store", "general_qa"],
        description="可用本地功能標籤",
    )

    def to_prompt_text(self) -> str:
        """轉換為 Prompt 注入用之清晰文字摘要."""
        lines = []
        if self.a2a_skills:
            lines.append("【可用 A2A 專門代理人技能 (Skills)】:")
            for s in self.a2a_skills:
                skill_id = s.get("id", "unknown")
                skill_name = s.get("name", "")
                tags = s.get("tags", [])
                lines.append(f"  - skill_id: '{skill_id}', name: '{skill_name}', tags: {tags}")
        else:
            lines.append("【可用 A2A 技能】: 無")

        if self.mcp_tools:
            lines.append("【可用 MCP 工具 (Tools)】:")
            for t in self.mcp_tools:
                lines.append(f"  - tool_name: '{t.get('name')}', desc: '{t.get('description', '')}'")
        else:
            lines.append("【可用 MCP 工具】: 無")

        if self.local_capabilities:
            lines.append(f"【可用本地能力 (Local)】: {', '.join(self.local_capabilities)}")

        return "\n".join(lines)


class BasePlanningBackend(ABC):
    """規劃器後端抽象介面 (支援 LLM 注入與測試 Mock)."""

    @abstractmethod
    def generate_plan_output(
        self,
        user_goal: str,
        capability_summary: CapabilitySummary,
    ) -> PlanStructuredOutput:
        """根據使用者目標與能力摘要產出結構化任務輸出."""
        pass


class MockDeterministicPlanningBackend(BasePlanningBackend):
    """確定性 Mock 規劃後端 (供測試與離線情境使用)."""

    def __init__(
        self,
        handler: Optional[Any] = None,
    ) -> None:
        """初始化 Mock 規劃後端.

        Args:
            handler: 自訂可呼叫之回呼函式 (user_goal, summary) -> PlanStructuredOutput
        """
        self.handler = handler

    def generate_plan_output(
        self,
        user_goal: str,
        capability_summary: CapabilitySummary,
    ) -> PlanStructuredOutput:
        """執行確定性規劃邏輯."""
        if self.handler is not None:
            return self.handler(user_goal, capability_summary)

        ug_lower = user_goal.lower()

        # 1. 檢查是否包含循序多步驟意圖 (Sequential Multi-step Indicator)
        # 例如：「幫我配一台 40000 元遊戲電腦，然後記住這套配置」
        is_sequential_combo = any(
            kw in user_goal for kw in ["然後", "接著", "之後", "完成後", "and then", "after that"]
        )
        has_pc_intent = any(
            k in ug_lower
            for k in [
                "配電腦",
                "組電腦",
                "買電腦",
                "電腦配置",
                "組裝電腦",
                "配單",
                "菜單",
                "推薦電腦",
                "電腦推薦",
                "組主機",
                "配主機",
                "電腦菜單",
                "想配電腦",
                "要配電腦",
                "我想配電腦",
                "我想組電腦",
            ]
        ) or (
            any(k in ug_lower for k in ["電腦", "pc", "主機", "硬體"])
            and any(k in ug_lower for k in ["配", "組", "菜單", "推薦", "預算", "買", "規格", "配置", "單子", "想要", "想買"])
        )
        is_casual_pc_mention = any(
            k in ug_lower
            for k in [
                "我昨天買了",
                "買了一台",
                "買了新",
                "已經買了",
                "入手了",
                "昨天買",
                "為什麼會變慢",
                "為什麼電腦",
                "電腦中毒",
            ]
        )
        if is_casual_pc_mention:
            has_pc_intent = False

        has_store_intent = any(
            k in ug_lower
            for k in [
                "記住",
                "儲存",
                "記錄",
                "儲存配置",
                "記下",
                "記得",
                "記起",
                "remember",
                "store",
                "save",
            ]
        )

        if is_sequential_combo and has_pc_intent and has_store_intent:
            memory_target = "memory_store" if "memory_store" in capability_summary.local_capabilities else "store_build"
            return PlanStructuredOutput(
                tasks=[
                    PlannedTask(
                        step_id="step_1",
                        execution_type=ExecutionType.A2A,
                        goal=user_goal,
                        target="pc_recommendation",
                        depends_on=[],
                    ),
                    PlannedTask(
                        step_id="step_2",
                        execution_type=ExecutionType.LOCAL,
                        goal="儲存產生的電腦配置",
                        target=memory_target,
                        depends_on=["step_1"],
                    ),
                ]
            )

        # 2. 直接記憶請求 (Direct Remember Request)
        # 例如：「記住我喜歡深色模式」、「請幫我記住我的生日是 8/16」
        if has_store_intent and not is_sequential_combo and ("memory_store" in capability_summary.local_capabilities):
            return PlanStructuredOutput(
                tasks=[
                    PlannedTask(
                        step_id="step_1",
                        execution_type=ExecutionType.LOCAL,
                        goal=user_goal,
                        target="memory_store",
                        parameters={"content": user_goal},
                        depends_on=[],
                    )
                ]
            )

        # 3. 單一 A2A 技能比對
        if not is_casual_pc_mention:
            for skill in capability_summary.a2a_skills:
                skill_id = skill.get("id", "").lower()
                skill_name = skill.get("name", "").lower()
                tags = [t.lower() for t in skill.get("tags", [])]
                if (
                    (skill_id and skill_id in ug_lower)
                    or (skill_name and skill_name in ug_lower)
                    or (has_pc_intent and any(k in skill_id for k in ["pc", "build", "hardware", "recommend"]))
                    or any(t in ug_lower for t in tags if len(t) > 2 or t == "pc" or t == "組裝" or t == "配單")
                ):
                    return PlanStructuredOutput(
                        tasks=[
                            PlannedTask(
                                step_id="step_1",
                                execution_type=ExecutionType.A2A,
                                goal=user_goal,
                                target=skill.get("id"),
                                depends_on=[],
                            )
                        ]
                    )

        # 4. 單一 MCP 工具比對
        has_time_intent = any(k in ug_lower for k in ["現在幾點", "幾點", "時間", "time", "clock"])
        has_cal_intent = any(k in ug_lower for k in ["行事曆", "calendar", "行程", "預約", "開會", "events"])
        has_note_intent = any(k in ug_lower for k in ["筆記", "notes", "note", "備忘"])

        for tool in capability_summary.mcp_tools:
            tool_name = tool.get("name", "").lower()
            if tool_name in ug_lower:
                return PlanStructuredOutput(
                    tasks=[
                        PlannedTask(
                            step_id="step_1",
                            execution_type=ExecutionType.MCP,
                            goal=user_goal,
                            target=tool.get("name"),
                            depends_on=[],
                        )
                    ]
                )
            if has_time_intent and any(k in tool_name for k in ["time", "current_time"]):
                return PlanStructuredOutput(
                    tasks=[
                        PlannedTask(
                            step_id="step_1",
                            execution_type=ExecutionType.MCP,
                            goal=user_goal,
                            target=tool.get("name"),
                            depends_on=[],
                        )
                    ]
                )
            if has_cal_intent and any(k in tool_name for k in ["event", "calendar"]):
                return PlanStructuredOutput(
                    tasks=[
                        PlannedTask(
                            step_id="step_1",
                            execution_type=ExecutionType.MCP,
                            goal=user_goal,
                            target=tool.get("name"),
                            depends_on=[],
                        )
                    ]
                )
            if has_note_intent and any(k in tool_name for k in ["note"]):
                return PlanStructuredOutput(
                    tasks=[
                        PlannedTask(
                            step_id="step_1",
                            execution_type=ExecutionType.MCP,
                            goal=user_goal,
                            target=tool.get("name"),
                            depends_on=[],
                        )
                    ]
                )

        # 5. 預設單一 LOCAL 任務
        return PlanStructuredOutput(
            tasks=[
                PlannedTask(
                    step_id="step_1",
                    execution_type=ExecutionType.LOCAL,
                    goal=user_goal,
                    target=None,
                    depends_on=[],
                )
            ]
        )


class LangChainStructuredPlanningBackend(BasePlanningBackend):
    """基於 LangChain Chat Model + Structured Output 之真實規劃後端."""

    SYSTEM_PROMPT_TEMPLATE = """You are M.Ber's task planner.

Your job is to classify and structure the user's request into a sequential task plan.
You may create multiple tasks ONLY when the user's request genuinely requires multiple capabilities or sequential steps (e.g. 'Do X, then remember the result').
Do NOT decompose simple requests unnecessarily.
Prefer the smallest valid plan.
Maximum tasks allowed: 5.
Do NOT invent unavailable agents or tools.
Use symbolic step_id like 'step_1', 'step_2'. Dependencies must refer ONLY to valid step_id declared in the same plan.
Do NOT create dependency cycles.
Do NOT execute tasks.

Execution Types:
- LOCAL: General QA, explanations, reasoning, or local capabilities (e.g. 'memory_store' for storing facts or previous step outputs).
- MCP: Tool operations requiring external services (e.g. database, calendar, time queries).
- A2A: Delegating to specialized external agents when a matching skill is available.

{capabilities_text}
"""

    def __init__(self, llm: Any) -> None:
        """初始化 LangChain Structured Output 後端.

        Args:
            llm: 支援 with_structured_output 之 LangChain ChatModel 實例
        """
        self.llm = llm
        try:
            self.structured_llm = llm.with_structured_output(PlanStructuredOutput)
        except Exception:
            self.structured_llm = llm

    def generate_plan_output(
        self,
        user_goal: str,
        capability_summary: CapabilitySummary,
    ) -> PlanStructuredOutput:
        """調用 LLM 產出 PlanStructuredOutput."""
        from langchain_core.messages import SystemMessage, HumanMessage

        capabilities_text = capability_summary.to_prompt_text()
        system_content = self.SYSTEM_PROMPT_TEMPLATE.format(capabilities_text=capabilities_text)

        messages = [
            SystemMessage(content=system_content),
            HumanMessage(content=user_goal),
        ]

        raw_output = self.structured_llm.invoke(messages)

        if isinstance(raw_output, PlanStructuredOutput):
            return raw_output
        elif isinstance(raw_output, dict):
            return PlanStructuredOutput.model_validate(raw_output)
        elif isinstance(raw_output, str):
            return PlanStructuredOutput.model_validate_json(raw_output)

        raise ValueError(f"無法解析之 LLM 規劃輸出型別: {type(raw_output)}")


class Planner:
    """M.Ber 任務規劃器 (Task Planner)."""

    def __init__(
        self,
        backend: Optional[BasePlanningBackend] = None,
        llm: Optional[Any] = None,
        capability_summary: Optional[CapabilitySummary] = None,
    ) -> None:
        """初始化 Planner.

        Args:
            backend: 規劃後端實例 (優先使用)
            llm: 若無自訂 backend，可傳入 LangChain LLM 自動建立 Structured 後端
            capability_summary: 初始可用能力摘要
        """
        if backend is not None:
            self.backend = backend
        elif llm is not None:
            self.backend = LangChainStructuredPlanningBackend(llm)
        else:
            self.backend = MockDeterministicPlanningBackend()

        self.capability_summary = capability_summary or CapabilitySummary()

    def set_capability_summary(self, summary: CapabilitySummary) -> None:
        """更新可用能力摘要資訊."""
        self.capability_summary = summary

    def plan(self, user_goal: str) -> TaskPlan:
        """將使用者目標規劃為嚴格驗證之 TaskPlan (支援 1..5 個子任務與相依關係).

        Args:
            user_goal: 使用者自然語言請求

        Returns:
            驗證合法之 TaskPlan 實體
        """
        clean_goal = (user_goal or "").strip()
        if not clean_goal:
            clean_goal = "空任務請求"

        logger.info(f"[Planner] Planning request for goal: '{clean_goal}'")

        try:
            output = self.backend.generate_plan_output(clean_goal, self.capability_summary)
            planned_tasks = output.tasks

            if not planned_tasks:
                raise ValueError("Planner 產出之任務清單不可為空")

            if len(planned_tasks) > MAX_PLAN_TASKS:
                raise ValueError(f"Planner 產出任務數量超過上限 ({len(planned_tasks)} > {MAX_PLAN_TASKS})")

            # 1. 檢查 step_id 重複
            seen_step_ids: Set[str] = set()
            for pt in planned_tasks:
                sid = (pt.step_id or "").strip()
                if not sid:
                    raise ValueError("PlannedTask 之 step_id 不得為空")
                if sid in seen_step_ids:
                    raise ValueError(f"PlannedTask 包含重複的 step_id: '{sid}'")
                seen_step_ids.add(sid)

            # 2. 建立符號化 step_id ➔ 領域 task_id 映射表
            step_to_task_id: Dict[str, str] = {
                pt.step_id.strip(): f"task_{uuid.uuid4().hex[:8]}"
                for pt in planned_tasks
            }

            # 3. 轉換為領域 SubTask 並映射相依性
            domain_subtasks: List[SubTask] = []
            for pt in planned_tasks:
                mapped_depends: List[str] = []
                for dep in pt.depends_on:
                    dep_clean = dep.strip()
                    if dep_clean not in step_to_task_id:
                        raise ValueError(
                            f"步驟 '{pt.step_id}' 依賴不存在的符號化步驟: '{dep_clean}'"
                        )
                    mapped_depends.append(step_to_task_id[dep_clean])

                subtask = SubTask(
                    task_id=step_to_task_id[pt.step_id.strip()],
                    execution_type=pt.execution_type,
                    goal=pt.goal,
                    target=pt.target,
                    parameters=pt.parameters,
                    depends_on=mapped_depends,
                )
                domain_subtasks.append(subtask)

            # 4. 建構 TaskPlan (觸發模型層拓撲與 Cycle 檢測)
            plan = TaskPlan(
                plan_id=f"plan_{uuid.uuid4().hex[:8]}",
                user_goal=clean_goal,
                tasks=domain_subtasks,
            )

            logger.info(f"[Planner] Created plan: {plan.plan_id} with {len(plan.tasks)} tasks")
            for t in plan.tasks:
                if t.depends_on:
                    logger.info(f"[Planner] Task {t.task_id} depends on: {t.depends_on}")
            return plan

        except Exception as e:
            logger.warning(f"[Planner] Structured planning failed: {e}")
            logger.info("[Planner] Falling back to safe single LOCAL plan")

            # Fallback 策略：建立單一 LOCAL 任務
            fallback_task = SubTask(
                task_id=f"task_{uuid.uuid4().hex[:8]}",
                execution_type=ExecutionType.LOCAL,
                goal=clean_goal,
                target=None,
                parameters={},
                depends_on=[],
            )
            return TaskPlan(
                plan_id=f"plan_{uuid.uuid4().hex[:8]}",
                user_goal=clean_goal,
                tasks=[fallback_task],
            )
