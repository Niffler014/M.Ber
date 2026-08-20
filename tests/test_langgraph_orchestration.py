"""Integration Tests for M.Ber LangGraph Orchestration & Single Routing Authority (P7-07)."""

from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock
import pytest
from langchain_core.messages import AIMessage, HumanMessage

from app.a2a.delegator import A2ADelegator
from app.a2a.discovery import AgentDiscoveryService
from app.a2a.models import AgentCard, AgentSkill
from app.agent.graph import create_agent_graph, create_orchestrated_graph
from app.mcp.manager import MCPManager
from app.orchestration.models import (
    AggregatedResult,
    AggregateStatus,
    ExecutionContext,
    ExecutionResult,
    ExecutionStatus,
    ExecutionType,
    SubTask,
    TaskPlan,
)
from app.orchestration.service import OrchestrationService
from memory.models import MemoryItem, MemoryType
from memory.repository import InMemoryMemoryRepository
from memory.service import MemoryService
from tests.test_pcforge_a2a import (
    fake_pcforge_card_transport,
    fake_pcforge_rpc_transport,
)


@pytest.fixture
def fake_discovery() -> AgentDiscoveryService:
    discovery = AgentDiscoveryService(config_path="non_existent.json")
    discovery.register_agent(
        AgentCard(
            name="PCforge",
            description="配單專家",
            url="http://localhost:8001/rpc",
            skills=[
                AgentSkill(
                    id="pc_recommendation",
                    name="電腦硬體推薦",
                    description="組裝菜單",
                    tags=["電腦", "pc", "硬體", "組裝", "主機", "菜單", "配單"],
                )
            ],
        )
    )
    return discovery


@pytest.fixture
def fake_memory_service() -> MemoryService:
    repo = InMemoryMemoryRepository()
    return MemoryService(repository=repo)


# ============================================================================
# 1. Single Routing Authority & Integration Tests
# ============================================================================

def test_orchestration_node_local_request() -> None:
    """測試一般本地推理解析請求：走 Planner -> LOCAL -> 產生 AIMessage."""
    graph = create_orchestrated_graph()
    initial_state = {"messages": [HumanMessage(content="解釋什麼是 dependency injection")]}

    result = graph.invoke(initial_state)
    messages = result.get("messages", [])

    assert len(messages) >= 2
    last_msg = messages[-1]
    assert isinstance(last_msg, AIMessage)
    assert "Dependency Injection" in last_msg.content or "依賴注入" in last_msg.content


def test_orchestration_node_a2a_request(fake_discovery: AgentDiscoveryService) -> None:
    """測試 A2A 委派請求：走 Planner -> A2A -> A2AExecutor -> PCforge -> AIMessage."""
    graph = create_orchestrated_graph(
        discovery_service=fake_discovery,
        a2a_delegator=A2ADelegator(discovery_service=fake_discovery, rpc_transport=fake_pcforge_rpc_transport),
    )

    initial_state = {"messages": [HumanMessage(content="推薦一台 40000 元左右的遊戲主機菜單")]}
    result = graph.invoke(initial_state)
    messages = result.get("messages", [])

    assert len(messages) >= 2
    last_msg = messages[-1]
    assert isinstance(last_msg, AIMessage)
    assert "PCforge" in last_msg.content
    assert "AMD Ryzen 5 7500F" in last_msg.content


def test_routing_authority_legacy_delegator_not_called(fake_discovery: AgentDiscoveryService) -> None:
    """驗證頂層路由全權由 Planner 負責，Phase 6 legacy A2ADelegator.match_and_delegate 絕不被呼叫."""
    delegator = A2ADelegator(discovery_service=fake_discovery, rpc_transport=fake_pcforge_rpc_transport)
    # Mock legacy match_and_delegate 方法
    delegator.match_and_delegate = MagicMock(return_value="LEGACY_CALLED")

    graph = create_orchestrated_graph(
        discovery_service=fake_discovery,
        a2a_delegator=delegator,
    )

    initial_state = {"messages": [HumanMessage(content="推薦一台 40000 元左右的遊戲主機菜單")]}
    result = graph.invoke(initial_state)
    messages = result.get("messages", [])

    # 驗證 legacy 方法未被直接呼叫
    delegator.match_and_delegate.assert_not_called()
    assert "LEGACY_CALLED" not in messages[-1].content
    assert "PCforge" in messages[-1].content


