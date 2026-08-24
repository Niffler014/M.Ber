"""Unit and Integration Tests for M.Ber LINE Webhook Gateway (app/interfaces/line_gateway.py).
Phase 8 - P8-05A: LINE Bidirectional Chat Integration

驗證項目：
1. 健康檢查端點 (GET /health)
2. 缺少/無效 X-Line-Signature 標頭之 400 阻擋
3. LINE 文字訊息統一經由 OrchestrationService 頂層調度
4. LOCAL 通用對話回覆 (例如「我肚子很餓」)
5. MCP 外部工具查詢回覆 (例如「現在幾點？」)
6. A2A 專門代理人技能委派回覆 (例如「幫我配一台四萬元遊戲電腦」)
7. A2A ➔ Memory 循序多步驟工作流程回覆 (例如「幫我配一台四萬元遊戲電腦，然後記住這套配置」)
8. Orchestration 失敗時回傳安全提示訊息 (不崩潰)
9. 未預期例外時回傳安全提示訊息 (不洩漏 traceback 或內部堆疊)
10. 超長回應文字安全分段切分 (Long Response Split)
11. 內部除錯軌跡 (plan_id, trace, metadata) 不直接外洩給 LINE 使用者
12. 採用標準穩定的 channel-neutral conversation_id (line:<USER_ID>)
"""

import base64
import hashlib
import hmac
import json
from typing import Any, Dict, List
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage, HumanMessage

from app.interfaces.line_formatter import mask_user_id, split_text_into_chunks
from app.interfaces.line_gateway import LINE_CHANNEL_SECRET, create_line_app
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
from app.orchestration.planner import (
    CapabilitySummary,
    MockDeterministicPlanningBackend,
    PlannedTask,
    Planner,
    PlanStructuredOutput,
)
from app.orchestration.service import OrchestrationService


from app.a2a.discovery import AgentDiscoveryService
from app.a2a.models import AgentCapabilities, AgentCard, AgentSkill


def mock_a2a_rpc_transport(url: str, request_data: Dict[str, Any], timeout: float = 10.0) -> Dict[str, Any]:
    """模擬 PCforge A2A JSON-RPC 回應 (零網路依賴)."""
    return {
        "jsonrpc": "2.0",
        "id": request_data.get("id", "req_1"),
        "result": {
            "role": "agent",
            "parts": [
                {
                    "type": "text",
                    "text": "【PCforge 電腦配置推薦】\n- 處理器: AMD Ryzen 5 7500F\n- 顯示卡: NVIDIA RTX 4060 Ti\n- 總計預算: 約 39,800 元",
                }
            ],
        },
    }


def generate_line_signature(body_str: str, secret: str) -> str:
    """計算 LINE Webhook HMAC-SHA256 簽章."""
    hash_value = hmac.new(
        secret.encode("utf-8"),
        body_str.encode("utf-8"),
        hashlib.sha256,
    ).digest()
    return base64.b64encode(hash_value).decode("utf-8")


def create_mock_webhook_payload(
    user_text: str,
    user_id: str = "U_USER_ALICE_123",
    reply_token: str = "dummy_reply_token_abc",
) -> Dict[str, Any]:
    """建構標準 LINE Webhook 文字訊息 Payload."""
    return {
        "destination": "U_BOT_DESTINATION",
        "events": [
            {
                "type": "message",
                "message": {
                    "type": "text",
                    "id": "msg_001",
                    "text": user_text,
                    "quoteToken": "quote_1",
                    "markAsReadToken": "read_1",
                },
                "timestamp": 1723812000000,
                "source": {
                    "type": "user",
                    "userId": user_id,
                },
                "replyToken": reply_token,
                "mode": "active",
                "webhookEventId": "event_001",
                "deliveryContext": {"isRedelivery": False},
            }
        ],
    }


def post_line_webhook(client: TestClient, payload: Dict[str, Any], secret: str = LINE_CHANNEL_SECRET):
    """向 LINE Gateway 發送已完成簽章的 POST /callback 請求."""
    body_bytes = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    signature = generate_line_signature(body_bytes.decode("utf-8"), secret)
    headers = {
        "X-Line-Signature": signature,
        "Content-Type": "application/json",
    }
    return client.post("/callback", content=body_bytes, headers=headers)


