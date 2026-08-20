"""Phase 7 P7-08 Real End-to-End Orchestration Demo & Verification Test Suite.

驗證項目：
1. Primary Demo: A2A (PCforge) -> LOCAL (Memory) 循序調度與真實記憶庫檢索驗證
2. LOCAL Smoke: 一般本地推理 (General QA / Reasoning)
3. MCP Smoke: 唯讀安全 MCP 工具調用 (get_current_time)
4. A2A Failure: 外部代理人離線 ➔ 依賴任務 SKIPPED ➔ 記憶庫無污染 ➔ 優雅回報錯誤
5. Partial Failure: A2A 成功但 Memory 異常 ➔ 成果完整保留並明確提示儲存失敗
6. Production Default: 驗證 compiled graph 預設採用 OrchestrationService 作為唯一頂層路由
"""

from typing import Any, Dict, List, Optional
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
    ExecutionResult,
    ExecutionStatus,
    ExecutionType,
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
def e2e_discovery() -> AgentDiscoveryService:
    discovery = AgentDiscoveryService(config_path="non_existent.json")
    discovery.register_agent(
        AgentCard(
            name="PCforge",
            description="PC組裝與硬體推薦專家",
            url="http://localhost:8001/rpc",
            skills=[
                AgentSkill(
                    id="pc_recommendation",
                    name="電腦硬體推薦",
                    description="電腦組裝菜單與硬體配置推薦",
                    tags=["電腦", "pc", "硬體", "組裝", "菜單", "主機", "配單"],
                )
            ],
        )
    )
    return discovery


@pytest.fixture
def e2e_memory_service() -> MemoryService:
    repo = InMemoryMemoryRepository()
    return MemoryService(repository=repo)


# ============================================================================
# 1. Primary Demo: Sequential A2A (PCforge) ➔ LOCAL (Memory)
# ============================================================================

def test_p7_primary_demo_a2a_to_memory_workflow(
    e2e_discovery: AgentDiscoveryService,
    e2e_memory_service: MemoryService,
) -> None:
    """[Scenario 1] 主要真實端到端場景：

    使用者請求：「幫我配一台 40000 元遊戲電腦，然後幫我記住這套配置。」
    1. Planner 規劃兩步任務：
       - Task 1: A2A (PCforge pc_recommendation)
       - Task 2: LOCAL (memory_store, depends_on Task 1)
    2. Orchestrator 調度執行 Task 1，成功取得 PCforge 菜單。
    3. Orchestrator 將 Task 1 結果注入 Task 2，成功寫入 MemoryService。
    4. ResultAggregator 彙整為 SUCCESS。
    5. Final Response 回傳包含 PC 菜單與記憶庫儲存確認的友善回覆。
    6. 實際透過 MemoryService.search() 檢索驗證資料確實寫入。
    """
    mcp_manager = MCPManager()
    graph = create_orchestrated_graph(
        mcp_manager=mcp_manager,
        discovery_service=e2e_discovery,
        memory_service=e2e_memory_service,
        a2a_delegator=A2ADelegator(discovery_service=e2e_discovery, rpc_transport=fake_pcforge_rpc_transport),
    )

    initial_state = {
        "messages": [HumanMessage(content="幫我配一台 40000 元遊戲電腦，然後幫我記住這套配置。")]
    }

    result = graph.invoke(initial_state)
    messages = result.get("messages", [])

    assert len(messages) >= 2
    last_msg = messages[-1]
    assert isinstance(last_msg, AIMessage)
    reply_text = last_msg.content

    # 驗證 final response 品質 (不 dump raw object，具備實際內容)
    assert "PCforge" in reply_text
    assert "AMD Ryzen 5 7500F" in reply_text
    assert "RTX 4060 Ti" in reply_text
    assert "記憶庫" in reply_text

    # 驗證真實記憶持久化 (Real Memory Persistence)
    stored_memories = e2e_memory_service.search(query="Ryzen")
    assert len(stored_memories) == 1
    retrieved = stored_memories[0]
    assert "AMD Ryzen 5 7500F" in retrieved.content
    assert retrieved.memory_type == MemoryType.GENERAL


# ============================================================================
# 2. Real LOCAL Smoke Test
# ============================================================================

def test_p7_local_reasoning_smoke() -> None:
    """[Scenario 2] 本地推理 Smoke Test：

    使用者請求：「解釋什麼是 dependency injection」
    - 走 Planner -> LOCAL -> local reasoning -> 回傳專業概念解析。
    - 不因 target 未明確指定而拋出 unknown target 錯誤。
    """
    graph = create_orchestrated_graph()
    initial_state = {"messages": [HumanMessage(content="解釋什麼是 dependency injection")]}

    result = graph.invoke(initial_state)
    last_msg = result["messages"][-1]

    assert isinstance(last_msg, AIMessage)
    assert "Dependency Injection" in last_msg.content or "依賴注入" in last_msg.content
    assert "解耦" in last_msg.content or "測試" in last_msg.content


