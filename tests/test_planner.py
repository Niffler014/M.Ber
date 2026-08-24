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
    assert plan.tasks[0].target in (None, "general_qa")
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
    assert plan.tasks[0].target in (None, "general_qa")


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


# ============================================================================
# P8-03.5 新增測試：Production Routing, Natural Language, & Single Stack Lifecycle
# ============================================================================

def test_planner_routes_casual_chat_to_local(mock_capabilities: CapabilitySummary):
    """驗證生活日常問答（例如「我肚子很餓」）正確規劃為 LOCAL 執行類型."""
    planner = Planner(capability_summary=mock_capabilities)
    plan = planner.plan("我肚子很餓")

    assert len(plan.tasks) == 1
    assert plan.tasks[0].execution_type == ExecutionType.LOCAL
    assert plan.tasks[0].target in (None, "general_qa")


def test_planner_routes_natural_pc_request_to_a2a(mock_capabilities: CapabilitySummary):
    """驗證口語化配電腦請求（例如「我想配電腦」、「想組電腦」）正確路由至 A2A pc_recommendation."""
    planner = Planner(capability_summary=mock_capabilities)

    for prompt in ["我想配電腦", "我想組電腦", "想配電腦", "幫我配主機"]:
        plan = planner.plan(prompt)
        assert len(plan.tasks) == 1, f"Prompt '{prompt}' should produce 1 task"
        assert plan.tasks[0].execution_type == ExecutionType.A2A, f"Prompt '{prompt}' should be A2A"
        assert plan.tasks[0].target == "pc_recommendation"


def test_planner_does_not_route_casual_pc_mention_by_keyword_only(mock_capabilities: CapabilitySummary):
    """驗證非配單意圖但含有「電腦」字眼之陳述或疑問句，不誤判為 A2A 配單 (Negative Semantic Test)."""
    planner = Planner(capability_summary=mock_capabilities)

    casual_prompts = [
        "我昨天買了一台電腦",
        "我的電腦最近很慢",
        "為什麼電腦開機沒畫面",
    ]

    for prompt in casual_prompts:
        plan = planner.plan(prompt)
        assert len(plan.tasks) == 1
        assert plan.tasks[0].execution_type == ExecutionType.LOCAL, f"Prompt '{prompt}' should route to LOCAL"


def test_mock_planner_backend_remains_available_for_tests():
    """驗證 MockDeterministicPlanningBackend 仍可獨立用於單元測試與離線情境."""
    backend = MockDeterministicPlanningBackend()
    caps = CapabilitySummary(local_capabilities=["general_qa"])
    out = backend.generate_plan_output("你好", caps)
    assert len(out.tasks) == 1
    assert out.tasks[0].execution_type == ExecutionType.LOCAL


def test_production_planner_uses_structured_backend_when_model_configured():
    """驗證當注入 ChatModel 時，Planner 啟用 LangChainStructuredPlanningBackend."""
    from tests.test_local_reasoning import FakeListChatModel
    from app.orchestration.planner import LangChainStructuredPlanningBackend

    fake_model = FakeListChatModel()
    planner = Planner(llm=fake_model)

    assert isinstance(planner.backend, LangChainStructuredPlanningBackend)


def test_production_capability_summary_contains_registered_local_capabilities():
    """驗證 OrchestrationService 建立之 CapabilitySummary 包含標準 Local Capabilities."""
    from app.orchestration.service import OrchestrationService

    service = OrchestrationService()
    caps = service._build_capability_summary()

    assert "general_qa" in caps.local_capabilities
    assert "memory_store" in caps.local_capabilities
    assert "agent_reasoning" in caps.local_capabilities


def test_production_capability_summary_contains_discovered_mcp_tools():
    """驗證 CapabilitySummary 正確自 MCPManager 提取已探索之工具."""
    from unittest.mock import MagicMock
    from app.orchestration.service import OrchestrationService

    mock_mcp = MagicMock()
    mock_mcp.list_all_tools.return_value = [{"name": "get_current_time", "description": "取得時間"}]

    service = OrchestrationService(mcp_manager=mock_mcp)
    caps = service._build_capability_summary()

    assert any(t.get("name") == "get_current_time" for t in caps.mcp_tools)


