"""M.Ber Minimal Orchestrator (最小調度中樞模組).

【新手教學 / 觀念解析】：
1. 什麼是 Orchestrator（調度中樞）？
   - Orchestrator 是整個多代理人與多工具架構的總指揮官。
   - 負責接收 `TaskPlan`（或單一 `SubTask`），按照相依性拓撲結構循序執行，
     並在任務間傳遞成果（Dependency Result Propagation），產出最終的執行成果清單。
   - 它遵循高內聚、低耦合原則（High Cohesion, Low Coupling），不自行處理底層通訊與協定細節，
     避免成為肥大的上帝物件（God Object）。

2. 相依性執行語意（Sequential Dependency Semantics）：
   - 若任務 B 依賴任務 A（`depends_on = [task_a]`）：
     ① 任務 A 狀態為 SUCCESS ➔ 任務 B 正常執行，並透過 `ExecutionContext` 獲得任務 A 的產出。
     ② 任務 A 狀態為 FAILED / TIMEOUT / SKIPPED ➔ 任務 B 直接被標記為 SKIPPED，不調用 Router。
"""

import logging
import time
from typing import Dict, List, Optional

from app.orchestration.events import (
    OrchestrationEvent,
    OrchestrationEventType,
    TraceSink,
)
from app.orchestration.models import (
    AggregatedResult,
    ExecutionContext,
    ExecutionResult,
    ExecutionStatus,
    SubTask,
    TaskPlan,
)
from app.orchestration.router import Router
from app.orchestration.aggregator import ResultAggregator

logger = logging.getLogger("mber.orchestration")


