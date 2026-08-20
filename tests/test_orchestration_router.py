"""Tests for M.Ber Orchestration Router, Executors, and Orchestrator (P7-01B)."""

import socket
import urllib.error
import pytest

from app.orchestration.models import (
    ExecutionType,
    ExecutionStatus,
    SubTask,
    ExecutionResult,
)
from app.orchestration.executors import LocalExecutor, A2AExecutor
from app.orchestration.router import Router
from app.orchestration.orchestrator import Orchestrator
from app.a2a.discovery import AgentDiscoveryService
from app.a2a.models import (
    AgentCard,
    AgentSkill,
    Artifact,
    Message,
    Task,
    TaskState,
    TaskStatus,
    TextPart,
)
from app.a2a.client import A2AClientError


@pytest.fixture
def mock_agent_card() -> AgentCard:
    """提供標準測試用 AgentCard (不依賴外部伺服器)."""
    return AgentCard(
        name="MockExpertAgent",
        description="專業測試代理人",
        url="http://mock-agent.local/rpc",
        skills=[
            AgentSkill(
                id="expert_skill",
                name="專業分析技能",
                description="提供測試分析",
                tags=["expert", "analysis"],
                examples=["幫我分析"],
            )
        ],
    )


@pytest.fixture
def mock_discovery(mock_agent_card: AgentCard) -> AgentDiscoveryService:
    """提供已註冊 Mock 代理人的 Discovery 服務實例."""
    discovery = AgentDiscoveryService(config_path="non_existent_config.json")
    discovery.register_agent(mock_agent_card)
    return discovery


def test_router_local_route():
    """驗證 Router 正確將 LOCAL 任務指派給 LocalExecutor."""
    local_executor = LocalExecutor()
    local_executor.register_handler("math", lambda task: task.parameters.get("a", 0) + task.parameters.get("b", 0))

    router = Router(local_executor=local_executor)
    task = SubTask(
        task_id="t_math",
        execution_type=ExecutionType.LOCAL,
        target="math",
        goal="計算總和",
        parameters={"a": 10, "b": 25},
    )

    res = router.route(task)
    assert res.task_id == "t_math"
    assert res.execution_type == ExecutionType.LOCAL
    assert res.status == ExecutionStatus.SUCCESS
    assert res.source == "local:math"
    assert res.result == 35


def test_router_a2a_route(mock_discovery: AgentDiscoveryService):
    """驗證 Router 正確將 A2A 任務指派給 A2AExecutor."""
    # 模擬 RPC 回傳 A2A Task (completed)
    def mock_transport(url: str, payload: dict) -> dict:
        return {
            "jsonrpc": "2.0",
            "id": payload.get("id", "1"),
            "result": {
                "id": "remote_task_999",
                "status": {
                    "state": "completed",
                    "message": {"role": "agent", "parts": [{"type": "text", "text": "分析完成"}]},
                },
                "artifacts": [],
            },
        }

    a2a_executor = A2AExecutor(discovery_service=mock_discovery, rpc_transport=mock_transport)
    router = Router(a2a_executor=a2a_executor)

    task = SubTask(
        task_id="t_a2a",
        execution_type=ExecutionType.A2A,
        target="expert_skill",
        goal="幫我分析市場趨勢",
    )

    res = router.route(task)
    assert res.task_id == "t_a2a"
    assert res.execution_type == ExecutionType.A2A
    assert res.status == ExecutionStatus.SUCCESS
    assert res.source == "a2a:MockExpertAgent"
    assert "分析完成" in res.result
    assert res.metadata["remote_task_id"] == "remote_task_999"


def test_orchestrator_local_success():
    """驗證 Orchestrator 呼叫本地能力並記錄成功."""
    local_exec = LocalExecutor(handlers={"echo": lambda t: f"Echo: {t.parameters.get('val')}"})
    router = Router(local_executor=local_exec)
    orchestrator = Orchestrator(router=router)

    task = SubTask(
        task_id="t_echo",
        execution_type=ExecutionType.LOCAL,
        target="echo",
        goal="回傳字串",
        parameters={"val": "Hello M.Ber"},
    )

    res = orchestrator.execute_task(task)
    assert res.status == ExecutionStatus.SUCCESS
    assert res.result == "Echo: Hello M.Ber"


def test_orchestrator_a2a_success(mock_discovery: AgentDiscoveryService):
    """驗證 Orchestrator 透過 A2A 委派並成功回傳結果."""
    def mock_transport(url: str, payload: dict) -> dict:
        return {
            "jsonrpc": "2.0",
            "id": payload.get("id", "1"),
            "result": {
                "id": "task_abc",
                "status": {
                    "state": "completed",
                    "message": {"role": "agent", "parts": [{"type": "text", "text": "配置成功"}]},
                },
                "artifacts": [
                    {
                        "id": "art_1",
                        "name": "build.txt",
                        "parts": [{"type": "text", "text": "RTX 4070"}],
                    }
                ],
            },
        }

    a2a_exec = A2AExecutor(discovery_service=mock_discovery, rpc_transport=mock_transport)
    orchestrator = Orchestrator(router=Router(a2a_executor=a2a_exec))

    task = SubTask(
        task_id="t_build",
        execution_type=ExecutionType.A2A,
        target="MockExpertAgent",
        goal="推薦硬體",
    )

    res = orchestrator.execute_task(task)
    assert res.status == ExecutionStatus.SUCCESS
    assert "配置成功" in res.result
    assert "RTX 4070" in res.result
    assert res.metadata["agent_name"] == "MockExpertAgent"


