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


LOCAL_CAPABILITY_DESCRIPTIONS: Dict[str, str] = {
    "general_qa": "Default capability for casual conversation, explanations, reasoning, advice, brainstorming, and generic questions that do not require external tools or agents. (No side effects).",
    "memory_store": "Persist information into long-term memory. STRICT RESTRICTION: Use ONLY when the user EXPLICITLY commands to remember, save, or store information (e.g. '記住...', '幫我存下來', 'remember this'). This causes a side effect and MUST NEVER be used for casual statements or unrequested helpful storage.",
    "agent_reasoning": "Structured local analysis and task reasoning.",
}


def _has_explicit_memory_intent(text: str) -> bool:
    """檢查文字是否包含明確儲存/記憶意圖 (非推測性)."""
    t_lower = text.lower()
    return any(
        kw in t_lower
        for kw in [
            "記住",
            "幫我記住",
            "幫我保存",
            "存下來",
            "儲存",
            "記錄",
            "記下",
            "記得",
            "記起",
            "remember",
            "store",
            "save",
            "memorize",
            "keep in mind",
        ]
    )


def _has_explicit_time_intent(text: str) -> bool:
    """檢查文字是否包含明確時間/日期查詢意圖."""
    t_lower = text.lower()
    return any(
        kw in t_lower
        for kw in [
            "幾點",
            "現在幾點",
            "目前幾點",
            "現在時間",
            "當前時間",
            "目前時間",
            "系統時間",
            "今天日期",
            "現在日期",
            "幾月幾號",
            "星期幾",
            "禮拜幾",
            "what time",
            "current time",
            "current date",
            "what is the date",
            "what day is it",
        ]
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
        """轉換為 Prompt 注入用之清晰文字摘要 (含語意與副作用約束說明)."""
        lines = []
        if self.local_capabilities:
            lines.append("【可用本地能力 (Local Capabilities)】:")
            for cap in self.local_capabilities:
                desc = LOCAL_CAPABILITY_DESCRIPTIONS.get(cap, "Local execution capability.")
                lines.append(f"  - capability: '{cap}', desc: '{desc}'")
        else:
            lines.append("【可用本地能力】: 無")

        if self.mcp_tools:
            lines.append("【可用 MCP 外部工具 (Tools)】:")
            for t in self.mcp_tools:
                lines.append(f"  - tool_name: '{t.get('name')}', desc: '{t.get('description', '')}'")
        else:
            lines.append("【可用 MCP 工具】: 無")

        if self.a2a_skills:
            lines.append("【可用 A2A 專門代理人技能 (Skills)】:")
            for s in self.a2a_skills:
                skill_id = s.get("id", "unknown")
                skill_name = s.get("name", "")
                tags = s.get("tags", [])
                lines.append(f"  - skill_id: '{skill_id}', name: '{skill_name}', tags: {tags}")
        else:
            lines.append("【可用 A2A 技能】: 無")

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
        if has_store_intent and not is_sequential_combo:
            if "memory_store" in capability_summary.local_capabilities:
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
            else:
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
        has_time_intent = _has_explicit_time_intent(user_goal)
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
        default_target = "general_qa" if "general_qa" in capability_summary.local_capabilities else None
        return PlanStructuredOutput(
            tasks=[
                PlannedTask(
                    step_id="step_1",
                    execution_type=ExecutionType.LOCAL,
                    goal=user_goal,
                    target=default_target,
                    depends_on=[],
                )
            ]
        )


class LangChainStructuredPlanningBackend(BasePlanningBackend):
    """基於 LangChain Chat Model + Structured Output 之真實規劃後端."""

    SYSTEM_PROMPT_TEMPLATE = """You are M.Ber's Task Planner.

Your single job is to analyze the user's explicit request and produce the SMALLEST VALID sequential task plan (`PlanStructuredOutput`).

=== CRITICAL PLANNING RULES ===
1. SMALLEST VALID PLAN RULE:
   - Most user requests require EXACTLY ONE task.
   - Do NOT add helpful extra steps, unrequested tool lookups, or proactive memory writes.
   - You may create multiple tasks (maximum 5) ONLY when the user explicitly requests multiple actions (e.g. "Do X and then do Y") or when an explicitly requested action strictly depends on the output of a preceding capability.

2. DEFAULT TO LOCAL `general_qa`:
   - `LOCAL` with target `general_qa` is the DEFAULT semantic capability.
   - Casual conversation, feelings, greetings (e.g. "我肚子很餓", "你好", "我今天很累"), explanations (e.g. "dependency injection 是什麼"), opinions, advice, and general knowledge questions MUST be planned as a SINGLE `LOCAL` task with target `general_qa`.

3. MCP TOOL ROUTING (NECESSITY-BASED):
   - MCP tools MUST be used ONLY when the user's request explicitly requires external/real-time tool data (e.g. "現在幾點" -> `get_current_time`, "查看行事曆" -> calendar tools).
   - NEVER call `get_current_time` or other tools for casual conversation, hunger, fatigue, or feelings, even if words like "現在" or "今天" appear incidentally in casual speech (e.g. "我肚子很餓", "我今天心情很好" MUST NOT call time tools).

4. SIDE-EFFECT RESTRICTION (STRICT):
   - Capabilities with side effects (such as `memory_store` for persisting memory, writing database records, or sending external messages) MUST NEVER be generated unless the user EXPLICITLY commands to remember/save/store/record the information using words like "記住", "幫我存下來", "儲存", "記得", "remember", "save", "store".
   - NEVER add `memory_store` as a helpful closing step unless explicitly requested.

5. A2A SPECIALIZED AGENTS:
   - Route to `A2A` ONLY when the request genuinely matches a specialized peer agent skill (e.g. "幫我配一台四萬元遊戲電腦" -> A2A skill `pc_recommendation`).
   - Casual mentions or general troubleshooting (e.g. "我昨天買了一台電腦", "我的電腦最近很慢") do NOT match PC build recommendation skills and MUST route to `LOCAL` `general_qa`.

=== FEW-SHOT EXAMPLES ===
- User: "我肚子很餓"
  Plan: [PlannedTask(step_id="step_1", execution_type="local", target="general_qa", goal="我肚子很餓")]

- User: "你好"
  Plan: [PlannedTask(step_id="step_1", execution_type="local", target="general_qa", goal="你好")]

- User: "dependency injection 是什麼"
  Plan: [PlannedTask(step_id="step_1", execution_type="local", target="general_qa", goal="dependency injection 是什麼")]

- User: "現在幾點"
  Plan: [PlannedTask(step_id="step_1", execution_type="mcp", target="get_current_time", goal="查詢現在時間")]

- User: "記住我喜歡深色模式"
  Plan: [PlannedTask(step_id="step_1", execution_type="local", target="memory_store", goal="記住我喜歡深色模式", parameters={{"content": "我喜歡深色模式"}})]

- User: "幫我配一台四萬元遊戲電腦"
  Plan: [PlannedTask(step_id="step_1", execution_type="a2a", target="pc_recommendation", goal="幫我配一台四萬元遊戲電腦")]

- User: "我昨天買了一台電腦"
  Plan: [PlannedTask(step_id="step_1", execution_type="local", target="general_qa", goal="我昨天買了一台電腦")]

- User: "幫我配一台四萬元遊戲電腦，然後記住這套配置"
  Plan: [
    PlannedTask(step_id="step_1", execution_type="a2a", target="pc_recommendation", goal="幫我配一台四萬元遊戲電腦"),
    PlannedTask(step_id="step_2", execution_type="local", target="memory_store", goal="儲存電腦配置", depends_on=["step_1"])
  ]

=== AVAILABLE CAPABILITIES ===
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

    def _validate_and_sanitize_tasks(
        self,
        goal: str,
        tasks: List[PlannedTask],
    ) -> List[PlannedTask]:
        """通用安全與語意驗證：過濾未經使用者明確要求的副作用（如 memory_store）與無關工具調用."""
        has_memory = _has_explicit_memory_intent(goal)
        has_time = _has_explicit_time_intent(goal)

        sanitized: List[PlannedTask] = []
        filtered_step_ids: Set[str] = set()

        for t in tasks:
            # 1. 檢查 memory_store 副作用
            if t.target in ("memory_store", "store_build") and not has_memory:
                logger.warning(
                    f"[Planner] Filtered unrequested side-effect task '{t.target}' (goal: '{goal}')"
                )
                filtered_step_ids.add(t.step_id)
                continue

            # 2. 檢查時間工具是否具備明確查詢意圖
            if (
                t.execution_type == ExecutionType.MCP
                and (t.target or "").lower() in ("get_current_time", "current_time")
                and not has_time
            ):
                logger.warning(
                    f"[Planner] Filtered unrequested time tool '{t.target}' (goal: '{goal}')"
                )
                filtered_step_ids.add(t.step_id)
                continue

            sanitized.append(t)

        # 若所有任務皆被過濾（例如原 plan 僅有 unrequested time + unrequested memory），回退為單一 LOCAL general_qa 任務
        if not sanitized:
            logger.info("[Planner] All planned tasks were unrequested/invalid; sanitized to single LOCAL task")
            default_target = "general_qa" if "general_qa" in self.capability_summary.local_capabilities else None
            return [
                PlannedTask(
                    step_id="step_1",
                    execution_type=ExecutionType.LOCAL,
                    goal=goal,
                    target=default_target,
                    depends_on=[],
                )
            ]

        # 僅清理被過濾掉的 step_id (若依賴未曾存在之未知 step_id 則保留以觸發後續的 unknown dependency 驗證與 fallback)
        if filtered_step_ids:
            for t in sanitized:
                t.depends_on = [dep for dep in t.depends_on if dep not in filtered_step_ids]

        return sanitized

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
            raw_planned_tasks = output.tasks

            if not raw_planned_tasks:
                raise ValueError("Planner 產出之任務清單不可為空")

            if len(raw_planned_tasks) > MAX_PLAN_TASKS:
                raise ValueError(f"Planner 產出任務數量超過上限 ({len(raw_planned_tasks)} > {MAX_PLAN_TASKS})")

            # 0. 執行通用安全與語意驗證 (Smallest Valid Plan / Side-effect Guardrail)
            planned_tasks = self._validate_and_sanitize_tasks(clean_goal, raw_planned_tasks)

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
            fallback_target = "general_qa" if "general_qa" in self.capability_summary.local_capabilities else None
            fallback_task = SubTask(
                task_id=f"task_{uuid.uuid4().hex[:8]}",
                execution_type=ExecutionType.LOCAL,
                goal=clean_goal,
                target=fallback_target,
                parameters={},
                depends_on=[],
            )
            return TaskPlan(
                plan_id=f"plan_{uuid.uuid4().hex[:8]}",
                user_goal=clean_goal,
                tasks=[fallback_task],
            )
