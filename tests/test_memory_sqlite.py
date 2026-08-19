"""Integration Tests for JARVIS SQLite Memory Repository (Phase 5.1).

驗證項目：
1. SQLite 資料庫檔案自動建表與索引建立
2. MemoryItem 持久化寫入、欄位對齊與 JSON 元數據序列化
3. 關鍵字模糊查詢與記憶類型篩選
4. 刪除與清空資料庫
5. MemoryService 注入 SQLiteMemoryRepository 之端到端整合
"""

from pathlib import Path
import pytest
from memory.models import MemoryItem, MemoryType
from memory.sqlite import SQLiteMemoryRepository
from memory.service import MemoryService
from memory import get_default_memory_service


def test_sqlite_repository_crud_flow(tmp_path: Path) -> None:
    """測試 SQLite 倉儲之完整 CRUD 操作流程."""
    db_file = tmp_path / "test_memory.db"
    repo = SQLiteMemoryRepository(db_path=db_file)

    # 1. 寫入 (Add)
    item = MemoryItem(
        content="我最喜歡的程式語言是 Python",
        memory_type=MemoryType.USER_PREFERENCE,
        metadata={"category": "programming", "level": "expert"},
    )
    saved = repo.add(item)
    assert saved.id == item.id

    # 2. 讀取 (Get)
    fetched = repo.get(item.id)
    assert fetched is not None
    assert fetched.id == item.id
    assert fetched.content == "我最喜歡的程式語言是 Python"
    assert fetched.memory_type == MemoryType.USER_PREFERENCE
    assert fetched.metadata.get("category") == "programming"

    # 3. 搜尋 (Search)
    results = repo.search(query="Python", memory_type=MemoryType.USER_PREFERENCE)
    assert len(results) == 1
    assert results[0].id == item.id

    # 4. 刪除 (Delete)
    assert repo.delete(item.id) is True
    assert repo.get(item.id) is None
    assert repo.delete(item.id) is False


def test_memory_service_with_sqlite_integration(tmp_path: Path) -> None:
    """測試 MemoryService 與 SQLite 倉儲的整合運作."""
    db_file = tmp_path / "service_memory.db"
    sqlite_repo = SQLiteMemoryRepository(db_path=db_file)
    service = MemoryService(repository=sqlite_repo)

    # 記住數筆不同類型的記憶
    service.remember("事實：系統運行時區為 Asia/Taipei", memory_type="fact")
    service.remember("偏好：回覆請使用繁體中文", memory_type="user_preference")
    service.remember("一般備忘：每週五下班前提交週報", memory_type="general")

    # 驗證總數
    all_items = service.list_all()
    assert len(all_items) == 3

    # 驗證字串類型自動轉換為 Enum
    facts = service.search(memory_type="fact")
    assert len(facts) == 1
    assert "Asia/Taipei" in facts[0].content

    # 驗證關鍵字檢索
    res = service.search(query="繁體中文")
    assert len(res) == 1
    assert res[0].memory_type == MemoryType.USER_PREFERENCE


def test_get_default_memory_service(tmp_path: Path) -> None:
    """測試 Composition Root 提供的 get_default_memory_service 工廠函式."""
    db_file = str(tmp_path / "factory_memory.db")
    service = get_default_memory_service(db_path=db_file)

    assert isinstance(service, MemoryService)
    assert isinstance(service.repository, SQLiteMemoryRepository)

    saved = service.remember("工廠組裝測試記憶", memory_type="general")
    assert saved.id is not None
    assert service.recall(saved.id) is not None

