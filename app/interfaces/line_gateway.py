"""M.Ber LINE Webhook Gateway (LINE 通訊轉接閘道模組).
Phase 8 - P8-05A: LINE Bidirectional Chat Integration

【新手教學 / 觀念解析】：
1. 什麼是 LINE Webhook Gateway？
   - 這是 M.Ber 的「LINE 通道轉接站（LINE Channel Adapter）」。
   - 核心原則：**Channel Adapter ≠ Agent Brain**。
   - LINE Gateway 不包含任何意圖判斷、MCP 路由或 A2A 委派邏輯，它唯一的職責是：
     ① 驗證 LINE Webhook 簽章（HMAC-SHA256）。
     ② 將 LINE TextMessage 事件轉換為統一的 LangChain `HumanMessage` 與標準通道對話識別碼（`line:<USER_ID>`）。
     ③ 呼叫頂層單一調度權威 `OrchestrationService.invoke_with_details(...)`。
     ④ 將生成的自然語言訊息經由 `LineResponseFormatter` 安全切分，透過 LINE Messaging API `reply_message` 回覆。
"""

import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv
from fastapi import FastAPI, Header, HTTPException, Request, status
from fastapi.responses import JSONResponse
from langchain_core.messages import AIMessage, HumanMessage
from linebot.v3.exceptions import InvalidSignatureError
from linebot.v3.messaging import (
    ApiClient,
    Configuration,
    MessagingApi,
    ReplyMessageRequest,
    TextMessage,
)
from linebot.v3.webhook import WebhookParser
from linebot.v3.webhooks import MessageEvent, TextMessageContent

from app.bootstrap import get_orchestration_service
from app.interfaces.line_formatter import mask_user_id, split_text_into_chunks
from app.orchestration.models import OrchestrationResponse
from app.orchestration.service import OrchestrationService

# 載入專案根目錄的 .env 環境變數
project_root = Path(__file__).resolve().parent.parent.parent
load_dotenv(project_root / ".env")

logger = logging.getLogger("mber.line")

LINE_CHANNEL_ACCESS_TOKEN = os.getenv("LINE_CHANNEL_ACCESS_TOKEN", "MOCK_LINE_ACCESS_TOKEN")
LINE_CHANNEL_SECRET = os.getenv("LINE_CHANNEL_SECRET", "MOCK_LINE_SECRET")


