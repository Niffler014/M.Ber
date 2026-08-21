"""M.Ber Orchestration Events & Trace Sinks (調度事件與執行軌跡核心模組).
Phase 8 - P8-02: Execution Trace & Streaming

【新手教學 / 觀念解析】：
1. 什麼是 Orchestration Event（調度事件）？
   - 當系統在進行「規劃 ➔ 路由 ➔ 執行 ➔ 彙整」時，每一個關鍵轉折點（如開始規劃、任務開始執行、任務成功/失敗、結果彙整）
     都會產出一個結構化的「事件（Event）」。
   - 核心原則：**事件只是「觀察者（Observer）」，絕對不能干預或控制調度邏輯（Non-intrusive Observation）**。

2. 為什麼依賴方向要保持單向？
   - 核心領域（`app/orchestration`）絕不 import 外部傳輸層的 DTO（如 `app.interfaces.web.models.TraceEvent`）。
   - 透過定義內部的 `OrchestrationEvent` 與 `TraceSink`，確保 Application Core 獨立於任何 HTTP / SSE / WebSocket 傳輸細節。
"""

from abc import ABC, abstractmethod
from enum import Enum
import time
from typing import Any, Callable, Dict, List, Optional
import uuid
from pydantic import BaseModel, Field

from app.orchestration.models import (
    AggregateStatus,
    ExecutionStatus,
    ExecutionType,
)


class OrchestrationEventType(str, Enum):
    """調度生命週期事件類型枚舉 (Orchestration Event Type)."""

    REQUEST_RECEIVED = "request_received"        # 收到使用者請求
    PLANNING_STARTED = "planning_started"        # Planner 開始進行意圖解析與規劃
    PLAN_CREATED = "plan_created"                # Planner 產出 TaskPlan 計畫
    TASK_STARTED = "task_started"                # 單一子任務開始執行 (LOCAL / MCP / A2A)
    TASK_COMPLETED = "task_completed"            # 單一子任務成功執行完畢
    TASK_FAILED = "task_failed"                  # 單一子任務執行失敗
    TASK_SKIPPED = "task_skipped"                # 因前置依賴失敗而略過子任務
    TASK_TIMEOUT = "task_timeout"                # 單一子任務執行逾時
    AGGREGATION_COMPLETED = "aggregation_completed"  # ResultAggregator 完成結果彙整
    RESPONSE_READY = "response_ready"            # 最終回覆文字合成就緒
    ERROR = "error"                              # 未預期系統錯誤


class OrchestrationEvent(BaseModel):
    """內部調度事件實體 (Internal Domain Event Model)."""

    event_id: str = Field(
        default_factory=lambda: f"evt_{uuid.uuid4().hex[:8]}",
        description="事件唯一識別碼",
    )
    event_type: OrchestrationEventType = Field(..., description="事件類型")
    plan_id: Optional[str] = Field(default=None, description="所屬計畫識別碼")
    task_id: Optional[str] = Field(default=None, description="所屬子任務識別碼")
    execution_type: Optional[ExecutionType] = Field(default=None, description="執行路由類型")
    target: Optional[str] = Field(default=None, description="執行目標 (工具名 / Agent 技能等)")
    status: Optional[str] = Field(default=None, description="執行狀態字串")
    message: Optional[str] = Field(default=None, description="事件描述或摘要")
    duration_ms: Optional[float] = Field(default=None, description="執行耗時 (毫秒)")
    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="內部元數據 (安全轉發至前端時需經 Allowlist 過濾)",
    )
    timestamp: float = Field(
        default_factory=time.time,
        description="事件產生之 Unix Timestamp",
    )


class TraceSink(ABC):
    """執行軌跡接收器抽象介面 (Abstract Trace Sink Interface)."""

    @abstractmethod
    def emit(self, event: OrchestrationEvent) -> None:
        """接收並處理一則調度事件."""
        pass


class ListEventSink(TraceSink):
    """將事件收集於記憶體清單之接收器 (In-Memory Collector Sink)."""

    def __init__(self) -> None:
        self.events: List[OrchestrationEvent] = []

    def emit(self, event: OrchestrationEvent) -> None:
        self.events.append(event)

    def get_events(self) -> List[OrchestrationEvent]:
        return list(self.events)


class CallbackEventSink(TraceSink):
    """將事件轉發給回呼函式之接收器 (Callback Sink - 常用於 SSE 即時串流推播)."""

    def __init__(self, callback: Callable[[OrchestrationEvent], None]) -> None:
        self.callback = callback

    def emit(self, event: OrchestrationEvent) -> None:
        try:
            self.callback(event)
        except Exception:
            # 確保外部接收端異常不影響核心調度執行
            pass


class CompositeEventSink(TraceSink):
    """將事件廣播給多個 Sinks 之組合接收器 (Composite Broadcaster Sink)."""

    def __init__(self, sinks: List[TraceSink]) -> None:
        self.sinks = list(sinks)

    def emit(self, event: OrchestrationEvent) -> None:
        for sink in self.sinks:
            try:
                sink.emit(event)
            except Exception:
                pass
