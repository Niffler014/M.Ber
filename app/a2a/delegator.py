"""M.Ber A2A Delegation & Deterministic Skill Routing Module.

【新手教學 / 觀念解析】：
1. 什麼是 A2A Delegator（代理委派中介層）？
   - 當使用者提出需要其他專業 AI 代理人（例如 PCforge 電腦硬體推薦專家）協助的任務時，
     M.Ber 需要一個乾淨的邊界將任務「外包 / 委派」給外部 Agent。
   - `A2ADelegator` 扮演這個中介角色：
     ① 透過 `AgentDiscoveryService` 檢查已發現之 AgentCard 其聲明的 Skills。
     ② 依據技能宣告進行確定性比對（Deterministic Matching）。
     ③ 透過 `A2AClient` 透過 JSON-RPC 2.0 協定發送任務並解析結果回傳。

2. 為什麼要獨立此模組？
   - 避免將特定外部領域（如 PC 硬體）的商業邏輯散落在 LangGraph 核心節點（`nodes.py`）中。
   - 此處為 Phase 6 的確定性 MVP 路由器，未來可直接平滑升級為 LLM Intent Router，
     而完全不影響底層 A2A 協定與發現服務。
"""

from typing import Any, Callable, Dict, Optional, Tuple, Union
from app.a2a.client import A2AClient, A2AClientError, TransportHandler
from app.a2a.discovery import AgentDiscoveryService, CardTransportHandler
from app.a2a.models import AgentCard, AgentSkill, Message, Task, TextPart


class A2ADelegator:
    """A2A 任務委派與確定性技能調度器 (Deterministic MVP Delegator)."""

    def __init__(
        self,
        discovery_service: Optional[AgentDiscoveryService] = None,
        rpc_transport: Optional[TransportHandler] = None,
        card_transport: Optional[CardTransportHandler] = None,
    ) -> None:
        """初始化 A2ADelegator.

        Args:
            discovery_service: 代理人發現服務實例 (若為 None 則使用預設實例)
            rpc_transport: 自訂 JSON-RPC 傳輸函式 (用於測試注入)
            card_transport: 自訂 Agent Card 探索傳輸函式 (用於測試注入)
        """
        self.discovery = discovery_service or AgentDiscoveryService()
        self.rpc_transport = rpc_transport
        self.card_transport = card_transport
        self._clients: Dict[str, A2AClient] = {}

    def get_client(self, endpoint_url: str) -> A2AClient:
        """取得或建立對應端點的 A2AClient 實例."""
        if endpoint_url not in self._clients:
            self._clients[endpoint_url] = A2AClient(
                endpoint_url=endpoint_url,
                transport=self.rpc_transport,
            )
        return self._clients[endpoint_url]

    def match_agent(self, user_text: str) -> Optional[Tuple[AgentCard, AgentSkill]]:
        """檢查使用者的自然語言輸入是否匹配任何已註冊之 Peer Agent 技能.

        Args:
            user_text: 使用者訊息

        Returns:
            若匹配回傳 (AgentCard, AgentSkill)，否則回傳 None
        """
        return self.discovery.find_agent_for_query(user_text)

    def delegate(
        self,
        card: AgentCard,
        skill: AgentSkill,
        user_text: str,
    ) -> str:
        """將使用者請求透過 A2A 協定委派給目標 Agent 並格式化輸出.

        Args:
            card: 目標代理人名片 (AgentCard)
            skill: 匹配之技能宣告 (AgentSkill)
            user_text: 使用者請求文字

        Returns:
            代理人執行結果之格式化字串
        """
        client = self.get_client(card.url)
        try:
            response = client.send_message(user_text)
        except A2AClientError as e:
            return (
                f"⚠️ [A2A 委派錯誤]: 向外部代理人 '{card.name}' ({card.url}) 發送任務失敗。\n"
                f"錯誤代碼: {e.code}, 錯誤訊息: {e}"
            )
        except Exception as e:
            return (
                f"⚠️ [A2A 通訊異常]: 無法連線至外部代理人 '{card.name}' ({card.url})。\n"
                f"連線狀況: {e}"
            )

        # 處理狀態化 Task 回應
        if isinstance(response, Task):
            status_text = ""
            if response.status.message:
                status_text = response.status.message.text_content

            artifacts_text = ""
            if response.artifacts:
                art_parts = []
                for art in response.artifacts:
                    art_name = art.name or "產物內容"
                    content = "\n".join(p.text for p in art.parts if isinstance(p, TextPart))
                    art_parts.append(f"📦 【{art_name}】\n{content}")
                artifacts_text = "\n\n" + "\n\n".join(art_parts)

            result_body = status_text or "任務已由外部代理人處理完成。"
            return (
                f"🤖 [A2A 遠端代理人: {card.name} (技能: {skill.name})]\n"
                f"任務狀態: {response.status.state.value}\n"
                f"{result_body}{artifacts_text}"
            )

        # 處理直接 Message 回應
        elif isinstance(response, Message):
            return (
                f"🤖 [A2A 遠端代理人: {card.name} (技能: {skill.name})]\n"
                f"{response.text_content}"
            )

        return f"🤖 [A2A 遠端代理人: {card.name}]: 收到非預期之回應結構。"

    def match_and_delegate(self, user_text: str) -> Optional[str]:
        """一站式嘗試技能比對與自動委派.

        Args:
            user_text: 使用者訊息

        Returns:
            若成功匹配並委派，回傳結果字串；若無匹配則回傳 None
        """
        match = self.match_agent(user_text)
        if match is None:
            return None

        card, skill = match
        return self.delegate(card, skill, user_text)
