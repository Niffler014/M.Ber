"""Integration Tests for JARVIS Phase 3 - Third-party MCP Server (sqlite_server.py).

驗證項目：
1. 第三方 SQLite MCP Server 之筆記寫入與讀取
2. LangGraph Agent 整合 MCP Manager 調用 add_note 工具
3. LangGraph Agent 整合 MCP Manager 調用 read_notes 工具
"""

import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from app.agent.graph import create_agent_graph
from app.mcp.manager import MCPManager


def test_sqlite_server_add_and_read_notes_flow() -> None:
    """測試 SQLite MCP Server 新增筆記與隨後讀取驗證."""
    manager = MCPManager()

    test_title = "Phase3_Test_Title"
    test_content = "Phase3_Test_Content_Payload"

    # 1. 新增筆記
    add_res = manager.call_tool("add_note", {"title": test_title, "content": test_content})
    assert "[SQLite Notes]: 成功新增筆記" in add_res
    assert test_title in add_res

    # 2. 查詢筆記
    read_res = manager.call_tool("read_notes", {"keyword": test_title})
    assert "[SQLite Notes]" in read_res
    assert test_title in read_res
    assert test_content in read_res


def test_agent_graph_with_third_party_add_note() -> None:
    """測試 LangGraph Agent 接收新增筆記意圖，透過 MCP Manager 成功寫入資料庫."""
    manager = MCPManager()
    graph = create_agent_graph(mcp_manager=manager)

    initial_state = {
        "messages": [HumanMessage(content="新增筆記：標題=明日待辦事項，內容=下午兩點開專案會議")]
    }

    result = graph.invoke(initial_state)
    messages = result.get("messages", [])

    assert len(messages) >= 4
    assert isinstance(messages[1], AIMessage)
    assert getattr(messages[1], "tool_calls", None) is not None
    assert messages[1].tool_calls[0]["name"] == "add_note"

    assert isinstance(messages[2], ToolMessage)
    assert "[SQLite Notes]: 成功新增筆記" in messages[2].content

    assert isinstance(messages[3], AIMessage)
    assert "已成功" in messages[3].content


def test_agent_graph_with_third_party_read_notes() -> None:
    """測試 LangGraph Agent 接收查詢筆記意圖，透過 MCP Manager 成功讀取資料庫."""
    manager = MCPManager()
    graph = create_agent_graph(mcp_manager=manager)

    initial_state = {
        "messages": [HumanMessage(content="查詢筆記：明日待辦事項")]
    }

    result = graph.invoke(initial_state)
    messages = result.get("messages", [])

    assert len(messages) >= 4
    assert isinstance(messages[1], AIMessage)
    assert messages[1].tool_calls[0]["name"] == "read_notes"

    assert isinstance(messages[2], ToolMessage)
    assert "[SQLite Notes]" in messages[2].content
