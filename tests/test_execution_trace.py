"""Unit & Integration Tests for Execution Trace Collection & SSE Streaming (Phase 8 - P8-02).

驗證項目：
1. 調度內部事件發送 (Planning / Task / Aggregation / Response-ready Events)
2. 非串流 POST /api/chat 回傳累積之 TraceEvent 清單
3. POST /api/chat/stream 產出符合 SSE 規範之 text/event-stream 格式
4. SSE 串流包含 trace 事件與 final 結尾事件
5. 應用層失敗時 (Application FAILED) SSE 正常串流並發送 final (status=failed)
6. 伺服器內部非預期例外時 SSE 發送 event: error
7. 多步驟 (A2A ➔ Memory) 串流順序驗證 (planning ➔ task A2A ➔ task Memory ➔ aggregation ➔ final)
8. 前置依賴失敗時 (A2A Failed ➔ Memory Skipped) 事件順序與 skipped 語意驗證
9. 部分失敗 (A2A Success + Memory Failed) 之 partial_success 串流驗證
10. 元數據安全性白名單過濾 (不洩漏敏感內部資料)
"""

import json
from typing import Any, Dict, List
from unittest.mock import MagicMock
import pytest
from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage, HumanMessage

from app.interfaces.web.gateway import create_web_app
from app.interfaces.web.models import TraceEvent, to_public_trace_event
from app.orchestration.events import (
    ListEventSink,
    OrchestrationEvent,
    OrchestrationEventType,
)
from app.orchestration.models import (
    AggregatedResult,
    AggregateStatus,
    ExecutionResult,
    ExecutionStatus,
    ExecutionType,
    OrchestrationResponse,
    SubTask,
    TaskPlan,
)
from app.orchestration.orchestrator import Orchestrator
from app.orchestration.router import Router
from app.orchestration.service import OrchestrationService


def parse_sse_events(raw_text: str) -> List[Dict[str, Any]]:
    """解析 SSE text/event-stream 格式字串為結構化事件清單."""
    events = []
    blocks = raw_text.strip().split("\n\n")
    for block in blocks:
        if not block.strip():
            continue
        lines = block.strip().split("\n")
        event_name = "message"
        data_str = ""
        for line in lines:
            if line.startswith("event:"):
                event_name = line.replace("event:", "").strip()
            elif line.startswith("data:"):
                data_str = line.replace("data:", "").strip()
        if data_str:
            try:
                parsed_data = json.loads(data_str)
            except Exception:
                parsed_data = data_str
            events.append({"event": event_name, "data": parsed_data})
    return events


def test_orchestration_emits_planning_events() -> None:
    """驗證 OrchestrationService 執行時正常發送 planning_started 與 plan_created 事件."""
    service = OrchestrationService()
    sink = ListEventSink()

    service.invoke_with_details([HumanMessage(content="你好 M.Ber")], event_sink=sink)
    events = sink.get_events()

    event_types = [e.event_type for e in events]
    assert OrchestrationEventType.REQUEST_RECEIVED in event_types
    assert OrchestrationEventType.PLANNING_STARTED in event_types
    assert OrchestrationEventType.PLAN_CREATED in event_types


def test_orchestration_emits_task_events() -> None:
    """驗證 Orchestrator 執行 TaskPlan 時正常發送 task_started 與 task_completed 事件."""
    router = MagicMock(spec=Router)
    router.route.return_value = ExecutionResult(
        task_id="t1",
        execution_type=ExecutionType.LOCAL,
        status=ExecutionStatus.SUCCESS,
        result="Success result",
    )
    orchestrator = Orchestrator(router=router)
    plan = TaskPlan(
        plan_id="p1",
        user_goal="測試",
        tasks=[
            SubTask(task_id="t1", execution_type=ExecutionType.LOCAL, goal="子任務1")
        ],
    )
    sink = ListEventSink()
    orchestrator.execute_plan(plan, event_sink=sink)

    events = sink.get_events()
    event_types = [e.event_type for e in events]
    assert OrchestrationEventType.TASK_STARTED in event_types
    assert OrchestrationEventType.TASK_COMPLETED in event_types

    completed_event = [e for e in events if e.event_type == OrchestrationEventType.TASK_COMPLETED][0]
    assert completed_event.status == "success"
    assert completed_event.duration_ms is not None


