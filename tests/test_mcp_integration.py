"""Integration Tests for JARVIS Phase 2 - LangGraph Agent + MCP Server.

驗證項目：
1. LangGraph Agent 透過 MCPStdioClient 調用自製 MCP Server 之 get_current_time
2. LangGraph Agent 透過 MCPStdioClient 調用自製 MCP Server 之 echo_message
3. 驗證完整循環 (START -> agent -> tools (MCP stdio) -> agent -> END)
"""

import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from app.agent.graph import create_agent_graph
from app.mcp.client import MCPStdioClient


def test_agent_graph_with_mcp_get_current_time() -> None:
    """測試 Agent 接收時間查詢意圖，透過 MCP 取得真實時間結果並回覆."""
    mcp_client = MCPStdioClient()
    graph = create_agent_graph(mcp_client=mcp_client)

    initial_state = {
        "messages": [HumanMessage(content="請問現在幾點？")]
    }

    result = graph.invoke(initial_state)
    messages = result.get("messages", [])

    # 驗證狀態圖走完完整 4 步循環
    assert len(messages) >= 4
    assert isinstance(messages[0], HumanMessage)
    assert isinstance(messages[1], AIMessage)
    assert getattr(messages[1], "tool_calls", None) is not None
    assert messages[1].tool_calls[0]["name"] == "get_current_time"

    # 驗證 ToolMessage 由真實 MCP Server 產出
    assert isinstance(messages[2], ToolMessage)
    assert "[JARVIS MCP Time Tool]" in messages[2].content

    # 驗證最終 Agent 回覆
    assert isinstance(messages[3], AIMessage)
    assert "已成功" in messages[3].content


def test_agent_graph_with_mcp_echo_message() -> None:
    """測試 Agent 接收 Echo 意圖，透過 MCP Server 執行參數回傳."""
    mcp_client = MCPStdioClient()
    graph = create_agent_graph(mcp_client=mcp_client)

    initial_state = {
        "messages": [HumanMessage(content="請幫我 echo 測試連線中")]
    }

    result = graph.invoke(initial_state)
    messages = result.get("messages", [])

    assert len(messages) >= 4
    assert isinstance(messages[2], ToolMessage)
    assert "[JARVIS MCP Echo Tool]" in messages[2].content
    assert "測試連線中" in messages[2].content
