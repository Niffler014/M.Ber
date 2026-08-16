"""JARVIS CLI Interactive Entrypoint (命令列互動式介面).

【新手教學 / 觀念解析】：
1. 如何執行 LangGraph？
   - `graph.stream(initial_state)` 可以讓我們一步步接收狀態圖的執行過程。
   - 每經過一個 Node，LangGraph 就會產出一個包含該節點名稱與更新內容的 event 事件。
   - 透過這種方式，我們可以在終端機即時看到：
     [START] -> [agent (大腦思考)] -> [tools (執行工具)] -> [agent (統整回覆)] -> [END]
"""

import sys
from langchain_core.messages import HumanMessage, AIMessage, ToolMessage
from app.agent.graph import create_agent_graph
from app.mcp.client import MCPStdioClient


def run_cli() -> None:
    """啟動 JARVIS 終端機對話互動介面 (已整合 Own MCP Server)."""
    print("=" * 60)
    print("🤖 JARVIS Phase 2: Own MCP Server & LangGraph Agent CLI")
    print("=" * 60)

    # 1. 建立 MCP Client 連線至自有 MCP Server
    mcp_client = MCPStdioClient()
    try:
        tools = mcp_client.list_tools()
        tool_names = [t["name"] for t in tools]
        print(f"🔌 [MCP 連線成功]: 已連線至自有 MCP Server，可用工具清單: {tool_names}")
    except Exception as e:
        print(f"⚠️ [MCP 警告]: 無法連線至 MCP Server ({e})，將使用 Fallback 模式")
        mcp_client = None

    print("-" * 60)
    print("💡 提示：輸入訊息後按 Enter 即可與 JARVIS 對話。")
    print("💡 測試工具關鍵字：")
    print("   - 輸入包含「現在幾點」或「時間」➔ 呼叫 MCP Server 之 get_current_time")
    print("   - 輸入包含「echo Hello MCP」➔ 呼叫 MCP Server 之 echo_message")
    print("   - 輸入包含「計算 15 * 8」➔ 測試計算機工具")
    print("   - 輸入「exit」或「quit」即可退出程式。")
    print("-" * 60)

    # 建立編譯好的狀態圖 (傳入 mcp_client)
    graph = create_agent_graph(mcp_client=mcp_client)

    # 維護多輪對話歷史 (Session Messages)
    chat_history = []

    while True:
        try:
            user_input = input("\n👤 使用者: ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\n👋 收到中斷訊號，JARVIS 已安全退出。")
            break

        if not user_input:
            continue

        if user_input.lower() in ["exit", "quit", "q"]:
            print("👋 再見！JARVIS 關閉中。")
            break

        # 將使用者的輸入包裝成 HumanMessage 並加入對話歷史
        user_message = HumanMessage(content=user_input)
        chat_history.append(user_message)

        print("\n⚙️  [Graph 狀態圖開始流轉...]")

        # 執行 LangGraph，傳入包含完整對話歷史的 State
        # 使用 stream 可以即時觀察每一步進入哪一個 Node
        events = graph.stream(
            {"messages": chat_history},
            stream_mode="updates",
        )

        for event in events:
            # event 的結構為: { "node_name": { "messages": [...] } }
            for node_name, state_update in event.items():
                print(f"  📍 進入節點: [{node_name}]")
                new_msgs = state_update.get("messages", [])
                for msg in new_msgs:
                    if isinstance(msg, AIMessage):
                        if getattr(msg, "tool_calls", None):
                            print(f"     🧠 Agent 思考: 決定發起工具調用 ➔ {msg.tool_calls}")
                        else:
                            print(f"     🧠 Agent 回覆: {msg.content}")
                    elif isinstance(msg, ToolMessage):
                        print(f"     🔧 Tool 執行結果: {msg.content}")

                    # 將產出的新訊息持續累加至對話歷史
                    chat_history.append(msg)

        # 取出最新的回覆呈現給使用者
        if chat_history and isinstance(chat_history[-1], AIMessage):
            print(f"\n🤖 JARVIS: {chat_history[-1].content}")

        print("-" * 60)


if __name__ == "__main__":
    run_cli()