@pytest.fixture
def mock_service():
    """建立具備確定性 Mock Planning 後端與 Mock A2A 傳輸之 OrchestrationService."""
    discovery = AgentDiscoveryService(config_path=None)
    card = AgentCard(
        name="PCforge",
        description="電腦配置推薦代理人",
        url="http://localhost:8001/v1/a2a",
        version="1.0.0",
        protocol_version="1.0.0",
        capabilities=AgentCapabilities(),
        skills=[
            AgentSkill(
                id="pc_recommendation",
                name="電腦配置推薦",
                description="根據預算與用途推薦電腦硬體配置",
                tags=["電腦", "pc", "硬體", "組裝", "配單"],
            )
        ],
    )
    discovery.register_agent(card)

    caps = CapabilitySummary(
        a2a_skills=[
            {
                "id": "pc_recommendation",
                "name": "電腦配置推薦",
                "description": "根據預算與用途推薦電腦硬體配置",
                "tags": ["電腦", "pc", "硬體", "組裝", "配單"],
                "agent_name": "PCforge",
            }
        ],
        mcp_tools=[
            {"name": "get_current_time", "description": "取得當前系統時間與日期"},
        ],
        local_capabilities=["memory_store", "general_qa", "agent_reasoning"],
    )
    planner = Planner(capability_summary=caps)
    service = OrchestrationService(
        planner=planner,
        discovery_service=discovery,
        rpc_transport=mock_a2a_rpc_transport,
    )
    return service


@pytest.fixture
def client(mock_service: OrchestrationService):
    """建立綁定 mock_service 之 FastAPI TestClient."""
    app = create_line_app(orchestration_service=mock_service)
    return TestClient(app)


# ============================================================================
# 1. 基礎健康檢查與簽章驗證測試
# ============================================================================

def test_line_gateway_health_check(client: TestClient) -> None:
    """測試健康檢查端點正常回應."""
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["service"] == "M.Ber LINE Webhook Gateway"


def test_line_gateway_missing_signature(client: TestClient) -> None:
    """測試未提供 X-Line-Signature 標頭時應回傳 400."""
    response = client.post("/callback", json={"events": []})
    assert response.status_code == 400
    assert "缺少" in response.json()["detail"] or "signature" in response.json()["detail"].lower()


def test_line_gateway_invalid_signature(client: TestClient) -> None:
    """測試提供錯誤簽章時應回傳 400 (Invalid Signature)."""
    headers = {"X-Line-Signature": "INVALID_SIGNATURE_STRING"}
    response = client.post("/callback", content=b'{"events": []}', headers=headers)
    assert response.status_code == 400
    assert "簽章" in response.json()["detail"] or "signature" in response.json()["detail"].lower()


# ============================================================================
# 2. 單一調度核心 (Single Application Core) 路由測試
# ============================================================================

def test_line_text_message_routes_through_orchestration_service(mock_service: OrchestrationService) -> None:
    """驗證 LINE TextMessage 正確轉化為 HumanMessage 並經由 OrchestrationService 調度."""
    app = create_line_app(orchestration_service=mock_service)
    test_client = TestClient(app)

    payload = create_mock_webhook_payload("你好，請問 M.Ber 是什麼？", user_id="U_ALICE")
    res = post_line_webhook(test_client, payload)

    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "success"
    assert data["processed_count"] == 1
    assert data["results"][0]["user_id"] == "U_ALICE"
    assert data["results"][0]["conversation_id"] == "line:U_ALICE"
    assert isinstance(data["results"][0]["reply"], str)
    assert len(data["results"][0]["reply"]) > 0


def test_line_local_chat_reply(client: TestClient) -> None:
    """測試 LOCAL 通用問答 (例如「我肚子很餓」) 經由 OrchestrationService 正常回覆."""
    payload = create_mock_webhook_payload("我肚子很餓")
    res = post_line_webhook(client, payload)

    assert res.status_code == 200
    data = res.json()
    reply = data["results"][0]["reply"]
    assert any(k in reply for k in ["吃", "餓", "食物", "餐", "建議", "M.Ber"])


def test_line_mcp_request(client: TestClient) -> None:
    """測試 MCP 工具請求 (例如「現在幾點？」) 經由 OrchestrationService 正常取得時間並回覆."""
    payload = create_mock_webhook_payload("現在幾點？")
    res = post_line_webhook(client, payload)

    assert res.status_code == 200
    data = res.json()
    reply = data["results"][0]["reply"]
    assert any(k in reply for k in ["現在", "時間", "CurrentTime", "目前", "系統時間"])


def test_line_a2a_request(mock_service: OrchestrationService) -> None:
    """測試 A2A 專門代理人委派請求 (例如「幫我配一台四萬元遊戲電腦」)."""
    app = create_line_app(orchestration_service=mock_service)
    test_client = TestClient(app)

    payload = create_mock_webhook_payload("幫我配一台四萬元遊戲電腦")
    res = post_line_webhook(test_client, payload)

    assert res.status_code == 200
    data = res.json()
    reply = data["results"][0]["reply"]
    assert any(k in reply for k in ["配置", "電腦", "處理器", "顯示卡", "預算", "PCforge", "主機"])


