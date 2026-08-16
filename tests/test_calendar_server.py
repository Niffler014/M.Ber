"""Unit Tests for JARVIS Calendar MCP Server (mcp_server/third_party/calendar_server.py).

驗證項目：
1. 強韌時間剖析器 (parse_flexible_datetime) 多格式解析
2. 新增行程 (add_event)
3. 查詢行程 (query_events) 時間區間與關鍵字搜尋
4. 修改行程 (update_event)
5. 刪除行程 (delete_event)
"""

import pytest
from datetime import datetime
from mcp_server.third_party.calendar_server import (
    parse_flexible_datetime,
    add_event,
    query_events,
    update_event,
    delete_event,
)


def test_parse_flexible_datetime() -> None:
    """測試強韌時間格式剖析器."""
    # 1. ISO 8601
    dt1 = parse_flexible_datetime("2026-08-17T15:00:00")
    assert dt1.year == 2026 and dt1.month == 8 and dt1.day == 17 and dt1.hour == 15

    # 2. 空格分隔
    dt2 = parse_flexible_datetime("2026-08-17 15:30:00")
    assert dt2.minute == 30

    # 3. 斜線格式
    dt3 = parse_flexible_datetime("2026/08/17 09:00")
    assert dt3.hour == 9 and dt3.minute == 0

    # 4. 純日期格式
    dt4 = parse_flexible_datetime("2026-08-18")
    assert dt4.day == 18 and dt4.hour == 0

    # 5. 帶有 Z 或時區
    dt5 = parse_flexible_datetime("2026-08-17T15:00:00Z")
    assert dt5.hour == 15


def test_calendar_crud_flow() -> None:
    """測試行程新增、查詢、修改與刪除完整 CRUD 流程."""
    test_title = "Phase4_團隊週會"
    test_start = "2026-08-20T10:00:00"
    test_end = "2026-08-20T11:30:00"

    # 1. 新增行程 (add_event)
    add_res = add_event(
        title=test_title,
        start_time=test_start,
        end_time=test_end,
        description="討論 Phase 4 與後續上線計畫",
        location="線上 Google Meet",
    )
    assert "[Calendar Events]: 成功新增行程" in add_res
    assert test_title in add_res

    # 2. 查詢行程 (query_events)
    query_res = query_events(
        start_time="2026-08-20T00:00:00",
        end_time="2026-08-20T23:59:59",
        keyword="Phase4",
    )
    assert "[Calendar Events]: 找到" in query_res
    assert test_title in query_res
    assert "Google Meet" in query_res

    # 提取 event_id 進行更新與刪除測試
    import re
    match = re.search(r'\[ID:\s*(\d+)\]', query_res)
    assert match is not None
    event_id = int(match.group(1))

    # 3. 修改行程 (update_event)
    updated_title = "Phase4_團隊週會_已改期"
    update_res = update_event(
        event_id=event_id,
        title=updated_title,
        start_time="2026-08-20T14:00:00",
        end_time="2026-08-20T15:00:00",
    )
    assert "[Calendar Events]: 成功更新行程" in update_res
    assert updated_title in update_res

    # 4. 刪除行程 (delete_event)
    del_res = delete_event(event_id=event_id)
    assert "[Calendar Events]: 成功刪除行程" in del_res
    assert updated_title in del_res