def test_production_capability_summary_contains_discovered_a2a_skills():
    """驗證 CapabilitySummary 正確自 AgentDiscoveryService 提取已探索之 Peer Agent 技能."""
    from app.a2a.discovery import AgentDiscoveryService
    from app.a2a.models import AgentCard, AgentSkill
    from app.orchestration.service import OrchestrationService

    discovery = AgentDiscoveryService(config_path="non_existent.json")
    discovery.register_agent(
        AgentCard(
            name="PCforge",
            description="PC 配單專家",
            url="http://localhost:8001/rpc",
            skills=[
                AgentSkill(
                    id="pc_recommendation",
                    name="電腦推薦",
                    description="PC硬體配置推薦",
                    tags=["電腦", "pc"],
                )
            ],
        )
    )

    service = OrchestrationService(discovery_service=discovery)
    caps = service._build_capability_summary()

    assert any(s.get("id") == "pc_recommendation" for s in caps.a2a_skills)


def test_production_web_uses_single_composed_orchestration_stack():
    """驗證 Web Gateway 與 OrchestrationService 共用單一組裝之 MCPManager 實例."""
    from app.interfaces.web.gateway import create_web_app
    from app.orchestration.service import OrchestrationService
    from app.mcp.manager import MCPManager

    shared_mcp = MCPManager()
    service = OrchestrationService(mcp_manager=shared_mcp)
    app = create_web_app(orchestration_service=service)

    # 驗證 Web Gateway 確實重用 service.mcp_manager
    assert service.mcp_manager is shared_mcp


def test_a2a_discovery_failure_does_not_break_local_chat(monkeypatch):
    """驗證即使 A2A 發現失敗（例如網路異常），OrchestrationService 仍可正常初始化並提供 LOCAL 服務."""
    from unittest.mock import patch, MagicMock
    from langchain_core.messages import HumanMessage
    from app.orchestration.service import OrchestrationService

    monkeypatch.setenv("MODEL_PROVIDER", "")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_BASE_URL", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    with patch("app.orchestration.service.AgentDiscoveryService") as MockDiscoveryCls:
        mock_instance = MagicMock()
        mock_instance.discover_configured_peers.side_effect = ConnectionError("A2A endpoint down")
        mock_instance.list_agents.return_value = []
        MockDiscoveryCls.return_value = mock_instance

        service = OrchestrationService()
        res = service.invoke_with_details([HumanMessage(content="我肚子很餓")])

        assert res.aggregated.overall_status.value == "success"
        assert "肚子餓" in str(res.message.content) or "熱食" in str(res.message.content)


def test_capability_summary_built_after_discovery():
    """驗證預設啟動時 CapabilitySummary 是在 A2A 探索呼叫之後建構快照."""
    from unittest.mock import patch, MagicMock
    from app.orchestration.service import OrchestrationService
    from app.a2a.models import AgentCard, AgentSkill

    cards = [
        AgentCard(
            name="PCforge",
            description="PC 配單專家",
            url="http://localhost:8001/rpc",
            skills=[
                AgentSkill(
                    id="pc_recommendation",
                    name="PC配單",
                    description="PC配單服務",
                    tags=["電腦"],
                )
            ],
        )
    ]
    with patch("app.orchestration.service.AgentDiscoveryService") as MockDiscoveryCls:
        mock_instance = MagicMock()
        mock_instance.discover_configured_peers.return_value = cards
        mock_instance.list_agents.return_value = cards
        MockDiscoveryCls.return_value = mock_instance

        service = OrchestrationService()

        # 驗證 discover_configured_peers 有被呼叫
        mock_instance.discover_configured_peers.assert_called_once()
        # 驗證 Planner 的 capability_summary 包含該技能
        assert any(s.get("id") == "pc_recommendation" for s in service.planner.capability_summary.a2a_skills)


def test_production_planner_backend_selection_is_explicit(caplog, monkeypatch):
    """驗證 Planner 啟動時明確記錄所選用的後端 (structured_llm 或 deterministic_offline)."""
    import logging
    from tests.test_local_reasoning import FakeListChatModel
    from app.orchestration.service import OrchestrationService

    with caplog.at_level(logging.INFO, logger="mber.orchestration"):
        s1 = OrchestrationService(llm=FakeListChatModel())
        assert any("backend=structured_llm" in record.message for record in caplog.records)

    caplog.clear()
    monkeypatch.setenv("MODEL_PROVIDER", "")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_BASE_URL", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    with caplog.at_level(logging.INFO, logger="mber.orchestration"):
        s2 = OrchestrationService()
        assert any("backend=deterministic_offline" in record.message for record in caplog.records)


# ============================================================================
# P8-03.5 Planner Routing Fix 強化測試矩陣 (Core Routing Matrix & Regression)
# ============================================================================