def test_line_a2a_to_memory_request(mock_service: OrchestrationService) -> None:
    """測試 A2A ➔ Memory 多步驟請求 (例如「幫我配一台四萬元遊戲電腦，然後記住這套配置」)."""
    app = create_line_app(orchestration_service=mock_service)
    test_client = TestClient(app)

    payload = create_mock_webhook_payload("幫我配一台四萬元遊戲電腦，然後記住這套配置")
    res = post_line_webhook(test_client, payload)

    assert res.status_code == 200
    data = res.json()
    reply = data["results"][0]["reply"]
    assert len(reply) > 0


# ============================================================================
# 3. 錯誤防護與安全性測試 (Safety & Error Handling)
# ============================================================================

def test_line_orchestration_failure_returns_safe_reply() -> None:
    """驗證當 Orchestration 發生失敗 (FAILED) 時，LINE 不會崩潰且回傳安全訊息."""
    mock_failing_service = MagicMock(spec=OrchestrationService)
    mock_failing_service.invoke_with_details.return_value = OrchestrationResponse(
        message=AIMessage(content="抱歉，目前所有外部工具皆無法連線，無法完成請求。"),
        plan=TaskPlan(plan_id="plan_fail", user_goal="查詢故障工具", tasks=[]),
        aggregated=AggregatedResult(plan_id="plan_fail", results=[]),
        events=[],
    )

    app = create_line_app(orchestration_service=mock_failing_service)
    test_client = TestClient(app)

    payload = create_mock_webhook_payload("查詢故障工具")
    res = post_line_webhook(test_client, payload)

    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "success"
    assert "抱歉" in data["results"][0]["reply"]


def test_line_unexpected_exception_returns_safe_reply() -> None:
    """驗證當 OrchestrationService 拋出未預期例外時，LINE 回傳安全通用訊息且不洩漏 Traceback."""
    mock_failing_service = MagicMock(spec=OrchestrationService)
    mock_failing_service.invoke_with_details.side_effect = RuntimeError("Critical Internal DB Crash: key=secret123")

    app = create_line_app(orchestration_service=mock_failing_service)
    test_client = TestClient(app)

    payload = create_mock_webhook_payload("任何指令")
    res = post_line_webhook(test_client, payload)

    assert res.status_code == 200
    data = res.json()
    reply = data["results"][0]["reply"]
    # 驗證未洩漏敏感 key 或 crash traceback
    assert "secret123" not in reply
    assert "Traceback" not in reply
    assert "抱歉" in reply


def test_line_long_response_is_split_safely() -> None:
    """驗證當回覆文字超過單則上限時，由 formatter 安全切分."""
    # 建立 3500 字元長篇文字
    long_text = "【電腦配單評估報告】\n\n" + ("這是一段電腦配置建議與詳細分析說明。" * 100)
    chunks = split_text_into_chunks(long_text, max_chunk_size=1000, max_chunks=5)

    assert len(chunks) > 1
    assert len(chunks) <= 5
    for c in chunks:
        assert len(c) <= 1200


def test_line_does_not_expose_internal_trace(client: TestClient) -> None:
    """驗證 LINE 回覆中不包含 plan_id, raw trace event 或 debug 結構."""
    payload = create_mock_webhook_payload("現在幾點？")
    res = post_line_webhook(client, payload)

    assert res.status_code == 200
    data = res.json()
    reply = data["results"][0]["reply"]

    assert "plan_" not in reply
    assert "ExecutionResult" not in reply
    assert "TraceEvent" not in reply
    assert "step_id" not in reply


def test_line_uses_stable_channel_conversation_id(client: TestClient) -> None:
    """驗證對話識別碼採用統一之 stable channel-neutral 格式 'line:<USER_ID>'."""
    payload = create_mock_webhook_payload("你好", user_id="U_BOB_789")
    res = post_line_webhook(client, payload)

    assert res.status_code == 200
    data = res.json()
    assert data["results"][0]["user_id"] == "U_BOB_789"
    assert data["results"][0]["conversation_id"] == "line:U_BOB_789"


def test_mask_user_id() -> None:
    """驗證 User ID 遮罩工具函式."""
    assert mask_user_id("U_USER_ALICE_123") == "U_US..._123"
    assert mask_user_id("short") == "short"
    assert mask_user_id("") == "anonymous"
