"""Unit and Workflow Tests for M.Ber Result Aggregation & Partial Failure (P7-06)."""

import pytest
from typing import Dict, List, Optional

from app.orchestration.models import (
    AggregatedResult,
    AggregateStatus,
    ExecutionContext,
    ExecutionResult,
    ExecutionStatus,
    ExecutionType,
    SubTask,
    TaskPlan,
)
from app.orchestration.aggregator import ResultAggregator
from app.orchestration.executors import A2AExecutor, LocalExecutor
from app.orchestration.memory_adapter import (
    CANONICAL_MEMORY_CAPABILITY,
    MemoryAdapter,
    register_memory_capability,
)
from app.orchestration.router import Router
from app.orchestration.orchestrator import Orchestrator
from app.a2a.discovery import AgentDiscoveryService
from app.a2a.models import AgentCard, AgentSkill
from memory.models import MemoryItem, MemoryType
from memory.repository import InMemoryMemoryRepository
from memory.service import MemoryService


@pytest.fixture
def aggregator() -> ResultAggregator:
    return ResultAggregator()


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


@pytest.fixture
def fake_memory_service() -> MemoryService:
    repo = InMemoryMemoryRepository()
    return MemoryService(repository=repo)


# ============================================================================
# 1. Core Aggregation Tests
# ============================================================================

def test_aggregate_all_success(aggregator: ResultAggregator):
    """驗證所有任務均成功時的彙整狀態 (Full Success)."""
    t1 = SubTask(task_id="t1", execution_type=ExecutionType.A2A, goal="配單")
    t2 = SubTask(task_id="t2", execution_type=ExecutionType.LOCAL, goal="存檔")
    plan = TaskPlan(user_goal="配單並存檔", tasks=[t1, t2])

    r1 = ExecutionResult(task_id="t1", execution_type=ExecutionType.A2A, status=ExecutionStatus.SUCCESS, result="PC配置")
    r2 = ExecutionResult(task_id="t2", execution_type=ExecutionType.LOCAL, status=ExecutionStatus.SUCCESS, result="已儲存")

    res = aggregator.aggregate(plan, [r1, r2])

    assert res.overall_status == AggregateStatus.SUCCESS
    assert res.success_count == 2
    assert res.failure_count == 0
    assert res.skipped_count == 0
    assert res.has_partial_failure is False
    assert len(res.results) == 2


def test_aggregate_full_failure(aggregator: ResultAggregator):
    """驗證所有任務均失敗或略過時的彙整狀態 (Full Failure)."""
    t1 = SubTask(task_id="t1", execution_type=ExecutionType.A2A, goal="配單")
    t2 = SubTask(task_id="t2", execution_type=ExecutionType.LOCAL, goal="存檔", depends_on=["t1"])
    plan = TaskPlan(user_goal="測試全失敗", tasks=[t1, t2])

    r1 = ExecutionResult(task_id="t1", execution_type=ExecutionType.A2A, status=ExecutionStatus.FAILED, error="Connection refused")
    r2 = ExecutionResult(task_id="t2", execution_type=ExecutionType.LOCAL, status=ExecutionStatus.SKIPPED, error="Dependency failed")

    res = aggregator.aggregate(plan, [r1, r2])

    assert res.overall_status == AggregateStatus.FAILED
    assert res.success_count == 0
    assert res.failure_count == 1
    assert res.skipped_count == 1
    assert res.has_partial_failure is False
    assert res.failed_task_ids == ["t1"]
    assert res.skipped_task_ids == ["t2"]


def test_aggregate_partial_failure(aggregator: ResultAggregator):
    """驗證一成一敗時的部分成功狀態 (Partial Failure)."""
    t1 = SubTask(task_id="t1", execution_type=ExecutionType.A2A, goal="配單")
    t2 = SubTask(task_id="t2", execution_type=ExecutionType.LOCAL, goal="存檔", depends_on=["t1"])
    plan = TaskPlan(user_goal="部分成功", tasks=[t1, t2])

    r1 = ExecutionResult(task_id="t1", execution_type=ExecutionType.A2A, status=ExecutionStatus.SUCCESS, result="RTX 4070")
    r2 = ExecutionResult(task_id="t2", execution_type=ExecutionType.LOCAL, status=ExecutionStatus.FAILED, error="DB lock")

    res = aggregator.aggregate(plan, [r1, r2])

    assert res.overall_status == AggregateStatus.PARTIAL_SUCCESS
    assert res.success_count == 1
    assert res.failure_count == 1
    assert res.skipped_count == 0
    assert res.has_partial_failure is True
    # 成功任務結果依然完整保留
    assert res.results[0].result == "RTX 4070"