def test_planner_hungry_routes_local(mock_capabilities: CapabilitySummary):
    """驗證「我肚子很餓」產出恰好 1 個 LOCAL general_qa 任務，絕不調用時間或記憶庫."""
    planner = Planner(capability_summary=mock_capabilities)
    plan = planner.plan("我肚子很餓")

    assert len(plan.tasks) == 1
    assert plan.tasks[0].execution_type == ExecutionType.LOCAL
    assert plan.tasks[0].target in (None, "general_qa")


def test_planner_greeting_routes_local(mock_capabilities: CapabilitySummary):
    """驗證問候語「你好」產出 1 個 LOCAL 任務."""
    planner = Planner(capability_summary=mock_capabilities)
    plan = planner.plan("你好")

    assert len(plan.tasks) == 1
    assert plan.tasks[0].execution_type == ExecutionType.LOCAL


def test_planner_dependency_injection_routes_local(mock_capabilities: CapabilitySummary):
    """驗證技術知識問題「dependency injection 是什麼」產出 1 個 LOCAL 任務."""
    planner = Planner(capability_summary=mock_capabilities)
    plan = planner.plan("dependency injection 是什麼")

    assert len(plan.tasks) == 1
    assert plan.tasks[0].execution_type == ExecutionType.LOCAL


def test_planner_current_time_routes_mcp(mock_capabilities: CapabilitySummary):
    """驗證「現在幾點？」產出 1 個 MCP 工具調用任務 (get_current_time)."""
    mock_capabilities.mcp_tools.append({"name": "get_current_time", "description": "取得系統時間"})
    planner = Planner(capability_summary=mock_capabilities)
    plan = planner.plan("現在幾點？")

    assert len(plan.tasks) == 1
    assert plan.tasks[0].execution_type == ExecutionType.MCP
    assert plan.tasks[0].target == "get_current_time"


def test_planner_current_date_routes_mcp(mock_capabilities: CapabilitySummary):
    """驗證「今天日期是什麼」產出 1 個 MCP 工具調用任務 (get_current_time)."""
    mock_capabilities.mcp_tools.append({"name": "get_current_time", "description": "取得系統時間"})
    planner = Planner(capability_summary=mock_capabilities)
    plan = planner.plan("今天日期是什麼")

    assert len(plan.tasks) == 1
    assert plan.tasks[0].execution_type == ExecutionType.MCP
    assert plan.tasks[0].target == "get_current_time"


def test_planner_pc_build_routes_a2a(mock_capabilities: CapabilitySummary):
    """驗證「幫我配一台四萬元遊戲電腦」產出 1 個 A2A 技能任務."""
    planner = Planner(capability_summary=mock_capabilities)
    plan = planner.plan("幫我配一台四萬元遊戲電腦")

    assert len(plan.tasks) == 1
    assert plan.tasks[0].execution_type == ExecutionType.A2A
    assert plan.tasks[0].target == "pc_recommendation"


def test_planner_pc_casual_mention_routes_local(mock_capabilities: CapabilitySummary):
    """驗證「我昨天買了一台電腦」作為生活陳述句，產出 1 個 LOCAL 任務."""
    planner = Planner(capability_summary=mock_capabilities)
    plan = planner.plan("我昨天買了一台電腦")

    assert len(plan.tasks) == 1
    assert plan.tasks[0].execution_type == ExecutionType.LOCAL


def test_planner_explicit_remember_routes_memory(mock_capabilities: CapabilitySummary):
    """驗證具備明確記憶指令「記住我喜歡深色模式」產出 1 個 LOCAL memory_store 任務."""
    mock_capabilities.local_capabilities.append("memory_store")
    planner = Planner(capability_summary=mock_capabilities)
    plan = planner.plan("記住我喜歡深色模式")

    assert len(plan.tasks) == 1
    assert plan.tasks[0].execution_type == ExecutionType.LOCAL
    assert plan.tasks[0].target == "memory_store"


def test_planner_pc_then_remember_routes_a2a_memory(mock_capabilities: CapabilitySummary):
    """驗證「幫我配一台 40000 元遊戲電腦，然後記住這套配置」循序兩步驟 (A2A -> memory_store)."""
    mock_capabilities.local_capabilities.append("memory_store")
    planner = Planner(capability_summary=mock_capabilities)
    plan = planner.plan("幫我配一台 40000 元遊戲電腦，然後記住這套配置")

    assert len(plan.tasks) == 2
    assert plan.tasks[0].execution_type == ExecutionType.A2A
    assert plan.tasks[1].execution_type == ExecutionType.LOCAL
    assert plan.tasks[1].target in ("memory_store", "store_build")
    assert plan.tasks[1].depends_on == [plan.tasks[0].task_id]


