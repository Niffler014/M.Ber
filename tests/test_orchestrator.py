"""Tests for M.Ber Orchestrator (Plan Execution & Dependency Resolution)."""

import socket
import pytest

from app.orchestration.models import (
    ExecutionContext,
    ExecutionResult,
    ExecutionStatus,
    ExecutionType,
    SubTask,
    TaskPlan,
)
from app.orchestration.executors import A2AExecutor, LocalExecutor
from app.orchestration.router import Router
from app.orchestration.orchestrator import Orchestrator
from app.a2a.discovery import AgentDiscoveryService
from app.a2a.models import AgentCard, AgentSkill


@pytest.fixture
def mock_agent_card() -> AgentCard:
    """提供標準 Mock AgentCard."""
    return AgentCard(
        name="PCforgeMock",
        description="電腦硬體配置專家",
        url="http://mock-pcforge.local/rpc",
        skills=[
            AgentSkill(
                id="pc_recommendation",
                name="電腦配置推薦",
                description="提供組裝清單",
                tags=["電腦", "pc", "硬體"],
            )
        ],
    )


@pytest.fixture
def mock_discovery(mock_agent_card: AgentCard) -> AgentDiscoveryService:
    """提供已註冊 PCforgeMock 的 Discovery 服務實例."""
    discovery = AgentDiscoveryService(config_path="non_existent_config.json")
    discovery.register_agent(mock_agent_card)
    return discovery


def test_execute_plan_single_task():
    """驗證 execute_plan 正確執行單一任務計畫."""
    local_exec = LocalExecutor(handlers={"echo": lambda t: "Hello Plan"})
    orchestrator = Orchestrator(router=Router(local_executor=local_exec))

    t1 = SubTask(task_id="t1", execution_type=ExecutionType.LOCAL, target="echo", goal="打招呼")
    plan = TaskPlan(user_goal="測試單一任務計畫", tasks=[t1])

    results = orchestrator.execute_plan(plan)
    assert len(results) == 1
    assert results[0].task_id == "t1"
    assert results[0].status == ExecutionStatus.SUCCESS
    assert results[0].result == "Hello Plan"


def test_execute_plan_sequential_success():
    """驗證 execute_plan 循序執行兩步驟任務且皆成功."""
    executed_order = []

    def handler_1(task: SubTask):
        executed_order.append("step_1")
        return "Result 1"

    def handler_2(task: SubTask):
        executed_order.append("step_2")
        return "Result 2"

    local_exec = LocalExecutor(handlers={"h1": handler_1, "h2": handler_2})
    orchestrator = Orchestrator(router=Router(local_executor=local_exec))

    t1 = SubTask(task_id="t1", execution_type=ExecutionType.LOCAL, target="h1", goal="第一步")
    t2 = SubTask(task_id="t2", execution_type=ExecutionType.LOCAL, target="h2", goal="第二步", depends_on=["t1"])
    plan = TaskPlan(user_goal="循序執行", tasks=[t1, t2])

    results = orchestrator.execute_plan(plan)
    assert len(results) == 2
    assert results[0].status == ExecutionStatus.SUCCESS
    assert results[1].status == ExecutionStatus.SUCCESS
    assert executed_order == ["step_1", "step_2"]


def test_execute_plan_dependency_result_propagation():
    """驗證前置依賴任務之產出結果透過 ExecutionContext 正確傳遞給後續任務."""
    def generate_value(task: SubTask):
        return {"data": "special_secret_value"}

    def consume_value(task: SubTask, context: ExecutionContext):
        # 從 context 提取依賴任務的成果
        prev_result = context.get_result("t_gen")
        return f"Consumed: {prev_result['data']}"

    local_exec = LocalExecutor(handlers={"gen": generate_value, "consume": consume_value})
    orchestrator = Orchestrator(router=Router(local_executor=local_exec))

    t1 = SubTask(task_id="t_gen", execution_type=ExecutionType.LOCAL, target="gen", goal="產出資料")
    t2 = SubTask(task_id="t_con", execution_type=ExecutionType.LOCAL, target="consume", goal="使用前置資料", depends_on=["t_gen"])
    plan = TaskPlan(user_goal="成果傳遞測試", tasks=[t1, t2])

    results = orchestrator.execute_plan(plan)
    assert len(results) == 2
    assert results[0].status == ExecutionStatus.SUCCESS
    assert results[1].status == ExecutionStatus.SUCCESS
    assert results[1].result == "Consumed: special_secret_value"


