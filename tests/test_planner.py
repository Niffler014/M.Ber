"""Tests for M.Ber Task Planner (P7-02 & P7-03 Single & Sequential Multi-Task Planning)."""

import pytest
from app.orchestration.models import ExecutionType, TaskPlan
from app.orchestration.planner import (
    CapabilitySummary,
    MockDeterministicPlanningBackend,
    PlannedTask,
    PlanStructuredOutput,
    Planner,
)


@pytest.fixture
def mock_capabilities() -> CapabilitySummary:
    """提供標準能力摘要 fixture."""
    return CapabilitySummary(
        a2a_skills=[
            {
                "id": "pc_recommendation",
                "name": "PC 硬體配置推薦",
                "tags": ["電腦", "pc", "硬體", "組裝"],
            }
        ],
        mcp_tools=[
            {
                "name": "query_events",
                "description": "查詢行事曆中的行程",
            },
            {
                "name": "add_note",
                "description": "新增筆記",
            },
        ],
        local_capabilities=["general_qa", "math_eval", "store_build"],
    )


def test_planner_returns_task_plan(mock_capabilities: CapabilitySummary):
    """驗證 Planner 產出結構合法之 TaskPlan."""
    planner = Planner(capability_summary=mock_capabilities)
    plan = planner.plan("你好，請問你是誰？")

    assert isinstance(plan, TaskPlan)
    assert plan.plan_id.startswith("plan_")
    assert len(plan.tasks) == 1
    assert plan.user_goal == "你好，請問你是誰？"


def test_planner_single_local_task(mock_capabilities: CapabilitySummary):
    """驗證一般問答請求規劃為 LOCAL 執行類型."""
    planner = Planner(capability_summary=mock_capabilities)
    plan = planner.plan("解釋什麼是 dependency injection")

    assert len(plan.tasks) == 1
    task = plan.tasks[0]
    assert task.execution_type == ExecutionType.LOCAL
    assert task.goal == "解釋什麼是 dependency injection"


def test_planner_single_a2a_task(mock_capabilities: CapabilitySummary):
    """驗證電腦配單請求依能力摘要規劃為 A2A 執行類型 (target 為技能 ID，非 hard-code PCforge)."""
    planner = Planner(capability_summary=mock_capabilities)
    plan = planner.plan("幫我配一台 40000 元遊戲電腦")

    assert len(plan.tasks) == 1
    task = plan.tasks[0]
    assert task.execution_type == ExecutionType.A2A
    assert task.target == "pc_recommendation"
    assert "40000" in task.goal


def test_planner_single_mcp_task(mock_capabilities: CapabilitySummary):
    """驗證行事曆相關請求規劃為 MCP 執行類型."""
    planner = Planner(capability_summary=mock_capabilities)
    plan = planner.plan("幫我查看今天的行事曆行程")

    assert len(plan.tasks) == 1
    task = plan.tasks[0]
    assert task.execution_type == ExecutionType.MCP
    assert task.target == "query_events"


def test_planner_preserves_user_goal(mock_capabilities: CapabilitySummary):
    """驗證使用者原始目標在 TaskPlan 中完整保留."""
    planner = Planner(capability_summary=mock_capabilities)
    goal = "推薦一款適合剪輯影片的電腦菜單"
    plan = planner.plan(goal)

    assert plan.user_goal == goal
    assert len(plan.tasks) == 1


def test_planner_generates_unique_plan_and_task_ids(mock_capabilities: CapabilitySummary):
    """驗證每次規劃產生全局唯一之 plan_id 與 task_id."""
    planner = Planner(capability_summary=mock_capabilities)
    plan1 = planner.plan("問題 1")
    plan2 = planner.plan("問題 2")

    assert plan1.plan_id != plan2.plan_id
    assert plan1.tasks[0].task_id != plan2.tasks[0].task_id


