"""Unit Tests for JARVIS Phase 2 - Own MCP Server (my_mcp_server.py).

驗證項目：
1. MCP Server 啟動與 stdio 連線
2. 工具清單探索 (list_tools) 包含 get_current_time 與 echo_message
3. 取得系統時間工具執行 (call_tool: get_current_time)
4. 訊息回傳工具執行 (call_tool: echo_message) 與參數傳遞
"""

import pytest
from app.mcp.client import MCPStdioClient


def test_mcp_server_list_tools() -> None:
    """測試 MCP Server 是否能正確透過 stdio 回應可用工具清單."""
    client = MCPStdioClient()
    tools = client.list_tools()

    assert len(tools) >= 2
    tool_names = [t["name"] for t in tools]
    assert "get_current_time" in tool_names
    assert "echo_message" in tool_names

    # 驗證工具說明與 Schema
    time_tool = next(t for t in tools if t["name"] == "get_current_time")
    assert "時間" in time_tool["description"] or "time" in time_tool["description"].lower()

    echo_tool = next(t for t in tools if t["name"] == "echo_message")
    assert "echo" in echo_tool["name"]
    assert "message" in echo_tool["parameters"].get("properties", {})


def test_mcp_server_call_get_current_time() -> None:
    """測試呼叫 MCP Server 之 get_current_time 工具."""
    client = MCPStdioClient()
    result = client.call_tool("get_current_time", {})

    assert "[JARVIS MCP Time Tool]" in result
    # 驗證包含西元年份數字格式 (如 2026 或 202)
    assert "202" in result


def test_mcp_server_call_echo_message() -> None:
    """測試呼叫 MCP Server 之 echo_message 工具與參數傳遞."""
    client = MCPStdioClient()
    test_str = "JARVIS_PHASE_2_TEST_PAYLOAD"
    result = client.call_tool("echo_message", {"message": test_str})

    assert "[JARVIS MCP Echo Tool]" in result
    assert test_str in result