def test_execute_plan_failed_dependency_skips_child():
    """驗證前置任務 FAILED 時，後續相依任務直接標記為 SKIPPED 且不執行."""
    child_called = False

    def failing_handler(task: SubTask):
        raise RuntimeError("Database locked")

    def child_handler(task: SubTask):
        nonlocal child_called
        child_called = True
        return "Should not be executed"

    local_exec = LocalExecutor(handlers={"fail": failing_handler, "child": child_handler})
    orchestrator = Orchestrator(router=Router(local_executor=local_exec))

    t1 = SubTask(task_id="t_fail", execution_type=ExecutionType.LOCAL, target="fail", goal="會失敗的任務")
    t2 = SubTask(task_id="t_child", execution_type=ExecutionType.LOCAL, target="child", goal="後續任務", depends_on=["t_fail"])
    plan = TaskPlan(user_goal="依賴失敗測試", tasks=[t1, t2])

    results = orchestrator.execute_plan(plan)
    assert len(results) == 2
    assert results[0].status == ExecutionStatus.FAILED
    assert results[1].status == ExecutionStatus.SKIPPED
    assert "Dependency failed: t_fail" in results[1].error
    assert child_called is False


def test_execute_plan_timeout_dependency_skips_child(mock_discovery: AgentDiscoveryService):
    """驗證前置任務 TIMEOUT 時，後續相依任務標記為 SKIPPED."""
    def mock_timeout_transport(url: str, payload: dict) -> dict:
        raise socket.timeout("Peer agent timed out")

    a2a_exec = A2AExecutor(discovery_service=mock_discovery, rpc_transport=mock_timeout_transport)
    local_exec = LocalExecutor(handlers={"store": lambda t: "stored"})
    router = Router(local_executor=local_exec, a2a_executor=a2a_exec)
    orchestrator = Orchestrator(router=router)

    t1 = SubTask(task_id="t_a2a_to", execution_type=ExecutionType.A2A, target="pc_recommendation", goal="推薦電腦")
    t2 = SubTask(task_id="t_save", execution_type=ExecutionType.LOCAL, target="store", goal="儲存", depends_on=["t_a2a_to"])
    plan = TaskPlan(user_goal="超時依賴測試", tasks=[t1, t2])

    results = orchestrator.execute_plan(plan)
    assert len(results) == 2
    assert results[0].status == ExecutionStatus.TIMEOUT
    assert results[1].status == ExecutionStatus.SKIPPED


def test_execute_plan_multiple_dependencies_all_success():
    """驗證任務依賴多個前置任務且全部成功時順利執行."""
    local_exec = LocalExecutor(
        handlers={
            "step_a": lambda t: "Alpha",
            "step_b": lambda t: "Beta",
            "step_c": lambda t, ctx: f"Combined: {ctx.get_result('ta')} & {ctx.get_result('tb')}",
        }
    )
    orchestrator = Orchestrator(router=Router(local_executor=local_exec))

    ta = SubTask(task_id="ta", execution_type=ExecutionType.LOCAL, target="step_a", goal="任務 A")
    tb = SubTask(task_id="tb", execution_type=ExecutionType.LOCAL, target="step_b", goal="任務 B")
    tc = SubTask(task_id="tc", execution_type=ExecutionType.LOCAL, target="step_c", goal="任務 C", depends_on=["ta", "tb"])
    plan = TaskPlan(user_goal="多重相依測試", tasks=[ta, tb, tc])

    results = orchestrator.execute_plan(plan)
    assert len(results) == 3
    assert results[0].status == ExecutionStatus.SUCCESS
    assert results[1].status == ExecutionStatus.SUCCESS
    assert results[2].status == ExecutionStatus.SUCCESS
    assert results[2].result == "Combined: Alpha & Beta"


