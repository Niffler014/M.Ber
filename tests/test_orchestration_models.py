"""Tests for M.Ber Orchestration Models & Contracts (調度領域模型與資料契約測試)."""

import json
import pytest
from pydantic import ValidationError
from app.orchestration.models import (
    ExecutionType,
    ExecutionStatus,
    SubTask,
    TaskPlan,
    ExecutionResult,
    AggregatedResult,
)


def test_execution_type_values_and_instance_types():
    """驗證 ExecutionType 枚舉值與實例型別保留 (非純 string 降級)."""
    assert ExecutionType.LOCAL.value == "local"
    assert ExecutionType.MCP.value == "mcp"
    assert ExecutionType.A2A.value == "a2a"

    task = SubTask(
        task_id="t1",
        execution_type=ExecutionType.A2A,
        goal="硬體推薦",
    )
    assert task.execution_type == ExecutionType.A2A
    assert task.execution_type is ExecutionType.A2A
    assert isinstance(task.execution_type, ExecutionType)


def test_execution_status_values_and_instance_types():
    """驗證 ExecutionStatus 枚舉值與實例型別保留."""
    assert ExecutionStatus.PENDING.value == "pending"
    assert ExecutionStatus.RUNNING.value == "running"
    assert ExecutionStatus.SUCCESS.value == "success"
    assert ExecutionStatus.FAILED.value == "failed"
    assert ExecutionStatus.SKIPPED.value == "skipped"
    assert ExecutionStatus.TIMEOUT.value == "timeout"

    res = ExecutionResult(
        task_id="t1",
        execution_type=ExecutionType.LOCAL,
        status=ExecutionStatus.SUCCESS,
    )
    assert res.status == ExecutionStatus.SUCCESS
    assert res.status is ExecutionStatus.SUCCESS
    assert isinstance(res.status, ExecutionStatus)


def test_create_single_subtask():
    """驗證建立單一 SubTask 與預設欄位."""
    task = SubTask(
        task_id="task_1",
        execution_type=ExecutionType.A2A,
        goal="取得 40000 元遊戲電腦配置",
        target="pc_recommendation",
        parameters={"budget": 40000},
    )
    assert task.task_id == "task_1"
    assert task.execution_type == ExecutionType.A2A
    assert task.goal == "取得 40000 元遊戲電腦配置"
    assert task.target == "pc_recommendation"
    assert task.parameters == {"budget": 40000}
    assert task.depends_on == []


def test_subtask_rejects_empty_task_id():
    """驗證 SubTask 拒絕空字串或純空白 task_id."""
    with pytest.raises(ValidationError) as exc_info:
        SubTask(
            task_id="",
            execution_type=ExecutionType.LOCAL,
            goal="空任務",
        )
    assert "task_id" in str(exc_info.value)

    with pytest.raises(ValidationError) as exc_info2:
        SubTask(
            task_id="   ",
            execution_type=ExecutionType.LOCAL,
            goal="空白任務",
        )
    assert "task_id" in str(exc_info2.value)


def test_task_plan_rejects_empty_identity():
    """驗證 TaskPlan 拒絕空字串或純空白之 plan_id 與 user_goal."""
    with pytest.raises(ValidationError) as exc1:
        TaskPlan(plan_id="", user_goal="測試", tasks=[])
    assert "plan_id" in str(exc1.value)

    with pytest.raises(ValidationError) as exc2:
        TaskPlan(plan_id="   ", user_goal="測試", tasks=[])
    assert "plan_id" in str(exc2.value)

    with pytest.raises(ValidationError) as exc3:
        TaskPlan(user_goal="", tasks=[])
    assert "user_goal" in str(exc3.value)

    with pytest.raises(ValidationError) as exc4:
        TaskPlan(user_goal="   ", tasks=[])
    assert "user_goal" in str(exc4.value)


def test_create_task_plan():
    """驗證建立正常之 TaskPlan 與任務清單關聯."""
    t1 = SubTask(
        task_id="t1",
        execution_type=ExecutionType.A2A,
        goal="推薦電腦配置",
        target="PCforge",
    )
    t2 = SubTask(
        task_id="t2",
        execution_type=ExecutionType.LOCAL,
        goal="儲存配置至記憶庫",
        target="memory_service",
        depends_on=["t1"],
    )
    plan = TaskPlan(
        plan_id="plan_1",
        user_goal="幫我配電腦並儲存",
        tasks=[t1, t2],
    )
    assert plan.plan_id == "plan_1"
    assert len(plan.tasks) == 2
    assert plan.tasks[1].depends_on == ["t1"]


