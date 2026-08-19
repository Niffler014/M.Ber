"""M.Ber Agent State Definition.

【新手教學 / 觀念解析】：
1. 什麼是 State（狀態）？
   - 在 LangGraph 中，State 是整個 Agent 運作時的「全域共享記憶體」。
   - 就像大家共同編輯一份即時文件，每個 Node（節點）都可以讀取 State 中的資料，
     並在執行完畢後產出更新，回寫到 State 中。

2. 為什麼使用 TypedDict？
   - TypedDict 讓我們可以定義一個字典結構，並為其中的鍵值指定型別（Type Annotations）。
   - 這樣做可以在寫程式與 IDE 開發時獲得完整的自動補全與型別檢查提示。

3. 什麼是 `Annotated` 與 `add_messages`？
   - 預設情況下，當一個節點回傳一個鍵值（例如 messages = [new_msg]），
     LangGraph 會直接用新值「覆蓋（Overwrite）」舊值。
   - 但對話歷史需要「不斷累積（Append）」，而不是洗掉過去的對話。
   - `Annotated[Sequence[BaseMessage], add_messages]` 中的 `add_messages` 是 LangGraph
     提供的內建 Reducer（合併器函式），它告訴 LangGraph：「當收到新訊息時，請自動將新訊息加入到既有清單末尾，不要覆蓋！」
"""

from typing import Annotated, Sequence
from typing_extensions import TypedDict
from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages


class AgentState(TypedDict):
    """M.Ber Agent 核心狀態定義.

    Attributes:
        messages: 儲存對話歷史訊息的清單。
                  使用 `add_messages` Reducer 確保訊息會按時間順序持續累加，
                  包含 HumanMessage（使用者輸入）、AIMessage（LLM 回應）以及 ToolMessage（工具執行結果）。
    """

    messages: Annotated[Sequence[BaseMessage], add_messages]
