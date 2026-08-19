"""Unit Tests for M.Ber Phase 1 - Basic LangGraph Agent.

驗證項目：
1. Graph 編譯完整性
2. 一般對話路由流轉 (agent -> END)
3. 工具調用循環流轉 (agent -> tools -> agent -> END)
4. Router 條件路由函式邏輯 (should_continue)
5. State 訊息累加機制 (add_messages)
6. 自訂 LLM 注入支援
"""

import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langgraph.graph import END
from app.agent.state import AgentState
from app.agent.nodes import dummy_tool, create_agent_node, tools_node
from app.agent.graph import create_agent_graph, should_continue


def test_graph_compilation() -> None:
    """測試 LangGraph 能否順利編譯無拋出例外."""
    graph = create_agent_graph()
    assert graph is not None
    # 驗證狀態圖中包含預期的節點
    assert "agent" in graph.nodes
    assert "tools" in graph.nodes


def test_router_should_continue() -> None:
    """測試 Router 條件路由判斷邏輯."""
    # 情況 1：無訊息 -> END
    empty_state: AgentState = {"messages": []}
    assert should_continue(empty_state) == END

    # 情況 2：一般 AIMessage（無 tool_calls）-> END
    normal_state: AgentState = {
        "messages": [
            HumanMessage(content="你好"),
            AIMessage(content="你好！我是 M.Ber。"),
        ]
    }
    assert should_continue(normal_state) == END

    # 情況 3：帶有 tool_calls 的 AIMessage -> "tools"
    tool_call_state: AgentState = {
        "messages": [
            HumanMessage(content="幫我算一下 2 + 2"),
            AIMessage(
                content="需要計算",
                tool_calls=[
                    {"id": "call_1", "name": "calculator", "args": {"expression": "2 + 2"}}
                ],
            ),
        ]
    }
    assert should_continue(tool_call_state) == "tools"


def test_normal_chat_execution_flow() -> None:
    """測試一般純對話流程：START -> agent -> END (無工具調用)."""
    graph = create_agent_graph()
    initial_state = {
        "messages": [HumanMessage(content="哈囉，你好！")]
    }

    result = graph.invoke(initial_state)

    messages = result.get("messages", [])
    assert len(messages) == 2
    assert isinstance(messages[0], HumanMessage)
    assert isinstance(messages[1], AIMessage)
    assert "M.Ber" in messages[1].content
    assert not getattr(messages[1], "tool_calls", None)


def test_tool_calling_execution_flow() -> None:
    """測試工具調用循環流程：START -> agent -> tools -> agent -> END."""
    graph = create_agent_graph()
    initial_state = {
        "messages": [HumanMessage(content="請幫我計算 25 * 4")]
    }

    result = graph.invoke(initial_state)

    messages = result.get("messages", [])
    # 預期包含：
    # 1. HumanMessage (使用者提問)
    # 2. AIMessage (Agent 發起工具調用 tool_calls)
    # 3. ToolMessage (Tools 節點執行工具產出結果)
    # 4. AIMessage (Agent 根據工具結果產出最終回覆)
    assert len(messages) >= 4
    assert isinstance(messages[0], HumanMessage)
    assert isinstance(messages[1], AIMessage)
    assert getattr(messages[1], "tool_calls", None) is not None
    assert isinstance(messages[2], ToolMessage)
    assert "100" in messages[2].content
    assert isinstance(messages[3], AIMessage)
    assert "已成功" in messages[3].content


def test_dummy_tool_implementations() -> None:
    """測試 Dummy 工具函式邏輯."""
    # 測試計算機
    calc_res = dummy_tool("calculator", {"expression": "10 + 20"})
    assert "30" in calc_res

    # 測試非法字元安全阻擋
    bad_calc = dummy_tool("calculator", {"expression": "__import__('os').system('ls')"})
    assert "[Calculator Error]" in bad_calc

    # 測試時間工具
    time_res = dummy_tool("get_system_time", {})
    assert "[System Time]" in time_res

    # 測試 Echo 工具
    echo_res = dummy_tool("dummy_echo", {"query": "測試內容"})
    assert "測試內容" in echo_res


def test_custom_mock_llm_injection() -> None:
    """測試 Graph 支援注入自訂 LLM / Mock 實例."""
    class MockLLM:
        def invoke(self, messages):
            return AIMessage(content="來自 Mock LLM 的客製化回應")

    graph = create_agent_graph(llm=MockLLM())
    result = graph.invoke({"messages": [HumanMessage(content="隨便輸入")]})

    messages = result.get("messages", [])
    assert len(messages) == 2
    assert messages[-1].content == "來自 Mock LLM 的客製化回應"
