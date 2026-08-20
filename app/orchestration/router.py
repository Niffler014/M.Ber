"""M.Ber Task Router (任務路由器模組).

【新手教學 / 觀念解析】：
1. 什麼是 Router（任務路由器）？
   - Router 是 Orchestrator 內部的分流中樞。
   - 它的單一職責（Single Responsibility）：依據 `task.execution_type`（LOCAL / A2A / MCP）
     將任務指派給合適的執行器（Executor）。
   - Router 本身不包含任何 HTTP 通訊、LLM 思考或資料庫持久化細節。
"""

import logging
from typing import Optional

from app.orchestration.executors import A2AExecutor, LocalExecutor, MCPExecutor
from app.orchestration.models import ExecutionContext, ExecutionResult, ExecutionStatus, ExecutionType, SubTask

logger = logging.getLogger("mber.orchestration")


class Router:
    """任務執行路由器 (Task Execution Router)."""

    def __init__(
        self,
        local_executor: Optional[LocalExecutor] = None,
        a2a_executor: Optional[A2AExecutor] = None,
        mcp_executor: Optional[MCPExecutor] = None,
    ) -> None:
        """初始化 Router.

        Args:
            local_executor: 本地能力執行器實例
            a2a_executor: A2A 代理人委派執行器實例
            mcp_executor: MCP 工具執行器實例
        """
        self.local_executor = local_executor or LocalExecutor()
        self.a2a_executor = a2a_executor or A2AExecutor()
        self.mcp_executor = mcp_executor or MCPExecutor()

    def route(self, task: SubTask, context: Optional[ExecutionContext] = None) -> ExecutionResult:
        """根據子任務之 execution_type 分派至對應執行器.

        Args:
            task: 待執行子任務實體
            context: 執行運行期上下文 (包含前置任務產出)

        Returns:
            執行成果 ExecutionResult
        """
        route_type = task.execution_type
        logger.info(f"[Router] {task.task_id} → {route_type.value.upper()}")

        if route_type == ExecutionType.LOCAL:
            return self.local_executor.execute(task, context=context)

        elif route_type == ExecutionType.A2A:
            return self.a2a_executor.execute(task, context=context)

        elif route_type == ExecutionType.MCP:
            return self.mcp_executor.execute(task, context=context)

        err_msg = f"未支援的執行路徑類型: '{route_type}'"
        logger.error(f"[Router] {err_msg}")
        return ExecutionResult(
            task_id=task.task_id,
            execution_type=route_type,
            status=ExecutionStatus.FAILED,
            error=err_msg,
        )
