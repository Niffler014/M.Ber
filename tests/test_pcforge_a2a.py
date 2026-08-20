"""Unit and Integration Tests for M.Ber Phase 6 - PCforge A2A Client Integration.

【新手教學 / 觀念驗證】：
1. 驗證 M.Ber 作為 A2A Client 與外部 PCforge A2A Server 通訊的完整流程。
2. 驗證 WHERE vs. WHAT 發現語意：
   - 本地設定檔僅紀錄 PCforge 端點位置（WHERE: http://localhost:8001）
   - 權威 Agent Card 必須自遠端 /.well-known/agent-card.json 動態取得（WHAT: 技能、能力、描述）
3. 驗證 JSON-RPC 2.0 協定請求封裝與 Task/Artifact 回應解析。
4. 驗證確定性 MVP 技能比對與 LangGraph 端到端委派流程（使用 Fake PCforge Server 模擬，零外部依賴）。
"""

from typing import Any, Dict
import pytest
from pydantic import ValidationError
from langchain_core.messages import AIMessage, HumanMessage

from app.a2a.client import A2AClient, A2AClientError
from app.a2a.delegator import A2ADelegator
from app.a2a.discovery import AgentDiscoveryService
from app.a2a.models import (
    AgentCapabilities,
    AgentCard,
    AgentSkill,
    Artifact,
    Message,
    Task,
    TaskState,
    TaskStatus,
    TextPart,
)
from app.agent.graph import create_agent_graph


# ============================================================================
# 模擬外部 PCforge A2A Server 資料與端點傳輸
# ============================================================================

PCFORGE_MOCK_CARD_DICT = {
    "name": "PCforge",
    "description": "PC 規格配置、組裝推薦與硬體相容性評估代理人 (PC Build & Hardware Recommendation Agent)",
    "url": "http://localhost:8001/v1/a2a",
    "version": "1.0.0",
    "protocol_version": "1.0.0",
    "capabilities": {
        "streaming": False,
        "push_notifications": False,
    },
    "skills": [
        {
            "id": "pc_recommendation",
            "name": "PC Hardware & Build Recommendation",
            "description": "根據使用者預算、用途推薦最合適的電腦零組件菜單與評估相容性",
            "tags": ["hardware", "pc_build", "gaming_pc", "compatibility", "pc_recommendation"],
            "examples": [
                "推薦一台 40000 元左右的遊戲主機",
                "幫我評估 RTX 4070 配 650W 電源是否足夠",
                "40k 預算組裝電腦菜單推薦",
            ],
            "input_modes": ["text/plain"],
            "output_modes": ["text/plain"],
        }
    ],
    "default_input_modes": ["text/plain"],
    "default_output_modes": ["text/plain"],
    "security_schemes": {},
    "security": [],
    "metadata": {
        "environment": "local_development",
        "provider": "PCforge Remote Agent",
    },
}


def fake_pcforge_card_transport(url: str) -> Dict[str, Any]:
    """模擬 PCforge 伺服器伺服 /.well-known/agent-card.json."""
    if ".well-known/agent-card.json" in url:
        return PCFORGE_MOCK_CARD_DICT
    raise RuntimeError(f"404 Not Found: {url}")