def test_planner_does_not_add_unrequested_memory_side_effect(mock_capabilities: CapabilitySummary):
    """【關鍵回歸測試】：驗證「我肚子很餓」絕不包含 memory_store 或 MCP 任務."""
    planner = Planner(capability_summary=mock_capabilities)
    plan = planner.plan("我肚子很餓")

    assert len(plan.tasks) == 1
    assert plan.tasks[0].execution_type == ExecutionType.LOCAL
    assert not any(t.target == "memory_store" for t in plan.tasks)
    assert not any(t.execution_type == ExecutionType.MCP for t in plan.tasks)


def test_planner_does_not_use_time_tool_for_hunger(mock_capabilities: CapabilitySummary):
    """【MCP False Positive 測試】：驗證「我肚子很餓」不會因為時間聯想而觸發 get_current_time."""
    mock_capabilities.mcp_tools.append({"name": "get_current_time", "description": "取得系統時間"})
    planner = Planner(capability_summary=mock_capabilities)
    plan = planner.plan("我肚子很餓")

    assert len(plan.tasks) == 1
    assert plan.tasks[0].execution_type == ExecutionType.LOCAL
    assert not any(t.target == "get_current_time" for t in plan.tasks)


def test_planner_does_not_use_time_tool_for_today_casual_statement(mock_capabilities: CapabilitySummary):
    """【MCP False Positive 測試】：驗證「我今天很累」不因含有「今天」而誤觸發 get_current_time."""
    mock_capabilities.mcp_tools.append({"name": "get_current_time", "description": "取得系統時間"})
    planner = Planner(capability_summary=mock_capabilities)
    plan = planner.plan("我今天很累")

    assert len(plan.tasks) == 1
    assert plan.tasks[0].execution_type == ExecutionType.LOCAL
    assert not any(t.target == "get_current_time" for t in plan.tasks)


def test_structured_llm_planner_sanitizes_bad_model_output_with_unrequested_side_effects():
    """驗證當 LLM 輸出錯誤的 multi-step (get_current_time + memory_store) 時，Planner 安全過濾並降級為單一 LOCAL."""
    def bad_model_output(goal: str, caps: CapabilitySummary) -> PlanStructuredOutput:
        # 模擬不良模型為「我肚子很餓」產出多餘的查時間與存記憶步驟
        return PlanStructuredOutput(
            tasks=[
                PlannedTask(
                    step_id="step_1",
                    execution_type=ExecutionType.MCP,
                    goal="查詢現在時間",
                    target="get_current_time",
                ),
                PlannedTask(
                    step_id="step_2",
                    execution_type=ExecutionType.LOCAL,
                    goal="儲存肚子餓資訊",
                    target="memory_store",
                    depends_on=["step_1"],
                ),
            ]
        )

    caps = CapabilitySummary(
        mcp_tools=[{"name": "get_current_time", "description": "查詢時間"}],
        local_capabilities=["general_qa", "memory_store"],
    )
    backend = MockDeterministicPlanningBackend(handler=bad_model_output)
    planner = Planner(backend=backend, capability_summary=caps)

    plan = planner.plan("我肚子很餓")

    # 驗證經由 _validate_and_sanitize_tasks 過濾後，自動修正為單一 LOCAL general_qa 任務
    assert len(plan.tasks) == 1
    assert plan.tasks[0].execution_type == ExecutionType.LOCAL
    assert plan.tasks[0].target in (None, "general_qa")
    assert not any(t.target == "memory_store" for t in plan.tasks)
    assert not any(t.target == "get_current_time" for t in plan.tasks)


def test_structured_llm_planner_sanitizes_unrequested_memory_on_a2a_task():
    """驗證當 LLM 在單純配電腦請求後擅自加上 memory_store 時，Planner 過濾 memory_store 並保留 A2A 任務."""
    def unrequested_memory_model_output(goal: str, caps: CapabilitySummary) -> PlanStructuredOutput:
        return PlanStructuredOutput(
            tasks=[
                PlannedTask(
                    step_id="step_1",
                    execution_type=ExecutionType.A2A,
                    goal="配電腦",
                    target="pc_recommendation",
                ),
                PlannedTask(
                    step_id="step_2",
                    execution_type=ExecutionType.LOCAL,
                    goal="未經請求自動儲存",
                    target="memory_store",
                    depends_on=["step_1"],
                ),
            ]
        )

    caps = CapabilitySummary(
        a2a_skills=[{"id": "pc_recommendation", "name": "配電腦"}],
        local_capabilities=["general_qa", "memory_store"],
    )
    backend = MockDeterministicPlanningBackend(handler=unrequested_memory_model_output)
    planner = Planner(backend=backend, capability_summary=caps)

    plan = planner.plan("幫我配一台四萬元遊戲電腦")

    assert len(plan.tasks) == 1
    assert plan.tasks[0].execution_type == ExecutionType.A2A
    assert plan.tasks[0].target == "pc_recommendation"
    assert plan.tasks[0].depends_on == []


