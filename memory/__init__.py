"""JARVIS Memory Package (記憶管理子系統).

提供領域實體、倉儲介面與記憶管理服務：
- MemoryItem, MemoryType: 記憶領域模型與分類
- MemoryRepository, InMemoryMemoryRepository: 儲存抽象合約與記憶體實作
- SQLiteMemoryRepository: SQLite 持久化儲存實作 (預設 data/memory.db)
- MemoryService: 高階領域服務 (remember, recall, search, forget)
- get_default_memory_service: 預設持久化領域服務工廠函式 (Composition Root)
"""

from memory.models import MemoryItem, MemoryType
from memory.repository import MemoryRepository, InMemoryMemoryRepository
from memory.sqlite import SQLiteMemoryRepository
from memory.service import MemoryService


def get_default_memory_service(db_path: str = "data/memory.db") -> MemoryService:
    """Composition Root 工廠函式：組裝預設以 SQLite 作為儲存後端的 MemoryService."""
    repo = SQLiteMemoryRepository(db_path=db_path)
    return MemoryService(repository=repo)


__all__ = [
    "MemoryItem",
    "MemoryType",
    "MemoryRepository",
    "InMemoryMemoryRepository",
    "SQLiteMemoryRepository",
    "MemoryService",
    "get_default_memory_service",
]
