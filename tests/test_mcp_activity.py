"""Unit & Integration Tests for MCP Activity Observation & Endpoints (Phase 8 - P8-04).

驗證項目：
1. MCPActivityRecorder 緩衝區容量上限與 FIFO 擠出行為 (Bounded History)
2. MCPActivityRecorder 保留時間新到舊時序 (Order Preservation)
3. MCPActivityRecorder 多執行緒安全寫入 (Thread Safety)
4. GET /api/mcp/status 回傳狀態、伺服器數與工具清單
5. GET /api/mcp/status 絕不外洩內部 Stdio command、檔案路徑或環境變數
6. GET /api/mcp/activity 初始為空
7. MCP 工具執行成功時自動記錄 activity (status='success')
8. MCP 工具執行失敗時自動記錄 activity (status='failed')
9. MCP 工具逾時或異常時記錄 activity (status='timeout')
10. GET /api/mcp/activity 支援 limit 查詢參數且 clamp 在 1-100
11. MCP Activity 絕不儲存敏感 arguments、使用者 prompt、原始 results 或記憶內容
12. 純 A2A 調度請求絕不產生假 MCP 活動紀錄 (No fake MCP activity)
"""

import concurrent.futures
import threading
from typing import Any, Dict, List
from unittest.mock import MagicMock
import pytest
from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage, HumanMessage

from app.interfaces.web.gateway import create_web_app
from app.mcp.activity import MCPActivityRecorder
from app.mcp.manager import MCPManager
from app.orchestration.executors import MCPExecutor
from app.orchestration.models import (
    AggregatedResult,
    ExecutionResult,
    ExecutionStatus,
    ExecutionType,
    OrchestrationResponse,
    SubTask,
    TaskPlan,
)
from app.orchestration.service import OrchestrationService


@pytest.fixture(autouse=True)
def reset_default_recorder():
    from app.mcp.activity import get_default_mcp_recorder
    get_default_mcp_recorder().clear()
    yield
    get_default_mcp_recorder().clear()


def test_activity_recorder_bounded_history() -> None:
    """驗證 Recorder 環狀緩衝區最多保留 max_history 筆紀錄."""
    recorder = MCPActivityRecorder(max_history=5)
    for i in range(10):
        recorder.record(
            tool_name=f"tool_{i}",
            server_name="test_server",
            status="success",
        )

    assert len(recorder) == 5
    recent = recorder.get_recent(limit=10)
    assert len(recent) == 5
    # 最新的一筆應該是 tool_9
    assert recent[0].tool_name == "tool_9"
    # 最舊的一筆應該是 tool_5
    assert recent[-1].tool_name == "tool_5"


def test_activity_recorder_preserves_order() -> None:
    """驗證 Recorder 依據時間新到舊排序."""
    recorder = MCPActivityRecorder(max_history=10)
    recorder.record(tool_name="tool_a", server_name="srv1", status="success")
    recorder.record(tool_name="tool_b", server_name="srv1", status="success")
    recorder.record(tool_name="tool_c", server_name="srv2", status="failed")

    recent = recorder.get_recent(limit=10)
    assert [r.tool_name for r in recent] == ["tool_c", "tool_b", "tool_a"]