def test_local_unknown_target_returns_failed():
    """驗證請求未註冊之本地能力目標時回傳 FAILED 且不 crash."""
    local_exec = LocalExecutor()
    task = SubTask(
        task_id="t_unknown",
        execution_type=ExecutionType.LOCAL,
        target="non_existent_capability",
        goal="嘗試執行不存在的本地能力",
    )

    res = local_exec.execute(task)
    assert res.status == ExecutionStatus.FAILED
    assert "未知的本地能力目標" in res.error


def test_a2a_unknown_agent_returns_failed(mock_discovery: AgentDiscoveryService):
    """驗證找不到匹配之 A2A 代理人時回傳 FAILED 且不 crash."""
    a2a_exec = A2AExecutor(discovery_service=mock_discovery)
    task = SubTask(
        task_id="t_no_agent",
        execution_type=ExecutionType.A2A,
        target="space_travel_skill",
        goal="安排火星太空旅行",
    )

    res = a2a_exec.execute(task)
    assert res.status == ExecutionStatus.FAILED
    assert "找不到符合能力目標" in res.error


def test_a2a_failure_maps_to_failed(mock_discovery: AgentDiscoveryService):
    """驗證 A2A 遠端任務回傳 failed 狀態時，正確映射為 ExecutionStatus.FAILED."""
    def mock_transport(url: str, payload: dict) -> dict:
        return {
            "jsonrpc": "2.0",
            "id": payload.get("id", "1"),
            "result": {
                "id": "task_fail_1",
                "status": {
                    "state": "failed",
                    "message": {"role": "agent", "parts": [{"type": "text", "text": "超出預算限制"}]},
                },
                "artifacts": [],
            },
        }

    a2a_exec = A2AExecutor(discovery_service=mock_discovery, rpc_transport=mock_transport)
    task = SubTask(
        task_id="t_fail",
        execution_type=ExecutionType.A2A,
        target="expert_skill",
        goal="執行會失敗的任務",
    )

    res = a2a_exec.execute(task)
    assert res.status == ExecutionStatus.FAILED
    assert res.result is None
    assert "超出預算限制" in res.error


def test_a2a_timeout_maps_to_timeout(mock_discovery: AgentDiscoveryService):
    """驗證 A2A 呼叫發生連線逾時（Timeout）時，正確映射為 ExecutionStatus.TIMEOUT."""
    def mock_timeout_transport(url: str, payload: dict) -> dict:
        raise socket.timeout("The read operation timed out")

    a2a_exec = A2AExecutor(discovery_service=mock_discovery, rpc_transport=mock_timeout_transport)
    task = SubTask(
        task_id="t_timeout",
        execution_type=ExecutionType.A2A,
        target="expert_skill",
        goal="執行超時任務",
    )

    res = a2a_exec.execute(task)
    assert res.status == ExecutionStatus.TIMEOUT
    assert "逾時" in res.error or "timed out" in res.error.lower()


def test_a2a_message_response_success(mock_discovery: AgentDiscoveryService):
    """驗證 A2A 遠端回傳直接 Message（非 Task 物件）時能正確解析並成功完成."""
    def mock_transport(url: str, payload: dict) -> dict:
        return {
            "jsonrpc": "2.0",
            "id": payload.get("id", "1"),
            "result": {
                "role": "agent",
                "parts": [{"type": "text", "text": "直接純文字回覆訊息"}],
            },
        }

    a2a_exec = A2AExecutor(discovery_service=mock_discovery, rpc_transport=mock_transport)
    task = SubTask(
        task_id="t_msg",
        execution_type=ExecutionType.A2A,
        target="expert_skill",
        goal="一般問答",
    )

    res = a2a_exec.execute(task)
    assert res.status == ExecutionStatus.SUCCESS
    assert res.result == "直接純文字回覆訊息"


def test_router_mcp_route_dispatch():
    """驗證 Router 正確將 MCP 任務分派至 MCPExecutor."""
    class FakeMCPExecutor:
        def execute(self, task, context=None):
            return ExecutionResult(
                task_id=task.task_id,
                execution_type=ExecutionType.MCP,
                status=ExecutionStatus.SUCCESS,
                source="mcp:fake_tool",
                result="Fake tool output",
            )

    router = Router(mcp_executor=FakeMCPExecutor())
    task = SubTask(
        task_id="t_mcp",
        execution_type=ExecutionType.MCP,
        target="fake_tool",
        goal="查詢行程",
    )

    res = router.route(task)
    assert res.status == ExecutionStatus.SUCCESS
    assert res.result == "Fake tool output"
