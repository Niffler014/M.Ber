"""M.Ber Agent Graph Construction (狀態圖建構模組).

【新手教學 / 觀念解析】：
1. 什麼是 StateGraph？
   - StateGraph 是 LangGraph 的核心類別，用來定義整個 Agent 的「狀態機（State Machine）」。
   - 你可以把 StateGraph 想像成一張地圖，地圖上有地標（Node 節點）和道路（Edge 邊）。

2. 什麼是 Normal Edge 與 Conditional Edge？
   - **Normal Edge（普通邊）**：固定方向的道路。例如 `builder.add_edge(START, "agent")`
     代表程式一旦啟動，第一步必定前往 "agent" 節點。
   - **Conditional Edge（條件邊 / 路由）**：有十字路口與紅綠燈的道路。
     透過一個判斷函式（如 `should_continue`），根據當前 State 的資料決定走哪條路。
     如果 LLM 說需要調用工具 ➔ 前往 "tools" 節點。
     如果 LLM 已經回答完畢 ➔ 前往 END 結束。

3. 什麼是循環（Loop）？
   - 當 "tools" 執行完工具後，透過 `builder.add_edge("tools", "agent")` 把結果送回 "agent"，
     這就形成了一個完整的反饋循環（Agent -> Tools -> Agent），直到 Agent 決定不需再用工具為止。
"""

from typing import Any, Literal, Optional, Union
from langgraph.graph import StateGraph, START, END
from langgraph.graph.state import CompiledStateGraph
from app.agent.state import AgentState
from app.agent.nodes import create_agent_node, create_tools_node, tools_node
from app.mcp.client import MCPStdioClient
from app.mcp.manager import MCPManager
from app.a2a.delegator import A2ADelegator


def should_continue(state: AgentState) -> Literal["tools", "__end__"]:
    """條件邊路由判斷函式 (Router).

    檢查最後一則訊息是否有 `tool_calls`（工具呼叫請求）：
    - 若有 tool_calls：回傳 "tools"，導向工具節點執行工具。
    - 若無 tool_calls：回傳 END，代表任務完成，結束狀態圖。

    Args:
        state: 當前 Agent 狀態

    Returns:
        "tools" 或 END ("__end__")
    """
    messages = state.get("messages", [])
    if not messages:
        return END

    last_message = messages[-1]

    # 檢查最後一則訊息是否包含 tool_calls
    tool_calls = getattr(last_message, "tool_calls", None)
    if tool_calls and len(tool_calls) > 0:
        return "tools"

    return END


def create_agent_graph(
    llm: Optional[Any] = None,
    mcp_client: Optional[Union[MCPManager, MCPStdioClient]] = None,
    mcp_manager: Optional[MCPManager] = None,
    a2a_delegator: Optional[A2ADelegator] = None,
    checkpointer: Optional[Any] = None,
) -> CompiledStateGraph:
    """建立並編譯 M.Ber Agent State Graph.

    此函式負責組裝 State、Nodes 與 Edges，並將其編譯為可執行的 CompiledStateGraph。

    架構流程：
    [START] ──> [agent] ──(should_continue)──┬──(有 tool_calls)──> [tools (MCP Manager)] ──> 回到 [agent]
                                             │
                                             └──(無 tool_calls)──> [END]

    Args:
        llm: 自訂的 LLM 模型實例（可選，若無則使用內建模擬器）
        mcp_client: 單一 MCP Stdio 客戶端實例（可選）
        mcp_manager: MCP 伺服器總管實例（可選，推薦使用，支援多 Server 路由）
        a2a_delegator: A2A 任務委派調度器（可選，支援外部 Peer Agent 技能委派）
        checkpointer: 狀態檢查點管理器（例如 MemorySaver，支援基於 thread_id 的對話記憶隔離）

    Returns:
        編譯完成、可直接呼叫 .invoke() 或 .stream() 的 Graph 物件
    """
    provider = mcp_manager or mcp_client

    builder = StateGraph(AgentState)

    agent_node_fn = create_agent_node(llm, a2a_delegator=a2a_delegator)
    tools_node_fn = create_tools_node(provider)

    builder.add_node("agent", agent_node_fn)
    builder.add_node("tools", tools_node_fn)

    builder.add_edge(START, "agent")

    builder.add_conditional_edges(
        "agent",
        should_continue,
        {
            "tools": "tools",
            END: END,
        },
    )

    builder.add_edge("tools", "agent")

    if checkpointer is not None:
        return builder.compile(checkpointer=checkpointer)

    return builder.compile()