def test_aggregate_timeout_counts_as_failure(aggregator: ResultAggregator):
    """驗證 TIMEOUT 正確計入 failure_count 且總體狀態為 FAILED."""
    t1 = SubTask(task_id="t1", execution_type=ExecutionType.MCP, goal="查詢")
    plan = TaskPlan(user_goal="逾時測試", tasks=[t1])

    r1 = ExecutionResult(task_id="t1", execution_type=ExecutionType.MCP, status=ExecutionStatus.TIMEOUT, error="Socket timeout")

    res = aggregator.aggregate(plan, [r1])

    assert res.overall_status == AggregateStatus.FAILED
    assert res.failure_count == 1
    assert res.success_count == 0
    assert res.failed_task_ids == ["t1"]


def test_aggregate_skipped_tasks(aggregator: ResultAggregator):
    """驗證包含 SKIPPED 且有 SUCCESS 時為 PARTIAL_SUCCESS."""
    t1 = SubTask(task_id="t1", execution_type=ExecutionType.LOCAL, goal="任務1")
    t2 = SubTask(task_id="t2", execution_type=ExecutionType.LOCAL, goal="任務2")
    plan = TaskPlan(user_goal="略過測試", tasks=[t1, t2])

    r1 = ExecutionResult(task_id="t1", execution_type=ExecutionType.LOCAL, status=ExecutionStatus.SUCCESS, result="OK")
    r2 = ExecutionResult(task_id="t2", execution_type=ExecutionType.LOCAL, status=ExecutionStatus.SKIPPED, error="Manual skip")

    res = aggregator.aggregate(plan, [r1, r2])

    assert res.overall_status == AggregateStatus.PARTIAL_SUCCESS
    assert res.skipped_count == 1
    assert res.success_count == 1
    assert res.has_partial_failure is True


def test_aggregate_preserves_result_order(aggregator: ResultAggregator):
    """驗證 Aggregator 嚴格依照 TaskPlan.tasks 原始順序排列，不依傳入順序或狀態改變."""
    t1 = SubTask(task_id="t_first", execution_type=ExecutionType.LOCAL, goal="第一步")
    t2 = SubTask(task_id="t_second", execution_type=ExecutionType.LOCAL, goal="第二步")
    t3 = SubTask(task_id="t_third", execution_type=ExecutionType.LOCAL, goal="第三步")
    plan = TaskPlan(user_goal="排序測試", tasks=[t1, t2, t3])

    r1 = ExecutionResult(task_id="t_first", execution_type=ExecutionType.LOCAL, status=ExecutionStatus.SUCCESS, result="1")
    r2 = ExecutionResult(task_id="t_second", execution_type=ExecutionType.LOCAL, status=ExecutionStatus.FAILED, error="2")
    r3 = ExecutionResult(task_id="t_third", execution_type=ExecutionType.LOCAL, status=ExecutionStatus.SUCCESS, result="3")

    # 亂序傳入 [r3, r1, r2]
    res = aggregator.aggregate(plan, [r3, r1, r2])

    assert [r.task_id for r in res.results] == ["t_first", "t_second", "t_third"]


# ============================================================================
# 2. Integrity & Validation Tests
# ============================================================================

def test_aggregate_rejects_duplicate_result_task_ids(aggregator: ResultAggregator):
    """驗證結果清單中包含重複 task_id 時拋出 ValueError."""
    t1 = SubTask(task_id="t1", execution_type=ExecutionType.LOCAL, goal="單一任務")
    plan = TaskPlan(user_goal="重複檢驗", tasks=[t1])

    r1 = ExecutionResult(task_id="t1", execution_type=ExecutionType.LOCAL, status=ExecutionStatus.SUCCESS, result="A")
    r2 = ExecutionResult(task_id="t1", execution_type=ExecutionType.LOCAL, status=ExecutionStatus.FAILED, error="B")

    with pytest.raises(ValueError, match="重複的 task_id"):
        aggregator.aggregate(plan, [r1, r2])