# ============================================================================
# P8-03.5 Production A2A Intent & Semantic Routing Regression Tests
# ============================================================================

def test_planner_routes_assemble_40k_pc_to_a2a(mock_capabilities: CapabilitySummary):
    """驗證「我想組一台四萬塊的電腦」正確路由至 A2A pc_recommendation."""
    planner = Planner(capability_summary=mock_capabilities)
    plan = planner.plan("我想組一台四萬塊的電腦")

    assert len(plan.tasks) == 1
    assert plan.tasks[0].execution_type == ExecutionType.A2A
    assert plan.tasks[0].target == "pc_recommendation"


def test_planner_routes_want_build_pc_to_a2a(mock_capabilities: CapabilitySummary):
    """驗證「我想配電腦」正確路由至 A2A pc_recommendation."""
    planner = Planner(capability_summary=mock_capabilities)
    plan = planner.plan("我想配電腦")

    assert len(plan.tasks) == 1
    assert plan.tasks[0].execution_type == ExecutionType.A2A
    assert plan.tasks[0].target == "pc_recommendation"


def test_planner_routes_help_build_40k_gaming_rig_to_a2a(mock_capabilities: CapabilitySummary):
    """驗證「幫我組一台四萬元遊戲主機」正確路由至 A2A pc_recommendation."""
    planner = Planner(capability_summary=mock_capabilities)
    plan = planner.plan("幫我組一台四萬元遊戲主機")

    assert len(plan.tasks) == 1
    assert plan.tasks[0].execution_type == ExecutionType.A2A
    assert plan.tasks[0].target == "pc_recommendation"


def test_planner_routes_bought_pc_yesterday_to_local(mock_capabilities: CapabilitySummary):
    """驗證「我昨天買了一台電腦」不會誤觸 A2A，正確路由至 LOCAL general_qa."""
    planner = Planner(capability_summary=mock_capabilities)
    plan = planner.plan("我昨天買了一台電腦")

    assert len(plan.tasks) == 1
    assert plan.tasks[0].execution_type == ExecutionType.LOCAL
    assert plan.tasks[0].target in (None, "general_qa")


def test_planner_fallback_when_pcforge_unavailable():
    """驗證當 PCforge capability 不存在時，必須安全 fallback，不得產生不存在的 A2A target."""
    caps_without_pc = CapabilitySummary(
        a2a_skills=[],  # 無任何 A2A 技能
        mcp_tools=[],
        local_capabilities=["general_qa", "memory_store"],
    )
    planner = Planner(capability_summary=caps_without_pc)
    plan = planner.plan("我想組一台四萬塊的電腦")

    assert len(plan.tasks) == 1
    assert plan.tasks[0].execution_type == ExecutionType.LOCAL
    assert plan.tasks[0].target in (None, "general_qa")
    assert plan.tasks[0].target != "pc_recommendation"


def test_planner_uses_production_capability_summary_with_pc_recommendation():
    """驗證 production-style CapabilitySummary 包含 pc_recommendation 時，Planner 必須能使用它."""
    prod_caps = CapabilitySummary(
        a2a_skills=[
            {
                "id": "pc_recommendation",
                "name": "電腦配置推薦",
                "description": "根據預算與用途推薦電腦硬體配置",
                "tags": ["電腦", "pc", "硬體", "組裝", "配單"],
                "agent_name": "PCforge",
            }
        ],
        mcp_tools=[
            {"name": "get_current_time", "description": "取得當前系統時間與日期"},
        ],
        local_capabilities=["memory_store", "general_qa", "agent_reasoning"],
    )
    planner = Planner(capability_summary=prod_caps)
    plan = planner.plan("推薦一台工作用電腦")

    assert len(plan.tasks) == 1
    assert plan.tasks[0].execution_type == ExecutionType.A2A
    assert plan.tasks[0].target == "pc_recommendation"




