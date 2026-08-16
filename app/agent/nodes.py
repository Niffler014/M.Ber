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

from typing import Any, Callable, Dict, List, Optional, Union
import json
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, ToolMessage
from app.agent.state import AgentState
from app.mcp.client import MCPStdioClient
from app.mcp.manager import MCPManager


def dummy_tool(tool_name: str, args: Dict[str, Any]) -> str:
    """備用 Dummy 工具函式 (Fallback Tool)."""
    if tool_name == "calculator":
        expression = str(args.get("expression", "0"))
        try:
            allowed_chars = set("0123456789+-*/(). ")
            if not set(expression).issubset(allowed_chars):
                return f"[Calculator Error]: 不合法的運算字元: {expression}"
            result = eval(expression, {"__builtins__": None}, {})
            return f"[Calculator Result]: {expression} = {result}"
        except Exception as e:
            return f"[Calculator Error]: 計算失敗 ({e})"
    elif tool_name in ["get_current_time", "get_system_time"]:
        from datetime import datetime
        return f"[System Time]: 現在時間為 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
    elif tool_name == "read_notes":
        keyword = args.get("keyword", "")
        return f"[Fallback Notes]: 模擬筆記查詢 (關鍵字: '{keyword}')"
    elif tool_name == "add_note":
        title = args.get("title", "未命名")
        content = args.get("content", "")
        return f"[Fallback Notes]: 模擬新增筆記 《{title}》: {content}"
    else:
        query = args.get("query") or args.get("message") or args.get("input") or str(args)
        return f"[Fallback Echo]: 收到工具請求 '{tool_name}'，參數為: {query}"


def create_agent_node(llm: Optional[Any] = None) -> Callable[[AgentState], Dict[str, List[BaseMessage]]]:
    """建立 Agent 思考節點.

    支援注入真實 LLM 或使用內建模擬器（分析使用者訊息發起 MCP 工具調用）。
    """
    def agent_node(state: AgentState) -> Dict[str, List[BaseMessage]]:
        messages = list(state.get("messages", []))
        if not messages:
            return {"messages": [AIMessage(content="您好！我是 JARVIS，請問有什麼我可以協助您的？")]}

        # 若有注入真實 LLM，直接呼叫
        if llm is not None:
            response = llm.invoke(messages)
            if not isinstance(response, BaseMessage):
                response = AIMessage(content=str(response))
            return {"messages": [response]}

        # --- 確定性模擬器 (Fallback / Demo 模式) ---
        last_msg = messages[-1]

        # 情況 A：工具執行結果已傳回，大腦統整回覆
        if isinstance(last_msg, ToolMessage):
            tool_output = last_msg.content
            return {
                "messages": [
                    AIMessage(
                        content=f"已成功透過 MCP 工具為您處理完畢！執行結果如下：\n{tool_output}\n請問還需要其他協助嗎？"
                    )
                ]
            }

        user_text = last_msg.content if isinstance(last_msg.content, str) else str(last_msg.content)
        user_text_lower = user_text.lower()

        # 檢查是否觸發新增筆記 (add_note)
        if "新增筆記" in user_text or "記一下" in user_text or "記錄筆記" in user_text:
            # 簡易擷取標題與內容
            parts = user_text.replace("新增筆記", "").replace("記一下", "").replace("記錄筆記", "").strip("：: ")
            if "內容" in parts:
                title_part, content_part = parts.split("內容", 1)
                title = title_part.replace("標題", "").strip("：: ，,") or "個人記事"
                content = content_part.strip("：: ")
            else:
                title = "重要記事"
                content = parts or "無詳細內容"

            return {
                "messages": [
                    AIMessage(
                        content="我正在透過 SQLite MCP 伺服器為您儲存筆記...",
                        tool_calls=[
                            {
                                "id": "call_mcp_add_note_001",
                                "name": "add_note",
                                "args": {"title": title, "content": content},
                            }
                        ],
                    )
                ]
            }

        # 檢查是否觸發查詢筆記 (read_notes)
        elif "查詢筆記" in user_text or "讀取筆記" in user_text or "查看筆記" in user_text or "列出筆記" in user_text or "筆記" in user_text:
            keyword = user_text.replace("查詢筆記", "").replace("讀取筆記", "").replace("查看筆記", "").replace("列出筆記", "").replace("筆記", "").strip("：: ")
            return {
                "messages": [
                    AIMessage(
                        content="我正在向 SQLite MCP 伺服器查詢相關筆記...",
                        tool_calls=[
                            {
                                "id": "call_mcp_read_notes_001",
                                "name": "read_notes",
                                "args": {"keyword": keyword},
                            }
                        ],
                    )
                ]
            }

        # 檢查是否觸發 MCP get_current_time 工具
        elif "時間" in user_text or "幾點" in user_text or "time" in user_text_lower:
            return {
                "messages": [
                    AIMessage(
                        content="我正在透過 MCP 協定向 Server 請求取得目前的系統時間...",
                        tool_calls=[
                            {
                                "id": "call_mcp_time_001",
                                "name": "get_current_time",
                                "args": {},
                            }
                        ],
                    )
                ]
            }

        # 檢查是否觸發 MCP echo_message 工具
        elif "echo" in user_text_lower or "回傳" in user_text:
            msg_to_echo = user_text
            for prefix in ["echo", "回傳"]:
                if prefix in msg_to_echo:
                    msg_to_echo = msg_to_echo.split(prefix, 1)[-1].strip() or "測試訊息"
                    break
            return {
                "messages": [
                    AIMessage(
                        content="已為您發起 MCP Echo 工具調用請求。",
                        tool_calls=[
                            {
                                "id": "call_mcp_echo_001",
                                "name": "echo_message",
                                "args": {"message": msg_to_echo},
                            }
                        ],
                    )
                ]
            }

        # 檢查是否觸發計算機工具
        elif "計算" in user_text or "算一下" in user_text or "calculate" in user_text_lower:
            import re
            match = re.search(r"[\d\+\-\*\/\(\)\. ]{3,}", user_text)
            expr = match.group(0).strip() if match else "1 + 1"
            return {
                "messages": [
                    AIMessage(
                        content="我需要使用計算機工具來為您計算這個數值。",
                        tool_calls=[
                            {
                                "id": "call_calc_001",
                                "name": "calculator",
                                "args": {"expression": expr},
                            }
                        ],
                    )
                ]
            }

        # 一般對話回覆
        return {
            "messages": [
                AIMessage(
                    content=f"JARVIS 收到您的訊息：『{user_text}』。這是一個直接回覆，不需要調用外部工具。"
                )
            ]
        }

    return agent_node