def test_aggregate_rejects_unknown_task_id(aggregator: ResultAggregator):
    """驗證結果清單中包含未在計畫中宣告的 unknown task_id 時拋出 ValueError."""
    t1 = SubTask(task_id="t1", execution_type=ExecutionType.LOCAL, goal="已知任務")
    plan = TaskPlan(user_goal="未知檢驗", tasks=[t1])

    r1 = ExecutionResult(task_id="t1", execution_type=ExecutionType.LOCAL, status=ExecutionStatus.SUCCESS)
    r_unknown = ExecutionResult(task_id="t_ghost", execution_type=ExecutionType.LOCAL, status=ExecutionStatus.SUCCESS)

    with pytest.raises(ValueError, match="未在計畫中宣告的未知 task_id"):
        aggregator.aggregate(plan, [r1, r_unknown])


def test_aggregate_handles_missing_task_result(aggregator: ResultAggregator):
    """驗證缺少某子任務結果時，Aggregator 自動補上確定性 FAILED 紀錄不崩潰."""
    t1 = SubTask(task_id="t1", execution_type=ExecutionType.LOCAL, goal="任務1")
    t2 = SubTask(task_id="t2", execution_type=ExecutionType.LOCAL, goal="任務2")
    plan = TaskPlan(user_goal="缺漏測試", tasks=[t1, t2])

    r1 = ExecutionResult(task_id="t1", execution_type=ExecutionType.LOCAL, status=ExecutionStatus.SUCCESS, result="OK")

    # 僅傳入 t1，缺漏 t2
    res = aggregator.aggregate(plan, [r1])

    assert len(res.results) == 2
    assert res.results[1].task_id == "t2"
    assert res.results[1].status == ExecutionStatus.FAILED
    assert "缺少任務執行結果" in res.results[1].error
    assert res.overall_status == AggregateStatus.PARTIAL_SUCCESS


# ============================================================================
# 3. Multi-Agent Workflow Aggregation Tests
# ============================================================================

def test_workflow_pcforge_memory_success_aggregation(
    mock_discovery: AgentDiscoveryService,
    fake_memory_service: MemoryService,
):
    """驗證 PCforge 配單 + Memory 儲存 全成功之端到端彙整."""
    def mock_rpc(url: str, payload: dict) -> dict:
        return {
            "jsonrpc": "2.0",
            "id": payload.get("id", "1"),
            "result": {
                "id": "pc_task_1",
                "status": {
                    "state": "completed",
                    "message": {"role": "agent", "parts": [{"type": "text", "text": "【菜單】：i7-14700 + RTX 4070Ti"}]},
                },
            },
        }

    a2a_exec = A2AExecutor(discovery_service=mock_discovery, rpc_transport=mock_rpc)
    local_exec = LocalExecutor()
    register_memory_capability(local_exec, memory_service=fake_memory_service)

    router = Router(local_executor=local_exec, a2a_executor=a2a_exec)
    orchestrator = Orchestrator(router=router)

    t1 = SubTask(task_id="t_pc", execution_type=ExecutionType.A2A, target="pc_recommendation", goal="配電腦")
    t2 = SubTask(task_id="t_mem", execution_type=ExecutionType.LOCAL, target=CANONICAL_MEMORY_CAPABILITY, goal="存檔", depends_on=["t_pc"])
    plan = TaskPlan(user_goal="配電腦並存檔", tasks=[t1, t2])

    aggregated = orchestrator.execute_and_aggregate(plan)

    assert aggregated.overall_status == AggregateStatus.SUCCESS
    assert aggregated.success_count == 2
    assert aggregated.failure_count == 0
    assert aggregated.skipped_count == 0
    assert aggregated.has_partial_failure is False
    assert "RTX 4070Ti" in aggregated.results[0].result
    assert aggregated.results[1].result["status"] == "stored"


