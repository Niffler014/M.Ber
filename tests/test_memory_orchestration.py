"""Unit and Workflow Tests for M.Ber Memory Capability Integration (P7-05)."""

import pytest
from typing import Any, Dict, List, Optional

from app.orchestration.models import (
    ExecutionContext,
    ExecutionResult,
    ExecutionStatus,
    ExecutionType,
    SubTask,
    TaskPlan,
)
from app.orchestration.executors import A2AExecutor, LocalExecutor
from app.orchestration.memory_adapter import (
    CANONICAL_MEMORY_CAPABILITY,
    MemoryAdapter,
    register_memory_capability,
)
from app.orchestration.router import Router
from app.orchestration.orchestrator import Orchestrator
from app.orchestration.planner import (
    CapabilitySummary,
    MockDeterministicPlanningBackend,
    PlannedTask,
    PlanStructuredOutput,
    Planner,
)
from app.a2a.discovery import AgentDiscoveryService
from app.a2a.models import AgentCard, AgentSkill
from memory.models import MemoryItem, MemoryType
from memory.repository import InMemoryMemoryRepository, MemoryRepository
from memory.service import MemoryService


@pytest.fixture
def fake_memory_service() -> MemoryService:
    repo = InMemoryMemoryRepository()
    return MemoryService(repository=repo)


@pytest.fixture
def mock_capabilities() -> CapabilitySummary:
    return CapabilitySummary(
        a2a_skills=[
            {
                "id": "pc_recommendation",
                "name": "PC 推薦",
                "tags": ["電腦", "pc", "組裝"],
            }
        ],
        mcp_tools=[],
        local_capabilities=["memory_store", "general_qa"],
    )


@pytest.fixture
def mock_discovery() -> AgentDiscoveryService:
    discovery = AgentDiscoveryService(config_path="non_existent_config.json")
    discovery.register_agent(
        AgentCard(
            name="PCforgeMock",
            description="配單專家",
            url="http://mock-pcforge.local/rpc",
            skills=[
                AgentSkill(
                    id="pc_recommendation",
                    name="電腦推薦",
                    description="組裝菜單",
                    tags=["電腦", "pc"],
                )
            ],
        )
    )
    return discovery


# ============================================================================
# 1. Planner Tests with Memory Capability
# ============================================================================

def test_planner_pc_build_then_remember(mock_capabilities: CapabilitySummary):
    """驗證 Planner 將配電腦並記住規劃為 A2A -> LOCAL(memory_store)."""
    planner = Planner(capability_summary=mock_capabilities)
    plan = planner.plan("幫我配一台 40000 元遊戲電腦，然後幫我記住這套配置")

    assert len(plan.tasks) == 2
    t1, t2 = plan.tasks

    assert t1.execution_type == ExecutionType.A2A
    assert t1.target == "pc_recommendation"

    assert t2.execution_type == ExecutionType.LOCAL
    assert t2.target == "memory_store"
    assert t2.depends_on == [t1.task_id]


def test_planner_direct_remember_request(mock_capabilities: CapabilitySummary):
    """驗證單純記住請求規劃為單一 LOCAL(memory_store) 任務."""
    planner = Planner(capability_summary=mock_capabilities)
    plan = planner.plan("記住我喜歡深色模式")

    assert len(plan.tasks) == 1
    task = plan.tasks[0]
    assert task.execution_type == ExecutionType.LOCAL
    assert task.target == "memory_store"
    assert task.parameters.get("content") == "記住我喜歡深色模式"


def test_planner_memory_target_uses_available_capability():
    """驗證 Planner 根據可用能力名稱選擇 canonical memory target."""
    caps = CapabilitySummary(
        a2a_skills=[],
        mcp_tools=[],
        local_capabilities=["memory_store"],
    )
    planner = Planner(capability_summary=caps)
    plan = planner.plan("請幫我記住明天的會議在下午三點")

    assert plan.tasks[0].target == "memory_store"


def test_planner_does_not_invent_memory_capability():
    """驗證當 local_capabilities 無 memory_store 時，不會強行指派不存在的 target."""
    caps = CapabilitySummary(
        a2a_skills=[],
        mcp_tools=[],
        local_capabilities=["general_qa"],
    )
    planner = Planner(capability_summary=caps)
    plan = planner.plan("記住這件事")

    assert plan.tasks[0].target is None


# ============================================================================
# 2. MemoryAdapter Unit Tests
# ============================================================================

def test_memory_handler_stores_explicit_content(fake_memory_service: MemoryService):
    """驗證 MemoryAdapter 正確儲存 task.parameters 提供的明確內容."""
    adapter = MemoryAdapter(memory_service=fake_memory_service)
    task = SubTask(
        task_id="t_mem_1",
        execution_type=ExecutionType.LOCAL,
        target="memory_store",
        goal="記錄偏好",
        parameters={"content": "使用者喜歡使用 Python 3.14", "memory_type": "user_preference"},
    )

    res = adapter.store_memory_handler(task)
    assert res["status"] == "stored"
    assert "Python 3.14" in res["content"]
    assert res["memory_type"] == "user_preference"

    # 驗證 MemoryService 內確有此筆記憶
    saved = fake_memory_service.recall(res["memory_id"])
    assert saved is not None
    assert "Python 3.14" in saved.content


