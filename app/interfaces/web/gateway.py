"""M.Ber Web Gateway & HTTP API Entrypoint (Web 應用程式閘道模組).
Phase 8 - P8-02: Execution Trace & Streaming

【新手教學 / 觀念解析】：
1. 什麼是 Web Gateway？
   - Web Gateway 是 M.Ber 的「HTTP 傳輸轉接站（HTTP Transport Layer）」。
   - 它負責：
     ① 監聽前端 HTTP 請求（例如 `/api/health`、`/api/chat`、`/api/chat/stream`）。
     ② 將傳入的 JSON 資料驗證轉換為 DTO（Data Transfer Object）。
     ③ 呼叫 Application Service（`OrchestrationService`）進行統一調度運算。
     ④ 將後端的 Domain Model / Event 轉換為前端安全的 Response DTO / SSE Stream 並回傳。
   - 核心原則：**Web Gateway 絕不自行做調度（Orchestration）**，所有調度權力均交由 `OrchestrationService`。

2. Server-Sent Events (SSE) 串流原理：
   - 使用標準 HTTP 長連線 (`text/event-stream`)，伺服器能主動向瀏覽器推播事件。
   - 事件格式：
     event: trace
     data: {"event_type": "task_started", ...}

     event: final
     data: {"message": "...", "status": "success"}
"""

import asyncio
import json
import logging
import threading
from typing import List, Optional

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from langchain_core.messages import HumanMessage

from app import __version__
from app.interfaces.web.models import (
    ChatRequest,
    ChatResponse,
    ErrorDetail,
    ErrorResponse,
    HealthResponse,
    TraceEvent,
    to_public_trace_event,
)
from app.orchestration.events import CallbackEventSink, OrchestrationEvent
from app.orchestration.models import OrchestrationResponse
from app.orchestration.service import OrchestrationService

logger = logging.getLogger("mber.web")

# 預設前端允許之來源 (Vite Dev Server 預設為 port 5173)
DEFAULT_ALLOWED_ORIGINS = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
]


