"""M.Ber MCP Activity Observation & Recording (MCP 活動觀測與記錄模組).
Phase 8 - P8-04: MCP Activity & Runtime Inspector

【新手教學 / 觀念解析】：
1. 為什麼需要 MCP Activity Recorder？
   - MCP Activity Recorder 負責收集「全域 MCP 工具調用歷史（Global Tool Call History）」。
   - 它扮演「純觀測者（Read-only Observer）」角色，記錄：
     ① 哪個 MCP 工具被執行（`tool_name`）
     ② 所屬的 MCP 伺服器（`server_name`）
     ③ 執行狀態（`status`: success / failed / timeout / running）
     ④ 執行耗時（`duration_ms`）與安全權限等級（`safety_level`）
   - 核心原則：**絕不記錄使用者敏感提示詞、完整參數（arguments）、工具回傳原始內文（results）或任何金鑰資訊**。

2. 記憶體環狀歷史緩衝區（Bounded In-Memory History）：
   - 使用 `collections.deque(maxlen=100)` 搭配 `threading.Lock()` 實現線程安全的高效記憶體緩衝區。
   - 保留最近 100 筆活動，不需額外引入資料庫，開銷極低且快速。
"""

from collections import deque
from dataclasses import dataclass
from datetime import datetime, timezone
import threading
import time
from typing import Any, Dict, List, Optional
import uuid


@dataclass(frozen=True)
class MCPActivityRecord:
    """單筆 MCP 工具活動觀測紀錄 (不可變資料物件)."""

    activity_id: str
    tool_name: str
    server_name: str
    status: str  # "success" | "failed" | "timeout" | "running"
    duration_ms: Optional[float]
    timestamp: str  # ISO 8601 UTC 字串
    task_id: Optional[str] = None
    safety_level: Optional[str] = None  # "READ_ONLY" | "WRITE / MUTATION"
    error_summary: Optional[str] = None


class MCPActivityRecorder:
    """線程安全的 MCP 活動記錄器 (In-Memory Thread-safe Activity Store)."""

    def __init__(self, max_history: int = 100) -> None:
        """初始化活動記錄器.

        Args:
            max_history: 緩衝區最多保留之歷史筆數 (預設 100 筆)
        """
        self._max_history = max_history
        self._history: deque[MCPActivityRecord] = deque(maxlen=max_history)
        self._lock = threading.Lock()

    def record(
        self,
        tool_name: str,
        server_name: str,
        status: str,
        duration_ms: Optional[float] = None,
        task_id: Optional[str] = None,
        safety_level: Optional[str] = None,
        error_summary: Optional[str] = None,
        activity_id: Optional[str] = None,
    ) -> MCPActivityRecord:
        """建立並儲存一筆 MCP 活動記錄 (自動過濾敏感資訊)."""
        now_iso = datetime.now(timezone.utc).isoformat()
        act_id = activity_id or f"mcp_act_{uuid.uuid4().hex[:12]}"

        # 清理並簡化 error_summary，防止 traceback 外洩
        clean_error: Optional[str] = None
        if error_summary:
            clean_error = str(error_summary).split("\n")[0][:200]

        record = MCPActivityRecord(
            activity_id=act_id,
            tool_name=tool_name,
            server_name=server_name or "unknown",
            status=status,
            duration_ms=round(duration_ms, 2) if duration_ms is not None else None,
            timestamp=now_iso,
            task_id=task_id,
            safety_level=safety_level,
            error_summary=clean_error,
        )

        with self._lock:
            self._history.appendleft(record)

        return record

    def get_recent(self, limit: int = 20) -> List[MCPActivityRecord]:
        """取得最近的 MCP 活動紀錄清單 (依時間新到舊排序)."""
        safe_limit = max(1, min(limit, self._max_history))
        with self._lock:
            # 複製前 safe_limit 筆
            return list(self._history)[:safe_limit]

    def clear(self) -> None:
        """清空歷史紀錄 (測試隔離使用)."""
        with self._lock:
            self._history.clear()

    def __len__(self) -> int:
        with self._lock:
            return len(self._history)


# 全域共用預設 Recorder 實例
_DEFAULT_RECORDER: Optional[MCPActivityRecorder] = None
_RECORDER_INIT_LOCK = threading.Lock()


def get_default_mcp_recorder() -> MCPActivityRecorder:
    """取得或建立全域預設 MCPActivityRecorder 單例."""
    global _DEFAULT_RECORDER
    if _DEFAULT_RECORDER is None:
        with _RECORDER_INIT_LOCK:
            if _DEFAULT_RECORDER is None:
                _DEFAULT_RECORDER = MCPActivityRecorder()
    return _DEFAULT_RECORDER