def test_memory_handler_stores_dependency_result(fake_memory_service: MemoryService):
    """驗證 MemoryAdapter 從 ExecutionContext 提取前置任務產出並寫入記憶體."""
    adapter = MemoryAdapter(memory_service=fake_memory_service)
    task = SubTask(
        task_id="t_mem_2",
        execution_type=ExecutionType.LOCAL,
        target="memory_store",
        goal="儲存前一步成果",
        depends_on=["t_prev_pc"],
    )
    context = ExecutionContext(
        dependency_results={
            "t_prev_pc": ExecutionResult(
                task_id="t_prev_pc",
                execution_type=ExecutionType.A2A,
                status=ExecutionStatus.SUCCESS,
                result="【遊戲電腦菜單】：RTX 4060 + Ryzen 7500F",
            )
        }
    )

    res = adapter.store_memory_handler(task, context=context)
    assert res["status"] == "stored"
    assert "RTX 4060" in res["content"]

    saved = fake_memory_service.recall(res["memory_id"])
    assert saved is not None
    assert saved.metadata.get("source_task_id") == "t_prev_pc"


def test_memory_handler_missing_content_returns_failed(fake_memory_service: MemoryService):
    """驗證未提供 content 且無依賴結果時，執行拋出例外且 LocalExecutor 捕捉為 FAILED."""
    local_exec = LocalExecutor()
    register_memory_capability(local_exec, memory_service=fake_memory_service)

    task = SubTask(
        task_id="t_empty_mem",
        execution_type=ExecutionType.LOCAL,
        target="memory_store",
        goal="空內容記憶",
        parameters={},
    )

    res = local_exec.execute(task)
    assert res.status == ExecutionStatus.FAILED
    assert "未提供 content" in res.error


def test_memory_handler_service_failure_returns_failed():
    """驗證 MemoryService 異常時 LocalExecutor 捕捉為 FAILED 不 crash."""
    class BrokenMemoryService(MemoryService):
        def remember(self, content, memory_type=MemoryType.GENERAL, metadata=None):
            raise RuntimeError("Disk I/O failure in storage")

    local_exec = LocalExecutor()
    broken_service = BrokenMemoryService(repository=InMemoryMemoryRepository())
    register_memory_capability(local_exec, memory_service=broken_service)

    task = SubTask(
        task_id="t_fail_mem",
        execution_type=ExecutionType.LOCAL,
        target="memory_store",
        goal="記錄",
        parameters={"content": "測試寫入失敗"},
    )

    res = local_exec.execute(task)
    assert res.status == ExecutionStatus.FAILED
    assert "Disk I/O failure" in res.error


def test_memory_handler_structured_result_serialization(fake_memory_service: MemoryService):
    """驗證結構化字典產出會被確定性 JSON 序列化."""
    adapter = MemoryAdapter(memory_service=fake_memory_service)
    task = SubTask(
        task_id="t_struct",
        execution_type=ExecutionType.LOCAL,
        target="memory_store",
        goal="儲存結構化菜單",
        depends_on=["t_a2a_build"],
    )
    context = ExecutionContext(
        dependency_results={
            "t_a2a_build": ExecutionResult(
                task_id="t_a2a_build",
                execution_type=ExecutionType.A2A,
                status=ExecutionStatus.SUCCESS,
                result={"cpu": "7500F", "gpu": "RTX 4060", "price": 38000},
            )
        }
    )

    res = adapter.store_memory_handler(task, context=context)
    assert res["status"] == "stored"
    assert '"cpu": "7500F"' in res["content"]
    assert '"price": 38000' in res["content"]


# ============================================================================
# 3. Full Multi-Agent Workflow Tests (A2A -> Memory)
# ============================================================================

