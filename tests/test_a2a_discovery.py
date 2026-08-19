"""Unit Tests for JARVIS Phase 6 - A2A Agent Discovery Service.

驗證項目：
1. Discovery 服務載入 config/a2a_agents.json 設定檔
2. 手動註冊 AgentCard 與列表查詢
3. 依據技能 (Skill ID 或 Tag) 探索目標 Agent
4. 標準 /.well-known/agent-card.json 端點路徑合成
"""

from pathlib import Path
import pytest
from app.a2a.discovery import AgentDiscoveryService
from app.a2a.models import AgentCard, AgentSkill


def test_discovery_load_from_default_config() -> None:
    """測試 Discovery 服務自動載入專案預設 config/a2a_agents.json."""
    service = AgentDiscoveryService()
    agents = service.list_agents()

    assert len(agents) >= 2
    agent_names = [a.name for a in agents]
    assert "ResearchAgent" in agent_names
    assert "CoderAgent" in agent_names

    researcher = service.get_agent("ResearchAgent")
    assert researcher is not None
    assert researcher.url == "https://research-agent.local/v1/a2a"
    assert len(researcher.skills) >= 1
    assert researcher.skills[0].id == "deep_research"


def test_discovery_find_by_skill_and_tag() -> None:
    """測試依據 Skill ID 與 Tag 搜尋對應能力之 Agent."""
    service = AgentDiscoveryService()

    # 1. 透過 Skill ID 查詢
    agent_by_id = service.find_agent_by_skill("deep_research")
    assert agent_by_id is not None
    assert agent_by_id.name == "ResearchAgent"

    # 2. 透過 Skill Tag 查詢
    agent_by_tag = service.find_agent_by_skill("refactor")
    assert agent_by_tag is not None
    assert agent_by_tag.name == "CoderAgent"

    # 3. 查詢不存在之技能
    assert service.find_agent_by_skill("non_existent_skill") is None


def test_discovery_manual_registration(tmp_path: Path) -> None:
    """測試在空白設定檔環境下手動註冊 Agent Card."""
    empty_conf = tmp_path / "empty_agents.json"
    empty_conf.write_text('{"agents": []}', encoding="utf-8")

    service = AgentDiscoveryService(config_path=empty_conf)
    assert len(service.list_agents()) == 0

    custom_card = AgentCard(
        name="CustomHelper",
        description="A helpful assistant",
        url="https://custom.local/a2a",
        skills=[AgentSkill(id="helper_task", name="Helper", description="Helps out", tags=["help"])],
    )
    service.register_agent(custom_card)

    assert len(service.list_agents()) == 1
    assert service.get_agent("CustomHelper") == custom_card
    assert service.find_agent_by_skill("help") == custom_card


def test_discovery_well_known_endpoint_helper() -> None:
    """測試合成標準 /.well-known/agent-card.json 端點 URL."""
    url = AgentDiscoveryService.get_well_known_endpoint("https://peer.agent.com/v1")
    assert url == "https://peer.agent.com/v1/.well-known/agent-card.json"

    url_slash = AgentDiscoveryService.get_well_known_endpoint("https://peer.agent.com/")
    assert url_slash == "https://peer.agent.com/.well-known/agent-card.json"