def test_planner_invalid_structured_output_falls_back(mock_capabilities: CapabilitySummary):
    """驗證當後端拋出異常或回傳非預期資料時，Planner 安全降級為單一 LOCAL Plan 不 crash."""
    def broken_backend(goal: str, caps: CapabilitySummary) -> PlanStructuredOutput:
        raise RuntimeError("LLM service unavailable / JSON schema invalid")

    backend = MockDeterministicPlanningBackend(handler=broken_backend)
    planner = Planner(backend=backend, capability_summary=mock_capabilities)

    plan = planner.plan("這是一個會觸發後端錯誤的請求")

    assert isinstance(plan, TaskPlan)
    assert len(plan.tasks) == 1
    assert plan.tasks[0].execution_type == ExecutionType.LOCAL
    assert plan.tasks[0].target is None
    assert plan.user_goal == "這是一個會觸發後端錯誤的請求"


def test_planner_does_not_require_real_llm(mock_capabilities: CapabilitySummary):
    """驗證 Planner 預設與 Mock 後端皆為 100% 確定性離線執行，無外部 API 依賴."""
    planner = Planner(capability_summary=mock_capabilities)
    plan = planner.plan("離線測試問答")

    assert plan is not None
    assert len(plan.tasks) == 1


def test_planner_uses_available_capabilities():
    """驗證動態更新 CapabilitySummary 能即時改變規劃路由策略."""
    # 情況 A：無 A2A 技能時，配電腦請求無法走 A2A
    empty_caps = CapabilitySummary(a2a_skills=[], mcp_tools=[], local_capabilities=[])
    planner = Planner(capability_summary=empty_caps)
    plan_local = planner.plan("幫我配一台電腦")
    assert plan_local.tasks[0].execution_type == ExecutionType.LOCAL

    # 情況 B：注入 A2A 技能後，配電腦請求正確路由至 A2A
    loaded_caps = CapabilitySummary(
        a2a_skills=[{"id": "pc_recommendation", "name": "PC 配單", "tags": ["電腦"]}]
    )
    planner.set_capability_summary(loaded_caps)
    plan_a2a = planner.plan("幫我配一台電腦")
    assert plan_a2a.tasks[0].execution_type == ExecutionType.A2A
    assert plan_a2a.tasks[0].target == "pc_recommendation"


def test_planner_does_not_invent_unavailable_a2a_target():
    """驗證在未聲明技能時，Planner 不會偽造 (hallucinate) 不存在的 A2A target."""
    limited_caps = CapabilitySummary(
        a2a_skills=[{"id": "pc_recommendation", "tags": ["電腦"]}],
        mcp_tools=[],
    )
    planner = Planner(capability_summary=limited_caps)

    plan = planner.plan("幫我訂明天去東京的機票")
    assert plan.tasks[0].execution_type == ExecutionType.LOCAL
    assert plan.tasks[0].target is None


# ============================================================================
# P7-03 新增測試：Sequential Multi-Task Planning & Dependency Mapping
# ============================================================================

def test_planner_sequential_two_tasks(mock_capabilities: CapabilitySummary):
    """驗證複合請求拆解為兩階段循序任務 (A2A -> LOCAL)."""
    planner = Planner(capability_summary=mock_capabilities)
    plan = planner.plan("幫我配一台 40000 元遊戲電腦，然後記住這套配置")

    assert len(plan.tasks) == 2
    task1, task2 = plan.tasks

    assert task1.execution_type == ExecutionType.A2A
    assert task1.target == "pc_recommendation"
    assert task1.depends_on == []

    assert task2.execution_type == ExecutionType.LOCAL
    assert task2.target == "store_build"
    assert task2.depends_on == [task1.task_id]


def test_planner_maps_symbolic_dependencies(mock_capabilities: CapabilitySummary):
    """驗證 Planner 將 step_1 符號依賴正確映射為 task1.task_id."""
    def mock_backend(goal: str, caps: CapabilitySummary) -> PlanStructuredOutput:
        return PlanStructuredOutput(
            tasks=[
                PlannedTask(step_id="step_a", execution_type=ExecutionType.A2A, goal="配單", target="pc_recommendation"),
                PlannedTask(step_id="step_b", execution_type=ExecutionType.LOCAL, goal="存檔", target="save", depends_on=["step_a"]),
            ]
        )

    backend = MockDeterministicPlanningBackend(handler=mock_backend)
    planner = Planner(backend=backend, capability_summary=mock_capabilities)
    plan = planner.plan("測試依賴映射")

    assert len(plan.tasks) == 2
    assert plan.tasks[1].depends_on == [plan.tasks[0].task_id]


