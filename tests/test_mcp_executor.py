"""Unit and Chaining Tests for M.Ber MCPExecutor (P7-04 MCP Integration)."""

import socket
import pytest
from typing import Any, Dict, Optional

from app.orchestration.models import (
    ExecutionContext,
    ExecutionResult,
    ExecutionStatus,
    ExecutionType,
    SubTask,
    TaskPlan,
)
from app.orchestration.executors import A2AExecutor, LocalExecutor, MCPExecutor
from app.orchestration.router import Router
from app.orchestration.orchestrator import Orchestrator
from app.a2a.discovery import AgentDiscoveryService
from app.a2a.models import AgentCard, AgentSkill


class MockMCPManager:
    """測試專用 Mock MCPManager (100% 離線確定性，不啟動真實子程序)."""

    def __init__(self, tools_map: Optional[Dict[str, Any]] = None) -> None:
        self.tools_map = tools_map or {
            "get_current_time": lambda args: "[Mock Time Tool]: 2026-08-20 23:25:00",
            "query_events": lambda args: '[{"id": 1, "title": "Team Sync", "start": "2026-08-20 10:00"}]',
            "echo_message": lambda args: f"Echo: {args.get('message', '')}",
            "empty_tool": lambda args: "",
        }
        self.last_called_tool = None
        self.last_called_args = None

    def call_tool(self, tool_name: str, arguments: Optional[Dict[str, Any]] = None) -> str:
        args = arguments or {}
        self.last_called_tool = tool_name
        self.last_called_args = args

        if tool_name not in self.tools_map:
            return f"❌ [MCP Manager 錯誤]: 找不到提供工具 '{tool_name}' 的 MCP Server"

        handler = self.tools_map[tool_name]
        if callable(handler):
            return handler(args)
        return str(handler)


@pytest.fixture
def mock_mcp_manager() -> MockMCPManager:
    return MockMCPManager()


@pytest.fixture
def mock_discovery() -> AgentDiscoveryService:
    discovery = AgentDiscoveryService(config_path="non_existent_config.json")
    discovery.register_agent(
        AgentCard(
            name="PCforgeMock",
            description="電腦配單專家",
            url="http://mock-pcforge.local/rpc",
            skills=[
                AgentSkill(
                    id="pc_recommendation",
                    name="電腦配置推薦",
                    description="提供組裝清單",
                    tags=["電腦", "pc", "硬體"],
                )
            ],
        )
    )
    return discovery


def test_router_mcp_route(mock_mcp_manager: MockMCPManager):
    """驗證 Router 正確將 MCP 任務導流至 MCPExecutor 執行."""
    mcp_exec = MCPExecutor(mcp_manager=mock_mcp_manager)
    router = Router(mcp_executor=mcp_exec)

    task = SubTask(
        task_id="t_time",
        execution_type=ExecutionType.MCP,
        target="get_current_time",
        goal="查詢現在時間",
    )

    res = router.route(task)
    assert res.status == ExecutionStatus.SUCCESS
    assert res.execution_type == ExecutionType.MCP
    assert "2026-08-20" in res.result
    assert res.source == "mcp:get_current_time"


def test_mcp_executor_success(mock_mcp_manager: MockMCPManager):
    """驗證 MCPExecutor 執行成功並正規化輸出為 ExecutionResult."""
    mcp_exec = MCPExecutor(mcp_manager=mock_mcp_manager)
    task = SubTask(
        task_id="t_echo",
        execution_type=ExecutionType.MCP,
        target="echo_message",
        goal="測試 Echo",
        parameters={"message": "Hello MCP"},
    )

    res = mcp_exec.execute(task)
    assert res.status == ExecutionStatus.SUCCESS
    assert res.result == "Echo: Hello MCP"
    assert res.metadata.get("tool_name") == "echo_message"


