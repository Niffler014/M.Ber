"""M.Ber Calendar MCP Server (第三方風格行事曆行程伺服器).

【新手教學 / 觀念解析】：
1. 為什麼 Agent 需要獨立的 Calendar MCP Server？
   - 遵從 Protocol First 原則，行程的儲存與 API 邏輯（如 Google Calendar 或本地 SQLite）
     封裝在獨立的 MCP Server 中。
   - LangGraph Agent 只需要知道有 `query_events`、`add_event`、`update_event`、`delete_event` 這 4 個工具，
     不需要知道底層資料庫是 SQLite 還是 Google API。

2. 【如何將「明天下午開會」轉換為精確的 datetime？】
   - 使用者說：「幫我安排明天下午 3 點開會 1 小時」。
   - Agent 從系統提示詞得知當前時間（例如 `2026-08-16 20:55:00`）。
   - Agent 推算出「明天」是 `2026-08-17`，「下午 3 點」是 `15:00:00`，「1小時後結束」是 `16:00:00`。
   - Agent 組合出標準 ISO 8601 時間字串 `2026-08-17T15:00:00`，並傳給 `add_event` 工具！

3. 【防呆設計】：
   - 提供 `parse_flexible_datetime`，容許多種常見日期字串格式（ISO 8601、空格分隔、斜線格式），避免 LLM 因格式微小偏差導致執行崩潰。
"""

import os
import sys
import sqlite3
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any

from mcp.server import MCPServer

# 建立獨立的 Calendar MCP Server 實例
app = MCPServer("mber-calendar-server")

# 資料庫路徑 (儲存於專案 data/calendar.db)
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
DB_DIR = PROJECT_ROOT / "data"
DB_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH = DB_DIR / "calendar.db"


def init_db() -> None:
    """初始化行事曆 SQLite 資料表結構."""
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                start_time TEXT NOT NULL,
                end_time TEXT,
                description TEXT DEFAULT '',
                location TEXT DEFAULT '',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        conn.commit()


# 初始化資料表
init_db()


def parse_flexible_datetime(dt_str: str) -> datetime:
    """強韌的時間格式剖析器 (容錯解析各類常見日期時間字串).

    支援格式：
    1. ISO 8601 (2026-08-17T15:00:00)
    2. 標準空格 (2026-08-17 15:00:00, 2026-08-17 15:00)
    3. 斜線格式 (2026/08/17 15:00:00, 2026/08/17 15:00)
    4. 純日期 (2026-08-17, 2026/08/17)
    """
    cleaned = dt_str.strip().replace("Z", "")
    # 移除可能存在的時區偏移如 +08:00
    if "+" in cleaned:
        cleaned = cleaned.split("+")[0]

    formats = [
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M",
        "%Y/%m/%d %H:%M:%S",
        "%Y/%m/%d %H:%M",
        "%Y-%m-%d",
        "%Y/%m/%d",
    ]

    for fmt in formats:
        try:
            return datetime.strptime(cleaned, fmt)
        except ValueError:
            continue

    # 若所有預設格式皆失敗，嘗試 Python 原生 fromisoformat
    try:
        return datetime.fromisoformat(cleaned)
    except Exception:
        raise ValueError(
            f"無法辨識的時間格式: '{dt_str}'。請使用 ISO 8601 格式，例如 'YYYY-MM-DDTHH:MM:SS'"
        )


@app.tool()
def query_events(
    start_time: Optional[str] = None,
    end_time: Optional[str] = None,
    keyword: Optional[str] = None,
) -> str:
    """查詢行事曆行程 (唯讀操作).

    Args:
        start_time: 查詢起始時間 (ISO 8601 格式，如 '2026-08-17T00:00:00')，若未提供則從當前時間開始
        end_time: 查詢結束時間 (ISO 8601 格式，如 '2026-08-17T23:59:59')，若未提供則預設為起始時間後 7 天
        keyword: 行程標題或內文搜尋關鍵字 (可選)

    Returns:
        符合條件的行程清單格式化字串
    """
    # 預設起始時間為今天開始
    if start_time:
        start_dt = parse_flexible_datetime(start_time)
    else:
        now = datetime.now()
        start_dt = datetime(now.year, now.month, now.day, 0, 0, 0)

    # 預設結束時間為起始時間後 7 天
    if end_time:
        end_dt = parse_flexible_datetime(end_time)
    else:
        end_dt = start_dt + timedelta(days=7)

    start_str = start_dt.strftime("%Y-%m-%d %H:%M:%S")
    end_str = end_dt.strftime("%Y-%m-%d %H:%M:%S")

    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        if keyword:
            cursor.execute(
                """
                SELECT id, title, start_time, end_time, description, location
                FROM events
                WHERE start_time >= ? AND start_time <= ? AND (title LIKE ? OR description LIKE ?)
                ORDER BY start_time ASC
                """,
                (start_str, end_str, f"%{keyword}%", f"%{keyword}%"),
            )
        else:
            cursor.execute(
                """
                SELECT id, title, start_time, end_time, description, location
                FROM events
                WHERE start_time >= ? AND start_time <= ?
                ORDER BY start_time ASC
                """,
                (start_str, end_str),
            )
        rows = cursor.fetchall()

    if not rows:
        return f"[Calendar Events]: 在 {start_str} 至 {end_str} 期間查無符合條件的行程。"

    result_lines = [f"[Calendar Events]: 找到 {len(rows)} 個行程 (區間: {start_str} ~ {end_str})："]
    for row in rows:
        eid, title, s_time, e_time, desc, loc = row
        loc_info = f" (地點: {loc})" if loc else ""
        desc_info = f" - 備註: {desc}" if desc else ""
        end_info = f" ~ {e_time}" if e_time else ""
        result_lines.append(f"• [ID: {eid}] 【{title}】 {s_time}{end_info}{loc_info}{desc_info}")

    return "\n".join(result_lines)