def create_web_app(
    orchestration_service: Optional[OrchestrationService] = None,
    allowed_origins: Optional[List[str]] = None,
) -> FastAPI:
    """建立並設定 M.Ber FastAPI Web 應用程式實例 (工廠函式 / Dependency Injection).

    Args:
        orchestration_service: 長期存活的調度總管服務實例 (若未提供則自動建立)
        allowed_origins: 允許跨來源請求的前端 URL 清單 (預設為 Localhost Vite 開發伺服器)

    Returns:
        設定完成的 FastAPI 應用實例
    """
    app = FastAPI(
        title="M.Ber Web API Gateway",
        description="M.Ber Personal AI Agent Platform - Web API Gateway",
        version=__version__,
    )

    # 1. 配置 CORS 跨來源資源共用中介軟體 (安全設定：不使用萬用字元 wildcard + credentials)
    origins = allowed_origins if allowed_origins is not None else DEFAULT_ALLOWED_ORIGINS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # 2. 服務實例生命週期管理 (Long-lived Service Instance)
    service = orchestration_service or OrchestrationService()

    # 3. 註冊全域例外處理器 (Global Exception Handlers)
    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        """將 FastAPI 預設的 422 轉換為標準 400 Bad Request 錯誤回應."""
        error_msg = "請求資料格式不正確或缺少必要欄位"
        errors = exc.errors()
        if errors and len(errors) > 0:
            first_err = errors[0]
            msg = first_err.get("msg", "")
            loc = first_err.get("loc", [])
            field_name = loc[-1] if loc else "message"
            if "Value error" in msg:
                clean_msg = msg.replace("Value error, ", "").strip()
                error_msg = f"欄位 [{field_name}] 驗證失敗: {clean_msg}"
            else:
                error_msg = f"欄位 [{field_name}]: {msg}"

        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content=ErrorResponse(
                error=ErrorDetail(
                    code="invalid_request",
                    message=error_msg,
                )
            ).model_dump(),
        )

    @app.exception_handler(HTTPException)
    async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
        """處理標準 HTTPException 並回傳結構化錯誤."""
        return JSONResponse(
            status_code=exc.status_code,
            content=ErrorResponse(
                error=ErrorDetail(
                    code="http_error",
                    message=str(exc.detail),
                )
            ).model_dump(),
        )

    @app.exception_handler(Exception)
    async def generic_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        """處理未預期的系統例外，記錄 Log 並回傳安全之 500 錯誤回應."""
        logger.exception(f"[Web Gateway] 伺服器未預期異常: {exc}")
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=ErrorResponse(
                error=ErrorDetail(
                    code="internal_error",
                    message="伺服器內部發生未預期錯誤，請稍後再試。",
                )
            ).model_dump(),
        )

    # 4. 註冊 HTTP 路由 (Endpoints)
    @app.get("/api/health", response_model=HealthResponse)
    async def health_check() -> HealthResponse:
        """健康檢查端點 (Minimal Health Check Endpoint)."""
        return HealthResponse(
            status="ok",
            service="mber",
            version=__version__,
        )

    @app.post("/api/chat", response_model=ChatResponse)
    async def chat(request: ChatRequest) -> ChatResponse:
        """對話處理端點 (Non-Streaming Chat Endpoint).

        流程：
        ChatRequest ➔ OrchestrationService.invoke_with_details ➔ 收集完整 Trace ➔ ChatResponse
        """
        user_message = request.message
        human_msg = HumanMessage(content=user_message)

        # 呼叫後端唯一調度權威 (OrchestrationService)
        response: OrchestrationResponse = service.invoke_with_details([human_msg])

        overall_status = response.aggregated.overall_status.value
        response_text = (
            response.message.content
            if isinstance(response.message.content, str)
            else str(response.message.content)
        )

        # 轉換累積之執行軌跡事件為前端安全 DTO
        public_trace = [to_public_trace_event(evt) for evt in response.events]

        return ChatResponse(
            message=response_text,
            status=overall_status,
            plan_id=response.plan.plan_id,
            conversation_id=request.conversation_id,
            trace=public_trace,
        )

    @app.post("/api/chat/stream")
    async def chat_stream(request: ChatRequest) -> StreamingResponse:
        """SSE 串流對話處理端點 (Server-Sent Events Streaming Endpoint).

        流程：
        - 以 Worker Thread 執行後端調度流程
        - 透過 CallbackEventSink 即時將 OrchestrationEvent 轉發至 asyncio.Queue
        - 透過 SSE (event: trace / event: final / event: error) 逐筆推播至前端
        """
        queue: asyncio.Queue = asyncio.Queue()
        loop = asyncio.get_running_loop()

        def on_event(event: OrchestrationEvent) -> None:
            public_event = to_public_trace_event(event)
            loop.call_soon_threadsafe(
                queue.put_nowait,
                ("trace", public_event.model_dump()),
            )

        def run_worker() -> None:
            try:
                human_msg = HumanMessage(content=request.message)
                sink = CallbackEventSink(on_event)
                res: OrchestrationResponse = service.invoke_with_details(
                    [human_msg],
                    event_sink=sink,
                )

                resp_text = (
                    res.message.content
                    if isinstance(res.message.content, str)
                    else str(res.message.content)
                )
                final_payload = {
                    "message": resp_text,
                    "status": res.aggregated.overall_status.value,
                    "plan_id": res.plan.plan_id,
                    "conversation_id": request.conversation_id,
                }
                loop.call_soon_threadsafe(queue.put_nowait, ("final", final_payload))
            except Exception as exc:
                logger.exception(f"[Web Gateway Stream] Worker error: {exc}")
                err_payload = {
                    "code": "internal_error",
                    "message": "伺服器內部發生未預期錯誤，請稍後再試。",
                }
                loop.call_soon_threadsafe(queue.put_nowait, ("error", err_payload))
            finally:
                loop.call_soon_threadsafe(queue.put_nowait, ("done", None))

        # 啟動背景 Worker Thread 執行調度
        threading.Thread(target=run_worker, daemon=True).start()

        async def sse_generator():
            try:
                while True:
                    evt_type, payload = await queue.get()
                    if evt_type == "done":
                        break
                    yield f"event: {evt_type}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"
            except asyncio.CancelledError:
                logger.info("[Web Gateway Stream] Client disconnected")

        return StreamingResponse(
            sse_generator(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    return app


# 預設應用程式實例 (供 uvicorn 直接啟動: uvicorn app.interfaces.web.gateway:app)
app = create_web_app()
