"""JARVIS Agent Nodes (工作節點模組).

【新手教學 / 觀念解析】：
1. 什麼是 Node（節點）？
   - Node 就是狀態圖中的「工人」或「加工站」。
   - 在 Python 中，Node 通常就是一個簡單的函式：
     def my_node(state: AgentState) -> dict:
         ...
         return {"messages": [new_message]}
   - Node 接收目前的 State（所有變數的狀態），執行它負責的工作（例如呼叫 LLM 或是執行某個 Tool 工具），
     最後回傳一個字典，表示這次要更新或增加哪些狀態欄位。

2. 系統中的兩個核心節點：
   - `agent_node` (大腦)：負責分析使用者的話或工具的回傳結果，思考後產生 AIMessage。
     如果大腦覺得需要使用工具，會在 AIMessage 中標記 `tool_calls`。
   - `tools_node` (工具手臂)：負責讀取 AIMessage 要求的 `tool_calls`，呼叫對應的函式（如查資料、算數學），
     並將結果打包成 `ToolMessage` 回傳給 State。
"""

from typing import Any, Callable, Dict, List, Optional
import json
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, ToolMessage
from app.agent.state import AgentState


def dummy_tool(tool_name: str, args: Dict[str, Any]) -> str:
    """模擬工具執行函式（Dummy Tool）.

    在 Phase 1 中，我們尚未連接真實的 MCP Server，
    因此使用 Dummy Tool 來驗證 LangGraph 的工具調用循環架構是否健全。

    Args:
        tool_name: 要執行的工具名稱（例如 "echo_tool" 或 "calculator"）
        args: 工具接收的參數字典

    Returns:
        工具執行的字串結果
    """
    if tool_name == "calculator":
        expression = str(args.get("expression", "0"))
        try:
            # 簡易安全計算 (僅限基礎運算字元)
            allowed_chars = set("0123456789+-*/(). ")
            if not set(expression).issubset(allowed_chars):
                return f"[Calculator Error]: 不合法的運算字元: {expression}"
            result = eval(expression, {"__builtins__": None}, {})
            return f"[Calculator Result]: {expression} = {result}"
        except Exception as e:
            return f"[Calculator Error]: 計算失敗 ({e})"

    elif tool_name == "get_system_time":
        from datetime import datetime
        return f"[System Time]: 現在時間為 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"

    else:
        # 預設 echo tool
        query = args.get("query") or args.get("input") or str(args)
        return f"[Dummy Echo Tool]: 收到工具請求 '{tool_name}'，參數為: {query}"


def create_agent_node(llm: Optional[Any] = None) -> Callable[[AgentState], Dict[str, List[BaseMessage]]]:
    """建立 Agent 節點函式.

    可接受外部傳入的 LLM 實例（例如 ChatOpenAI、ChatOllama 或 MockLLM）。
    若未傳入 LLM，則使用內建的確定性模擬器（Deterministic Simulator），
    確保在無 API Key 的環境下仍能完整走完工具調用流程與測試。

    Args:
        llm: 實作 LangChain BaseChatModel 介面的語言模型實例（可選）

    Returns:
        符合 LangGraph 規格的節點函式 (state) -> dict
    """

    def agent_node(state: AgentState) -> Dict[str, List[BaseMessage]]:
        """Agent 大腦思考節點.

        讀取對話歷史中的所有 messages，決定下一步是要直接回答使用者，
        還是產生 tool_calls 請求呼叫外部工具。
        """
        messages = list(state.get("messages", []))
        if not messages:
            return {"messages": [AIMessage(content="您好！我是 JARVIS，請問有什麼我可以協助您的？")]}

        # 如果有注入真實的 LLM，直接呼叫 LLM
        if llm is not None:
            response = llm.invoke(messages)
            if not isinstance(response, BaseMessage):
                response = AIMessage(content=str(response))
            return {"messages": [response]}

        # --- 無 LLM 時的內建模擬邏輯 (Fallback / Demo / Test 模式) ---
        last_msg = messages[-1]

        # 情況 A：如果上一則訊息是 ToolMessage，代表工具剛執行完畢，大腦做最後總結
        if isinstance(last_msg, ToolMessage):
            tool_output = last_msg.content
            return {
                "messages": [
                    AIMessage(content=f"已成功為您執行工具！執行結果如下：\n{tool_output}\n請問還需要其他協助嗎？")
                ]
            }

        # 情況 B：分析使用者最新輸入的文字
        user_text = last_msg.content if isinstance(last_msg.content, str) else str(last_msg.content)
        user_text_lower = user_text.lower()

        # 檢查是否觸發計算機工具
        if "計算" in user_text or "算一下" in user_text or "calculate" in user_text_lower:
            # 簡易提取運算式
            import re
            match = re.search(r"[\d\+\-\*\/\(\)\. ]{3,}", user_text)
            expr = match.group(0).strip() if match else "1 + 1"
            tool_call = {
                "id": "call_calc_001",
                "name": "calculator",
                "args": {"expression": expr},
            }
            return {
                "messages": [
                    AIMessage(
                        content="我需要使用計算機工具來為您計算這個數值。",
                        tool_calls=[tool_call],
                    )
                ]
            }

        # 檢查是否觸發時間查詢工具
        elif "時間" in user_text or "幾點" in user_text or "time" in user_text_lower:
            tool_call = {
                "id": "call_time_001",
                "name": "get_system_time",
                "args": {},
            }
            return {
                "messages": [
                    AIMessage(
                        content="我正在查詢目前的系統時間...",
                        tool_calls=[tool_call],
                    )
                ]
            }

        # 檢查是否觸發通用 dummy 工具
        elif "工具" in user_text or "tool" in user_text_lower or "echo" in user_text_lower:
            tool_call = {
                "id": "call_echo_001",
                "name": "dummy_echo",
                "args": {"query": user_text},
            }
            return {
                "messages": [
                    AIMessage(
                        content="已為您觸發範例工具調用。",
                        tool_calls=[tool_call],
                    )
                ]
            }

        # 情況 C：一般閒聊 / 問答（不需要調用工具，直接給出最終文字回覆）
        return {
            "messages": [
                AIMessage(
                    content=f"JARVIS 收到您的訊息：『{user_text}』。這是一個直接回覆，不需要調用外部工具。"
                )
            ]
        }

    return agent_node


def tools_node(state: AgentState) -> Dict[str, List[BaseMessage]]:
    """Tools 執行節點.

    檢查最新一則 AIMessage 中是否包含 `tool_calls`。
    若有，依序執行對應的工具，並將每個工具的執行結果包裝成 `ToolMessage` 回傳。
    """
    messages = list(state.get("messages", []))
    if not messages:
        return {"messages": []}

    last_msg = messages[-1]
    tool_messages: List[BaseMessage] = []

    # 檢查是否有 tool_calls 屬性
    tool_calls = getattr(last_msg, "tool_calls", []) or []

    for call in tool_calls:
        call_id = call.get("id", "call_default")
        tool_name = call.get("name", "unknown_tool")
        args = call.get("args", {})

        # 執行 dummy 工具
        result_str = dummy_tool(tool_name, args)

        # 建立 ToolMessage：必須帶入 tool_call_id，讓 LLM 知道這是回應該次呼叫的結果
        tool_messages.append(
            ToolMessage(
                content=result_str,
                tool_call_id=call_id,
                name=tool_name,
            )
        )

    return {"messages": tool_messages}
