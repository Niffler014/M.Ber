"""JARVIS SQLite Memory Repository Implementation.

【新手教學 / 觀念解析】：
1. 為什麼把 SQLite 限制在 `sqlite.py` 裡？
   - 所有的 SQL 語句（如 `SELECT`, `INSERT`, `DELETE`）與資料庫連線只存在於這個檔案中。
   - 外部的 Agent 和 Service 永遠不會看到 SQL 語法，也不需要擔心 SQL Injection（透過參數化查詢防護）。
   - 如果未來想切換成 PostgreSQL 或雲端資料庫，只要寫一個新的 `PostgresMemoryRepository`，上層程式碼一行都不用改！
"""

import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from memory.models import MemoryItem, MemoryType
from memory.repository import MemoryRepository


class SQLiteMemoryRepository(MemoryRepository):
    """基於 SQLite 的持久化記憶倉儲實作."""

    def __init__(self, db_path: Optional[Union[str, Path]] = None) -> None:
        """初始化 SQLite 記憶倉儲.

        Args:
            db_path: 資料庫檔案路徑 (預設為專案目錄下 data/memory.db)
        """
        if db_path is None:
            project_root = Path(__file__).resolve().parent.parent
            data_dir = project_root / "data"
            data_dir.mkdir(parents=True, exist_ok=True)
            db_path = data_dir / "memory.db"

        self.db_path = Path(db_path)
        self._init_table()

    def _get_connection(self) -> sqlite3.Connection:
        """取得資料庫連線."""
        return sqlite3.connect(self.db_path)

    def _init_table(self) -> None:
        """初始化 memories 資料表結構."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS memories (
                    id TEXT PRIMARY KEY,
                    content TEXT NOT NULL,
                    memory_type TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    metadata_json TEXT DEFAULT '{}'
                )
                """
            )
            # 建立索引以加速記憶類型與內容檢索
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_memories_type ON memories(memory_type)"
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_memories_created_at ON memories(created_at)"
            )
            conn.commit()

    def _row_to_item(self, row: tuple) -> MemoryItem:
        """將 SQLite 資料列轉換為 MemoryItem 領域模型."""
        mem_id, content, mem_type, created_at_str, meta_json = row
        try:
            created_at = datetime.fromisoformat(created_at_str)
        except Exception:
            created_at = datetime.now()

        try:
            metadata = json.loads(meta_json) if meta_json else {}
        except Exception:
            metadata = {}

        return MemoryItem(
            id=mem_id,
            content=content,
            memory_type=MemoryType(mem_type) if mem_type in [t.value for t in MemoryType] else MemoryType.GENERAL,
            created_at=created_at,
            metadata=metadata,
        )

    def add(self, item: MemoryItem) -> MemoryItem:
        """新增或覆蓋一筆記憶至 SQLite 資料庫."""
        type_str = item.memory_type.value if hasattr(item.memory_type, "value") else str(item.memory_type)
        created_str = item.created_at.isoformat()
        meta_str = json.dumps(item.metadata, ensure_ascii=False)

        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT OR REPLACE INTO memories (id, content, memory_type, created_at, metadata_json)
                VALUES (?, ?, ?, ?, ?)
                """,
                (item.id, item.content, type_str, created_str, meta_str),
            )
            conn.commit()
        return item

    def get(self, memory_id: str) -> Optional[MemoryItem]:
        """依據 ID 查詢單一記憶."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT id, content, memory_type, created_at, metadata_json FROM memories WHERE id = ?",
                (memory_id,),
            )
            row = cursor.fetchone()
            if not row:
                return None
            return self._row_to_item(row)

    def search(
        self,
        query: Optional[str] = None,
        memory_type: Optional[MemoryType] = None,
        limit: int = 10,
    ) -> List[MemoryItem]:
        """搜尋符合條件的記憶清單 (支援類型篩選與關鍵字模糊比對)."""
        conditions: List[str] = []
        params: List[Any] = []

        if memory_type is not None:
            type_str = memory_type.value if hasattr(memory_type, "value") else str(memory_type)
            conditions.append("memory_type = ?")
            params.append(type_str)

        if query is not None and query.strip():
            conditions.append("content LIKE ?")
            params.append(f"%{query.strip()}%")

        where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        sql = f"""
            SELECT id, content, memory_type, created_at, metadata_json
            FROM memories
            {where_clause}
            ORDER BY created_at DESC
            LIMIT ?
        """
        params.append(limit)

        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(sql, params)
            rows = cursor.fetchall()
            return [self._row_to_item(r) for r in rows]

    def delete(self, memory_id: str) -> bool:
        """依據 ID 刪除記憶."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM memories WHERE id = ?", (memory_id,))
            conn.commit()
            return cursor.rowcount > 0

    def clear(self) -> None:
        """清空 memories 資料表."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM memories")
            conn.commit()
