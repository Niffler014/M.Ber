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
import urllib.request
import urllib.error
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple, Union
from app.a2a.models import AgentCard, AgentSkill


# 定義用於探索端點之 Transport 型別 (供注入與測試)
CardTransportHandler = Callable[[str], Union[str, Dict[str, Any]]]


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
        self._peers: List[Dict[str, str]] = []

        project_root = Path(__file__).resolve().parent.parent.parent
        if config_path is None:
            config_path = project_root / "config" / "a2a_agents.json"
        self.config_path = Path(config_path)

        # 啟動時自動載入設定檔
        self.reload()

    @property
    def configured_peers(self) -> List[Dict[str, str]]:
        """取得設定檔中已登記的外部 Peer 端點清單 (僅記錄位置 WHERE)."""
        return list(self._peers)

    def reload(self) -> None:
        """重新讀取設定檔並更新代理人註冊表."""
        self._registry.clear()
        self._peers.clear()
        if not self.config_path.exists():
            return

        try:
            raw_text = self.config_path.read_text(encoding="utf-8")
            data = json.loads(raw_text)

            # 1. 載入外部 Peer 端點宣告 (僅包含名稱與 URL，不含 Agent Card 內容)
            peers_data = data.get("peers", [])
            if isinstance(peers_data, list):
                self._peers = [p for p in peers_data if isinstance(p, dict) and "url" in p]

            # 2. 載入靜態/本地已知代理人卡片 (若有)
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

    def find_agent_for_query(self, query: str) -> Optional[Tuple[AgentCard, AgentSkill]]:
        """確定性 MVP 技能匹配：根據使用者輸入字串與已註冊代理人之技能宣告進行判定.

        【架構說明】：
        此為 Phase 6 的確定性技能比對 MVP 實作，直接依據 AgentCard 中聲明的
        tags、examples、skill id 與 name 進行匹配。
        未來在更進階的架構中，此處可抽換為 LLM Intent Router，而無需變更 A2A 協定底層。

        Args:
            query: 使用者輸入之自然語言訊息

        Returns:
            匹配之 (AgentCard, AgentSkill) 二元組，若無匹配則回傳 None
        """
        q_lower = query.lower().strip()
        for card in self._registry.values():
            for skill in card.skills:
                # 1. 檢查技能 ID 與名稱
                if skill.id.lower() in q_lower or skill.name.lower() in q_lower:
                    return card, skill

                # 2. 檢查技能標籤 (Tags)
                for tag in skill.tags:
                    tag_clean = tag.lower().strip().replace("_", " ")
                    if tag_clean and (tag_clean in q_lower or tag.lower() in q_lower):
                        return card, skill

                # 3. 檢查範例 (Examples)
                for ex in skill.examples:
                    ex_clean = ex.lower().strip()
                    # 若使用者輸入與範例有顯著交集關鍵字
                    if any(part in q_lower for part in ex_clean.split() if len(part) >= 2):
                        return card, skill

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

    @classmethod
    def fetch_agent_card(
        cls,
        endpoint_url: str,
        transport: Optional[CardTransportHandler] = None,
        timeout: float = 10.0,
    ) -> AgentCard:
        """從遠端端點獲取權威 Agent Card (/.well-known/agent-card.json).

        Args:
            endpoint_url: 遠端伺服器基底 URL 或完整 card URL
            transport: 自訂傳輸函式 (若為 None 則使用 urllib HTTP GET)
            timeout: 連線超時秒數

        Returns:
            解析並驗證通過之 AgentCard 實體
        """
        if endpoint_url.endswith(".json"):
            card_url = endpoint_url
        else:
            card_url = cls.get_well_known_endpoint(endpoint_url)

        if transport is not None:
            raw_data = transport(card_url)
            return cls.parse_agent_card(raw_data)

        req = urllib.request.Request(
            url=card_url,
            headers={
                "Accept": "application/json",
                "User-Agent": "M.Ber-A2A-Discovery/1.0",
            },
            method="GET",
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                content = resp.read().decode("utf-8")
                return cls.parse_agent_card(content)
        except Exception as e:
            raise RuntimeError(f"無法從 '{card_url}' 取得 Agent Card: {e}") from e

    def discover_peer(
        self,
        endpoint_url: str,
        transport: Optional[CardTransportHandler] = None,
        timeout: float = 10.0,
    ) -> AgentCard:
        """動態探索外部 Peer 代理人並註冊至註冊表.

        Args:
            endpoint_url: 外部代理人端點位置 (WHERE)
            transport: 傳輸函式 (可選，供測試注入)
            timeout: 超時秒數

        Returns:
            權威 AgentCard 實體
        """
        card = self.fetch_agent_card(endpoint_url, transport=transport, timeout=timeout)
        self.register_agent(card)
        return card

    def discover_configured_peers(
        self,
        transport: Optional[CardTransportHandler] = None,
        timeout: float = 10.0,
    ) -> List[AgentCard]:
        """批量探索設定檔中登記的所有 external peers.

        Returns:
            成功探索之 AgentCard 清單
        """
        discovered: List[AgentCard] = []
        for peer in self._peers:
            url = peer.get("url")
            if not url:
                continue
            try:
                card = self.discover_peer(url, transport=transport, timeout=timeout)
                discovered.append(card)
            except Exception as e:
                print(f"⚠️ [A2A Discovery] 自動探索 Peer 失敗 ({peer.get('name', url)}): {e}")
        return discovered

