"""Unit Tests for JARVIS Memory Subsystem Architecture & Contract (Phase 5.1).

驗證項目：
1. MemoryItem 與 MemoryType 領域模型屬性與預設值
2. MemoryService 與 InMemoryMemoryRepository 純記憶體行為
3. remember / recall / search / forget 領域操作
4. 記憶分類篩選與關鍵字檢索
5. 領域例外驗證 (空白內容防護)
"""

import pytest
from memory.models import MemoryItem, MemoryType
from memory.repository import InMemoryMemoryRepository
from memory.service import MemoryService


def test_memory_models_instantiation() -> None:
    """測試 MemoryItem 建立與預設值."""
    item = MemoryItem(content="使用者喜歡喝無糖拿鐵", memory_type=MemoryType.USER_PREFERENCE)
    assert len(item.id) > 0
    assert item.content == "使用者喜歡喝無糖拿鐵"
    assert item.memory_type == MemoryType.USER_PREFERENCE
    assert item.created_at is not None
    assert isinstance(item.metadata, dict)


def test_memory_service_remember_and_recall() -> None:
    """測試 MemoryService 記憶與喚醒流程."""
    repo = InMemoryMemoryRepository()
    service = MemoryService(repository=repo)

    # 1. 記住偏好
    item1 = service.remember("我喜歡早上喝美式咖啡", memory_type=MemoryType.USER_PREFERENCE, metadata={"source": "chat"})
    assert item1.id is not None
    assert item1.content == "我喜歡早上喝美式咖啡"

    # 2. 依 ID 喚醒
    recalled = service.recall(item1.id)
    assert recalled is not None
    assert recalled.id == item1.id
    assert recalled.content == "我喜歡早上喝美式咖啡"
    assert recalled.metadata.get("source") == "chat"

    # 3. 喚醒不存在的 ID
    assert service.recall("non_existent_id") is None


def test_memory_service_validation() -> None:
    """測試空白記憶內容防護."""
    repo = InMemoryMemoryRepository()
    service = MemoryService(repository=repo)

    with pytest.raises(ValueError, match="記憶內容不得為空白"):
        service.remember("")

    with pytest.raises(ValueError, match="記憶內容不得為空白"):
        service.remember("   ")


def test_memory_service_search_and_filtering() -> None:
    """測試關鍵字搜尋與分類篩選."""
    repo = InMemoryMemoryRepository()
    service = MemoryService(repository=repo)

    service.remember("偏好：每週二開技術分享會", memory_type=MemoryType.USER_PREFERENCE)
    service.remember("事實：專案名稱叫做 M.Ber", memory_type=MemoryType.FACT)
    service.remember("事實：公司伺服器 IP 是 192.168.1.100", memory_type=MemoryType.FACT)
    service.remember("備忘：明天下午要買牛奶", memory_type=MemoryType.GENERAL)

    # 1. 關鍵字搜尋
    results = service.search(query="專案名稱")
    assert len(results) == 1
    assert "M.Ber" in results[0].content

    # 2. 分類篩選
    fact_results = service.search(memory_type=MemoryType.FACT)
    assert len(fact_results) == 2
    for r in fact_results:
        assert r.memory_type == MemoryType.FACT

    # 3. 複合篩選 (分類 + 關鍵字)
    filtered = service.search(query="192.168", memory_type=MemoryType.FACT)
    assert len(filtered) == 1
    assert "192.168.1.100" in filtered[0].content


def test_memory_service_forget() -> None:
    """測試忘記/刪除記憶."""
    repo = InMemoryMemoryRepository()
    service = MemoryService(repository=repo)

    item = service.remember("暫時性備忘：下午三點打電話", memory_type=MemoryType.GENERAL)
    assert service.recall(item.id) is not None

    # 刪除既有記憶
    assert service.forget(item.id) is True
    assert service.recall(item.id) is None

    # 刪除已不存在的記憶
    assert service.forget(item.id) is False