def test_execute_plan_one_failed_dependency_skips_task():
    """驗證多前置依賴中只要有任一個失敗，子任務即被標記為 SKIPPED."""
    local_exec = LocalExecutor(
        handlers={
            "ok": lambda t: "Good",
            "fail": lambda t: 1 / 0,
            "child": lambda t: "Not executed",
        }
    )
    orchestrator = Orchestrator(router=Router(local_executor=local_exec))

    t1 = SubTask(task_id="t1", execution_type=ExecutionType.LOCAL, target="ok", goal="成功任務")
    t2 = SubTask(task_id="t2", execution_type=ExecutionType.LOCAL, target="fail", goal="失敗任務")
    t3 = SubTask(task_id="t3", execution_type=ExecutionType.LOCAL, target="child", goal="子任務", depends_on=["t1", "t2"])
    plan = TaskPlan(user_goal="多重依賴部分失敗測試", tasks=[t1, t2, t3])

    results = orchestrator.execute_plan(plan)
    assert results[0].status == ExecutionStatus.SUCCESS
    assert results[1].status == ExecutionStatus.FAILED
    assert results[2].status == ExecutionStatus.SKIPPED
    assert "t2" in results[2].error


def test_skipped_task_does_not_call_router():
    """驗證被 SKIPPED 的任務絕對不會進入 Router."""
    router_called = False

    class TrackingRouter(Router):
        def route(self, task, context=None):
            nonlocal router_called
            if task.task_id == "t_child":
                router_called = True
            return super().route(task, context=context)

    local_exec = LocalExecutor(handlers={"fail": lambda t: (_ for _ in ()).throw(ValueError("Error"))})
    router = TrackingRouter(local_executor=local_exec)
    orchestrator = Orchestrator(router=router)

    t1 = SubTask(task_id="t1", execution_type=ExecutionType.LOCAL, target="fail", goal="失敗")
    t2 = SubTask(task_id="t_child", execution_type=ExecutionType.LOCAL, target="child", goal="子任務", depends_on=["t1"])
    plan = TaskPlan(user_goal="跳過不調用 Router 測試", tasks=[t1, t2])

    orchestrator.execute_plan(plan)
    assert router_called is False


def test_e2e_style_a2a_to_local_result_propagation(mock_discovery: AgentDiscoveryService):
    """驗證示範情境：Task 1 (A2A PC Recommendation) -> Task 2 (LOCAL Fake Memory Store)."""
    # 模擬 PCforge 回傳菜單
    def mock_pcforge_rpc(url: str, payload: dict) -> dict:
        return {
            "jsonrpc": "2.0",
            "id": payload.get("id", "1"),
            "result": {
                "id": "pc_task_40000",
                "status": {
                    "state": "completed",
                    "message": {
                        "role": "agent",
                        "parts": [{"type": "text", "text": "【40000元遊戲菜單】：CPU: Ryzen 5 7500F, GPU: RTX 4060 Ti, RAM: 32G"}],
                    },
                },
                "artifacts": [],
            },
        }

    stored_data = None

    def fake_memory_store_handler(task: SubTask, context: ExecutionContext):
        nonlocal stored_data
        # 從 context 取得 A2A PCforge 的執行成果
        pc_build = context.get_result("task_pc_build")
        stored_data = {"saved_content": pc_build, "tags": ["pc_config", "gaming"]}
        return "電腦配置已成功記錄至本地記憶體。"

    a2a_exec = A2AExecutor(discovery_service=mock_discovery, rpc_transport=mock_pcforge_rpc)
    local_exec = LocalExecutor(handlers={"fake_memory_store": fake_memory_store_handler})
    router = Router(local_executor=local_exec, a2a_executor=a2a_exec)
    orchestrator = Orchestrator(router=router)

    # 建立兩步驟計畫 (Task 1: A2A, Task 2: LOCAL)
    t1 = SubTask(
        task_id="task_pc_build",
        execution_type=ExecutionType.A2A,
        target="pc_recommendation",
        goal="幫我配一台 40000 元遊戲電腦",
    )
    t2 = SubTask(
        task_id="task_save_config",
        execution_type=ExecutionType.LOCAL,
        target="fake_memory_store",
        goal="儲存電腦配置",
        depends_on=["task_pc_build"],
    )
    plan = TaskPlan(user_goal="配電腦並儲存", tasks=[t1, t2])

    results = orchestrator.execute_plan(plan)

    # 驗證 Task 1 成功
    assert results[0].task_id == "task_pc_build"
    assert results[0].status == ExecutionStatus.SUCCESS
    assert "RTX 4060 Ti" in results[0].result

    # 驗證 Task 2 成功且完整拿到 Task 1 的菜單資料
    assert results[1].task_id == "task_save_config"
    assert results[1].status == ExecutionStatus.SUCCESS
    assert "已成功記錄" in results[1].result

    # 驗證 Handler 內部確實拿到產出
    assert stored_data is not None
    assert "Ryzen 5 7500F" in stored_data["saved_content"]
