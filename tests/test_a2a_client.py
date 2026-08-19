"""Unit Tests for M.Ber Phase 6 - A2A JSON-RPC 2.0 Client.

驗證項目：
1. A2AClient 呼叫 SendMessage 接收 Task 狀態化回傳
2. A2AClient 呼叫 SendMessage 接收 Message 直接對話回傳 (A2A 1.0 語意)
3. A2AClient 呼叫 SendMessage 帶入 taskId
4. A2AClient 呼叫 GetTask 使用 A2A 1.0 官方參數結構 {"id": "..."}
5. A2AClient 呼叫 CancelTask 使用 A2A 1.0 官方參數結構 {"id": "..."}
6. JSON-RPC 錯誤回應轉化為 A2AClientError 例外
7. 參數驗證 (空白 task_id 防護)
"""

from typing import Any, Dict
import pytest
from app.a2a.client import A2AClient, A2AClientError
from app.a2a.models import (
    Artifact,
    Message,
    Task,
    TaskState,
    TaskStatus,
    TextPart,
)


def mock_remote_transport(url: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    """模擬符合 A2A 1.0 規範之嚴格遠端 JSON-RPC 2.0 伺服器."""
    req_id = payload.get("id")
    method = payload.get("method")
    params = payload.get("params", {})

    # 驗證 JSON-RPC 2.0 協定基本規範
    if payload.get("jsonrpc") != "2.0":
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "error": {"code": -32600, "message": "Invalid JSON-RPC version (must be 2.0)"},
        }

    if method == "SendMessage":
        if "message" not in params or not isinstance(params["message"], dict):
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "error": {"code": -32602, "message": "Invalid params: 'message' is required"},
            }

        # 嚴格驗證 Message 模型
        try:
            msg_obj = Message.model_validate(params["message"])
        except Exception as e:
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "error": {"code": -32602, "message": f"Invalid Message schema: {e}"},
            }

        text = msg_obj.text_content

        # 情境 A：若文字包含 'direct_reply'，模擬遠端 Agent 直接回傳 Message (A2A 1.0 語意)
        if "direct_reply" in text:
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "role": "agent",
                    "parts": [{"type": "text", "text": f"Direct response: {text}"}],
                    "metadata": {},
                },
            }

        # 情境 B：一般任務委派，回傳狀態化 Task
        task_id = params.get("taskId", "mock-task-1001")
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {
                "id": task_id,
                "status": {
                    "state": "completed",
                    "message": {
                        "role": "agent",
                        "parts": [{"type": "text", "text": f"已收到並完成請求: {text}"}],
                    },
                },
                "history": [
                    msg_obj.model_dump(),
                    {
                        "role": "agent",
                        "parts": [{"type": "text", "text": f"已收到並完成請求: {text}"}],
                    },
                ],
                "artifacts": [
                    {
                        "id": "art-001",
                        "name": "result.txt",
                        "parts": [{"type": "text", "text": "任務產出成果檔案內容"}],
                    }
                ],
            },
        }

    elif method == "GetTask":
        # 嚴格驗證 A2A 1.0 官方參數名稱 'id'
        if "id" not in params:
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "error": {"code": -32602, "message": "Invalid params: 'id' is required by A2A 1.0 specification"},
            }

        task_id = params["id"]
        if task_id == "not_found":
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "error": {
                    "code": -32004,
                    "message": f"Task '{task_id}' not found",
                },
            }
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {
                "id": task_id,
                "status": {"state": "working"},
                "history": [],
                "artifacts": [],
            },
        }

    elif method == "CancelTask":
        # 嚴格驗證 A2A 1.0 官方參數名稱 'id'
        if "id" not in params:
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "error": {"code": -32602, "message": "Invalid params: 'id' is required by A2A 1.0 specification"},
            }

        task_id = params["id"]
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {
                "id": task_id,
                "status": {"state": "canceled"},
                "history": [],
                "artifacts": [],
            },
        }

    return {
        "jsonrpc": "2.0",
        "id": req_id,
        "error": {"code": -32601, "message": f"Method '{method}' not found"},
    }