def fake_pcforge_rpc_transport(url: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    """模擬外部 PCforge A2A Server 處理 JSON-RPC 2.0 請求."""
    req_id = payload.get("id")
    method = payload.get("method")
    params = payload.get("params", {})

    if payload.get("jsonrpc") != "2.0":
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "error": {"code": -32600, "message": "Invalid JSON-RPC version"},
        }

    if method == "SendMessage":
        message_dict = params.get("message", {})
        msg_obj = Message.model_validate(message_dict)
        user_query = msg_obj.text_content

        # 模擬 PCforge 生成菜單推薦與 Markdown 產物
        build_markdown = (
            "# PCforge 40K 遊戲主機推薦菜單\n"
            "- CPU: AMD Ryzen 5 7500F ($5,200)\n"
            "- 主機板: B650M GAMING X AX ($3,990)\n"
            "- 顯示卡: NVIDIA RTX 4060 Ti 8G ($12,900)\n"
            "- 記憶體: DDR5-6000 16GBx2 ($3,199)\n"
            "- SSD: 1TB PCIe 4.0 NVMe ($2,200)\n"
            "- 電源: 650W 80+ 金牌 ($2,590)\n"
            "- 機殼: 散熱透側機殼 ($1,690)\n"
            "總預算約: 31,769 ~ 39,800 NTD。"
        )

        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {
                "id": "pcforge-task-40k-001",
                "status": {
                    "state": "completed",
                    "message": {
                        "role": "agent",
                        "parts": [
                            {
                                "type": "text",
                                "text": f"已為您完成電腦組裝規劃（依據需求：'{user_query}'）！",
                            }
                        ],
                    },
                },
                "history": [
                    msg_obj.model_dump(),
                    {
                        "role": "agent",
                        "parts": [{"type": "text", "text": "已規劃合適硬體菜單。"}],
                    },
                ],
                "artifacts": [
                    {
                        "id": "art-pcforge-menu-01",
                        "name": "pc_build_recommendation.md",
                        "description": "40K 遊戲主機硬體推薦菜單",
                        "parts": [{"type": "text", "text": build_markdown}],
                    }
                ],
            },
        }

    return {
        "jsonrpc": "2.0",
        "id": req_id,
        "error": {"code": -32601, "message": f"Method '{method}' not found"},
    }


# ============================================================================
# 1. 探索測試 (Discovery Tests)
# ============================================================================

def test_pcforge_configured_endpoint_in_config() -> None:
    """驗證 M.Ber 設定檔僅記錄 PCforge 端點位置 (WHERE)，不硬編碼 Agent Card 內容."""
    discovery = AgentDiscoveryService()
    peers = discovery.configured_peers

    assert len(peers) >= 1
    pcforge_peer = next((p for p in peers if p.get("name") == "PCforge"), None)
    assert pcforge_peer is not None
    assert "url" in pcforge_peer
    assert "skills" not in pcforge_peer  # 確保設定檔不重複定義技能 source of truth


def test_pcforge_dynamic_agent_card_discovery() -> None:
    """驗證自外部端點動態拉取並解析權威 PCforge Agent Card."""
    discovery = AgentDiscoveryService()

    card = discovery.discover_peer(
        endpoint_url="http://localhost:8001",
        transport=fake_pcforge_card_transport,
    )

    assert isinstance(card, AgentCard)
    assert card.name == "PCforge"
    assert card.url == "http://localhost:8001/v1/a2a"
    assert card.version == "1.0.0"
    assert len(card.skills) == 1
    assert card.skills[0].id == "pc_recommendation"
    assert "hardware" in card.skills[0].tags
    assert "gaming_pc" in card.skills[0].tags

    # 驗證動態註冊至統一註冊表
    registered = discovery.get_agent("PCforge")
    assert registered is not None
    assert registered.name == "PCforge"


def test_pcforge_invalid_agent_card_rejection() -> None:
    """驗證當外部端點回傳不合法之 Agent Card 時進行防禦性拒絕."""
    discovery = AgentDiscoveryService()

    def corrupt_card_transport(url: str) -> Dict[str, Any]:
        return {"name": "CorruptAgent"}  # 缺少 url 等必填欄位

    with pytest.raises(ValidationError):
        discovery.discover_peer("http://localhost:8001", transport=corrupt_card_transport)


# ============================================================================
# 2. 客戶端協定測試 (Client & JSON-RPC Protocol Tests)
# ============================================================================