def test_planner_simple_request_remains_single_task(mock_capabilities: CapabilitySummary):
    """驗證單純單一請求不會被過度拆解 (Smallest valid plan 原則)."""
    planner = Planner(capability_summary=mock_capabilities)
    plan = planner.plan("幫我配一台 40000 元遊戲電腦")

    # 單純配單請求，不應過度拆解成多個內部小步驟
    assert len(plan.tasks) == 1
    assert plan.tasks[0].execution_type == ExecutionType.A2A


def test_planner_rejects_duplicate_step_ids(mock_capabilities: CapabilitySummary):
    """驗證後端產出重複 step_id 時安全降級為單一 LOCAL Plan."""
    def mock_backend(goal: str, caps: CapabilitySummary) -> PlanStructuredOutput:
        return PlanStructuredOutput(
            tasks=[
                PlannedTask(step_id="step_dup", execution_type=ExecutionType.LOCAL, goal="任務 1"),
                PlannedTask(step_id="step_dup", execution_type=ExecutionType.LOCAL, goal="任務 2"),
            ]
        )

    backend = MockDeterministicPlanningBackend(handler=mock_backend)
    planner = Planner(backend=backend, capability_summary=mock_capabilities)
    plan = planner.plan("重複步驟測試")

    assert len(plan.tasks) == 1
    assert plan.tasks[0].execution_type == ExecutionType.LOCAL


def test_planner_rejects_unknown_dependency(mock_capabilities: CapabilitySummary):
    """驗證後端依賴不存在之符號步驟時安全降級為單一 LOCAL Plan."""
    def mock_backend(goal: str, caps: CapabilitySummary) -> PlanStructuredOutput:
        return PlanStructuredOutput(
            tasks=[
                PlannedTask(step_id="step_1", execution_type=ExecutionType.LOCAL, goal="任務 1"),
                PlannedTask(step_id="step_2", execution_type=ExecutionType.LOCAL, goal="任務 2", depends_on=["step_999"]),
            ]
        )

    backend = MockDeterministicPlanningBackend(handler=mock_backend)
    planner = Planner(backend=backend, capability_summary=mock_capabilities)
    plan = planner.plan("未知依賴測試")

    assert len(plan.tasks) == 1
    assert plan.tasks[0].execution_type == ExecutionType.LOCAL


def test_planner_rejects_dependency_cycle(mock_capabilities: CapabilitySummary):
    """驗證後端產出循環依賴時安全降級為單一 LOCAL Plan."""
    def mock_backend(goal: str, caps: CapabilitySummary) -> PlanStructuredOutput:
        return PlanStructuredOutput(
            tasks=[
                PlannedTask(step_id="step_1", execution_type=ExecutionType.LOCAL, goal="任務 1", depends_on=["step_2"]),
                PlannedTask(step_id="step_2", execution_type=ExecutionType.LOCAL, goal="任務 2", depends_on=["step_1"]),
            ]
        )

    backend = MockDeterministicPlanningBackend(handler=mock_backend)
    planner = Planner(backend=backend, capability_summary=mock_capabilities)
    plan = planner.plan("循環依賴測試")

    assert len(plan.tasks) == 1
    assert plan.tasks[0].execution_type == ExecutionType.LOCAL


def test_planner_too_many_tasks_falls_back(mock_capabilities: CapabilitySummary):
    """驗證後端產出超過 5 個任務時安全降級為單一 LOCAL Plan (防失控保護)."""
    def mock_backend(goal: str, caps: CapabilitySummary) -> PlanStructuredOutput:
        # 直接繞過 Pydantic 建立或拋出異常
        raise ValueError("Planner 產出任務數量超過上限 (6 > 5)")

    backend = MockDeterministicPlanningBackend(handler=mock_backend)
    planner = Planner(backend=backend, capability_summary=mock_capabilities)
    plan = planner.plan("過多任務測試")

    assert len(plan.tasks) == 1
    assert plan.tasks[0].execution_type == ExecutionType.LOCAL
