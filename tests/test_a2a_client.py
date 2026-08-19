"""Unit Tests for JARVIS Phase 6 - A2A JSON-RPC 2.0 Client.

驗證項目：
1. A2AClient 呼叫 SendMessage 建立新任務與延續既有任務
2. A2AClient 呼叫 GetTask 查詢任務狀態
3. A2AClient 呼叫 CancelTask 取消任務
4. JSON-RPC 錯誤回應轉化為 A2AClientError 例外
5. 參數驗證 (空白 task_id 防護)
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
    """模擬遠端 A2A 伺服器之 JSON-RPC 2.0 處理器."""
    req_id = payload.get("id")
    method = payload.get("method")
    params = payload.get("params", {})

    if method == "SendMessage":
        msg_data = params.get("message", {})
        task_id = params.get("task_id", "mock-task-1001")
        text = ""
        for p in msg_data.get("parts", []):
            if p.get("type") == "text":
                text += p.get("text", "")

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
                    msg_data,
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
        task_id = params.get("task_id")
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
        task_id = params.get("task_id")
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


def test_a2a_client_send_message() -> None:
    """測試 A2AClient 發送訊息並接收 Task 成果."""
    client = A2AClient(endpoint_url="https://mock.agent/rpc", transport=mock_remote_transport)

    task = client.send_message("請幫我撰寫一份報告")

    assert isinstance(task, Task)
    assert task.id == "mock-task-1001"
    assert task.status.state == TaskState.COMPLETED
    assert task.status.message is not None
    assert "已收到並完成請求" in task.status.message.text_content
    assert len(task.artifacts) == 1
    assert task.artifacts[0].name == "result.txt"


def test_a2a_client_send_message_with_task_id() -> None:
    """測試在既有 Task 脈絡下發送訊息."""
    client = A2AClient(endpoint_url="https://mock.agent/rpc", transport=mock_remote_transport)

    msg = Message.from_text("請補充參考文獻", role="user")
    task = client.send_message(msg, task_id="task-custom-888")

    assert task.id == "task-custom-888"


def test_a2a_client_get_task() -> None:
    """測試 A2AClient 查詢任務狀態."""
    client = A2AClient(endpoint_url="https://mock.agent/rpc", transport=mock_remote_transport)

    task = client.get_task("task-12345")
    assert task.id == "task-12345"
    assert task.status.state == TaskState.WORKING


def test_a2a_client_cancel_task() -> None:
    """測試 A2AClient 取消任務."""
    client = A2AClient(endpoint_url="https://mock.agent/rpc", transport=mock_remote_transport)

    task = client.cancel_task("task-12345")
    assert task.id == "task-12345"
    assert task.status.state == TaskState.CANCELED


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