def create_line_app(
    orchestration_service: Optional[OrchestrationService] = None,
    channel_secret: Optional[str] = None,
    channel_access_token: Optional[str] = None,
) -> FastAPI:
    """建立並設定 M.Ber FastAPI LINE Webhook 應用程式實例 (工廠函式 / Dependency Injection).

    Args:
        orchestration_service: 長期存活的調度總管服務實例 (若未提供則從 bootstrap 取得全域實例)
        channel_secret: LINE Channel Secret 金鑰
        channel_access_token: LINE Channel Access Token 金鑰

    Returns:
        設定完成的 FastAPI 應用實例
    """
    secret = channel_secret or LINE_CHANNEL_SECRET
    token = channel_access_token or LINE_CHANNEL_ACCESS_TOKEN
    service = orchestration_service or get_orchestration_service()

    parser = WebhookParser(secret)
    line_config = Configuration(access_token=token)

    app_instance = FastAPI(
        title="M.Ber LINE Webhook Gateway",
        description="M.Ber Personal AI Agent Platform - LINE Channel Gateway",
        version="1.0.0",
    )

    # 儲存服務實例於 app.state 供測試檢查與內部存取
    app_instance.state.orchestration_service = service

    @app_instance.get("/")
    @app_instance.get("/health")
    def health_check() -> Dict[str, Any]:
        """健康檢查端點."""
        mcp_servers = []
        if getattr(service, "mcp_manager", None) and hasattr(service.mcp_manager, "clients"):
            mcp_servers = list(service.mcp_manager.clients.keys())
        return {
            "status": "healthy",
            "service": "M.Ber LINE Webhook Gateway",
            "version": "1.0.0",
            "mcp_servers": mcp_servers,
        }

    @app_instance.post("/callback")
    async def callback(
        request: Request,
        x_line_signature: Optional[str] = Header(None, alias="X-Line-Signature"),
    ) -> JSONResponse:
        """LINE Webhook 進入點.

        接收 LINE 伺服器推播的事件，驗證簽章後轉發給 OrchestrationService 運算並發送回覆。
        """
        if not x_line_signature:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="缺少 X-Line-Signature 標頭",
            )

        body_bytes = await request.body()
        body_str = body_bytes.decode("utf-8")

        try:
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

        processed_replies: List[Dict[str, Any]] = []

        for event in events:
            if isinstance(event, MessageEvent) and isinstance(event.message, TextMessageContent):
                user_id = getattr(event.source, "user_id", "anonymous_user") or "anonymous_user"
                user_text = (event.message.text or "").strip()
                reply_token = getattr(event, "reply_token", None)

                # 建立通道標準對話識別碼 (Channel-neutral conversation identity)
                conversation_id = f"line:{user_id}"
                masked_id = mask_user_id(user_id)

                logger.info(f"[LINE] Request received from {masked_id} (conversation: {conversation_id})")

                # 呼叫頂層調度總管 OrchestrationService
                reply_text: str = ""
                try:
                    orchestration_res: OrchestrationResponse = service.invoke_with_details(
                        messages=[HumanMessage(content=user_text)],
                    )
                    msg_obj = orchestration_res.message
                    if isinstance(msg_obj, AIMessage):
                        reply_text = str(msg_obj.content)
                    elif isinstance(msg_obj, str):
                        reply_text = msg_obj
                    else:
                        reply_text = str(msg_obj)

                    status_str = (
                        orchestration_res.aggregated.overall_status.value
                        if hasattr(orchestration_res, "aggregated")
                        and hasattr(orchestration_res.aggregated, "overall_status")
                        else "completed"
                    )
                    logger.info(
                        f"[LINE] Orchestration completed for {masked_id} (status: {status_str})"
                    )

                    # 若調度結果為空時提供安全提示
                    if not reply_text:
                        reply_text = "抱歉，M.Ber 目前無法完成這個請求，請稍後再試。"

                except Exception as orchestrate_err:
                    logger.exception(f"[LINE] Orchestration unexpected error for {masked_id}: {orchestrate_err}")
                    reply_text = "抱歉，M.Ber 伺服器目前處理發生異常，請稍後再試。"

                # 格式化與長度防護 (切分為合規的 TextMessage 清單)
                chunks = split_text_into_chunks(reply_text)
                line_messages = [TextMessage(text=c) for c in chunks]

                # 透過 LINE Messaging API 發送回覆 (若非 Mock/Dummy Token 且具備 reply_token)
                is_mock_token = (
                    not token
                    or token.startswith("MOCK_")
                    or token.startswith("dummy_")
                    or token.startswith("test_")
                )
                if reply_token and not is_mock_token:
                    try:
                        with ApiClient(line_config) as api_client:
                            messaging_api = MessagingApi(api_client)
                            messaging_api.reply_message(
                                ReplyMessageRequest(
                                    reply_token=reply_token,
                                    messages=line_messages,
                                )
                            )
                        logger.info(f"[LINE] Reply sent to {masked_id} ({len(line_messages)} message chunks)")
                    except Exception as line_err:
                        logger.warning(f"[LINE] Failed to send reply to {masked_id}: {line_err}")

                processed_replies.append(
                    {
                        "user_id": user_id,
                        "conversation_id": conversation_id,
                        "query": user_text,
                        "reply": reply_text,
                    }
                )

        return JSONResponse(
            content={
                "status": "success",
                "processed_count": len(processed_replies),
                "results": processed_replies,
            }
        )

    return app_instance


# 建立模組層級預設 app 實例供 Uvicorn 等伺服器啟動
app = create_line_app()
