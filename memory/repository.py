"""M.Ber Memory Repository Interface & In-Memory Implementation.

【新手教學 / 觀念解析】：
1. 什麼是 Repository Pattern（倉儲模式）？
   - Repository 是一層「儲存轉接介面」，它扮演記憶體集合（Collection）的抽象外表。
   - 上層的業務邏輯（MemoryService）只與 `MemoryRepository` 這個介面溝通，
     完全不知道底層到底是用 SQLite、PostgreSQL 還是純記憶體列表儲存！
   - 這讓我們可以在寫單元測試時，瞬間換上 `InMemoryMemoryRepository`，不用建立實體資料庫，測試又快又乾淨！
"""

from abc import ABC, abstractmethod
from typing import Dict, List, Optional
from memory.models import MemoryItem, MemoryType


class MemoryRepository(ABC):
    """記憶儲存抽象合約介面 (Abstract Base Class)."""

    @abstractmethod
    def add(self, item: MemoryItem) -> MemoryItem:
        """新增或儲存一筆記憶."""
        pass

    @abstractmethod
    def get(self, memory_id: str) -> Optional[MemoryItem]:
        """依據 ID 取得單一記憶."""
        pass

    @abstractmethod
    def search(
        self,
        query: Optional[str] = None,
        memory_type: Optional[MemoryType] = None,
        limit: int = 10,
    ) -> List[MemoryItem]:
        """搜尋符合條件的記憶清單."""
        pass

    @abstractmethod
    def delete(self, memory_id: str) -> bool:
        """依據 ID 刪除記憶，若成功回傳 True."""
        pass

    @abstractmethod
    def clear(self) -> None:
        """清除所有記憶 (主要用於測試或重置)."""
        pass


class InMemoryMemoryRepository(MemoryRepository):
    """記憶體內部儲存實作 (專供單元測試與輕量模擬使用)."""

    def __init__(self) -> None:
        self._storage: Dict[str, MemoryItem] = {}

    def add(self, item: MemoryItem) -> MemoryItem:
        self._storage[item.id] = item
        return item

    def get(self, memory_id: str) -> Optional[MemoryItem]:
        return self._storage.get(memory_id)

    def search(
        self,
        query: Optional[str] = None,
        memory_type: Optional[MemoryType] = None,
        limit: int = 10,
    ) -> List[MemoryItem]:
        results: List[MemoryItem] = []
        for item in self._storage.values():
            if memory_type is not None:
                # 支援 enum 或字串比較
                item_type = item.memory_type.value if hasattr(item.memory_type, "value") else str(item.memory_type)
                target_type = memory_type.value if hasattr(memory_type, "value") else str(memory_type)
                if item_type != target_type:
                    continue

            if query is not None and query.strip():
                if query.lower() not in item.content.lower():
                    continue

            results.append(item)
            if len(results) >= limit:
                break

        # 依建立時間倒序排序 (最新優先)
        results.sort(key=lambda x: x.created_at, reverse=True)
        return results[:limit]

    def delete(self, memory_id: str) -> bool:
        if memory_id in self._storage:
            del self._storage[memory_id]
            return True
        return False

    def clear(self) -> None:
        self._storage.clear()