def test_a2a_client_send_message_returning_task() -> None:
    """測試 A2AClient 發送訊息並接收 Task 成果."""
    client = A2AClient(endpoint_url="https://mock.agent/rpc", transport=mock_remote_transport)

    response = client.send_message("請幫我撰寫一份報告")

    assert isinstance(response, Task)
    assert response.id == "mock-task-1001"
    assert response.status.state == TaskState.COMPLETED
    assert response.status.message is not None
    assert "已收到並完成請求" in response.status.message.text_content
    assert len(response.artifacts) == 1
    assert response.artifacts[0].name == "result.txt"


def test_a2a_client_send_message_returning_message() -> None:
    """測試 A2AClient 呼叫 SendMessage 時支援接收 Message 物件 (A2A 1.0 多態回應)."""
    client = A2AClient(endpoint_url="https://mock.agent/rpc", transport=mock_remote_transport)

    response = client.send_message("direct_reply: 請告訴我目前伺服器狀況")

    assert isinstance(response, Message)
    assert response.role == "agent"
    assert "Direct response" in response.text_content


def test_a2a_client_send_message_with_task_id() -> None:
    """測試在既有 Task 脈絡下發送訊息 (使用 taskId 參數)."""
    recorded_params = {}

    def inspect_transport(url: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        nonlocal recorded_params
        recorded_params = payload.get("params", {})
        return mock_remote_transport(url, payload)

    client = A2AClient(endpoint_url="https://mock.agent/rpc", transport=inspect_transport)
    msg = Message.from_text("請補充參考文獻", role="user")
    response = client.send_message(msg, task_id="task-custom-888")

    assert isinstance(response, Task)
    assert response.id == "task-custom-888"
    assert recorded_params.get("taskId") == "task-custom-888"


def test_a2a_client_get_task_request_shape() -> None:
    """測試 A2AClient 查詢任務狀態時傳送符合 A2A 1.0 的 {'id': '...'} 參數結構."""
    recorded_params = {}

    def inspect_transport(url: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        nonlocal recorded_params
        recorded_params = payload.get("params", {})
        return mock_remote_transport(url, payload)

    client = A2AClient(endpoint_url="https://mock.agent/rpc", transport=inspect_transport)
    task = client.get_task("task-12345")

    assert isinstance(task, Task)
    assert task.id == "task-12345"
    assert task.status.state == TaskState.WORKING
    # 確保傳送給遠端的是官方欄位 'id' 而非私有 'task_id'
    assert recorded_params == {"id": "task-12345"}


def test_a2a_client_cancel_task_request_shape() -> None:
    """測試 A2AClient 取消任務時傳送符合 A2A 1.0 的 {'id': '...'} 參數結構."""
    recorded_params = {}

    def inspect_transport(url: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        nonlocal recorded_params
        recorded_params = payload.get("params", {})
        return mock_remote_transport(url, payload)

    client = A2AClient(endpoint_url="https://mock.agent/rpc", transport=inspect_transport)
    task = client.cancel_task("task-12345")

    assert isinstance(task, Task)
    assert task.id == "task-12345"
    assert task.status.state == TaskState.CANCELED
    # 確保傳送給遠端的是官方欄位 'id' 而非私有 'task_id'
    assert recorded_params == {"id": "task-12345"}


def test_a2a_client_error_handling() -> None:
    """測試遠端 JSON-RPC 錯誤被正確轉換為 A2AClientError."""
    client = A2AClient(endpoint_url="https://mock.agent/rpc", transport=mock_remote_transport)

    with pytest.raises(A2AClientError) as exc_info:
        client.get_task("not_found")

    assert exc_info.value.code == -32004
    assert "not found" in str(exc_info.value)


def test_a2a_client_validation_error() -> None:
    """測試空白 task_id 輸入防護."""
    client = A2AClient(endpoint_url="https://mock.agent/rpc", transport=mock_remote_transport)

    with pytest.raises(ValueError, match="task_id 不得為空白"):
        client.get_task("   ")

    with pytest.raises(ValueError, match="task_id 不得為空白"):
        client.cancel_task("")
