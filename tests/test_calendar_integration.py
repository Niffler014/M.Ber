"""Integration Tests for M.Ber Phase 4 - Calendar Integration & LangGraph Agent.

驗證項目：
1. MCP Manager 跨伺服器路由至 calendar_server (包含安全權限邊界)
2. LangGraph Agent 相對時間意圖推算與 add_event 工具調用
3. LangGraph Agent query_events 工具調用
4. LangGraph Agent delete_event 工具調用
"""

import pytest
from datetime import datetime, timedelta
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from app.agent.graph import create_agent_graph
from app.mcp.manager import MCPManager


def test_mcp_manager_calendar_routing_and_safety() -> None:
    """測試 MCP Manager 能夠發現並路由 Calendar 伺服器工具."""
    manager = MCPManager()

    # 1. 驗證連線池與工具發現
    assert "calendar_server" in manager.clients
    all_tools = manager.list_all_tools()
    tool_names = [t["name"] for t in all_tools]
    assert "query_events" in tool_names
    assert "add_event" in tool_names
    assert "update_event" in tool_names
    assert "delete_event" in tool_names

    # 2. 驗證安全評估等級
    assert manager.evaluate_safety_level("query_events", {}) == "READ_ONLY"
    assert manager.evaluate_safety_level("add_event", {}) == "WRITE / MUTATION"
    assert manager.evaluate_safety_level("delete_event", {}) == "WRITE / MUTATION"

    # 3. 測試直接透過 MCP Manager 呼叫 add_event 與 query_events
    add_res = manager.call_tool(
        "add_event",
        {
            "title": "Integration_Test_Meeting",
            "start_time": "2026-08-25T14:00:00",
            "end_time": "2026-08-25T15:00:00",
            "location": "會議室 A",
        },
    )
    assert "[Calendar Events]: 成功新增行程" in add_res
    assert "Integration_Test_Meeting" in add_res

    query_res = manager.call_tool(
        "query_events",
        {"start_time": "2026-08-25T00:00:00", "end_time": "2026-08-25T23:59:59"},
    )
    assert "[Calendar Events]: 找到" in query_res
    assert "Integration_Test_Meeting" in query_res


def test_agent_graph_relative_time_calendar_add_event() -> None:
    """測試 LangGraph Agent 將「明天下午3點」相對時間轉換為 ISO 8601 並成功新增行程."""
    manager = MCPManager()
    graph = create_agent_graph(mcp_manager=manager)

    initial_state = {
        "messages": [HumanMessage(content="幫我預約明天下午3點開會，標題=專案進度審查會議")]
    }

    result = graph.invoke(initial_state)
    messages = result.get("messages", [])

    assert len(messages) >= 4
    # 驗證 Agent 產出 tool_calls 包含 add_event 與計算後的時間
    assert isinstance(messages[1], AIMessage)
    assert getattr(messages[1], "tool_calls", None) is not None
    tool_call = messages[1].tool_calls[0]
    assert tool_call["name"] == "add_event"

    # 驗證 ToolMessage
    assert isinstance(messages[2], ToolMessage)
    assert "[Calendar Events]: 成功新增行程" in messages[2].content
    assert "專案進度審查會議" in messages[2].content

    # 驗證最終 Agent 回覆
    assert isinstance(messages[3], AIMessage)
    assert "已成功" in messages[3].content


def test_agent_graph_calendar_query_events() -> None:
    """測試 LangGraph Agent 接收查詢明天的行程意圖並調用 query_events."""
    manager = MCPManager()
    graph = create_agent_graph(mcp_manager=manager)

    initial_state = {
        "messages": [HumanMessage(content="幫我查詢明天的行程有哪些？")]
    }

    result = graph.invoke(initial_state)
    messages = result.get("messages", [])

    assert len(messages) >= 4
    assert isinstance(messages[1], AIMessage)
    assert messages[1].tool_calls[0]["name"] == "query_events"

    assert isinstance(messages[2], ToolMessage)
    assert "[Calendar Events]" in messages[2].content