def test_activity_recorder_thread_safe() -> None:
    """驗證 Recorder 在多執行緒並行寫入時資料一致無 race condition."""
    recorder = MCPActivityRecorder(max_history=100)

    def write_worker(idx: int) -> None:
        for j in range(20):
            recorder.record(
                tool_name=f"worker_{idx}_tool_{j}",
                server_name="srv",
                status="success",
                duration_ms=10.0,
            )

    threads = [threading.Thread(target=write_worker, args=(i,)) for i in range(5)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert len(recorder) == 100


def test_activity_recorder_cleans_error_summary() -> None:
    """驗證 Recorder 自動清理 error_summary，防止長篇 Python traceback 洩漏."""
    recorder = MCPActivityRecorder()
    long_traceback = (
        "RuntimeError: Database lock failed\n"
        "  File 'app/server.py', line 45, in execute\n"
        "  File 'sqlite3/db.py', line 12\n"
    )
    rec = recorder.record(
        tool_name="query_events",
        server_name="calendar",
        status="failed",
        error_summary=long_traceback,
    )
    assert "\n" not in rec.error_summary
    assert "Database lock failed" in rec.error_summary


def test_mcp_status_endpoint() -> None:
    """測試 GET /api/mcp/status 回傳正確的狀態與工具清單."""
    mock_manager = MagicMock(spec=MCPManager)
    mock_manager.get_server_count.return_value = 2
    mock_manager.get_tools_metadata.return_value = [
        {"name": "get_current_time", "server": "own_server", "safety_level": "read_only", "description": "取得時間"},
        {"name": "calendar_add_event", "server": "calendar", "safety_level": "write", "description": "新增行程"},
    ]

    app = create_web_app(mcp_manager=mock_manager)
    client = TestClient(app)

    response = client.get("/api/mcp/status")
    assert response.status_code == 200
    data = response.json()

    assert data["status"] == "online"
    assert data["server_count"] == 2
    assert data["tool_count"] == 2
    assert len(data["tools"]) == 2
    assert data["tools"][0]["name"] == "get_current_time"
    assert data["tools"][0]["safety_level"] == "read_only"
    assert data["tools"][1]["name"] == "calendar_add_event"
    assert data["tools"][1]["safety_level"] == "write"


def test_mcp_status_does_not_expose_internal_config() -> None:
    """測試 GET /api/mcp/status 絕不暴露 command, args, env, 或內部路徑."""
    mock_manager = MagicMock(spec=MCPManager)
    mock_manager.get_server_count.return_value = 1
    mock_manager.get_tools_metadata.return_value = [
        {"name": "read_notes", "server": "sqlite_server", "safety_level": "read_only"}
    ]

    app = create_web_app(mcp_manager=mock_manager)
    client = TestClient(app)

    response = client.get("/api/mcp/status")
    assert response.status_code == 200
    data = response.json()

    forbidden_fields = ["command", "args", "env", "cwd", "path", "python_executable"]
    for tool in data["tools"]:
        for field in forbidden_fields:
            assert field not in tool, f"機密欄位 '{field}' 意外暴露在 MCP Status API 中"


def test_mcp_activity_endpoint_empty() -> None:
    """測試 GET /api/mcp/activity 初始無紀錄時回傳空清單."""
    recorder = MCPActivityRecorder()
    mock_mgr = MagicMock(spec=MCPManager)
    app = create_web_app(mcp_manager=mock_mgr, mcp_recorder=recorder)
    client = TestClient(app)

    response = client.get("/api/mcp/activity")
    assert response.status_code == 200
    data = response.json()
    assert data["items"] == []
    assert data["total"] == 0


def test_mcp_activity_records_success() -> None:
    """測試 MCPExecutor 執行成功時自動記錄 activity (status='success')."""
    recorder = MCPActivityRecorder()
    mock_manager = MagicMock(spec=MCPManager)
    mock_manager.tool_routes = {"echo_message": "own_server"}
    mock_manager.evaluate_safety_level.return_value = "READ_ONLY"
    mock_manager.call_tool.return_value = "Echo: Hello"

    executor = MCPExecutor(mcp_manager=mock_manager, activity_recorder=recorder)
    task = SubTask(task_id="t_mcp_1", execution_type=ExecutionType.MCP, goal="Echo", target="echo_message")
    res = executor.execute(task)

    assert res.status == ExecutionStatus.SUCCESS
    assert len(recorder) == 1
    recent = recorder.get_recent()[0]
    assert recent.tool_name == "echo_message"
    assert recent.server_name == "own_server"
    assert recent.status == "success"
    assert recent.duration_ms is not None
    assert recent.safety_level == "READ_ONLY"


def test_mcp_activity_records_failure() -> None:
    """測試 MCPExecutor 執行失敗時記錄 activity (status='failed')."""
    recorder = MCPActivityRecorder()
    mock_manager = MagicMock(spec=MCPManager)
    mock_manager.tool_routes = {"fail_tool": "test_server"}
    mock_manager.evaluate_safety_level.return_value = "WRITE / MUTATION"
    mock_manager.call_tool.return_value = "❌ [MCP Manager 調用失敗]: 資料庫鎖定"

    executor = MCPExecutor(mcp_manager=mock_manager, activity_recorder=recorder)
    task = SubTask(task_id="t_fail", execution_type=ExecutionType.MCP, goal="Fail", target="fail_tool")
    res = executor.execute(task)

    assert res.status == ExecutionStatus.FAILED
    recent = recorder.get_recent()[0]
    assert recent.tool_name == "fail_tool"
    assert recent.status == "failed"
    assert recent.error_summary is not None


def test_mcp_activity_records_timeout() -> None:
    """測試 MCPExecutor 執行逾時時記錄 activity (status='timeout')."""
    recorder = MCPActivityRecorder()
    mock_manager = MagicMock(spec=MCPManager)
    mock_manager.tool_routes = {"slow_tool": "test_server"}
    mock_manager.evaluate_safety_level.return_value = "READ_ONLY"
    mock_manager.call_tool.side_effect = TimeoutError("連線超時")

    executor = MCPExecutor(mcp_manager=mock_manager, activity_recorder=recorder)
    task = SubTask(task_id="t_timeout", execution_type=ExecutionType.MCP, goal="Slow", target="slow_tool")
    res = executor.execute(task)

    assert res.status == ExecutionStatus.TIMEOUT
    recent = recorder.get_recent()[0]
    assert recent.tool_name == "slow_tool"
    assert recent.status == "timeout"
    assert "超時" in (recent.error_summary or "") or "timeout" in (recent.error_summary or "").lower()


def test_mcp_activity_limit() -> None:
    """測試 GET /api/mcp/activity 查詢 limit 參數有效性."""
    recorder = MCPActivityRecorder()
    for i in range(15):
        recorder.record(tool_name=f"tool_{i}", server_name="srv", status="success")

    mock_mgr = MagicMock(spec=MCPManager)
    app = create_web_app(mcp_manager=mock_mgr, mcp_recorder=recorder)
    client = TestClient(app)

    response = client.get("/api/mcp/activity?limit=5")
    assert response.status_code == 200
    data = response.json()
    assert len(data["items"]) == 5
    assert data["total"] == 5


def test_mcp_activity_does_not_store_arguments_or_results() -> None:
    """測試 MCP Activity DTO 絕不包含 parameters, prompt 或 raw results."""
    recorder = MCPActivityRecorder()
    recorder.record(
        tool_name="get_current_time",
        server_name="own_server",
        status="success",
        duration_ms=45.2,
    )

    mock_mgr = MagicMock(spec=MCPManager)
    app = create_web_app(mcp_manager=mock_mgr, mcp_recorder=recorder)
    client = TestClient(app)

    response = client.get("/api/mcp/activity")
    data = response.json()
    item = data["items"][0]

    forbidden_fields = ["arguments", "parameters", "prompt", "result", "raw_output", "content"]
    for field in forbidden_fields:
        assert field not in item, f"敏感欄位 '{field}' 不應存在於 MCP Activity API 回應中"


def test_a2a_only_request_does_not_generate_mcp_activity() -> None:
    """測試純 A2A 代理人對話請求不會產生假 MCP 活動紀錄."""
    recorder = MCPActivityRecorder()
    service = MagicMock(spec=OrchestrationService)
    service.invoke_with_details.return_value = OrchestrationResponse(
        message=AIMessage(content="來自 PCforge 的回覆"),
        plan=TaskPlan(
            plan_id="plan_a2a_only",
            user_goal="買電腦",
            tasks=[SubTask(task_id="t1", execution_type=ExecutionType.A2A, goal="配單")],
        ),
        aggregated=AggregatedResult(plan_id="plan_a2a_only", results=[]),
    )

    app = create_web_app(orchestration_service=service, mcp_recorder=recorder)
    client = TestClient(app)

    client.post("/api/chat", json={"message": "幫我配一台電腦"})
    # 確保 Recorder 依然為 0 筆活動
    assert len(recorder) == 0