def test_orchestration_emits_aggregation_event() -> None:
    """驗證 OrchestrationService 執行後正常發送 aggregation_completed 與 response_ready 事件."""
    service = OrchestrationService()
    sink = ListEventSink()

    service.invoke_with_details([HumanMessage(content="解釋 dependency injection")], event_sink=sink)
    events = sink.get_events()
    event_types = [e.event_type for e in events]

    assert OrchestrationEventType.AGGREGATION_COMPLETED in event_types
    assert OrchestrationEventType.RESPONSE_READY in event_types


def test_chat_response_contains_trace() -> None:
    """驗證非串流 POST /api/chat 回傳累積之 TraceEvent 清單."""
    service = OrchestrationService()
    app = create_web_app(orchestration_service=service)
    client = TestClient(app)

    response = client.post("/api/chat", json={"message": "解釋 dependency injection"})
    assert response.status_code == 200
    data = response.json()

    assert "trace" in data
    assert len(data["trace"]) > 0
    trace_event_types = [t["event_type"] for t in data["trace"]]
    assert "planning_started" in trace_event_types
    assert "plan_created" in trace_event_types
    assert "task_started" in trace_event_types
    assert "task_completed" in trace_event_types
    assert "aggregation_completed" in trace_event_types


def test_chat_trace_preserves_event_order() -> None:
    """驗證 TraceEvents 保留嚴格的時序先後順序."""
    service = OrchestrationService()
    app = create_web_app(orchestration_service=service)
    client = TestClient(app)

    response = client.post("/api/chat", json={"message": "你好"})
    data = response.json()
    trace = data["trace"]

    req_idx = next(i for i, t in enumerate(trace) if t["event_type"] == "request_received")
    plan_idx = next(i for i, t in enumerate(trace) if t["event_type"] == "plan_created")
    task_idx = next(i for i, t in enumerate(trace) if t["event_type"] == "task_started")
    agg_idx = next(i for i, t in enumerate(trace) if t["event_type"] == "aggregation_completed")

    assert req_idx < plan_idx < task_idx < agg_idx


def test_chat_trace_does_not_expose_unsafe_metadata() -> None:
    """驗證 metadata 安全白名單過濾機制，確保不洩漏未授權之內部欄位."""
    unsafe_event = OrchestrationEvent(
        event_type=OrchestrationEventType.TASK_COMPLETED,
        plan_id="p1",
        task_id="t1",
        metadata={
            "agent_name": "PCforge",  # 安全白名單
            "internal_url": "http://10.0.0.1:9999/rpc",  # 不安全，應過濾
            "auth_token": "secret_bearer_123",  # 不安全，應過濾
            "task_count": 2,  # 安全白名單
        },
    )
    public_dto = to_public_trace_event(unsafe_event)
    assert public_dto.metadata is not None
    assert "agent_name" in public_dto.metadata
    assert "task_count" in public_dto.metadata
    assert "internal_url" not in public_dto.metadata
    assert "auth_token" not in public_dto.metadata


def test_chat_stream_endpoint_returns_event_stream() -> None:
    """驗證 POST /api/chat/stream 回傳正確的 text/event-stream Content-Type."""
    service = OrchestrationService()
    app = create_web_app(orchestration_service=service)
    client = TestClient(app)

    response = client.post("/api/chat/stream", json={"message": "你好"})
    assert response.status_code == 200
    assert "text/event-stream" in response.headers.get("content-type", "")


