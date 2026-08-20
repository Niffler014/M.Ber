"""M.Ber LINE 通訊介面模組 (LINE Webhook Gateway).

【新手教學 / 觀念解析】：
1. 什麼是 LINE Webhook Gateway？
   - 這是一個基於 FastAPI 的「周邊通訊轉接站」。
   - 它負責：
     ① 監聽來自 LINE Platform 的 HTTP POST 請求（`/callback`）。
     ② 使用 HMAC-SHA256 驗證 `X-Line-Signature` 簽章，防止偽造訊息。
     ③ 提取使用者的文字與 `user_id`，並將 `user_id` 當作 LangGraph 的 `thread_id`。
     ④ 觸發 LangGraph Agent 思考與 MCP 工具調用。
     ⑤ 透過 LINE Messaging API 將結果回覆給使用者。

2. 為什麼使用 `thread_id: user_id`？
   - 每個 LINE 使用者的 ID 都是唯一的（例如 `U1234...`）。
   - 將其設定為 LangGraph 的 `thread_id`，MemorySaver 就能為每個使用者獨立儲存對話歷史，
     讓小明和小華同時對話時，記憶絕不串線！

3. 【本機除錯指南 (ngrok 穿透)】：
   - 啟動服務：`uv run uvicorn app.interfaces.line_gateway:app --reload --port 8000`
   - 啟動隧道：`ngrok http 8000`
   - 在 LINE Developers Console 設定 Webhook URL 為：`https://<你的ngrok網址>/callback`
"""

import os
import sys
from pathlib import Path
from typing import Optional, Dict, Any

from dotenv import load_dotenv
from fastapi import FastAPI, Request, Header, HTTPException, status
from fastapi.responses import JSONResponse

from linebot.v3.webhook import WebhookParser
from linebot.v3.webhooks import MessageEvent, TextMessageContent
from linebot.v3.messaging import (
    Configuration,
    ApiClient,
    MessagingApi,
    ReplyMessageRequest,
    TextMessage,
)
from linebot.v3.exceptions import InvalidSignatureError

from langchain_core.messages import HumanMessage, AIMessage
from langgraph.checkpoint.memory import MemorySaver
from app.agent.graph import create_agent_graph
from app.mcp.manager import MCPManager

# 載入專案根目錄的 .env 環境變數
project_root = Path(__file__).resolve().parent.parent.parent
load_dotenv(project_root / ".env")

# 讀取 LINE 金鑰（若未設定則使用預設 Mock 字串供測試與本機離線驗證）
LINE_CHANNEL_ACCESS_TOKEN = os.getenv("LINE_CHANNEL_ACCESS_TOKEN", "MOCK_LINE_ACCESS_TOKEN")
LINE_CHANNEL_SECRET = os.getenv("LINE_CHANNEL_SECRET", "MOCK_LINE_SECRET")

# 建立 FastAPI 應用實例
app = FastAPI(
    title="M.Ber LINE Webhook Gateway",
    description="LINE Bot Webhook 與 LangGraph Agent 整合轉接閘道器",
    version="1.0.0",
)

# 1. 建立 LangGraph 記憶檢查點 (MemorySaver)
# 確保不同使用者透過 thread_id 享有獨立且持續的對話記憶
checkpointer = MemorySaver()

# 2. 建立 MCP Manager 與 LangGraph 狀態圖實例
mcp_manager = MCPManager()
agent_graph = create_agent_graph(
    mcp_manager=mcp_manager,
    checkpointer=checkpointer,
    use_orchestration=True,
)

# 3. 初始化 LINE SDK 處理器
parser = WebhookParser(LINE_CHANNEL_SECRET)
line_config = Configuration(access_token=LINE_CHANNEL_ACCESS_TOKEN)


@app.get("/")
@app.get("/health")
def health_check() -> Dict[str, Any]:
    """健康檢查端點."""
    return {
        "status": "healthy",
        "service": "M.Ber LINE Webhook Gateway",
        "version": "1.0.0",
        "mcp_servers": list(mcp_manager.clients.keys()),
    }


@app.post("/callback")
async def callback(
    request: Request,
    x_line_signature: Optional[str] = Header(None, alias="X-Line-Signature"),
) -> JSONResponse:
    """LINE Webhook 進入點.

    接收 LINE 伺服器推播的事件，驗證簽章後轉發給 LangGraph 運算並發送回覆。
    """
    if not x_line_signature:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="缺少 X-Line-Signature 標頭",
        )

    # 讀取 Raw Body 位元組資料以供簽章驗證
    body_bytes = await request.body()
    body_str = body_bytes.decode("utf-8")

    try:
        # 驗證簽章並解析為事件清單
        events = parser.parse(body_str, x_line_signature)
    except InvalidSignatureError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="無效的 LINE Webhook 簽章 (Invalid Signature)",
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"解析 Webhook 請求失敗: {e}",
        )

    processed_replies = []

    for event in events:
        # 僅處理文字訊息事件
        if isinstance(event, MessageEvent) and isinstance(event.message, TextMessageContent):
            user_id = getattr(event.source, "user_id", "anonymous_user") or "anonymous_user"
            user_text = event.message.text
            reply_token = event.reply_token

            print(f"\n📩 [LINE Webhook 收到訊息]: UserID='{user_id}', 內容='{user_text}'")

            # 4. 呼叫 LangGraph Agent，傳入 thread_id 保持多輪對話隔離
            config = {"configurable": {"thread_id": user_id}}
            initial_state = {"messages": [HumanMessage(content=user_text)]}

            try:
                # 執行 LangGraph 狀態圖
                graph_result = agent_graph.invoke(initial_state, config=config)
                messages = graph_result.get("messages", [])

                # 提取最新一則 AIMessage 回覆文字
                reply_text = "M.Ber 處理完成。"
                for msg in reversed(messages):
                    if isinstance(msg, AIMessage):
                        reply_text = msg.content
                        break

                print(f"🤖 [M.Ber 產生回覆]: {reply_text}")

                # 5. 透過 LINE Messaging API 發送回覆 (若非 Mock Token)
                if LINE_CHANNEL_ACCESS_TOKEN and not LINE_CHANNEL_ACCESS_TOKEN.startswith("MOCK_"):
                    try:
                        with ApiClient(line_config) as api_client:
                            messaging_api = MessagingApi(api_client)
                            messaging_api.reply_message(
                                ReplyMessageRequest(
                                    reply_token=reply_token,
                                    messages=[TextMessage(text=reply_text)],
                                )
                            )
                    except Exception as line_err:
                        print(f"⚠️ [LINE API 發送警告]: {line_err}")

                processed_replies.append(
                    {
                        "user_id": user_id,
                        "query": user_text,
                        "reply": reply_text,
                    }
                )

            except Exception as graph_err:
                print(f"❌ [LangGraph 執行錯誤]: {graph_err}")

    return JSONResponse(
        content={
            "status": "success",
            "processed_count": len(processed_replies),
            "results": processed_replies,
        }
    )