def test_mcp_unknown_tool_returns_failed(mock_mcp_manager: MockMCPManager):
    """驗證呼叫不存在之 MCP 工具時安全回傳 FAILED."""
    mcp_exec = MCPExecutor(mcp_manager=mock_mcp_manager)
    task = SubTask(
        task_id="t_missing",
        execution_type=ExecutionType.MCP,
        target="non_existent_tool",
        goal="呼叫不存在的工具",
    )

    res = mcp_exec.execute(task)
    assert res.status == ExecutionStatus.FAILED
    assert "找不到提供工具" in res.error


def test_mcp_server_unavailable_returns_failed():
    """驗證底層 Server 調用失敗時 MCPExecutor 映射為 FAILED."""
    class BrokenMCPManager:
        def call_tool(self, tool_name: str, arguments: dict) -> str:
            return f"❌ [MCP Manager 調用失敗]: 執行 Server 'calendar_server' 之工具 '{tool_name}' 時發生錯誤: Connection refused"

    mcp_exec = MCPExecutor(mcp_manager=BrokenMCPManager())
    task = SubTask(
        task_id="t_broken",
        execution_type=ExecutionType.MCP,
        target="query_events",
        goal="查詢行程",
    )

    res = mcp_exec.execute(task)
    assert res.status == ExecutionStatus.FAILED
    assert "Connection refused" in res.error


def test_mcp_timeout_maps_to_timeout():
    """驗證 MCP 調用逾時例外與字串皆正確映射為 TIMEOUT 狀態."""
    class TimeoutMCPManager:
        def call_tool(self, tool_name: str, arguments: dict) -> str:
            raise socket.timeout("MCP stdio process timed out")

    mcp_exec = MCPExecutor(mcp_manager=TimeoutMCPManager())
    task = SubTask(
        task_id="t_to",
        execution_type=ExecutionType.MCP,
        target="heavy_tool",
        goal="耗時任務",
    )

    res = mcp_exec.execute(task)
    assert res.status == ExecutionStatus.TIMEOUT
    assert "逾時" in res.error or "timed out" in res.error


def test_mcp_structured_result_success(mock_mcp_manager: MockMCPManager):
    """驗證 MCP 回傳之結構化 JSON 字串完整保留."""
    mcp_exec = MCPExecutor(mcp_manager=mock_mcp_manager)
    task = SubTask(
        task_id="t_query",
        execution_type=ExecutionType.MCP,
        target="query_events",
        goal="查詢行事曆",
    )

    res = mcp_exec.execute(task)
    assert res.status == ExecutionStatus.SUCCESS
    assert "Team Sync" in res.result


def test_mcp_empty_result_is_handled(mock_mcp_manager: MockMCPManager):
    """驗證 MCP 回傳空字串或空內容時安全處理不崩潰."""
    mcp_exec = MCPExecutor(mcp_manager=mock_mcp_manager)
    task = SubTask(
        task_id="t_empty",
        execution_type=ExecutionType.MCP,
        target="empty_tool",
        goal="空回傳工具",
    )

    res = mcp_exec.execute(task)
    assert res.status == ExecutionStatus.SUCCESS
    assert res.result == ""


def test_mcp_executor_receives_execution_context(mock_mcp_manager: MockMCPManager):
    """驗證 MCPExecutor 正確接收 ExecutionContext 上下文參數."""
    mcp_exec = MCPExecutor(mcp_manager=mock_mcp_manager)
    task = SubTask(
        task_id="t_echo",
        execution_type=ExecutionType.MCP,
        target="echo_message",
        goal="測試",
        parameters={"message": "Direct"},
    )
    context = ExecutionContext(
        dependency_results={
            "t_prev": ExecutionResult(
                task_id="t_prev",
                execution_type=ExecutionType.LOCAL,
                status=ExecutionStatus.SUCCESS,
                result="Prev Data",
            )
        }
    )

    res = mcp_exec.execute(task, context=context)
    assert res.status == ExecutionStatus.SUCCESS