def test_chat_stream_emits_planning_and_task_and_final_events() -> None:
    """驗證 POST /api/chat/stream 串流輸出包含 trace 事件與 final 結尾事件."""
    service = OrchestrationService()
    app = create_web_app(orchestration_service=service)
    client = TestClient(app)

    response = client.post("/api/chat/stream", json={"message": "解釋 dependency injection", "conversation_id": "c1"})
    parsed_events = parse_sse_events(response.text)

    event_names = [e["event"] for e in parsed_events]
    assert "trace" in event_names
    assert "final" in event_names
    assert event_names[-1] == "final"

    # 驗證 final 事件內容
    final_event = [e for e in parsed_events if e["event"] == "final"][0]
    final_data = final_event["data"]
    assert final_data["status"] == "success"
    assert final_data["conversation_id"] == "c1"
    assert "依賴注入" in final_data["message"]


def test_chat_stream_application_failure_still_emits_final() -> None:
    """驗證應用層調度失敗時 (如外部 Peer 離線)，SSE 仍順暢串流並以 final (status='failed') 結束."""
    fake_service = MagicMock(spec=OrchestrationService)
    failed_plan = TaskPlan(
        plan_id="p_fail",
        user_goal="買電腦",
        tasks=[SubTask(task_id="t_fail", execution_type=ExecutionType.A2A, goal="配單")],
    )
    failed_agg = AggregatedResult(
        plan_id="p_fail",
        results=[
            ExecutionResult(
                task_id="t_fail",
                execution_type=ExecutionType.A2A,
                status=ExecutionStatus.FAILED,
                error="Peer offline",
            )
        ],
    )

    def side_effect_invoke(messages, event_sink=None):
        if event_sink:
            event_sink.emit(
                OrchestrationEvent(
                    event_type=OrchestrationEventType.TASK_FAILED,
                    plan_id="p_fail",
                    task_id="t_fail",
                    status="failed",
                    message="Peer offline",
                )
            )
        return OrchestrationResponse(
            message=AIMessage(content="⚠️ 任務執行失敗：Peer offline"),
            plan=failed_plan,
            aggregated=failed_agg,
        )

    fake_service.invoke_with_details.side_effect = side_effect_invoke
    app = create_web_app(orchestration_service=fake_service)
    client = TestClient(app)

    response = client.post("/api/chat/stream", json={"message": "買電腦"})
    assert response.status_code == 200
    parsed = parse_sse_events(response.text)

    final_event = [e for e in parsed if e["event"] == "final"][0]
    assert final_event["data"]["status"] == "failed"
    assert "Peer offline" in final_event["data"]["message"]


def test_chat_stream_unexpected_exception_emits_error() -> None:
    """驗證伺服器內部發生未預期異常時，SSE 串流發送 event: error."""
    fake_service = MagicMock(spec=OrchestrationService)
    fake_service.invoke_with_details.side_effect = RuntimeError("爆炸了")

    app = create_web_app(orchestration_service=fake_service)
    client = TestClient(app)

    response = client.post("/api/chat/stream", json={"message": "觸發異常"})
    assert response.status_code == 200
    parsed = parse_sse_events(response.text)

    error_events = [e for e in parsed if e["event"] == "error"]
    assert len(error_events) == 1
    assert error_events[0]["data"]["code"] == "internal_error"
    # 不洩漏 Python traceback
    assert "爆炸了" not in error_events[0]["data"]["message"]


