"""第三方風格 SQLite 本地筆記 MCP 伺服器 (SQLite Notes MCP Server).

【新手教學 / 觀念解析】：
1. 這是什麼？
   - 這是一個獨立運行的第三方程式，專門負責管理 SQLite 本地資料庫。
   - 它展示了如何將任何既有的 Python 函式庫（如 SQLite、檔案操作、API）包裝成標準的 MCP Server。

2. 提供的工具 (Tools)：
   - `read_notes(keyword)`: 搜尋或列出筆記（唯讀操作 READ_ONLY）。
   - `add_note(title, content)`: 新增一筆新筆記（修改操作 WRITE / MUTATION）。
"""

import sqlite3
from pathlib import Path
from datetime import datetime
import anyio
from mcp.server import MCPServer

# 建立獨立的 SQLite MCP 伺服器
app = MCPServer("jarvis-sqlite-server")

# 本地 SQLite 資料庫路徑 (儲存於專案目錄下的 notes.db)
DB_PATH = Path(__file__).resolve().parent.parent.parent / "notes.db"


def init_db() -> None:
    """初始化 SQLite 資料表結構."""
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS notes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                content TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )
        conn.commit()


# 模組載入時自動初始化資料庫
init_db()


@app.tool()
def read_notes(keyword: str = "") -> str:
    """讀取或搜尋本地 SQLite 資料庫中的筆記 (READ_ONLY).

    Args:
        keyword: 搜尋關鍵字（若留空則列出所有筆記）
    """
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        if keyword:
            cursor.execute(
                "SELECT id, title, content, created_at FROM notes WHERE title LIKE ? OR content LIKE ? ORDER BY id DESC",
                (f"%{keyword}%", f"%{keyword}%"),
            )
        else:
            cursor.execute("SELECT id, title, content, created_at FROM notes ORDER BY id DESC LIMIT 10")
        rows = cursor.fetchall()

    if not rows:
        return "[SQLite Notes]: 目前資料庫中沒有找到相關筆記。"

    result_lines = [f"[SQLite Notes]: 共找到 {len(rows)} 則筆記："]
    for row in rows:
        note_id, title, content, created_at = row
        result_lines.append(f"  - [ID: {note_id}] 《{title}》: {content} (建立時間: {created_at})")

    return "\n".join(result_lines)


@app.tool()
def add_note(title: str, content: str) -> str:
    """在本地 SQLite 資料庫中新增一則筆記 (WRITE / MUTATION).

    Args:
        title: 筆記標題
        content: 筆記詳細內容
    """
    created_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO notes (title, content, created_at) VALUES (?, ?, ?)",
            (title, content, created_at),
        )
        conn.commit()
        note_id = cursor.lastrowid

    return f"[SQLite Notes]: 成功新增筆記 [ID: {note_id}] 《{title}》 (建立時間: {created_at})。"


def run_server() -> None:
    """以 stdio 模式啟動 SQLite MCP Server."""
    anyio.run(app.run_stdio_async)


if __name__ == "__main__":
    run_server()
