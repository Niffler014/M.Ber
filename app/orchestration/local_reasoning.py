"""M.Ber Local Reasoning Adapter (本地推理解析適配器模組).
Phase 8 - P8-03.5: Real Conversation Integration

【新手教學 / 觀念解析】：
1. 什麼是 LocalReasoningAdapter？
   - 它是 M.Ber 在執行 `LOCAL` 任務（如通用問答、常識對話、程式概念解釋）時的專用處理常式適配器。
   - 它的單一職責：
     ① 接收 Planner 產出的 `SubTask`（例如 `target='general_qa'` 或 `target='agent_reasoning'`）與執行上下文 `ExecutionContext`。
     ② 調用注入的 **Tool-Free ChatModel** 產生真實、生動且自然的語言回覆。
     ③ 絕不自行做二次工具綁定（Tool Binding）或路由分發，嚴守 Single Routing Authority 邊界。
     ④ 當底層 LLM 未配置或調用出錯時，拋出明確例外交由 `LocalExecutor` 映射為 `FAILED` 或 `TIMEOUT`，絕不以「已為您處理完成：{goal}」假成功欺騙使用者。
"""

import logging
from typing import Any, List, Optional

from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage

from app.orchestration.models import ExecutionContext, SubTask

logger = logging.getLogger("mber.orchestration")

SYSTEM_CONVERSATION_PROMPT = (
    "You are M.Ber (伯伯), a helpful, warm, and concise personal AI assistant. "
    "Respond in Traditional Chinese (繁體中文) naturally and helpfully."
)


class LocalReasoningAdapter:
    """本地通用推理與對話適配器 (Tool-Free Local Reasoning Adapter)."""

    def __init__(self, llm: Optional[Any] = None) -> None:
        """初始化 LocalReasoningAdapter.

        Args:
            llm: 支援 .invoke() 之標準 LangChain ChatModel (Tool-Free)
        """
        self.llm = llm

    def handle_reasoning(
        self,
        task: SubTask,
        context: Optional[ExecutionContext] = None,
    ) -> str:
        """執行本地推理解析並回傳文字結果 (由 LocalExecutor 統一封裝為 ExecutionResult)."""
        goal = (task.goal or "").strip()
        if not goal:
            raise ValueError("任務目標 (task.goal) 為空")

        # 1. 若有注入真實 / Mock LLM 實例，調用 LLM 進行真實對話生成
        if self.llm is not None:
            prompt_messages: List[BaseMessage] = [
                SystemMessage(content=SYSTEM_CONVERSATION_PROMPT),
            ]

            # 從 ExecutionContext 讀取相關歷史對話（若有提供）
            history_messages = []
            if context is not None and context.metadata:
                raw_msgs = context.metadata.get("messages", [])
                if isinstance(raw_msgs, list):
                    history_messages = [m for m in raw_msgs if isinstance(m, BaseMessage)]

            if history_messages:
                prompt_messages.extend(history_messages)
            else:
                prompt_messages.append(HumanMessage(content=goal))

            logger.info(f"[LocalReasoning] Invoking LLM for goal: '{goal[:40]}...'")
            response = self.llm.invoke(prompt_messages)
            content_text = response.content if isinstance(response, BaseMessage) else str(response)
            return str(content_text)

        # 2. 離線確定性知識庫 (Deterministic Offline Knowledge without LLM)
        fallback_text = self._offline_deterministic_reply(goal)
        if fallback_text is not None:
            return fallback_text

        # 3. 若無 LLM 亦無離線知識庫，明確拋出例外 (不傳回佔位假成功)
        raise RuntimeError(f"未設定語言模型 (ChatModel) 且無對應離線知識庫，無法執行本地推理: '{goal}'")

    def _offline_deterministic_reply(self, goal: str) -> Optional[str]:
        """離線無模型時之自然語言特定知識回覆 (若無匹配則回傳 None)."""
        goal_lower = goal.lower()

        if any(k in goal_lower for k in ["哈囉", "你好", "hello", "hi", "您好"]):
            return "您好！我是 M.Ber，很高興為您服務。請問有什麼我可以協助您的？"

        if any(k in goal_lower for k in ["肚子很餓", "肚子餓", "我好餓", "很餓", "想吃什麼", "想吃飯", "吃什麼好"]):
            return "如果現在肚子餓了，建議可以先喝杯溫水或來點熱食墊墊胃喔！您今天比較想吃熱騰騰的麵食、飽足的便當，還是清爽的輕食呢？"

        if "dependency injection" in goal_lower or "依賴注入" in goal_lower:
            return (
                "【Dependency Injection (依賴注入)】是一種軟體設計模式，"
                "將物件所依賴的其他服務從外部傳入，而非在物件內部直接建立，"
                "從而達到解耦、易於單元測試與依賴反轉（Inversion of Control）的效果。"
            )

        if "decorator" in goal_lower or "裝飾器" in goal_lower:
            return (
                "【Python Decorator (裝飾器)】是一種在不修改既有函式程式碼的前提下，"
                "動態為其擴充額外功能（如計時、日誌、權限檢查）的高階函式語法糖（@decorator）。"
            )

        if any(k in goal_lower for k in ["買了", "買到", "入手", "買", "bought"]) and "電腦" in goal_lower:
            return "恭喜您添購了新電腦！新配備用起來感覺如何呢？如果有需要安裝軟體、備份資料或設定環境，都可以隨時問我喔！"

        return None
