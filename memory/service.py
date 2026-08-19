"""JARVIS Memory Service (記憶領域服務與門面).

【新手教學 / 觀念解析】：
1. 什麼是 MemoryService？
   - `MemoryService` 是整個記憶子系統的「服務窗口（Domain Facade）」。
   - 它負責：
     ① 驗證記憶內容（不能為空白）。
     ② 將使用者常用的動作轉換成領域語言：
        - `remember`：請幫我記住這件事。
        - `recall`：喚醒/回想特定 ID 的記憶。
        - `search`：搜尋有沒有相關的記憶。
        - `forget`：請幫我忘記這件事。
     ③ 協調 Repository 進行儲存與讀取。
"""

from typing import Any, Dict, List, Optional, Union
from memory.models import MemoryItem, MemoryType
from memory.repository import MemoryRepository


class MemoryService:
    """記憶高階領域服務類別."""

    def __init__(self, repository: MemoryRepository) -> None:
        """初始化 MemoryService.

        Args:
            repository: 記憶倉儲實例 (遵循 MemoryRepository 抽象合約)
        """
        if repository is None:
            raise ValueError("repository 必須為有效的 MemoryRepository 實例。")
        self.repository: MemoryRepository = repository

    def remember(
        self,
        content: str,
        memory_type: Union[MemoryType, str] = MemoryType.GENERAL,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> MemoryItem:
        """記住一筆新資訊 (Store Memory).

        Args:
            content: 記憶文字內容
            memory_type: 記憶分類 (可為 MemoryType 枚舉或字串)
            metadata: 附加元數據 (可選)

        Returns:
            儲存完成之 MemoryItem 實體
        """
        if not content or not content.strip():
            raise ValueError("記憶內容不得為空白。")

        if isinstance(memory_type, str):
            try:
                type_enum = MemoryType(memory_type)
            except ValueError:
                type_enum = MemoryType.GENERAL
        else:
            type_enum = memory_type

        item = MemoryItem(
            content=content.strip(),
            memory_type=type_enum,
            metadata=metadata or {},
        )
        return self.repository.add(item)

    def recall(self, memory_id: str) -> Optional[MemoryItem]:
        """依據 ID 回想單一記憶 (Retrieve Memory).

        Args:
            memory_id: 記憶識別碼

        Returns:
            若存在回傳 MemoryItem，否則回傳 None
        """
        if not memory_id or not memory_id.strip():
            return None
        return self.repository.get(memory_id.strip())

    def search(
        self,
        query: Optional[str] = None,
        memory_type: Optional[Union[MemoryType, str]] = None,
        limit: int = 10,
    ) -> List[MemoryItem]:
        """搜尋相關記憶 (Search/Query Memory).

        Args:
            query: 搜尋關鍵字 (可選)
            memory_type: 記憶分類篩選 (可選)
            limit: 最大回傳筆數 (預設 10 筆)

        Returns:
            符合條件之 MemoryItem 清單
        """
        type_enum: Optional[MemoryType] = None
        if memory_type is not None:
            if isinstance(memory_type, str):
                try:
                    type_enum = MemoryType(memory_type)
                except ValueError:
                    type_enum = None
            else:
                type_enum = memory_type

        return self.repository.search(query=query, memory_type=type_enum, limit=limit)

    def forget(self, memory_id: str) -> bool:
        """忘記/刪除指定記憶 (Delete Memory).

        Args:
            memory_id: 要刪除的記憶 ID

        Returns:
            若刪除成功回傳 True，若不存在回傳 False
        """
        if not memory_id or not memory_id.strip():
            return False
        return self.repository.delete(memory_id.strip())

    def list_all(self, limit: int = 100) -> List[MemoryItem]:
        """列出所有記憶項目 (最新優先)."""
        return self.repository.search(limit=limit)