def test_execute_plan_a2a_to_mcp(mock_discovery: AgentDiscoveryService, mock_mcp_manager: MockMCPManager):
    """驗證跨協定 Chaining：Task 1 (A2A PC Recommendation) -> Task 2 (MCP Save Note)."""
    # 模擬 PCforge 回傳菜單
    def mock_pcforge_rpc(url: str, payload: dict) -> dict:
        return {
            "jsonrpc": "2.0",
            "id": payload.get("id", "1"),
            "result": {
                "id": "pc_task_1",
                "status": {
                    "state": "completed",
                    "message": {
                        "role": "agent",
                        "parts": [{"type": "text", "text": "【菜單】：RTX 4070 SUPER + i5-14600K"}],
                    },
                },
            },
        }

    # 模擬 MCP 筆記工具
    saved_note_content = None

    def mock_add_note_tool(args: dict) -> str:
        nonlocal saved_note_content
        saved_note_content = args.get("content", "")
        return "[SQLite Notes]: 筆記已成功寫入資料庫。"

    mock_mcp_manager.tools_map["add_note"] = mock_add_note_tool

    a2a_exec = A2AExecutor(discovery_service=mock_discovery, rpc_transport=mock_pcforge_rpc)
    mcp_exec = MCPExecutor(mcp_manager=mock_mcp_manager)
    router = Router(a2a_executor=a2a_exec, mcp_executor=mcp_exec)
    orchestrator = Orchestrator(router=router)

    t1 = SubTask(
        task_id="task_a2a",
        execution_type=ExecutionType.A2A,
        target="pc_recommendation",
        goal="幫我配一台電腦",
    )
    t2 = SubTask(
        task_id="task_mcp",
        execution_type=ExecutionType.MCP,
        target="add_note",
        goal="將配單寫入筆記",
        parameters={"content": "預設筆記"},
        depends_on=["task_a2a"],
    )
    plan = TaskPlan(user_goal="配單並存入 MCP 筆記", tasks=[t1, t2])

    results = orchestrator.execute_plan(plan)

    assert results[0].status == ExecutionStatus.SUCCESS
    assert "RTX 4070 SUPER" in results[0].result

    assert results[1].status == ExecutionStatus.SUCCESS
    assert "已成功寫入" in results[1].result


def test_execute_plan_mcp_to_local(mock_mcp_manager: MockMCPManager):
    """驗證跨協定 Chaining：Task 1 (MCP Query Events) -> Task 2 (LOCAL Summarize Events)."""
    summarized_output = None

    def summarize_handler(task: SubTask, context: ExecutionContext) -> str:
        nonlocal summarized_output
        mcp_result = context.get_result("task_mcp_query")
        summarized_output = f"統整行程報告: {mcp_result}"
        return summarized_output

    local_exec = LocalExecutor(handlers={"summarize": summarize_handler})
    mcp_exec = MCPExecutor(mcp_manager=mock_mcp_manager)
    router = Router(local_executor=local_exec, mcp_executor=mcp_exec)
    orchestrator = Orchestrator(router=router)

    t1 = SubTask(
        task_id="task_mcp_query",
        execution_type=ExecutionType.MCP,
        target="query_events",
        goal="查詢今天行程",
    )
    t2 = SubTask(
        task_id="task_local_summary",
        execution_type=ExecutionType.LOCAL,
        target="summarize",
        goal="統整行程摘要",
        depends_on=["task_mcp_query"],
    )
    plan = TaskPlan(user_goal="查行程並做摘要", tasks=[t1, t2])

    results = orchestrator.execute_plan(plan)

    assert results[0].status == ExecutionStatus.SUCCESS
    assert "Team Sync" in results[0].result

    assert results[1].status == ExecutionStatus.SUCCESS
    assert "統整行程報告" in results[1].result
    assert "Team Sync" in summarized_output