def test_chat_stream_multistep_a2a_to_memory_flow() -> None:
    """多步驟場景驗證：A2A 推薦 ➔ Memory 儲存 之完整事件流."""
    fake_service = MagicMock(spec=OrchestrationService)
    plan = TaskPlan(
        plan_id="plan_pc_mem",
        user_goal="幫我配電腦並記住",
        tasks=[
            SubTask(task_id="t_a2a", execution_type=ExecutionType.A2A, goal="配電腦", target="pc_recommendation"),
            SubTask(task_id="t_mem", execution_type=ExecutionType.LOCAL, goal="記住", target="memory_store", depends_on=["t_a2a"]),
        ],
    )
    agg = AggregatedResult(
        plan_id="plan_pc_mem",
        results=[
            ExecutionResult(task_id="t_a2a", execution_type=ExecutionType.A2A, status=ExecutionStatus.SUCCESS, result="PC單"),
            ExecutionResult(task_id="t_mem", execution_type=ExecutionType.LOCAL, status=ExecutionStatus.SUCCESS, result="Saved"),
        ],
    )

    def side_effect_invoke(messages, event_sink=None):
        if event_sink:
            event_sink.emit(OrchestrationEvent(event_type=OrchestrationEventType.PLAN_CREATED, plan_id="plan_pc_mem"))
            event_sink.emit(OrchestrationEvent(event_type=OrchestrationEventType.TASK_STARTED, task_id="t_a2a", execution_type=ExecutionType.A2A))
            event_sink.emit(OrchestrationEvent(event_type=OrchestrationEventType.TASK_COMPLETED, task_id="t_a2a", execution_type=ExecutionType.A2A, status="success"))
            event_sink.emit(OrchestrationEvent(event_type=OrchestrationEventType.TASK_STARTED, task_id="t_mem", execution_type=ExecutionType.LOCAL))
            event_sink.emit(OrchestrationEvent(event_type=OrchestrationEventType.TASK_COMPLETED, task_id="t_mem", execution_type=ExecutionType.LOCAL, status="success"))
            event_sink.emit(OrchestrationEvent(event_type=OrchestrationEventType.AGGREGATION_COMPLETED, plan_id="plan_pc_mem", status="success"))
        return OrchestrationResponse(
            message=AIMessage(content="PC單\n\n💾 【記憶庫】: 已為您成功記住這項資訊。"),
            plan=plan,
            aggregated=agg,
        )

    fake_service.invoke_with_details.side_effect = side_effect_invoke
    app = create_web_app(orchestration_service=fake_service)
    client = TestClient(app)

    response = client.post("/api/chat/stream", json={"message": "幫我配電腦並記住"})
    parsed = parse_sse_events(response.text)

    trace_event_types = [e["data"].get("event_type") for e in parsed if e["event"] == "trace"]
    assert "plan_created" in trace_event_types
    assert "task_started" in trace_event_types
    assert "task_completed" in trace_event_types
    assert "aggregation_completed" in trace_event_types

    final_event = [e for e in parsed if e["event"] == "final"][0]
    assert final_event["data"]["status"] == "success"


