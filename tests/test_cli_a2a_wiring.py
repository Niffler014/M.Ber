"""Unit and Integration Tests for M.Ber CLI A2A Wiring.

【新手教學 / 觀念驗證】：
1. 驗證 M.Ber CLI 啟動時正確初始化 A2A Discovery Service 與 A2ADelegator。
2. 驗證由 config/a2a_agents.json 設定檔自動探索外部 Peer (PCforge)。
3. 驗證當外部 Peer (PCforge) 在線時，使用者提出電腦組裝需求能正確觸發 A2A 委派。
4. 驗證當外部 Peer (PCforge) 離線時，CLI 啟動輸出警告但不崩潰，維持正常功能運作。
"""

from typing import Any, Dict
from unittest.mock import patch
import pytest
from langchain_core.messages import AIMessage, HumanMessage

from app.a2a.delegator import A2ADelegator
from app.a2a.discovery import AgentDiscoveryService
from app.agent.graph import create_agent_graph
from app.cli import run_cli
from app.mcp.manager import MCPManager
from tests.test_pcforge_a2a import (
    PCFORGE_MOCK_CARD_DICT,
    fake_pcforge_card_transport,
    fake_pcforge_rpc_transport,
)


def test_cli_a2a_wiring_success_delegation(capsys: pytest.CaptureFixture[str]) -> None:
    """驗證 CLI A2A 接線：當 PCforge 在線時，Graph 接收 a2a_delegator 並成功委派任務."""
    discovery_service = AgentDiscoveryService()
    discovered_cards = discovery_service.discover_configured_peers(
        transport=fake_pcforge_card_transport
    )
    assert len(discovered_cards) >= 1
    assert any(card.name == "PCforge" for card in discovered_cards)

    a2a_delegator = A2ADelegator(
        discovery_service=discovery_service,
        rpc_transport=fake_pcforge_rpc_transport,
    )

    mcp_manager = MCPManager()
    graph = create_agent_graph(
        mcp_manager=mcp_manager,
        a2a_delegator=a2a_delegator,
    )

    # 模擬使用者輸入電腦硬體推薦需求
    user_query = "幫我推薦一台 40000 元左右的遊戲電腦"
    initial_state = {"messages": [HumanMessage(content=user_query)]}

    result = graph.invoke(initial_state)
    messages = result.get("messages", [])

    assert len(messages) >= 2
    last_msg = messages[-1]
    assert isinstance(last_msg, AIMessage)
    assert "PCforge" in last_msg.content
    assert "AMD Ryzen 5 7500F" in last_msg.content


def test_cli_a2a_wiring_offline_fallback() -> None:
    """驗證當外部 Peer 離線時，CLI 接線不崩潰，且一般對話與 MCP 功能正常運作."""
    def failing_card_transport(url: str) -> Dict[str, Any]:
        raise RuntimeError("Connection refused: http://localhost:8001")

    discovery_service = AgentDiscoveryService()
    discovered_cards = discovery_service.discover_configured_peers(
        transport=failing_card_transport
    )
    # 離線時 discovered 清單應為空
    assert len(discovered_cards) == 0

    a2a_delegator = A2ADelegator(
        discovery_service=discovery_service,
    )

    mcp_manager = MCPManager()
    graph = create_agent_graph(
        mcp_manager=mcp_manager,
        a2a_delegator=a2a_delegator,
    )

    # 一般問候對話仍可正常運行
    greet_state = {"messages": [HumanMessage(content="你好")]}
    result_greet = graph.invoke(greet_state)
    assert len(result_greet["messages"]) >= 2
    assert "M.Ber" in result_greet["messages"][-1].content


def test_run_cli_online_discovery_output(capsys: pytest.CaptureFixture[str]) -> None:
    """測試 run_cli 在 Peer 在線時的終端機輸出資訊."""
    with patch("builtins.input", side_effect=["exit"]):
        with patch.object(
            AgentDiscoveryService,
            "fetch_agent_card",
            return_value=AgentDiscoveryService.parse_agent_card(PCFORGE_MOCK_CARD_DICT),
        ):
            run_cli()

    captured = capsys.readouterr().out
    assert "🤝 [A2A Discovery]: discovered agents:" in captured
    assert "PCforge" in captured


def test_run_cli_offline_discovery_output(capsys: pytest.CaptureFixture[str]) -> None:
    """測試 run_cli 在 Peer 離線時的終端機警告輸出與安全退出."""
    with patch("builtins.input", side_effect=["exit"]):
        with patch.object(
            AgentDiscoveryService,
            "fetch_agent_card",
            side_effect=RuntimeError("Connection refused"),
        ):
            run_cli()

    captured = capsys.readouterr().out
    assert "⚠️ [A2A Discovery]" in captured
    assert "unavailable" in captured or "失敗" in captured
    assert "M.Ber 關閉中" in captured
