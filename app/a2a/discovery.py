"""M.Ber A2A Agent Discovery Service (代理人發現與註冊服務).

【新手教學 / 觀念解析】：
1. 什麼是 Agent Discovery（代理人發現）？
   - 就像瀏覽器透過 URL 找到網站、或是手機透過通訊錄找到聯絡人一樣，M.Ber 需要一套機制來「發現」周遭可用的其他 AI 代理人（Peer Agents）。
   - 在 A2A 1.0 規範中：
     ① 遠端端點會在 `/.well-known/agent-card.json` 伺服其 Agent Card。
     ② 本地系統可透過設定檔（`config/a2a_agents.json`）預先登記已知的合作代理人。

2. 本模組職責：
   - 載入並解析靜態 Peer Agents 設定。
   - 提供 Agent Card 檢索、按技能（Skill）或名稱查找代理人之功能。
   - 維護記憶體內已驗證之 Agent Card 快取清單。
"""

import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Union
from app.a2a.models import AgentCard, AgentSkill


class AgentDiscoveryService:
    """A2A 代理人發現、解析與元數據註冊服務."""

    WELL_KNOWN_CARD_PATH = "/.well-known/agent-card.json"
    LEGACY_WELL_KNOWN_PATH = "/.well-known/agent.json"

    def __init__(self, config_path: Optional[Union[str, Path]] = None) -> None:
        """初始化 AgentDiscoveryService.

        Args:
            config_path: a2a_agents.json 設定檔路徑（若無指定則預設尋找 config/a2a_agents.json）
        """
        self._registry: Dict[str, AgentCard] = {}

        project_root = Path(__file__).resolve().parent.parent.parent
        if config_path is None:
            config_path = project_root / "config" / "a2a_agents.json"
        self.config_path = Path(config_path)

        # 啟動時自動載入設定檔
        self.reload()

    def reload(self) -> None:
        """重新讀取設定檔並更新代理人註冊表."""
        self._registry.clear()
        if not self.config_path.exists():
            return

        try:
            raw_text = self.config_path.read_text(encoding="utf-8")
            data = json.loads(raw_text)
            agents_data = data.get("agents", [])
            if isinstance(agents_data, dict):
                agents_data = list(agents_data.values())

            for item in agents_data:
                try:
                    card = self.parse_agent_card(item)
                    self.register_agent(card)
                except Exception as e:
                    print(f"⚠️ [A2A Discovery] 解析 Agent Card 失敗 ({item.get('name', 'unknown')}): {e}")
        except Exception as e:
            print(f"❌ [A2A Discovery] 讀取設定檔失敗: {e}")

    @staticmethod
    def parse_agent_card(data: Union[str, Dict[str, Any]]) -> AgentCard:
        """將字串或字典解析並驗證為標準 AgentCard 實體.

        Args:
            data: JSON 字串或 Python 字典

        Returns:
            驗證完成之 AgentCard 物件
        """
        if isinstance(data, str):
            return AgentCard.model_validate_json(data)
        return AgentCard.model_validate(data)

    def register_agent(self, card: AgentCard) -> None:
        """手動註冊或更新 Agent Card 至本地快取註冊表.

        Args:
            card: 欲註冊之 AgentCard 物件
        """
        # 以名稱與 URL 作為索引識別
        self._registry[card.name] = card

    def get_agent(self, name: str) -> Optional[AgentCard]:
        """依據代理人名稱取得 Agent Card.

        Args:
            name: 代理人名稱 (例如 'ResearchAgent')

        Returns:
            若存在回傳 AgentCard，否則回傳 None
        """
        return self._registry.get(name)

    def list_agents(self) -> List[AgentCard]:
        """列出所有已註冊之代理人清單."""
        return list(self._registry.values())

    def find_agent_by_skill(self, skill_id_or_tag: str) -> Optional[AgentCard]:
        """依據技能 ID 或標籤尋找適合承接任務的代理人.

        Args:
            skill_id_or_tag: 技能標識符或標籤關鍵字 (如 'deep_research' 或 'code')

        Returns:
            符合能力條件之第一個 AgentCard，若無則回傳 None
        """
        target = skill_id_or_tag.lower().strip()
        for card in self._registry.values():
            for skill in card.skills:
                if skill.id.lower() == target:
                    return card
                if any(tag.lower() == target for tag in skill.tags):
                    return card
        return None

    @classmethod
    def get_well_known_endpoint(cls, base_url: str) -> str:
        """組合標準 A2A Well-Known Agent Card 探索路徑.

        Args:
            base_url: 代理人伺服器根 URL (例如 'https://agent.example.com')

        Returns:
            完整的 Agent Card 探索 URL
        """
        clean_url = base_url.rstrip("/")
        return f"{clean_url}{cls.WELL_KNOWN_CARD_PATH}"
