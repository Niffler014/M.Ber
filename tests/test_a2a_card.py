"""Unit Tests for M.Ber Phase 6 - A2A 1.0.0 Domain Models & Agent Card.

驗證項目：
1. AgentCard 與 AgentSkill 模型屬性與預設值
2. TextPart, Part 與 Message 建立與 text_content 提取
3. Task, TaskStatus 與 TaskState 生命週期流轉
4. JSON-RPC 2.0 Request / Response / Error 結構驗證
5. 官方 A2A 1.0 JSON 序列化與無損反序列化
"""

import json
import pytest
from app.a2a.models import (
    AgentCapabilities,
    AgentCard,
    AgentSkill,
    Artifact,
    JSONRPCError,
    JSONRPCRequest,
    JSONRPCResponse,
    Message,
    Task,
    TaskState,
    TaskStatus,
    TextPart,
)


def test_agent_card_instantiation_and_defaults() -> None:
    """測試 AgentCard 建立、預設欄位與型別檢查."""
    card = AgentCard(
        name="M.Ber",
        description="Personal AI Assistant",
        url="https://mber.local/v1/a2a",
    )

    assert card.name == "M.Ber"
    assert card.description == "Personal AI Assistant"
    assert card.url == "https://mber.local/v1/a2a"
    assert card.version == "1.0.0"
    assert card.protocol_version == "1.0.0"
    assert card.capabilities.streaming is False
    assert card.default_input_modes == ["text/plain"]
    assert len(card.skills) == 0


def test_agent_skill_model() -> None:
    """測試 AgentSkill 屬性、範例與標籤."""
    skill = AgentSkill(
        id="schedule_management",
        name="Schedule & Calendar Management",
        description="Manages calendar events and meetings",
        tags=["calendar", "schedule"],
        examples=["幫我預約明天下午3點開會"],
    )

    assert skill.id == "schedule_management"
    assert skill.name == "Schedule & Calendar Management"
    assert "calendar" in skill.tags
    assert len(skill.examples) == 1
    assert skill.input_modes == ["text/plain"]


def test_message_and_text_part() -> None:
    """測試 Message 與 TextPart 之多段組合與純文字輔助方法."""
    msg = Message.from_text("你好，請幫我分析資料", role="user")

    assert msg.role == "user"
    assert len(msg.parts) == 1
    assert isinstance(msg.parts[0], TextPart)
    assert msg.parts[0].text == "你好，請幫我分析資料"
    assert msg.text_content == "你好，請幫我分析資料"


def test_task_lifecycle_and_status() -> None:
    """測試 Task 狀態演進與成果物 Artifact 關聯."""
    task = Task()
    assert task.status.state == TaskState.SUBMITTED
    assert len(task.history) == 0
    assert len(task.artifacts) == 0

    # 模擬進入 WORKING
    task.status.state = TaskState.WORKING
    task.history.append(Message.from_text("請分析 M.Ber 專案結構", role="user"))

    # 模擬完成並產出 Artifact
    artifact = Artifact(
        name="analysis_summary.md",
        description="架構分析報告",
        parts=[TextPart(text="# 分析成果\n專案架構良好。")],
    )
    task.artifacts.append(artifact)
    task.status.state = TaskState.COMPLETED
    task.status.message = Message.from_text("分析任務已完成", role="agent")

    assert task.status.state == TaskState.COMPLETED
    assert len(task.artifacts) == 1
    assert task.artifacts[0].name == "analysis_summary.md"


def test_jsonrpc_envelopes() -> None:
    """測試 JSON-RPC 2.0 請求與回應封包結構."""
    req = JSONRPCRequest(method="SendMessage", params={"message": {"role": "user", "parts": [{"type": "text", "text": "Hello"}]}})
    assert req.jsonrpc == "2.0"
    assert req.method == "SendMessage"
    assert req.id is not None

    # 測試成功回應
    resp_ok = JSONRPCResponse(id=req.id, result={"id": "task-123", "status": {"state": "completed"}})
    assert resp_ok.is_success is True
    assert resp_ok.error is None

    # 測試錯誤回應
    err = JSONRPCError(code=-32601, message="Method not found")
    resp_err = JSONRPCResponse(id=req.id, error=err)
    assert resp_err.is_success is False
    assert resp_err.error.code == -32601


def test_agent_card_json_serialization_roundtrip() -> None:
    """測試 AgentCard 完整 JSON 序列化與反序列化一致性 (Roundtrip)."""
    original = AgentCard(
        name="ResearchAgent",
        description="Web Research Specialist",
        url="https://research.local/a2a",
        skills=[
            AgentSkill(
                id="deep_research",
                name="Deep Research",
                description="Performs in-depth research",
                tags=["research"],
                examples=["Search recent AI agent papers"],
            )
        ],
    )

    json_str = original.model_dump_json()
    parsed = AgentCard.model_validate_json(json_str)

    assert parsed.name == original.name
    assert parsed.url == original.url
    assert len(parsed.skills) == 1
    assert parsed.skills[0].id == "deep_research"
    assert parsed.skills[0].examples == ["Search recent AI agent papers"]


def test_a2a_invalid_part_rejection() -> None:
    """測試 Part 嚴格型別驗證：拒絕非 TextPart 或無效字典之物件 (避免無約束跳脫門)."""
    from pydantic import ValidationError

    # 1. 拒絕未宣告 type 或未知 type 之字典
    with pytest.raises(ValidationError):
        Message(role="user", parts=[{"type": "unsupported_blob", "data": "123"}])  # type: ignore

    # 2. 拒絕缺少必要欄位之字典
    with pytest.raises(ValidationError):
        Message(role="user", parts=[{"type": "text"}])  # 缺少 text 欄位 # type: ignore

    # 3. 拒絕隨機非結構化字串或純數字放入 parts
    with pytest.raises(ValidationError):
        Message(role="user", parts=["plain string not a part"])  # type: ignore
