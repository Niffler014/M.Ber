"""JARVIS A2A Client (A2A 1.0.0 JSON-RPC 2.0 客戶端通訊模組).

【新手教學 / 觀念解析】：
1. 什麼是 A2A Client？
   - `A2AClient` 是 JARVIS 與外部 AI 代理人「交涉與發送任務」的通訊轉發窗口。
   - 它遵循 A2A 1.0 規範，使用 **JSON-RPC 2.0** 協議將請求包裝成標準信封傳輸給遠端 Agent。

2. 支援的標準方法 (Standard Methods)：
   - `SendMessage`：發送新訊息或交付新任務給目標 Agent，取得狀態化的 `Task` 回應。
   - `GetTask`：查詢既有任務的最新執行進度與產物（Artifacts）。
   - `CancelTask`：取消正在進行中的任務。
"""

import json
from typing import Any, Callable, Dict, Optional, Union
import urllib.request
import urllib.error

from app.a2a.models import (
    JSONRPCError,
    JSONRPCRequest,
    JSONRPCResponse,
    Message,
    Task,
    TextPart,
)


class A2AClientError(Exception):
    """A2A 協定或 JSON-RPC 遠端呼叫錯誤例外."""

    def __init__(self, message: str, code: Optional[int] = None, data: Optional[Any] = None) -> None:
        super().__init__(message)
        self.code = code
        self.data = data


# 傳輸適配器函式型別 (供測試與自訂 HTTP 實作注入)
TransportHandler = Callable[[str, Dict[str, Any]], Dict[str, Any]]


class A2AClient:
    """A2A 1.0.0 JSON-RPC 2.0 客戶端實作類別."""

    def __init__(
        self,
        endpoint_url: str,
        transport: Optional[TransportHandler] = None,
        timeout: float = 30.0,
    ) -> None:
        """初始化 A2A Client.

        Args:
            endpoint_url: 遠端 Agent 服務端點 URL (例如 'https://agent.example.com/v1/rpc')
            transport: 自訂傳輸函式 (若為 None 則使用內建 HTTP POST)
            timeout: HTTP 請求超時秒數
        """
        self.endpoint_url = endpoint_url
        self.transport = transport or self._default_http_transport
        self.timeout = timeout

    def _default_http_transport(self, url: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        """預設基於 Python 標準庫 urllib 的 HTTP POST JSON-RPC 傳輸實作."""
        data_bytes = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        req = urllib.request.Request(
            url=url,
            data=data_bytes,
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json",
                "User-Agent": "JARVIS-A2A-Client/1.0",
            },
            method="POST",
        )

        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                resp_bytes = resp.read()
                return json.loads(resp_bytes.decode("utf-8"))
        except urllib.error.HTTPError as e:
            try:
                err_body = e.read().decode("utf-8")
                err_json = json.loads(err_body)
                return err_json
            except Exception:
                raise A2AClientError(f"HTTP 連線失敗 ({e.code}): {e.reason}") from e
        except Exception as e:
            raise A2AClientError(f"A2A 遠端通訊失敗: {e}") from e

    def _call_rpc(self, method: str, params: Dict[str, Any]) -> Any:
        """發送 JSON-RPC 2.0 請求並解析回應."""
        request = JSONRPCRequest(method=method, params=params)
        payload = request.model_dump()

        raw_response = self.transport(self.endpoint_url, payload)
        rpc_resp = JSONRPCResponse.model_validate(raw_response)

        if rpc_resp.error is not None:
            raise A2AClientError(
                message=f"[{rpc_resp.error.code}] {rpc_resp.error.message}",
                code=rpc_resp.error.code,
                data=rpc_resp.error.data,
            )

        return rpc_resp.result

    def send_message(
        self,
        message: Union[str, Message],
        task_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Task:
        """發送訊息/委派任務給遠端 Agent (呼叫 SendMessage 方法).

        Args:
            message: 文字訊息內容或完整 Message 物件
            task_id: 關聯既有任務 ID (若為新任務則留空)
            metadata: 附加元數據

        Returns:
            遠端 Agent 回傳之 Task 實體
        """
        if isinstance(message, str):
            msg_obj = Message(role="user", parts=[TextPart(text=message)])
        else:
            msg_obj = message

        params: Dict[str, Any] = {
            "message": msg_obj.model_dump(),
        }
        if task_id is not None:
            params["task_id"] = task_id
        if metadata:
            params["metadata"] = metadata

        result = self._call_rpc("SendMessage", params)
        if isinstance(result, dict):
            return Task.model_validate(result)
        raise A2AClientError(f"無效的 Task 回傳格式: {type(result)}")

    def get_task(self, task_id: str) -> Task:
        """向遠端 Agent 查詢指定任務狀態與歷史 (呼叫 GetTask 方法).

        Args:
            task_id: 任務識別碼

        Returns:
            當前 Task 實體
        """
        if not task_id or not task_id.strip():
            raise ValueError("task_id 不得為空白。")

        result = self._call_rpc("GetTask", {"task_id": task_id.strip()})
        if isinstance(result, dict):
            return Task.model_validate(result)
        raise A2AClientError(f"無效的 Task 回傳格式: {type(result)}")

    def cancel_task(self, task_id: str) -> Task:
        """向遠端 Agent 請求取消指定任務 (呼叫 CancelTask 方法).

        Args:
            task_id: 欲取消的任務 ID

        Returns:
            更新後為 CANCELED 狀態之 Task 實體
        """
        if not task_id or not task_id.strip():
            raise ValueError("task_id 不得為空白。")

        result = self._call_rpc("CancelTask", {"task_id": task_id.strip()})
        if isinstance(result, dict):
            return Task.model_validate(result)
        raise A2AClientError(f"無效的 Task 回傳格式: {type(result)}")