class Orchestrator:
    """任務調度中樞 (Multi-Agent & Tool Orchestrator)."""

    def __init__(
        self,
        router: Optional[Router] = None,
        aggregator: Optional[ResultAggregator] = None,
    ) -> None:
        """初始化 Orchestrator.

        Args:
            router: 任務路由器實例 (若為 None 則使用預設 Router)
            aggregator: 結果彙整器實例 (若為 None 則使用預設 ResultAggregator)
        """
        self.router = router or Router()
        self.aggregator = aggregator or ResultAggregator()

    def execute_task(self, task: SubTask, context: Optional[ExecutionContext] = None) -> ExecutionResult:
        """執行單一子任務並回傳執行成果.

        Args:
            task: 待執行之 SubTask 實體
            context: 運行期上下文 (包含前置依賴產出)

        Returns:
            標準化 ExecutionResult 物件
        """
        logger.info(f"[Orchestrator] Executing task: {task.task_id} (type: {task.execution_type.value})")

        result = self.router.route(task, context=context)

        logger.info(f"[Orchestrator] {task.task_id} → {result.status.value.upper()}")
        return result

    def execute_plan(
        self,
        plan: TaskPlan,
        event_sink: Optional[TraceSink] = None,
    ) -> List[ExecutionResult]:
        """按照依賴關係循序調度執行整個 TaskPlan (並選擇性向 event_sink 推播事件).

        Args:
            plan: 待執行之 TaskPlan 計畫實體
            event_sink: 執行軌跡事件接收器 (可選)

        Returns:
            依原計畫順序排列之 List[ExecutionResult]
        """
        logger.info(f"[Orchestrator] Executing plan: {plan.plan_id} ({len(plan.tasks)} tasks)")

        results_by_task_id: Dict[str, ExecutionResult] = {}
        pending_tasks: List[SubTask] = list(plan.tasks)

        while pending_tasks:
            # 尋找所有前置依賴皆已處理完成的候選子任務
            ready_task: Optional[SubTask] = None
            for candidate in pending_tasks:
                if all(dep in results_by_task_id for dep in candidate.depends_on):
                    ready_task = candidate
                    break

            # 若無就緒任務 (防禦性死鎖保護)
            if ready_task is None:
                logger.error("[Orchestrator] Detected unresolvable task dependency deadlock")
                for remaining in pending_tasks:
                    deadlock_res = ExecutionResult(
                        task_id=remaining.task_id,
                        execution_type=remaining.execution_type,
                        status=ExecutionStatus.SKIPPED,
                        source=None,
                        result=None,
                        error="Unresolvable dependency deadlock",
                    )
                    results_by_task_id[remaining.task_id] = deadlock_res
                    if event_sink:
                        event_sink.emit(
                            OrchestrationEvent(
                                event_type=OrchestrationEventType.TASK_SKIPPED,
                                plan_id=plan.plan_id,
                                task_id=remaining.task_id,
                                execution_type=remaining.execution_type,
                                target=remaining.target,
                                status=ExecutionStatus.SKIPPED.value,
                                message="Deadlock: unresolvable dependencies",
                            )
                        )
                break

            pending_tasks.remove(ready_task)

            # 檢查所有前置依賴是否皆為 SUCCESS
            failed_deps = [
                dep
                for dep in ready_task.depends_on
                if results_by_task_id[dep].status != ExecutionStatus.SUCCESS
            ]

            if failed_deps:
                # 任一前置依賴失敗 ➔ 直接標記為 SKIPPED，不調用 Router
                err_msg = f"Dependency failed: {', '.join(failed_deps)}"
                logger.warning(
                    f"[Orchestrator] {ready_task.task_id} skipped due to failed dependency: {', '.join(failed_deps)}"
                )
                res = ExecutionResult(
                    task_id=ready_task.task_id,
                    execution_type=ready_task.execution_type,
                    status=ExecutionStatus.SKIPPED,
                    source=None,
                    result=None,
                    error=err_msg,
                    metadata={"failed_dependencies": failed_deps},
                )
                results_by_task_id[ready_task.task_id] = res

                # 發送 TASK_SKIPPED 觀察事件
                if event_sink:
                    event_sink.emit(
                        OrchestrationEvent(
                            event_type=OrchestrationEventType.TASK_SKIPPED,
                            plan_id=plan.plan_id,
                            task_id=ready_task.task_id,
                            execution_type=ready_task.execution_type,
                            target=ready_task.target,
                            status=ExecutionStatus.SKIPPED.value,
                            message=f"Task [{ready_task.task_id}] skipped: {err_msg}",
                            metadata={"failed_dependencies": failed_deps},
                        )
                    )
            else:
                # 前置依賴皆圓滿成功 ➔ 建構 ExecutionContext 並執行任務
                if ready_task.depends_on:
                    logger.info(f"[Orchestrator] Dependencies satisfied for {ready_task.task_id}")

                context = ExecutionContext(
                    dependency_results={
                        dep: results_by_task_id[dep] for dep in ready_task.depends_on
                    }
                )

                # 發送 TASK_STARTED 事件
                if event_sink:
                    event_sink.emit(
                        OrchestrationEvent(
                            event_type=OrchestrationEventType.TASK_STARTED,
                            plan_id=plan.plan_id,
                            task_id=ready_task.task_id,
                            execution_type=ready_task.execution_type,
                            target=ready_task.target,
                            status=ExecutionStatus.RUNNING.value,
                            message=f"Starting {ready_task.execution_type.value} task [{ready_task.task_id}]: {ready_task.goal}",
                        )
                    )

                # 計時與調用 Router
                t_start = time.perf_counter()
                res = self.execute_task(ready_task, context=context)
                duration_ms = round((time.perf_counter() - t_start) * 1000.0, 2)
                results_by_task_id[ready_task.task_id] = res

                # 發送完成/失敗/逾時事件
                if event_sink:
                    if res.status == ExecutionStatus.SUCCESS:
                        evt_type = OrchestrationEventType.TASK_COMPLETED
                        status_str = ExecutionStatus.SUCCESS.value
                        msg = f"Task [{ready_task.task_id}] completed successfully"
                    elif res.status == ExecutionStatus.TIMEOUT:
                        evt_type = OrchestrationEventType.TASK_TIMEOUT
                        status_str = ExecutionStatus.TIMEOUT.value
                        msg = res.error or f"Task [{ready_task.task_id}] timed out"
                    else:
                        evt_type = OrchestrationEventType.TASK_FAILED
                        status_str = ExecutionStatus.FAILED.value
                        msg = res.error or f"Task [{ready_task.task_id}] failed"

                    # 提取安全元數據 (不洩漏敏感內部資料)
                    safe_meta = {}
                    if ready_task.target:
                        safe_meta["target"] = ready_task.target

                    event_sink.emit(
                        OrchestrationEvent(
                            event_type=evt_type,
                            plan_id=plan.plan_id,
                            task_id=ready_task.task_id,
                            execution_type=ready_task.execution_type,
                            target=ready_task.target,
                            status=status_str,
                            duration_ms=duration_ms,
                            message=msg,
                            metadata=safe_meta,
                        )
                    )

        return [results_by_task_id[task.task_id] for task in plan.tasks]

    def execute_and_aggregate(
        self,
        plan: TaskPlan,
        event_sink: Optional[TraceSink] = None,
    ) -> AggregatedResult:
        """執行 TaskPlan 並直接透過 ResultAggregator 產出結構化彙整報告.

        Args:
            plan: 待執行之 TaskPlan 計畫實體
            event_sink: 執行軌跡事件接收器 (可選)

        Returns:
            驗證排序後之 AggregatedResult 實體
        """
        results = self.execute_plan(plan, event_sink=event_sink)
        return self.aggregator.aggregate(plan, results)
