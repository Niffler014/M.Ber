"""M.Ber CLI Interactive Entrypoint (命令列互動式介面).

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
from app.mcp.manager import MCPManager


def run_cli() -> None:
    """啟動 M.Ber 終端機對話互動介面 (已整合 Multi-Server MCP Manager)."""
    print("=" * 65)
    print("🤖 M.Ber Personal AI Agent Platform CLI")
    print("=" * 65)

    # 1. 建立 MCP Manager 載入外部設定檔 (config/mcp_servers.json)
    mcp_manager = MCPManager()
    connected_servers = list(mcp_manager.clients.keys())
    all_tools = mcp_manager.list_all_tools()
    tool_names = [t["name"] for t in all_tools]

    print(f"🔌 [MCP Manager 啟動成功]: 已連線伺服器清單: {connected_servers}")
    print(f"📦 [工具探索彙整]: 共發現 {len(tool_names)} 個工具 ➔ {tool_names}")

    print("-" * 65)
    print("💡 提示：輸入訊息後按 Enter 即可與 M.Ber 對話。")
    print("💡 測試工具關鍵字：")
    print("   - 輸入「現在幾點」或「時間」➔ 呼叫 own_server 之 get_current_time")
    print("   - 輸入「幫我預約明天下午 3 點開會」➔ 呼叫 calendar_server 之 add_event")
    print("   - 輸入「查詢明天的行程」或「查看行事曆」➔ 呼叫 calendar_server 之 query_events")
    print("   - 輸入「新增筆記：標題=買菜，內容=買雞蛋和鮮奶」➔ 呼叫 sqlite_server 之 add_note")
    print("   - 輸入「查詢筆記：買菜」或「列出筆記」➔ 呼叫 sqlite_server 之 read_notes")
    print("   - 輸入「echo Hello MCP」➔ 呼叫 own_server 之 echo_message")
    print("   - 輸入「exit」或「quit」即可退出程式。")
    print("-" * 65)

    # 建立編譯好的狀態圖 (注入 mcp_manager)
    graph = create_agent_graph(mcp_manager=mcp_manager)

    # 維護多輪對話歷史 (Session Messages)
    chat_history = []

    while True:
        try:
            user_input = input("\n👤 使用者: ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\n👋 收到中斷訊號，M.Ber 已安全退出。")
            break

        if not user_input:
            continue

        if user_input.lower() in ["exit", "quit", "q"]:
            print("👋 再見！M.Ber 關閉中。")
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
            print(f"\n🤖 M.Ber: {chat_history[-1].content}")

        print("-" * 60)


if __name__ == "__main__":
    run_cli()
