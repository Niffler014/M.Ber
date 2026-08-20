"""M.Ber Orchestration Memory Adapter (調度層與記憶服務轉接模組).

【新手教學 / 觀念解析】：
1. 什麼是 Memory Adapter？
   - `MemoryAdapter` 是調度層（Orchestration Layer）與 Phase 5 核心 `MemoryService` 之間的「轉接器」。
   - 它作為 `ExecutionType.LOCAL` 底下註冊的標準處理常式（Canonical Target: `memory_store`）。
   - 它的職責：
     ① 從 `task.parameters` 或 `ExecutionContext` 提取待儲存內容（依賴結果傳遞優先於空內容）。
     ② 對結構化成果（如字典、清單）進行確定性 JSON 序列化（`ensure_ascii=False`）。
     ③ 調用 `MemoryService.remember()` 寫入持久化倉儲，並回傳標準化記憶收條資訊。
"""

import json
import logging
from typing import Any, Dict, Optional, Union

from app.orchestration.models import ExecutionContext, SubTask
from memory.models import MemoryItem, MemoryType
from memory.service import MemoryService

logger = logging.getLogger("mber.orchestration")

CANONICAL_MEMORY_CAPABILITY = "memory_store"


class MemoryAdapter:
    """調度層記憶服務適配器."""

    def __init__(self, memory_service: Optional[MemoryService] = None) -> None:
        """初始化 MemoryAdapter.

        Args:
            memory_service: 記憶服務實例 (若為 None 則於調用時使用預設工廠建立)
        """
        self._memory_service = memory_service

    @property
    def memory_service(self) -> MemoryService:
        """取得或延遲初始化 MemoryService 實例."""
        if self._memory_service is None:
            from memory import get_default_memory_service

            self._memory_service = get_default_memory_service()
        return self._memory_service

    def serialize_content(self, raw_content: Any) -> str:
        """將任意型別的產出內容確定性序列化為字串."""
        if raw_content is None:
            raise ValueError("記憶內容不可為 None")

        if isinstance(raw_content, str):
            clean_str = raw_content.strip()
            if not clean_str:
                raise ValueError("記憶文字內容不得為空白字串")
            return clean_str

        if isinstance(raw_content, (dict, list)):
            return json.dumps(raw_content, ensure_ascii=False, indent=2)

        if hasattr(raw_content, "model_dump"):
            return json.dumps(raw_content.model_dump(mode="json"), ensure_ascii=False, indent=2)

        str_repr = str(raw_content).strip()
        if not str_repr:
            raise ValueError("物件轉換後字串不得為空白")
        return str_repr

    def store_memory_handler(
        self,
        task: SubTask,
        context: Optional[ExecutionContext] = None,
    ) -> Dict[str, Any]:
        """處理 memory_store 本地子任務之標準 Handler.

        Args:
            task: 待執行子任務實體
            context: 執行期上下文 (包含前置依賴成果)

        Returns:
            儲存成功之確認字典 (包含 memory_id, status, content 等)
        """
        logger.info(f"[MemoryAdapter] Processing memory store request (task_id: {task.task_id})")
        params = dict(task.parameters or {})

        # 1. 內容提取順序：explicit parameters['content'] ➔ context 前置依賴產出
        raw_content = params.get("content")
        dep_task_id = None

        if raw_content is None or (isinstance(raw_content, str) and not raw_content.strip()):
            if context and task.depends_on:
                # 依賴單一或明確指定的來源任務
                dep_task_id = params.get("source_task_id") or task.depends_on[0]
                raw_content = context.get_result(dep_task_id)
            elif context and context.dependency_results:
                raw_content = context.get_first_result()

        if raw_content is None or (isinstance(raw_content, str) and not raw_content.strip()):
            err_msg = "記憶儲存失敗：未提供 content 參數且無有效的前置依賴產出結果"
            logger.warning(f"[MemoryAdapter] {err_msg}")
            raise ValueError(err_msg)

        # 2. 確定性序列化
        content_str = self.serialize_content(raw_content)

        # 3. 準備元數據
        metadata = dict(params.get("metadata") or {})
        metadata["source"] = "orchestration"
        if dep_task_id:
            metadata["source_task_id"] = dep_task_id

        memory_type = params.get("memory_type", MemoryType.GENERAL)

        # 4. 調用 MemoryService
        item: MemoryItem = self.memory_service.remember(
            content=content_str,
            memory_type=memory_type,
            metadata=metadata,
        )

        logger.info(f"[MemoryAdapter] Successfully stored memory item (id: {item.id})")
        return {
            "memory_id": item.id,
            "status": "stored",
            "content": item.content,
            "memory_type": item.memory_type.value if hasattr(item.memory_type, "value") else str(item.memory_type),
            "created_at": item.created_at.isoformat() if hasattr(item.created_at, "isoformat") else str(item.created_at),
        }


def register_memory_capability(
    local_executor: Any,
    memory_service: Optional[MemoryService] = None,
    capability_name: str = CANONICAL_MEMORY_CAPABILITY,
) -> MemoryAdapter:
    """便利工廠函式：將 MemoryAdapter 註冊進指定的 LocalExecutor."""
    adapter = MemoryAdapter(memory_service=memory_service)
    local_executor.register_handler(capability_name, adapter.store_memory_handler)
    return adapter
