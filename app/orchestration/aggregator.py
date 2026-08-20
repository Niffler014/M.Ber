"""M.Ber Result Aggregator (執行結果彙整器模組).

【新手教學 / 觀念解析】：
1. 什麼是 ResultAggregator？
   - 當 Orchestrator 執行完一個包含多個子任務的 TaskPlan 後，會產出一組 `List[ExecutionResult]`。
   - `ResultAggregator` 的單一職責：
     ① 驗證執行結果的完整性與一致性（檢查重複 ID、未知 ID、缺漏結果）。
     ② 依據原始 TaskPlan 的宣告順序，嚴格重組並保留成果順序。
     ③ 產出確定性的 `AggregatedResult`，明確標記全成功（SUCCESS）、全失敗（FAILED）或部分成功（PARTIAL_SUCCESS）。
   - 【重要原則】：ResultAggregator 是 100% 確定性模組（Deterministic），絕不呼叫 LLM、絕不做重試、絕不向外部網路發送請求。
"""

import logging
from typing import Dict, List, Set

from app.orchestration.models import (
    AggregatedResult,
    ExecutionResult,
    ExecutionStatus,
    TaskPlan,
)

logger = logging.getLogger("mber.orchestration")


class ResultAggregator:
    """計畫執行結果彙整器."""

    def aggregate(
        self,
        plan: TaskPlan,
        results: List[ExecutionResult],
    ) -> AggregatedResult:
        """將執行產出之 ExecutionResult 清單根據 TaskPlan 進行驗證、排序並彙整.

        Args:
            plan: 原始任務計畫
            results: 執行產出之各子任務結果清單

        Returns:
            驗證排序後之 AggregatedResult 實體

        Raises:
            ValueError: 若結果中存在重複之 task_id 或包含未在計畫中宣告之未知 task_id
        """
        logger.info(f"[ResultAggregator] Aggregating plan: {plan.plan_id} with {len(results)} execution results")

        # 1. 檢查結果清單中是否有重複的 task_id
        seen_result_ids: Set[str] = set()
        result_map: Dict[str, ExecutionResult] = {}
        for r in results:
            if r.task_id in seen_result_ids:
                err_msg = f"結果清單中包含重複的 task_id: '{r.task_id}'"
                logger.error(f"[ResultAggregator] {err_msg}")
                raise ValueError(err_msg)
            seen_result_ids.add(r.task_id)
            result_map[r.task_id] = r

        # 2. 建立計畫內合法的 task_id 集合
        plan_task_ids: Set[str] = {t.task_id for t in plan.tasks}

        # 3. 檢查是否有未在計畫內宣告的未知 task_id
        for r in results:
            if r.task_id not in plan_task_ids:
                err_msg = f"結果清單中包含未在計畫中宣告的未知 task_id: '{r.task_id}'"
                logger.error(f"[ResultAggregator] {err_msg}")
                raise ValueError(err_msg)

        # 4. 依照 TaskPlan 原始順序排列，若有缺漏結果則補上確定性 FAILED 結果
        ordered_results: List[ExecutionResult] = []
        for task in plan.tasks:
            if task.task_id in result_map:
                ordered_results.append(result_map[task.task_id])
            else:
                logger.warning(
                    f"[ResultAggregator] Missing execution result for task: '{task.task_id}', generating failure record"
                )
                fallback_result = ExecutionResult(
                    task_id=task.task_id,
                    execution_type=task.execution_type,
                    status=ExecutionStatus.FAILED,
                    error=f"缺少任務執行結果 (Missing execution result for task '{task.task_id}')",
                )
                ordered_results.append(fallback_result)

        # 5. 建構 AggregatedResult
        aggregated = AggregatedResult(
            plan_id=plan.plan_id,
            results=ordered_results,
        )

        logger.info(
            f"[ResultAggregator] Aggregation complete for plan {plan.plan_id}: "
            f"overall={aggregated.overall_status.value}, "
            f"success={aggregated.success_count}, "
            f"failure={aggregated.failure_count}, "
            f"skipped={aggregated.skipped_count}"
        )

        return aggregated