@app.tool()
def add_event(
    title: str,
    start_time: str,
    end_time: Optional[str] = None,
    description: Optional[str] = "",
    location: Optional[str] = "",
) -> str:
    """新增行事曆行程 (寫入修改操作).

    Args:
        title: 行程標題 (例如 '專案週會', '與客戶午餐')
        start_time: 開始時間 (ISO 8601 格式，例如 '2026-08-17T15:00:00')
        end_time: 結束時間 (ISO 8601 格式，例如 '2026-08-17T16:00:00')，若未指定則預設為開始後 1 小時
        description: 行程詳細說明或備註 (可選)
        location: 地點或線上會議連結 (可選)

    Returns:
        新增成功訊息與行程 ID
    """
    start_dt = parse_flexible_datetime(start_time)
    if end_time:
        end_dt = parse_flexible_datetime(end_time)
    else:
        end_dt = start_dt + timedelta(hours=1)

    start_str = start_dt.strftime("%Y-%m-%d %H:%M:%S")
    end_str = end_dt.strftime("%Y-%m-%d %H:%M:%S")

    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO events (title, start_time, end_time, description, location)
            VALUES (?, ?, ?, ?, ?)
            """,
            (title, start_str, end_str, description or "", location or ""),
        )
        conn.commit()
        event_id = cursor.lastrowid

    loc_str = f"，地點：{location}" if location else ""
    return f"[Calendar Events]: 成功新增行程 [ID: {event_id}]「{title}」，時間：{start_str} ~ {end_str}{loc_str}"


@app.tool()
def update_event(
    event_id: int,
    title: Optional[str] = None,
    start_time: Optional[str] = None,
    end_time: Optional[str] = None,
    description: Optional[str] = None,
    location: Optional[str] = None,
) -> str:
    """修改既有的行事曆行程 (修改操作).

    Args:
        event_id: 要修改的行程 ID
        title: 新的行程標題 (若不變更則留空)
        start_time: 新的開始時間 (若不變更則留空)
        end_time: 新的結束時間 (若不變更則留空)
        description: 新的說明備註 (若不變更則留空)
        location: 新的地點 (若不變更則留空)

    Returns:
        修改結果訊息
    """
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id, title, start_time, end_time, description, location FROM events WHERE id = ?", (event_id,))
        row = cursor.fetchone()
        if not row:
            return f"[Calendar Events]: 找不到 ID 為 {event_id} 的行程，無法修改。"

        curr_id, curr_title, curr_start, curr_end, curr_desc, curr_loc = row

        new_title = title if title is not None else curr_title
        new_desc = description if description is not None else curr_desc
        new_loc = location if location is not None else curr_loc

        if start_time is not None:
            new_start = parse_flexible_datetime(start_time).strftime("%Y-%m-%d %H:%M:%S")
        else:
            new_start = curr_start

        if end_time is not None:
            new_end = parse_flexible_datetime(end_time).strftime("%Y-%m-%d %H:%M:%S")
        else:
            new_end = curr_end

        cursor.execute(
            """
            UPDATE events
            SET title = ?, start_time = ?, end_time = ?, description = ?, location = ?
            WHERE id = ?
            """,
            (new_title, new_start, new_end, new_desc, new_loc, event_id),
        )
        conn.commit()

    return f"[Calendar Events]: 成功更新行程 [ID: {event_id}]「{new_title}」，更新後時間：{new_start} ~ {new_end}"


@app.tool()
def delete_event(event_id: int) -> str:
    """刪除指定 ID 的行事曆行程 (刪除高風險操作).

    Args:
        event_id: 要刪除的行程 ID

    Returns:
        刪除結果訊息
    """
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT title FROM events WHERE id = ?", (event_id,))
        row = cursor.fetchone()
        if not row:
            return f"[Calendar Events]: 找不到 ID 為 {event_id} 的行程，無法刪除。"

        title = row[0]
        cursor.execute("DELETE FROM events WHERE id = ?", (event_id,))
        conn.commit()

    return f"[Calendar Events]: 成功刪除行程 [ID: {event_id}]「{title}」。"


if __name__ == "__main__":
    # 以 stdio 協定啟動 Calendar MCP Server
    import asyncio
    asyncio.run(app.run_stdio_async())