def test_task_plan_rejects_duplicate_task_ids():
    """驗證 TaskPlan 拒絕重複的 task_id."""
    t1 = SubTask(task_id="dup_id", execution_type=ExecutionType.LOCAL, goal="任務 1")
    t2 = SubTask(task_id="dup_id", execution_type=ExecutionType.MCP, goal="任務 2")

    with pytest.raises(ValidationError) as exc_info:
        TaskPlan(user_goal="重複測試", tasks=[t1, t2])
    assert "重複的 task_id" in str(exc_info.value)


def test_task_plan_rejects_self_dependency():
    """驗證 TaskPlan 拒絕自我依賴 (Self-dependency)."""
    t1 = SubTask(
        task_id="task_self",
        execution_type=ExecutionType.A2A,
        goal="自我依賴任務",
        depends_on=["task_self"],
    )

    with pytest.raises(ValidationError) as exc_info:
        TaskPlan(user_goal="自依賴測試", tasks=[t1])
    assert "Self-dependency" in str(exc_info.value) or "不可依賴自身" in str(exc_info.value)


def test_task_plan_rejects_missing_dependency():
    """驗證 TaskPlan 拒絕依賴不存在之任務 ID."""
    t1 = SubTask(
        task_id="task_1",
        execution_type=ExecutionType.LOCAL,
        goal="依賴不存在目標",
        depends_on=["non_existent_task"],
    )

    with pytest.raises(ValidationError) as exc_info:
        TaskPlan(user_goal="遺失依賴測試", tasks=[t1])
    assert "依賴不存在的任務" in str(exc_info.value)


def test_task_plan_rejects_dependency_cycle():
    """驗證 TaskPlan 透過 Cycle Detection 拒絕循環依賴 (task_a <-> task_b)."""
    t1 = SubTask(
        task_id="task_a",
        execution_type=ExecutionType.A2A,
        goal="任務 A",
        depends_on=["task_b"],
    )
    t2 = SubTask(
        task_id="task_b",
        execution_type=ExecutionType.LOCAL,
        goal="任務 B",
        depends_on=["task_a"],
    )

    with pytest.raises(ValidationError) as exc_info:
        TaskPlan(user_goal="循環依賴測試", tasks=[t1, t2])
    assert "循環依賴" in str(exc_info.value) or "Dependency cycle detected" in str(exc_info.value)


def test_execution_result_success():
    """驗證 ExecutionResult 成功實體建構."""
    res = ExecutionResult(
        task_id="task_1",
        execution_type=ExecutionType.A2A,
        status=ExecutionStatus.SUCCESS,
        source="a2a:PCforge",
        result="CPU: Ryzen 5, GPU: RTX 4060",
        metadata={"duration_ms": 150, "remote_task_id": "pc_task_123"},
    )
    assert res.task_id == "task_1"
    assert res.execution_type == ExecutionType.A2A
    assert res.status == ExecutionStatus.SUCCESS
    assert res.source == "a2a:PCforge"
    assert res.result == "CPU: Ryzen 5, GPU: RTX 4060"
    assert res.error is None
    assert res.metadata["duration_ms"] == 150


def test_execution_result_failure():
    """驗證 ExecutionResult 失敗實體建構."""
    res = ExecutionResult(
        task_id="task_2",
        execution_type=ExecutionType.MCP,
        status=ExecutionStatus.FAILED,
        source="mcp:calendar_server",
        error="Server connection timeout",
        metadata={"tool_name": "add_event"},
    )
    assert res.task_id == "task_2"
    assert res.execution_type == ExecutionType.MCP
    assert res.status == ExecutionStatus.FAILED
    assert res.result is None
    assert res.error == "Server connection timeout"
    assert res.metadata["tool_name"] == "add_event"


def test_aggregated_result_results_is_source_of_truth():
    """驗證 AggregatedResult 的統計欄位完全由 results 動態計算，無矛盾可能."""
    r1 = ExecutionResult(
        task_id="t1",
        execution_type=ExecutionType.A2A,
        status=ExecutionStatus.SUCCESS,
        source="a2a:PCforge",
        result="PC build ready",
    )
    r2 = ExecutionResult(
        task_id="t2",
        execution_type=ExecutionType.LOCAL,
        status=ExecutionStatus.FAILED,
        source="local:memory",
        error="SQLite lock error",
    )
    r3 = ExecutionResult(
        task_id="t3",
        execution_type=ExecutionType.LOCAL,
        status=ExecutionStatus.SKIPPED,
    )

    agg = AggregatedResult(plan_id="plan_xyz", results=[r1, r2, r3])

    # 驗證 computed fields 正確衍生
    assert agg.plan_id == "plan_xyz"
    assert agg.success_count == 1
    assert agg.failure_count == 1
    assert agg.skipped_count == 1
    assert agg.has_partial_failure is True

    # 序列化時包含 computed fields
    dumped = agg.model_dump(mode="json")
    assert dumped["success_count"] == 1
    assert dumped["failure_count"] == 1
    assert dumped["skipped_count"] == 1
    assert dumped["has_partial_failure"] is True
