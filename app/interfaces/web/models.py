"""M.Ber Web API Data Transfer Objects (DTOs).
Phase 8 - P8-02: Execution Trace & Streaming

【新手教學 / 觀念解析】：
1. 什麼是 DTO (Data Transfer Object)？
   - DTO 是專門用來在前端（瀏覽器 / HTTP 客戶端）與後端之間傳遞資料的資料模型。
   - 核心原則：**DTO 與內部 Domain Model 分離**。
     不要把內部的 LangChain AIMessage、TaskPlan 或 ExecutionResult 原始物件直接暴露給前端，
     而是透過清楚定義的 Request / Response DTO 進行轉換，確保 API 契約穩定且具備安全性（避免外洩內部敏感資訊）。

2. 元數據安全過濾 (Metadata Safety Allowlist)：
   - `to_public_trace_event()` 透過白名單機制（`SAFE_METADATA_KEYS`），僅允許前端視覺化真正需要的欄位（如 `task_count`, `agent_name`, `tool_name` 等），
     嚴格杜絕內部 Token、API 金鑰、連線 URL、記憶庫敏感內文或 Raw Exception 外洩。
"""

from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field, field_validator


# 前端安全之元數據白名單 (Allowlist)
SAFE_METADATA_KEYS = {
    "task_count",
    "dependency_count",
    "agent_name",
    "tool_name",
    "target",
    "failed_dependencies",
    "capability",
}


class ChatRequest(BaseModel):
    """使用者對話請求模型 (Chat Request DTO)."""

    message: str = Field(..., description="使用者輸入之訊息字串 (不可為空或純空白字元)")
    conversation_id: Optional[str] = Field(
        default=None,
        description="對話 Session ID (可選，供未來多輪對話記憶隔離使用)",
    )

    @field_validator("message")
    @classmethod
    def validate_message_non_empty(cls, v: str) -> str:
        """驗證訊息不可為空字串或純空白字元."""
        if not v or not v.strip():
            raise ValueError("message 不可為空字串或純空白字元")
        return v.strip()


class TraceEvent(BaseModel):
    """執行軌跡事件 DTO (Execution Trace Event DTO)."""

    event_id: Optional[str] = Field(default=None, description="事件唯一識別碼")
    event_type: str = Field(..., description="事件類型 (例如 planning_started, task_started, task_completed 等)")
    plan_id: Optional[str] = Field(default=None, description="對應計畫 ID")
    task_id: Optional[str] = Field(default=None, description="對應子任務 ID")
    execution_type: Optional[str] = Field(default=None, description="執行類型 (LOCAL / MCP / A2A)")
    target: Optional[str] = Field(default=None, description="執行目標 (Tool 名稱、Agent 技能等)")
    status: Optional[str] = Field(default=None, description="執行狀態 (running / success / failed / skipped / timeout)")
    message: Optional[str] = Field(default=None, description="事件描述或結果摘要")
    duration_ms: Optional[float] = Field(default=None, description="耗時 (毫秒)")
    metadata: Optional[Dict[str, Any]] = Field(default=None, description="前端安全之額外元數據")


def to_public_trace_event(event: Any) -> TraceEvent:
    """將內部調度事件 (OrchestrationEvent) 安全轉換為前端公開之 TraceEvent DTO."""
    # 取得 event_type 字串
    evt_type = getattr(event, "event_type", "unknown")
    if hasattr(evt_type, "value"):
        evt_type = evt_type.value
    else:
        evt_type = str(evt_type)

    # 取得 execution_type 字串
    exec_type = getattr(event, "execution_type", None)
    if exec_type is not None:
        exec_type = exec_type.value if hasattr(exec_type, "value") else str(exec_type)

    # 取得 status 字串
    status_val = getattr(event, "status", None)
    if status_val is not None:
        status_val = status_val.value if hasattr(status_val, "value") else str(status_val)

    # 安全過濾 metadata (Allowlist Only)
    raw_meta = getattr(event, "metadata", {}) or {}
    safe_meta = {k: v for k, v in raw_meta.items() if k in SAFE_METADATA_KEYS}

    return TraceEvent(
        event_id=getattr(event, "event_id", None),
        event_type=evt_type,
        plan_id=getattr(event, "plan_id", None),
        task_id=getattr(event, "task_id", None),
        execution_type=exec_type,
        target=getattr(event, "target", None),
        status=status_val,
        message=getattr(event, "message", None),
        duration_ms=getattr(event, "duration_ms", None),
        metadata=safe_meta if safe_meta else None,
    )