def test_chat_stream_a2a_failure_skips_memory() -> None:
    """失敗場景驗證：A2A 失敗時 Memory 被標記為 skipped (task_skipped)，不應出現 task_started."""
    fake_service = MagicMock(spec=OrchestrationService)
    plan = TaskPlan(
        plan_id="plan_fail_flow",
        user_goal="幫我配電腦並記住",
        tasks=[
            SubTask(task_id="t_a2a", execution_type=ExecutionType.A2A, goal="配電腦"),
            SubTask(task_id="t_mem", execution_type=ExecutionType.LOCAL, goal="記住", depends_on=["t_a2a"]),
        ],
    )
    agg = AggregatedResult(
        plan_id="plan_fail_flow",
        results=[
            ExecutionResult(task_id="t_a2a", execution_type=ExecutionType.A2A, status=ExecutionStatus.FAILED, error="A2A Offline"),
            ExecutionResult(task_id="t_mem", execution_type=ExecutionType.LOCAL, status=ExecutionStatus.SKIPPED, error="Dependency failed"),
        ],
    )

    def side_effect_invoke(messages, event_sink=None):
        if event_sink:
            event_sink.emit(OrchestrationEvent(event_type=OrchestrationEventType.TASK_STARTED, task_id="t_a2a", execution_type=ExecutionType.A2A))
            event_sink.emit(OrchestrationEvent(event_type=OrchestrationEventType.TASK_FAILED, task_id="t_a2a", execution_type=ExecutionType.A2A, status="failed"))
            event_sink.emit(OrchestrationEvent(event_type=OrchestrationEventType.TASK_SKIPPED, task_id="t_mem", execution_type=ExecutionType.LOCAL, status="skipped"))
            event_sink.emit(OrchestrationEvent(event_type=OrchestrationEventType.AGGREGATION_COMPLETED, plan_id="plan_fail_flow", status="failed"))
        return OrchestrationResponse(
            message=AIMessage(content="⚠️ 任務無法順利完成"),
            plan=plan,
            aggregated=agg,
        )

    fake_service.invoke_with_details.side_effect = side_effect_invoke
    app = create_web_app(orchestration_service=fake_service)
    client = TestClient(app)

    response = client.post("/api/chat/stream", json={"message": "配電腦並記住"})
    parsed = parse_sse_events(response.text)

    trace_events = [e["data"] for e in parsed if e["event"] == "trace"]
    mem_started = [t for t in trace_events if t.get("task_id") == "t_mem" and t.get("event_type") == "task_started"]
    mem_skipped = [t for t in trace_events if t.get("task_id") == "t_mem" and t.get("event_type") == "task_skipped"]

    # 確保被略過的記憶任務絕不會發出 task_started
    assert len(mem_started) == 0
    assert len(mem_skipped) == 1
    assert mem_skipped[0]["status"] == "skipped"


def test_chat_stream_partial_failure() -> None:
    """部分失敗場景驗證：A2A 成功但 Memory 失敗 ➔ 聚合狀態為 partial_success."""
    fake_service = MagicMock(spec=OrchestrationService)
    plan = TaskPlan(
        plan_id="plan_partial",
        user_goal="配電腦並記住",
        tasks=[
            SubTask(task_id="t_a2a", execution_type=ExecutionType.A2A, goal="配電腦"),
            SubTask(task_id="t_mem", execution_type=ExecutionType.LOCAL, goal="記住", depends_on=["t_a2a"]),
        ],
    )
    agg = AggregatedResult(
        plan_id="plan_partial",
        results=[
            ExecutionResult(task_id="t_a2a", execution_type=ExecutionType.A2A, status=ExecutionStatus.SUCCESS, result="PC推薦單"),
            ExecutionResult(task_id="t_mem", execution_type=ExecutionType.LOCAL, status=ExecutionStatus.FAILED, error="Memory Lock"),
        ],
    )

    def side_effect_invoke(messages, event_sink=None):
        if event_sink:
            event_sink.emit(OrchestrationEvent(event_type=OrchestrationEventType.TASK_COMPLETED, task_id="t_a2a", execution_type=ExecutionType.A2A, status="success"))
            event_sink.emit(OrchestrationEvent(event_type=OrchestrationEventType.TASK_FAILED, task_id="t_mem", execution_type=ExecutionType.LOCAL, status="failed"))
            event_sink.emit(OrchestrationEvent(event_type=OrchestrationEventType.AGGREGATION_COMPLETED, plan_id="plan_partial", status="partial_success"))
        return OrchestrationResponse(
            message=AIMessage(content="PC推薦單\n\n⚠️ 【注意】：部分步驟執行發生問題：\n- 任務 [t_mem] 執行失敗: Memory Lock"),
            plan=plan,
            aggregated=agg,
        )

    fake_service.invoke_with_details.side_effect = side_effect_invoke
    app = create_web_app(orchestration_service=fake_service)
    client = TestClient(app)

    response = client.post("/api/chat/stream", json={"message": "配電腦並記住"})
    parsed = parse_sse_events(response.text)

    final_event = [e for e in parsed if e["event"] == "final"][0]
    assert final_event["data"]["status"] == "partial_success"