def create_tools_node(
    mcp_provider: Optional[Union[MCPManager, MCPStdioClient]] = None,
) -> Callable[[AgentState], Dict[str, List[BaseMessage]]]:
    """建立 Tools 執行節點.

    支援傳入 `MCPManager`（多伺服器路由）或 `MCPStdioClient`（單伺服器）。
    若皆未提供或執行失敗，則降級使用 fallback dummy 工具。
    """
    def tools_node_fn(state: AgentState) -> Dict[str, List[BaseMessage]]:
        messages = list(state.get("messages", []))
        if not messages:
            return {"messages": []}

        last_msg = messages[-1]
        tool_messages: List[BaseMessage] = []
        tool_calls = getattr(last_msg, "tool_calls", []) or []

        for call in tool_calls:
            call_id = call.get("id", "call_default")
            tool_name = call.get("name", "unknown_tool")
            args = call.get("args", {})

            result_str = None
            # 優先透過 MCP Manager 進行多伺服器智慧路由
            if isinstance(mcp_provider, MCPManager):
                try:
                    result_str = mcp_provider.call_tool(tool_name, args)
                except Exception as e:
                    result_str = f"[MCP Manager Error]: 執行工具 '{tool_name}' 發生錯誤 ({e})"

            # 若傳入的是單一 MCPStdioClient
            elif isinstance(mcp_provider, MCPStdioClient):
                try:
                    result_str = mcp_provider.call_tool(tool_name, args)
                except Exception as e:
                    result_str = f"[MCP Error]: 呼叫工具 '{tool_name}' 發生錯誤 ({e})"

            # 若皆無，使用 fallback 工具
            if result_str is None:
                result_str = dummy_tool(tool_name, args)

            tool_messages.append(
                ToolMessage(
                    content=result_str,
                    tool_call_id=call_id,
                    name=tool_name,
                )
            )

        return {"messages": tool_messages}

    return tools_node_fn


# 預設 tools_node（無 client/manager 時使用 fallback）
tools_node = create_tools_node()