class ChatResponse(BaseModel):
    """對話回覆模型 (Chat Response DTO)."""

    message: str = Field(..., description="M.Ber 最終回應文字")
    status: str = Field(..., description="執行整體狀態 (success / partial_success / failed)")
    plan_id: Optional[str] = Field(default=None, description="調度計畫唯一識別碼")
    conversation_id: Optional[str] = Field(default=None, description="對話 Session ID")
    trace: List[TraceEvent] = Field(
        default_factory=list,
        description="累積之執行軌跡清單",
    )


class HealthResponse(BaseModel):
    """服務健康檢查回應模型 (Health Check Response DTO)."""

    status: str = Field(default="ok", description="服務狀態 (ok)")
    service: str = Field(default="mber", description="服務名稱識別")
    version: str = Field(..., description="M.Ber 核心版本號")


class ErrorDetail(BaseModel):
    """結構化錯誤資訊."""

    code: str = Field(..., description="錯誤代碼 (例如 invalid_request, internal_error)")
    message: str = Field(..., description="對使用者友善之錯誤描述")


class ErrorResponse(BaseModel):
    """標準錯誤回應模型 (Error Response DTO)."""

    error: ErrorDetail = Field(..., description="錯誤詳情")


# ==========================================
# Phase 8 - P8-04: MCP Activity & Status DTOs
# ==========================================


class McpToolInfo(BaseModel):
    """MCP 工具公開資訊模型 (不洩漏敏感內部路徑或參數細節)."""

    name: str = Field(..., description="工具識別名稱 (例如 get_current_time)")
    server: str = Field(..., description="所屬 MCP 伺服器識別名稱 (例如 own_server, calendar)")
    safety_level: str = Field(..., description="安全等級 (read_only / write)")
    description: Optional[str] = Field(default=None, description="工具功能摘要說明")


class McpStatusResponse(BaseModel):
    """MCP 系統整體狀態回應模型."""

    status: str = Field(..., description="MCP 總管狀態 (online / unavailable)")
    tool_count: int = Field(..., description="目前已探索並就緒之工具總數")
    server_count: int = Field(..., description="目前連線就緒之 MCP 伺服器總數")
    tools: List[McpToolInfo] = Field(default_factory=list, description="就緒之工具清單")


class McpActivityItem(BaseModel):
    """MCP 工具執行活動紀錄項目 (純觀測性元數據，不含使用者敏感對話或參數)."""

    activity_id: str = Field(..., description="活動紀錄唯一識別碼")
    tool_name: str = Field(..., description="調用之工具名稱")
    server_name: str = Field(..., description="所屬伺服器名稱")
    status: str = Field(..., description="執行結果狀態 (success / failed / timeout / running)")
    duration_ms: Optional[float] = Field(default=None, description="執行耗時 (毫秒)")
    timestamp: str = Field(..., description="調用時間戳記 (ISO 8601 UTC)")
    task_id: Optional[str] = Field(default=None, description="對應調度 SubTask ID")
    safety_level: Optional[str] = Field(default=None, description="安全等級 (READ_ONLY / WRITE / MUTATION)")
    error_summary: Optional[str] = Field(default=None, description="安全之錯誤摘要 (不含 Traceback)")


class McpActivityResponse(BaseModel):
    """MCP 活動紀錄查詢回應模型."""

    items: List[McpActivityItem] = Field(default_factory=list, description="最近活動紀錄清單 (由新到舊)")
    total: int = Field(..., description="回傳之紀錄筆數")

