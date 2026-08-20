"""M.Ber Agent Graph Construction (狀態圖建構模組).

【新手教學 / 觀念解析】：
1. 什麼是 StateGraph？
   - StateGraph 是 LangGraph 的核心類別，用來定義整個 Agent 的「狀態機（State Machine）」。
   - 在 Phase 7 (P7-07)，M.Ber 支援以 `OrchestrationService` 作為頂層單一調度權威（Single Routing Authority）：
     所有使用者意圖均透過 Planner 統一規劃為 LOCAL / MCP / A2A 任務，
     並由 Orchestrator 與 ResultAggregator 完成調度與成果彙整。
   - 同時保留 Phase 1-4 經典 tool-calling 循環邊界以確保平滑相容。
"""

from typing import Any, Literal, Optional, Union
from langgraph.graph import StateGraph, START, END
from langgraph.graph.state import CompiledStateGraph
from app.agent.state import AgentState
from app.agent.nodes import create_agent_node, create_tools_node, tools_node
from app.mcp.client import MCPStdioClient
from app.mcp.manager import MCPManager
from app.a2a.delegator import A2ADelegator
from app.a2a.discovery import AgentDiscoveryService
from memory.service import MemoryService


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
    discovery_service: Optional[AgentDiscoveryService] = None,
    memory_service: Optional[MemoryService] = None,
    planner: Optional[Any] = None,
    orchestrator: Optional[Any] = None,
    orchestration_service: Optional[Any] = None,
    use_orchestration: bool = False,
    checkpointer: Optional[Any] = None,
) -> CompiledStateGraph:
    """建立並編譯 M.Ber Agent State Graph.

    此函式負責組裝 State、Nodes 與 Edges，並將其編譯為可執行的 CompiledStateGraph。

    Args:
        llm: 自訂的 LLM 模型實例（可選）
        mcp_client: 單一 MCP Stdio 客戶端實例（可選）
        mcp_manager: MCP 伺服器總管實例（可選，推薦使用，支援多 Server 路由）
        a2a_delegator: A2A 任務委派調度器（可選，支援外部 Peer Agent 技能委派）
        discovery_service: A2A 發現服務實例（可選）
        memory_service: 記憶服務實例（可選）
        planner: 自訂 Planner 實例（可選）
        orchestrator: 自訂 Orchestrator 實例（可選）
        orchestration_service: 自訂 OrchestrationService 實例（可選）
        use_orchestration: 是否啟用 Phase 7 OrchestrationService 作為唯一頂層路由權威 (預設 False 維持舊版測試相容)
        checkpointer: 狀態檢查點管理器（例如 MemorySaver，支援基於 thread_id 的對話記憶隔離）

    Returns:
        編譯完成、可直接呼叫 .invoke() 或 .stream() 的 Graph 物件
    """
    provider = mcp_manager or mcp_client
    manager = provider if isinstance(provider, MCPManager) else None

    # 從 a2a_delegator 提取 discovery_service 與 rpc_transport
    disc = discovery_service
    rpc_trans = None
    if a2a_delegator is not None:
        if disc is None:
            disc = a2a_delegator.discovery
        if rpc_trans is None:
            rpc_trans = a2a_delegator.rpc_transport

    active_orchestration_service = None
    if use_orchestration or orchestration_service is not None or planner is not None or orchestrator is not None:
        if orchestration_service is not None:
            active_orchestration_service = orchestration_service
        else:
            from app.orchestration.service import OrchestrationService

            active_orchestration_service = OrchestrationService(
                planner=planner,
                orchestrator=orchestrator,
                llm=llm,
                mcp_manager=manager,
                discovery_service=disc,
                memory_service=memory_service,
                rpc_transport=rpc_trans,
            )

    builder = StateGraph(AgentState)

    agent_node_fn = create_agent_node(
        llm=llm,
        a2a_delegator=a2a_delegator,
        orchestration_service=active_orchestration_service,
    )
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


def create_orchestrated_graph(
    llm: Optional[Any] = None,
    mcp_manager: Optional[MCPManager] = None,
    discovery_service: Optional[AgentDiscoveryService] = None,
    memory_service: Optional[MemoryService] = None,
    a2a_delegator: Optional[A2ADelegator] = None,
    planner: Optional[Any] = None,
    orchestrator: Optional[Any] = None,
    checkpointer: Optional[Any] = None,
) -> CompiledStateGraph:
    """便利工廠函式：建立以 Phase 7 OrchestrationService 為核心的生產級 StateGraph."""
    return create_agent_graph(
        llm=llm,
        mcp_manager=mcp_manager,
        discovery_service=discovery_service,
        memory_service=memory_service,
        a2a_delegator=a2a_delegator,
        planner=planner,
        orchestrator=orchestrator,
        use_orchestration=True,
        checkpointer=checkpointer,
    )