def test_orchestration_node_mcp_request() -> None:
    """測試 MCP 工具請求：走 Planner -> MCP -> MCPExecutor -> 產出標準回覆."""
    mcp_manager = MCPManager()
    graph = create_orchestrated_graph(mcp_manager=mcp_manager)

    initial_state = {"messages": [HumanMessage(content="現在幾點")]}
    result = graph.invoke(initial_state)
    messages = result.get("messages", [])

    assert len(messages) >= 2
    last_msg = messages[-1]
    assert isinstance(last_msg, AIMessage)
    assert "已成功透過 MCP 工具" in last_msg.content or "現在時間" in last_msg.content or "當前時間" in last_msg.content


def test_orchestration_node_multistep_request(
    fake_discovery: AgentDiscoveryService,
    fake_memory_service: MemoryService,
) -> None:
    """測試多步驟循序工作流：配電腦 + 記憶儲存 ➔ 成果完整寫入 MemoryService 且回傳合成回覆."""
    graph = create_orchestrated_graph(
        discovery_service=fake_discovery,
        memory_service=fake_memory_service,
        a2a_delegator=A2ADelegator(discovery_service=fake_discovery, rpc_transport=fake_pcforge_rpc_transport),
    )

    initial_state = {"messages": [HumanMessage(content="幫我配一台 40000 元遊戲電腦，然後幫我記住這套配置")]}
    result = graph.invoke(initial_state)
    messages = result.get("messages", [])

    assert len(messages) >= 2
    last_msg = messages[-1]
    assert isinstance(last_msg, AIMessage)
    content = last_msg.content
    assert "PCforge" in content
    assert "AMD Ryzen 5 7500F" in content
    assert "記憶庫" in content

    # 驗證 MemoryService 內確實已持久化儲存
    all_mems = fake_memory_service.search(query="Ryzen")
    assert len(all_mems) == 1
    assert "AMD Ryzen 5 7500F" in all_mems[0].content


def test_orchestration_node_partial_failure_response(
    fake_discovery: AgentDiscoveryService,
) -> None:
    """測試部分失敗情境：A2A 成功但 Memory 失敗 ➔ AIMessage 保留成功配單成果並提示記憶異常."""
    class FailingMemoryService(MemoryService):
        def remember(self, content, memory_type=MemoryType.GENERAL, metadata=None):
            raise RuntimeError("Storage table locked")

    broken_mem = FailingMemoryService(repository=InMemoryMemoryRepository())
    graph = create_orchestrated_graph(
        discovery_service=fake_discovery,
        memory_service=broken_mem,
        a2a_delegator=A2ADelegator(discovery_service=fake_discovery, rpc_transport=fake_pcforge_rpc_transport),
    )

    initial_state = {"messages": [HumanMessage(content="幫我配一台 40000 元遊戲電腦，然後幫我記住這套配置")]}
    result = graph.invoke(initial_state)
    messages = result.get("messages", [])

    assert len(messages) >= 2
    last_msg = messages[-1]
    assert isinstance(last_msg, AIMessage)
    content = last_msg.content
    # 成功項目必須存在
    assert "AMD Ryzen 5 7500F" in content
    # 失敗項目必須提示
    assert "注意" in content or "失敗" in content
    assert "Storage table locked" in content


def test_orchestration_node_full_failure_response(
    fake_discovery: AgentDiscoveryService,
    fake_memory_service: MemoryService,
) -> None:
    """測試全失敗情境：A2A 連線中斷 ➔ Memory 略過 ➔ AIMessage 清楚回報錯誤而不拋出異常."""
    def broken_rpc(url: str, payload: dict) -> dict:
        raise ConnectionRefusedError("PCforge is down")

    graph = create_orchestrated_graph(
        discovery_service=fake_discovery,
        memory_service=fake_memory_service,
        a2a_delegator=A2ADelegator(discovery_service=fake_discovery, rpc_transport=broken_rpc),
    )

    initial_state = {"messages": [HumanMessage(content="幫我配一台 40000 元遊戲電腦，然後幫我記住這套配置")]}
    result = graph.invoke(initial_state)
    messages = result.get("messages", [])

    assert len(messages) >= 2
    last_msg = messages[-1]
    assert isinstance(last_msg, AIMessage)
    content = last_msg.content
    assert "任務無法順利完成" in content or "失敗" in content


def test_custom_llm_injection_with_orchestration() -> None:
    """測試 Graph 注入自訂 LLM 時能透過 OrchestrationService LOCAL reasoning 產生回應."""
    class CustomLLM:
        def invoke(self, messages):
            return AIMessage(content="來自整合 LLM 的專業回答")

    graph = create_orchestrated_graph(llm=CustomLLM())
    result = graph.invoke({"messages": [HumanMessage(content="任意問題")]})

    messages = result.get("messages", [])
    assert len(messages) == 2
    assert messages[-1].content == "來自整合 LLM 的專業回答"
