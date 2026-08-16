"""Unit Tests for JARVIS Phase 3 - MCP Manager (app/mcp/manager.py).

驗證項目：
1. 外部設定檔 (config/mcp_servers.json) 讀取與解析
2. 多伺服器連線池建立 (own_server + sqlite_server)
3. 跨伺服器工具探索彙整 (list_all_tools)
4. 多伺服器智慧請求路由 (call_tool 根據工具名稱自動導向)
5. 安全權限模型分類 (READ_ONLY vs WRITE / MUTATION)
"""

import pytest
from app.mcp.manager import MCPManager


def test_mcp_manager_initialization_and_tool_discovery() -> None:
    """測試 MCP Manager 初始化、連線池與工具探索."""
    manager = MCPManager()

    # 驗證至少連線了 own_server 與 sqlite_server 兩個伺服器
    assert "own_server" in manager.clients
    assert "sqlite_server" in manager.clients

    # 驗證匯總工具清單包含來自兩個伺服器的工具
    all_tools = manager.list_all_tools()
    tool_names = [t["name"] for t in all_tools]

    assert "get_current_time" in tool_names
    assert "echo_message" in tool_names
    assert "read_notes" in tool_names
    assert "add_note" in tool_names


def test_mcp_manager_multi_server_routing() -> None:
    """測試 MCP Manager 是否能將請求正確分流至不同 Server."""
    manager = MCPManager()

    # 1. 測試路由至 own_server
    time_res = manager.call_tool("get_current_time", {})
    assert "[JARVIS MCP Time Tool]" in time_res

    # 2. 測試路由至 sqlite_server (唯讀查詢)
    read_res = manager.call_tool("read_notes", {"keyword": "test_non_existent_xyz"})
    assert "[SQLite Notes]" in read_res


def test_mcp_manager_safety_level_evaluation() -> None:
    """測試安全權限模型之唯讀與修改等級判斷."""
    manager = MCPManager()

    # 唯讀操作檢驗
    assert manager.evaluate_safety_level("get_current_time", {}) == "READ_ONLY"
    assert manager.evaluate_safety_level("read_notes", {}) == "READ_ONLY"
    assert manager.evaluate_safety_level("list_files", {}) == "READ_ONLY"
    assert manager.evaluate_safety_level("query_database", {}) == "READ_ONLY"

    # 修改/寫入操作檢驗
    assert manager.evaluate_safety_level("add_note", {"title": "A"}) == "WRITE / MUTATION"
    assert manager.evaluate_safety_level("create_task", {}) == "WRITE / MUTATION"
    assert manager.evaluate_safety_level("delete_file", {}) == "WRITE / MUTATION"
    assert manager.evaluate_safety_level("update_profile", {}) == "WRITE / MUTATION"