def test_workflow_pcforge_success_memory_failure_partial_aggregation(
    mock_discovery: AgentDiscoveryService,
):
    """驗證 PCforge 成功 + Memory 失敗 之部分成功彙整 (Task 1 成果不丟失)."""
    def mock_rpc(url: str, payload: dict) -> dict:
        return {
            "jsonrpc": "2.0",
            "id": payload.get("id", "1"),
            "result": {
                "id": "pc_task_2",
                "status": {
                    "state": "completed",
                    "message": {"role": "agent", "parts": [{"type": "text", "text": "【菜單】：Ryzen 7800X3D + RTX 4090"}]},
                },
            },
        }

    class FailingMemoryService(MemoryService):
        def remember(self, content, memory_type=MemoryType.GENERAL, metadata=None):
            raise RuntimeError("Database full")

    a2a_exec = A2AExecutor(discovery_service=mock_discovery, rpc_transport=mock_rpc)
    local_exec = LocalExecutor()
    failing_service = FailingMemoryService(repository=InMemoryMemoryRepository())
    register_memory_capability(local_exec, memory_service=failing_service)

    router = Router(local_executor=local_exec, a2a_executor=a2a_exec)
    orchestrator = Orchestrator(router=router)

    t1 = SubTask(task_id="t_pc_ok", execution_type=ExecutionType.A2A, target="pc_recommendation", goal="配頂級電腦")
    t2 = SubTask(task_id="t_mem_fail", execution_type=ExecutionType.LOCAL, target=CANONICAL_MEMORY_CAPABILITY, goal="存檔", depends_on=["t_pc_ok"])
    plan = TaskPlan(user_goal="頂級配單", tasks=[t1, t2])

    aggregated = orchestrator.execute_and_aggregate(plan)

    assert aggregated.overall_status == AggregateStatus.PARTIAL_SUCCESS
    assert aggregated.success_count == 1
    assert aggregated.failure_count == 1
    assert aggregated.has_partial_failure is True
    # 核心成果必須存在
    assert "RTX 4090" in aggregated.results[0].result
    assert "Database full" in aggregated.results[1].error


def test_workflow_pcforge_failure_memory_skipped_aggregation(
    mock_discovery: AgentDiscoveryService,
    fake_memory_service: MemoryService,
):
    """驗證 PCforge 失敗 + Memory 略過 之全失敗彙整 (Full Failure)."""
    def mock_broken_rpc(url: str, payload: dict) -> dict:
        raise ConnectionRefusedError("PCforge server unavailable")

    a2a_exec = A2AExecutor(discovery_service=mock_discovery, rpc_transport=mock_broken_rpc)
    local_exec = LocalExecutor()
    register_memory_capability(local_exec, memory_service=fake_memory_service)

    router = Router(local_executor=local_exec, a2a_executor=a2a_exec)
    orchestrator = Orchestrator(router=router)

    t1 = SubTask(task_id="t_pc_fail", execution_type=ExecutionType.A2A, target="pc_recommendation", goal="配電腦")
    t2 = SubTask(task_id="t_mem_skip", execution_type=ExecutionType.LOCAL, target=CANONICAL_MEMORY_CAPABILITY, goal="存檔", depends_on=["t_pc_fail"])
    plan = TaskPlan(user_goal="失敗測試", tasks=[t1, t2])

    aggregated = orchestrator.execute_and_aggregate(plan)

    assert aggregated.overall_status == AggregateStatus.FAILED
    assert aggregated.success_count == 0
    assert aggregated.failure_count == 1
    assert aggregated.skipped_count == 1
    assert aggregated.has_partial_failure is False
    assert aggregated.failed_task_ids == ["t_pc_fail"]
    assert aggregated.skipped_task_ids == ["t_mem_skip"]


def test_aggregated_result_to_context_text(aggregator: ResultAggregator):
    """驗證 AggregatedResult.to_context_text() 產生乾淨文字摘要供上層使用."""
    t1 = SubTask(task_id="t1", execution_type=ExecutionType.A2A, goal="配單")
    t2 = SubTask(task_id="t2", execution_type=ExecutionType.LOCAL, goal="存檔", depends_on=["t1"])
    plan = TaskPlan(plan_id="plan_test_ctx", user_goal="文字摘要測試", tasks=[t1, t2])

    r1 = ExecutionResult(task_id="t1", execution_type=ExecutionType.A2A, status=ExecutionStatus.SUCCESS, source="a2a:PCforge", result="i5-13600K")
    r2 = ExecutionResult(task_id="t2", execution_type=ExecutionType.LOCAL, status=ExecutionStatus.FAILED, source="local:memory_store", error="Disk write error")

    res = aggregator.aggregate(plan, [r1, r2])
    text = res.to_context_text()

    assert "Plan ID: plan_test_ctx (Overall Status: partial_success)" in text
    assert "- Task 1 [t1]: type=a2a, status=success, source=a2a:PCforge" in text
    assert "Result: i5-13600K" in text
    assert "- Task 2 [t2]: type=local, status=failed, source=local:memory_store" in text
    assert "Error: Disk write error" in text