def test_execute_plan_a2a_to_real_memory_adapter(
    mock_discovery: AgentDiscoveryService,
    fake_memory_service: MemoryService,
):
    """驗證完整工作流：A2A (PCforge 配單) -> LOCAL (MemoryAdapter 存入 MemoryService)."""
    # 模擬 PCforge A2A RPC
    def mock_pcforge_rpc(url: str, payload: dict) -> dict:
        return {
            "jsonrpc": "2.0",
            "id": payload.get("id", "1"),
            "result": {
                "id": "pc_task_999",
                "status": {
                    "state": "completed",
                    "message": {
                        "role": "agent",
                        "parts": [{"type": "text", "text": "【菜單明細】：AMD 7500F + RTX 4060 Ti 16G"}],
                    },
                },
            },
        }

    a2a_exec = A2AExecutor(discovery_service=mock_discovery, rpc_transport=mock_pcforge_rpc)
    local_exec = LocalExecutor()
    register_memory_capability(local_exec, memory_service=fake_memory_service)

    router = Router(local_executor=local_exec, a2a_executor=a2a_exec)
    orchestrator = Orchestrator(router=router)

    t1 = SubTask(
        task_id="task_build_pc",
        execution_type=ExecutionType.A2A,
        target="pc_recommendation",
        goal="配一台 40000 電腦",
    )
    t2 = SubTask(
        task_id="task_save_pc",
        execution_type=ExecutionType.LOCAL,
        target=CANONICAL_MEMORY_CAPABILITY,
        goal="儲存電腦配置",
        depends_on=["task_build_pc"],
    )
    plan = TaskPlan(user_goal="配電腦並記住配置", tasks=[t1, t2])

    results = orchestrator.execute_plan(plan)

    # 驗證 Task 1 成功
    assert results[0].status == ExecutionStatus.SUCCESS
    assert "RTX 4060 Ti 16G" in results[0].result

    # 驗證 Task 2 成功
    assert results[1].status == ExecutionStatus.SUCCESS
    stored_ack = results[1].result
    assert stored_ack["status"] == "stored"

    # 驗證 MemoryService 內確實已儲存且內容一致
    all_mems = fake_memory_service.search(query="4060 Ti")
    assert len(all_mems) == 1
    assert "AMD 7500F" in all_mems[0].content


def test_a2a_failure_skips_memory_store(
    mock_discovery: AgentDiscoveryService,
    fake_memory_service: MemoryService,
):
    """驗證 A2A 任務 FAILED 時，相依的 MemoryStore 任務自動 SKIPPED 且 MemoryService 絕不被調用."""
    # 模擬 A2A 連線失敗
    def mock_broken_rpc(url: str, payload: dict) -> dict:
        raise ConnectionRefusedError("PCforge server is offline")

    a2a_exec = A2AExecutor(discovery_service=mock_discovery, rpc_transport=mock_broken_rpc)
    local_exec = LocalExecutor()
    register_memory_capability(local_exec, memory_service=fake_memory_service)

    router = Router(local_executor=local_exec, a2a_executor=a2a_exec)
    orchestrator = Orchestrator(router=router)

    t1 = SubTask(
        task_id="task_pc_offline",
        execution_type=ExecutionType.A2A,
        target="pc_recommendation",
        goal="配電腦",
    )
    t2 = SubTask(
        task_id="task_mem_skip",
        execution_type=ExecutionType.LOCAL,
        target=CANONICAL_MEMORY_CAPABILITY,
        goal="儲存",
        depends_on=["task_pc_offline"],
    )
    plan = TaskPlan(user_goal="失敗跳過測試", tasks=[t1, t2])

    results = orchestrator.execute_plan(plan)

    assert results[0].status == ExecutionStatus.FAILED
    assert results[1].status == ExecutionStatus.SKIPPED
    assert "Dependency failed: task_pc_offline" in results[1].error

    # 驗證 MemoryService 完全未被寫入任何資料
    assert len(fake_memory_service.list_all()) == 0


def test_memory_failure_after_a2a_success(
    mock_discovery: AgentDiscoveryService,
):
    """驗證 A2A 成功但 Memory 儲存失敗時，Task 1 仍維持 SUCCESS，Task 2 為 FAILED (保留 Partial Results)."""
    def mock_pcforge_rpc(url: str, payload: dict) -> dict:
        return {
            "jsonrpc": "2.0",
            "id": payload.get("id", "1"),
            "result": {
                "id": "pc_task_101",
                "status": {
                    "state": "completed",
                    "message": {"role": "agent", "parts": [{"type": "text", "text": "【菜單】：RTX 4080"}]},
                },
            },
        }

    class BrokenMemoryService(MemoryService):
        def remember(self, content, memory_type=MemoryType.GENERAL, metadata=None):
            raise RuntimeError("Database table is locked")

    a2a_exec = A2AExecutor(discovery_service=mock_discovery, rpc_transport=mock_pcforge_rpc)
    local_exec = LocalExecutor()
    broken_service = BrokenMemoryService(repository=InMemoryMemoryRepository())
    register_memory_capability(local_exec, memory_service=broken_service)

    router = Router(local_executor=local_exec, a2a_executor=a2a_exec)
    orchestrator = Orchestrator(router=router)

    t1 = SubTask(
        task_id="t1_a2a_ok",
        execution_type=ExecutionType.A2A,
        target="pc_recommendation",
        goal="配電腦",
    )
    t2 = SubTask(
        task_id="t2_mem_fail",
        execution_type=ExecutionType.LOCAL,
        target=CANONICAL_MEMORY_CAPABILITY,
        goal="儲存",
        depends_on=["t1_a2a_ok"],
    )
    plan = TaskPlan(user_goal="部分成功測試", tasks=[t1, t2])

    results = orchestrator.execute_plan(plan)

    # Task 1 必須保留 SUCCESS 成果
    assert results[0].status == ExecutionStatus.SUCCESS
    assert "RTX 4080" in results[0].result

    # Task 2 必須為 FAILED
    assert results[1].status == ExecutionStatus.FAILED
    assert "Database table is locked" in results[1].error