def test_pcforge_a2a_request_envelope_structure() -> None:
    """驗證 A2AClient 構造符合 JSON-RPC 2.0 的 SendMessage 請求封包."""
    recorded_payload: Dict[str, Any] = {}

    def inspect_transport(url: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        nonlocal recorded_payload
        recorded_payload = payload
        return fake_pcforge_rpc_transport(url, payload)

    client = A2AClient(endpoint_url="http://localhost:8001/v1/a2a", transport=inspect_transport)
    response = client.send_message("推薦一台 40000 元左右的遊戲主機")

    # 1. 驗證 Request 封包
    assert recorded_payload.get("jsonrpc") == "2.0"
    assert recorded_payload.get("method") == "SendMessage"
    assert "id" in recorded_payload
    params = recorded_payload.get("params", {})
    assert "message" in params
    assert params["message"]["role"] == "user"
    assert params["message"]["parts"][0]["text"] == "推薦一台 40000 元左右的遊戲主機"

    # 2. 驗證 Response 解析
    assert isinstance(response, Task)
    assert response.id == "pcforge-task-40k-001"
    assert response.status.state == TaskState.COMPLETED
    assert len(response.artifacts) == 1
    assert response.artifacts[0].name == "pc_build_recommendation.md"
    assert "AMD Ryzen 5 7500F" in response.artifacts[0].parts[0].text


# ============================================================================
# 3. 確定性技能匹配測試 (Deterministic MVP Skill Matching)
# ============================================================================

def test_deterministic_skill_matching_for_pcforge() -> None:
    """測試根據 AgentCard 宣告之技能標籤與範例進行確定性技能匹配."""
    discovery = AgentDiscoveryService()
    discovery.discover_peer("http://localhost:8001", transport=fake_pcforge_card_transport)

    # 測試匹配硬體相關問題
    queries = [
        "推薦一台 40000 元左右的遊戲主機",
        "幫我評估 RTX 4070 配 650W 電源是否足夠",
        "請推薦 40k 預算組裝電腦菜單",
        "想組一台 gaming_pc",
    ]
    for q in queries:
        match = discovery.find_agent_for_query(q)
        assert match is not None, f"查詢 '{q}' 應該匹配 PCforge"
        card, skill = match
        assert card.name == "PCforge"
        assert skill.id == "pc_recommendation"

    # 測試不應匹配的不相關問題 (如行程、時間)
    unrelated_queries = [
        "幫我預約明天下午3點開會",
        "查詢明天的行程有哪些",
        "現在幾點",
    ]
    for uq in unrelated_queries:
        match = discovery.find_agent_for_query(uq)
        if match is not None:
            # 若有匹配不能是 PCforge
            assert match[0].name != "PCforge"


# ============================================================================
# 4. 端到端整合測試 (End-to-End LangGraph Agent Flow)
# ============================================================================

def test_e2e_agent_graph_pcforge_delegation_flow() -> None:
    """測試完整的 M.Ber Agent 接收使用者電腦組裝需求並成功委派給 PCforge 遠端 Agent.

    驗證路徑：
    User -> M.Ber Agent -> A2ADelegator -> A2AClient -> Fake PCforge Server -> A2A Task Response -> M.Ber Output
    """
    discovery = AgentDiscoveryService()
    discovery.discover_peer("http://localhost:8001", transport=fake_pcforge_card_transport)

    delegator = A2ADelegator(
        discovery_service=discovery,
        rpc_transport=fake_pcforge_rpc_transport,
    )

    graph = create_agent_graph(a2a_delegator=delegator)

    user_prompt = "推薦一台 40000 元左右的遊戲主機菜單"
    initial_state = {"messages": [HumanMessage(content=user_prompt)]}

    result = graph.invoke(initial_state)
    messages = result.get("messages", [])

    assert len(messages) >= 2
    last_msg = messages[-1]
    assert isinstance(last_msg, AIMessage)

    # 驗證輸出包含 PCforge 回傳的任務成果與推薦清單
    content = last_msg.content
    assert "PCforge" in content
    assert "pc_build_recommendation.md" in content
    assert "AMD Ryzen 5 7500F" in content
    assert "RTX 4060 Ti" in content
    assert "任務狀態: completed" in content