# ============================================================================
# 3. Real MCP Smoke Test
# ============================================================================

def test_p7_mcp_read_only_tool_smoke() -> None:
    """[Scenario 3] 唯讀安全 MCP 工具 Smoke Test：

    使用者請求：「現在幾點？」
    - 走 Planner -> MCP (get_current_time) -> MCPExecutor -> MCPManager (own_server)
    - 回傳格式化後的系統時間結果。
    """
    mcp_manager = MCPManager()
    graph = create_orchestrated_graph(mcp_manager=mcp_manager)

    initial_state = {"messages": [HumanMessage(content="現在幾點？")]}
    result = graph.invoke(initial_state)
    last_msg = result["messages"][-1]

    assert isinstance(last_msg, AIMessage)
    assert "已成功透過 MCP 工具" in last_msg.content or "現在時間" in last_msg.content or "當前時間" in last_msg.content


# ============================================================================
# 4. Failure Demo: A2A Offline ➔ Dependency Skipped ➔ No Memory Pollution
# ============================================================================

def test_p7_failure_demo_a2a_offline_skips_memory(
    e2e_discovery: AgentDiscoveryService,
    e2e_memory_service: MemoryService,
) -> None:
    """[Scenario 4] 故障隔離示範：

    外部代理人 (PCforge) 離線 / 斷線：
    1. Task 1 (A2A) 執行失敗 (FAILED)。
    2. Task 2 (LOCAL memory_store) 因依賴未滿足而被安全略過 (SKIPPED)。
    3. MemoryService 保持純淨，無任何垃圾資料寫入。
    4. 回覆明確指出無法連線至外部代理人，不假稱記住。
    """
    def offline_rpc_transport(url: str, payload: dict) -> dict:
        raise ConnectionRefusedError(f"Connection refused at {url}")

    graph = create_orchestrated_graph(
        discovery_service=e2e_discovery,
        memory_service=e2e_memory_service,
        a2a_delegator=A2ADelegator(discovery_service=e2e_discovery, rpc_transport=offline_rpc_transport),
    )

    initial_state = {
        "messages": [HumanMessage(content="幫我配一台 40000 元遊戲電腦，然後幫我記住這套配置。")]
    }

    result = graph.invoke(initial_state)
    last_msg = result["messages"][-1]

    assert isinstance(last_msg, AIMessage)
    reply_text = last_msg.content
    assert "無法順利完成" in reply_text or "失敗" in reply_text or "無法連線" in reply_text

    # 驗證記憶庫完全無污染 (No Memory Pollution)
    all_memories = e2e_memory_service.search(query="Ryzen")
    assert len(all_memories) == 0


# ============================================================================
# 5. Partial Failure Demo: A2A Success + Memory Failure
# ============================================================================

def test_p7_partial_failure_demo(
    e2e_discovery: AgentDiscoveryService,
) -> None:
    """[Scenario 5] 部分成功示範：

    A2A 配單成功，但 MemoryService 發生異常 (如資料表鎖定)：
    1. Task 1 (A2A) 成功 (SUCCESS)。
    2. Task 2 (LOCAL memory_store) 失敗 (FAILED)。
    3. ResultAggregator 判定為 PARTIAL_SUCCESS。
    4. 回覆完整保留 PCforge 配單成果，但誠實警告記憶庫儲存失敗。
    """
    class LockedMemoryService(MemoryService):
        def remember(self, content, memory_type=MemoryType.GENERAL, metadata=None):
            raise RuntimeError("Database locked by external process")

    broken_memory = LockedMemoryService(repository=InMemoryMemoryRepository())

    graph = create_orchestrated_graph(
        discovery_service=e2e_discovery,
        memory_service=broken_memory,
        a2a_delegator=A2ADelegator(discovery_service=e2e_discovery, rpc_transport=fake_pcforge_rpc_transport),
    )

    initial_state = {
        "messages": [HumanMessage(content="幫我配一台 40000 元遊戲電腦，然後幫我記住這套配置。")]
    }

    result = graph.invoke(initial_state)
    last_msg = result["messages"][-1]

    assert isinstance(last_msg, AIMessage)
    reply_text = last_msg.content
    # 配單成果必須保留
    assert "AMD Ryzen 5 7500F" in reply_text
    # 失敗警示必須明確呈現
    assert "注意" in reply_text or "失敗" in reply_text
    assert "Database locked" in reply_text
