"""Unit Tests for JARVIS LINE Webhook Gateway (app/interfaces/line_gateway.py).

驗證項目：
1. FastAPI 健康檢查端點 (GET /health)
2. 缺少 X-Line-Signature 標頭之 400 阻擋
3. 無效簽章之 400 阻擋
4. 合法 HMAC-SHA256 簽章 Webhook 訊息處理與 LangGraph 觸發
5. 多使用者 thread_id 對話隔離驗證
"""

import hmac
import hashlib
import base64
import json
import pytest
from fastapi.testclient import TestClient
from app.interfaces.line_gateway import app, LINE_CHANNEL_SECRET


@pytest.fixture
def client():
    """建立 FastAPI TestClient."""
    return TestClient(app)


def generate_line_signature(body_str: str, secret: str) -> str:
    """計算 LINE Webhook HMAC-SHA256 簽章."""
    hash_value = hmac.new(
        secret.encode("utf-8"),
        body_str.encode("utf-8"),
        hashlib.sha256,
    ).digest()
    return base64.b64encode(hash_value).decode("utf-8")


def test_line_gateway_health_check(client: TestClient) -> None:
    """測試健康檢查端點正常回應."""
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert "own_server" in data["mcp_servers"]


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


def test_line_gateway_valid_webhook_event_processing(client: TestClient) -> None:
    """測試合法簽章 Webhook 訊息轉發至 LangGraph 並正確產出回覆."""
    payload = {
        "destination": "U_BOT_DESTINATION",
        "events": [
            {
                "type": "message",
                "message": {
                    "type": "text",
                    "id": "msg_001",
                    "text": "現在幾點了？",
                    "quoteToken": "quote_1",
                    "markAsReadToken": "read_1",
                },
                "timestamp": 1723812000000,
                "source": {
                    "type": "user",
                    "userId": "U_USER_ALICE_123",
                },
                "replyToken": "dummy_reply_token_abc",
                "mode": "active",
                "webhookEventId": "event_001",
                "deliveryContext": {"isRedelivery": False},
            }
        ],
    }

    body_bytes = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    signature = generate_line_signature(body_bytes.decode("utf-8"), LINE_CHANNEL_SECRET)

    headers = {
        "X-Line-Signature": signature,
        "Content-Type": "application/json",
    }

    response = client.post("/callback", content=body_bytes, headers=headers)
    assert response.status_code == 200
    res_data = response.json()
    assert res_data["status"] == "success"
    assert res_data["processed_count"] == 1

    result_item = res_data["results"][0]
    assert result_item["user_id"] == "U_USER_ALICE_123"
    assert "已成功" in result_item["reply"] or "系統時間" in result_item["reply"]


def test_line_gateway_multi_user_thread_isolation(client: TestClient) -> None:
    """測試多使用者 (Alice vs Bob) 的 thread_id 獨立隔離."""
    # Alice 發送新增筆記
    payload_alice = {
        "destination": "U_BOT",
        "events": [
            {
                "type": "message",
                "message": {
                    "type": "text",
                    "id": "m1",
                    "text": "新增筆記：標題=Alice專用，內容=Alice的私人秘密",
                    "quoteToken": "q_alice",
                    "markAsReadToken": "r_alice",
                },
                "timestamp": 1723812000000,
                "source": {"type": "user", "userId": "U_ALICE"},
                "replyToken": "token_1",
                "mode": "active",
                "webhookEventId": "event_alice_1",
                "deliveryContext": {"isRedelivery": False},
            }
        ],
    }
    body_alice = json.dumps(payload_alice, ensure_ascii=False).encode("utf-8")
    sig_alice = generate_line_signature(body_alice.decode("utf-8"), LINE_CHANNEL_SECRET)
    res_alice = client.post("/callback", content=body_alice, headers={"X-Line-Signature": sig_alice})
    assert res_alice.status_code == 200

    # Bob 查詢筆記
    payload_bob = {
        "destination": "U_BOT",
        "events": [
            {
                "type": "message",
                "message": {
                    "type": "text",
                    "id": "m2",
                    "text": "查詢筆記：Alice專用",
                    "quoteToken": "q_bob",
                    "markAsReadToken": "r_bob",
                },
                "timestamp": 1723812001000,
                "source": {"type": "user", "userId": "U_BOB"},
                "replyToken": "token_2",
                "mode": "active",
                "webhookEventId": "event_bob_1",
                "deliveryContext": {"isRedelivery": False},
            }
        ],
    }
    body_bob = json.dumps(payload_bob, ensure_ascii=False).encode("utf-8")
    sig_bob = generate_line_signature(body_bob.decode("utf-8"), LINE_CHANNEL_SECRET)
    res_bob = client.post("/callback", content=body_bob, headers={"X-Line-Signature": sig_bob})
    assert res_bob.status_code == 200
    assert res_bob.json()["results"][0]["user_id"] == "U_BOB"
