"""M.Ber Orchestration Task Executors (任務執行器模組).

【新手教學 / 觀念解析】：
1. 什麼是 Task Executor（任務執行器）？
   - 當 Router 決定將 SubTask 路由至 LOCAL、A2A 或 MCP 時，由對應的 Executor 負責「具體與底層能力對接與執行」。
   - `LocalExecutor`：處理內部函式、記憶體或其他本機能力。
   - `A2AExecutor`：作為 A2A 適配層（Adapter），負責透過 `AgentDiscoveryService` 與 `A2AClient` 委派遠端 Peer Agent。
   - `MCPExecutor`：作為 MCP 適配層（Adapter），負責透過 `MCPManager` 調用 MCP Server 上的外部工具（如 Calendar、SQLite 等），
     並執行安全權限評估與結果標準化。

2. 依賴產出傳遞（Dependency Propagation）：
   - Executor 接受可選的 `ExecutionContext`，執行器與處理器（Handlers）可從中提取前置依賴任務的成果，
     達成無副作用的跨步驟資料串接。
"""

from abc import ABC, abstractmethod
import inspect
import logging
import socket
from typing import Any, Callable, Dict, Optional, Union
import urllib.error

from app.orchestration.models import ExecutionContext, ExecutionResult, ExecutionStatus, ExecutionType, SubTask
from app.a2a.client import A2AClient, A2AClientError, TransportHandler
from app.a2a.discovery import AgentDiscoveryService
from app.a2a.models import AgentCard, Message, Task, TaskState, TextPart
from app.mcp.manager import MCPManager

logger = logging.getLogger("mber.orchestration")


class BaseExecutor(ABC):
    """任務執行器抽象介面."""

    @abstractmethod
    def execute(self, task: SubTask, context: Optional[ExecutionContext] = None) -> ExecutionResult:
        """執行子任務並回傳標準 ExecutionResult."""
        pass


class LocalExecutor(BaseExecutor):
    """本地能力執行器 (Local Handler Registry Executor)."""

    def __init__(self, handlers: Optional[Dict[str, Callable[..., Any]]] = None) -> None:
        """初始化 LocalExecutor.

        Args:
            handlers: 初始本地處理器字典 (以 capability target 為鍵)
        """
        self._handlers: Dict[str, Callable[..., Any]] = dict(handlers or {})

    def register_handler(self, target: str, handler: Callable[..., Any]) -> None:
        """註冊本機能力處理常式.

        Args:
            target: 能力識別標籤 (例如 'echo', 'math_eval', 'store_memory')
            handler: 回呼函式，支援 `handler(task)` 或 `handler(task, context)`
        """
        self._handlers[target] = handler

    def execute(self, task: SubTask, context: Optional[ExecutionContext] = None) -> ExecutionResult:
        """執行本地子任務."""
        target_name = task.target or "default"
        logger.info(f"[Local] Executing capability: {target_name} (task_id: {task.task_id})")

        if target_name not in self._handlers:
            err_msg = f"未知的本地能力目標: '{target_name}' (未註冊 handler)"
            logger.warning(f"[Local] {err_msg}")
            return ExecutionResult(
                task_id=task.task_id,
                execution_type=ExecutionType.LOCAL,
                status=ExecutionStatus.FAILED,
                source=f"local:{target_name}",
                error=err_msg,
            )

        handler = self._handlers[target_name]
        try:
            # 檢查 handler 是否支援接收 context 參數
            sig = inspect.signature(handler)
            if len(sig.parameters) >= 2 or any(p.kind == inspect.Parameter.VAR_KEYWORD for p in sig.parameters.values()):
                output = handler(task, context)
            else:
                output = handler(task)

            logger.info(f"[Local] Capability '{target_name}' completed successfully")
            return ExecutionResult(
                task_id=task.task_id,
                execution_type=ExecutionType.LOCAL,
                status=ExecutionStatus.SUCCESS,
                source=f"local:{target_name}",
                result=output,
            )
        except Exception as e:
            err_msg = f"本地能力 '{target_name}' 執行時發生錯誤: {e}"
            logger.error(f"[Local] {err_msg}")
            return ExecutionResult(
                task_id=task.task_id,
                execution_type=ExecutionType.LOCAL,
                status=ExecutionStatus.FAILED,
                source=f"local:{target_name}",
                error=err_msg,
            )


class A2AExecutor(BaseExecutor):
    """A2A 代理人通訊與狀態適配執行器 (A2A Protocol Adapter Executor)."""

    def __init__(
        self,
        discovery_service: Optional[AgentDiscoveryService] = None,
        rpc_transport: Optional[TransportHandler] = None,
    ) -> None:
        """初始化 A2AExecutor.

        Args:
            discovery_service: 代理人發現服務實例 (若為 None 則使用預設實例)
            rpc_transport: 自訂 JSON-RPC 傳輸函式 (用於測試注入與隔離)
        """
        self.discovery = discovery_service or AgentDiscoveryService()
        self.rpc_transport = rpc_transport
        self._clients: Dict[str, A2AClient] = {}

    def get_client(self, endpoint_url: str) -> A2AClient:
        """取得或建立對應端點的 A2AClient 快取實例."""
        if endpoint_url not in self._clients:
            self._clients[endpoint_url] = A2AClient(
                endpoint_url=endpoint_url,
                transport=self.rpc_transport,
            )
        return self._clients[endpoint_url]

    def _resolve_agent(self, task: SubTask) -> Optional[AgentCard]:
        """依據 task.target 或 task.goal 動態解析目標 AgentCard (無 hard-code)."""
        target = (task.target or "").strip()

        # 1. 依據名稱尋找已註冊之 Agent
        if target:
            agent = self.discovery.get_agent(target)
            if agent:
                return agent

            # 2. 依據 Skill ID 或 Tag 尋找適合的 Agent
            agent_by_skill = self.discovery.find_agent_by_skill(target)
            if agent_by_skill:
                return agent_by_skill

        # 3. 依據 Goal 或 Target 進行自然語言意圖模糊匹配
        query = target or task.goal
        match = self.discovery.find_agent_for_query(query)
        if match:
            card, _ = match
            return card

        return None

    def execute(self, task: SubTask, context: Optional[ExecutionContext] = None) -> ExecutionResult:
        """透過 A2A 協定將子任務委派給遠端 Peer Agent 並適配回傳結果."""
        target_name = task.target or task.goal
        logger.info(f"[A2A] Resolving agent for target/goal: '{target_name}' (task_id: {task.task_id})")

        card = self._resolve_agent(task)
        if card is None:
            err_msg = f"找不到符合能力目標 '{target_name}' 之 A2A 代理人 (Agent not found)"
            logger.warning(f"[A2A] {err_msg}")
            return ExecutionResult(
                task_id=task.task_id,
                execution_type=ExecutionType.A2A,
                status=ExecutionStatus.FAILED,
                source=f"a2a:{task.target or 'unknown'}",
                error=err_msg,
            )

        logger.info(f"[A2A] Delegating target '{target_name}' to Agent '{card.name}' at {card.url}")
        client = self.get_client(card.url)
        message_text = task.parameters.get("message") or task.goal

        try:
            response = client.send_message(message_text)
        except (TimeoutError, socket.timeout) as e:
            err_msg = f"向代理人 '{card.name}' 發送任務連線逾時: {e}"
            logger.error(f"[A2A] {err_msg}")
            return ExecutionResult(
                task_id=task.task_id,
                execution_type=ExecutionType.A2A,
                status=ExecutionStatus.TIMEOUT,
                source=f"a2a:{card.name}",
                error=err_msg,
                metadata={"agent_name": card.name, "endpoint_url": card.url},
            )
        except urllib.error.URLError as e:
            if isinstance(getattr(e, "reason", None), (socket.timeout, TimeoutError)) or "timed out" in str(e).lower():
                err_msg = f"向代理人 '{card.name}' 發送任務超時: {e}"
                logger.error(f"[A2A] {err_msg}")
                return ExecutionResult(
                    task_id=task.task_id,
                    execution_type=ExecutionType.A2A,
                    status=ExecutionStatus.TIMEOUT,
                    source=f"a2a:{card.name}",
                    error=err_msg,
                    metadata={"agent_name": card.name, "endpoint_url": card.url},
                )
            err_msg = f"無法連線至外部代理人 '{card.name}' ({card.url}): {e}"
            logger.error(f"[A2A] {err_msg}")
            return ExecutionResult(
                task_id=task.task_id,
                execution_type=ExecutionType.A2A,
                status=ExecutionStatus.FAILED,
                source=f"a2a:{card.name}",
                error=err_msg,
                metadata={"agent_name": card.name, "endpoint_url": card.url},
            )
        except A2AClientError as e:
            err_msg = f"A2A 協定錯誤 (Code: {e.code}): {e}"
            logger.error(f"[A2A] {err_msg}")
            return ExecutionResult(
                task_id=task.task_id,
                execution_type=ExecutionType.A2A,
                status=ExecutionStatus.FAILED,
                source=f"a2a:{card.name}",
                error=err_msg,
                metadata={"agent_name": card.name, "error_code": e.code},
            )
        except Exception as e:
            err_str = str(e).lower()
            if "timeout" in err_str or "timed out" in err_str:
                err_msg = f"向代理人 '{card.name}' 發送任務逾時: {e}"
                logger.error(f"[A2A] {err_msg}")
                return ExecutionResult(
                    task_id=task.task_id,
                    execution_type=ExecutionType.A2A,
                    status=ExecutionStatus.TIMEOUT,
                    source=f"a2a:{card.name}",
                    error=err_msg,
                    metadata={"agent_name": card.name},
                )
            err_msg = f"委派代理人 '{card.name}' 執行時發生異常: {e}"
            logger.error(f"[A2A] {err_msg}")
            return ExecutionResult(
                task_id=task.task_id,
                execution_type=ExecutionType.A2A,
                status=ExecutionStatus.FAILED,
                source=f"a2a:{card.name}",
                error=err_msg,
                metadata={"agent_name": card.name},
            )

        # 狀態映射（A2A Protocol Status -> Orchestration Status）
        if isinstance(response, Task):
            state = response.status.state
            status_text = response.status.message.text_content if response.status.message else ""

            # 彙整產物 Artifacts
            artifacts_content = []
            if response.artifacts:
                for art in response.artifacts:
                    art_name = art.name or "產物內容"
                    content = "\n".join(p.text for p in art.parts if isinstance(p, TextPart))
                    artifacts_content.append(f"📦 【{art_name}】\n{content}")
            combined_body = "\n\n".join(filter(None, [status_text] + artifacts_content))

            meta = {
                "remote_task_id": response.id,
                "agent_name": card.name,
                "a2a_state": state.value,
            }

            formatted_result = (
                f"🤖 [A2A 遠端代理人: {card.name}]\n"
                f"任務狀態: {state.value}\n"
                f"{combined_body or '任務已由外部代理人處理完成。'}"
            )

            if state == TaskState.COMPLETED:
                logger.info(f"[A2A] Task completed by '{card.name}' (remote_id: {response.id})")
                return ExecutionResult(
                    task_id=task.task_id,
                    execution_type=ExecutionType.A2A,
                    status=ExecutionStatus.SUCCESS,
                    source=f"a2a:{card.name}",
                    result=formatted_result,
                    metadata=meta,
                )
            elif state in (TaskState.FAILED, TaskState.CANCELED):
                err_text = status_text or f"A2A 任務狀態為 {state.value}"
                logger.warning(f"[A2A] Task failed on '{card.name}': {err_text}")
                return ExecutionResult(
                    task_id=task.task_id,
                    execution_type=ExecutionType.A2A,
                    status=ExecutionStatus.FAILED,
                    source=f"a2a:{card.name}",
                    error=err_text,
                    metadata=meta,
                )
            else:
                logger.info(f"[A2A] Task state '{state.value}' received from '{card.name}'")
                return ExecutionResult(
                    task_id=task.task_id,
                    execution_type=ExecutionType.A2A,
                    status=ExecutionStatus.SUCCESS,
                    source=f"a2a:{card.name}",
                    result=combined_body or f"任務已接收，當前狀態為: {state.value}",
                    metadata=meta,
                )

        elif isinstance(response, Message):
            logger.info(f"[A2A] Message response received from '{card.name}'")
            return ExecutionResult(
                task_id=task.task_id,
                execution_type=ExecutionType.A2A,
                status=ExecutionStatus.SUCCESS,
                source=f"a2a:{card.name}",
                result=response.text_content,
                metadata={"agent_name": card.name},
            )

        err_msg = f"來自 '{card.name}' 之回應非預期型別: {type(response)}"
        logger.error(f"[A2A] {err_msg}")
        return ExecutionResult(
            task_id=task.task_id,
            execution_type=ExecutionType.A2A,
            status=ExecutionStatus.FAILED,
            source=f"a2a:{card.name}",
            error=err_msg,
        )


class MCPExecutor(BaseExecutor):
    """Model Context Protocol 工具執行適配器 (MCP Tool Adapter Executor).

    【職責與邊界】：
    - 重用既有 `MCPManager`，負責將 SubTask(execution_type=MCP, target=tool_name)
      轉交由 MCPManager 調用對應的 MCP Server 工具。
    - 保留原有 SafetyLevel 評估流程（唯讀與寫入審查）。
    - 將 MCP 輸出標準化為字串或資料，映射回 ExecutionResult。
    """

    def __init__(self, mcp_manager: Optional[MCPManager] = None) -> None:
        """初始化 MCPExecutor.

        Args:
            mcp_manager: MCP 伺服器總管實例 (若為 None 則於初次調用或初始化時建立預設實例)
        """
        self._mcp_manager = mcp_manager

    @property
    def mcp_manager(self) -> MCPManager:
        """取得或延遲初始化 MCPManager 實例."""
        if self._mcp_manager is None:
            self._mcp_manager = MCPManager()
        return self._mcp_manager

    def execute(self, task: SubTask, context: Optional[ExecutionContext] = None) -> ExecutionResult:
        """執行 MCP 工具子任務."""
        tool_name = (task.target or "").strip()
        if not tool_name:
            err_msg = "未指定 MCP 工具名稱 (task.target 為空)"
            logger.warning(f"[MCP] {err_msg}")
            return ExecutionResult(
                task_id=task.task_id,
                execution_type=ExecutionType.MCP,
                status=ExecutionStatus.FAILED,
                source="mcp:unknown",
                error=err_msg,
            )

        args = dict(task.parameters or {})
        logger.info(f"[MCP] Executing tool: {tool_name} (task_id: {task.task_id})")

        try:
            raw_output = self.mcp_manager.call_tool(tool_name, args)
        except (TimeoutError, socket.timeout) as e:
            err_msg = f"MCP 工具 '{tool_name}' 調用逾時: {e}"
            logger.error(f"[MCP] {err_msg}")
            return ExecutionResult(
                task_id=task.task_id,
                execution_type=ExecutionType.MCP,
                status=ExecutionStatus.TIMEOUT,
                source=f"mcp:{tool_name}",
                error=err_msg,
                metadata={"tool_name": tool_name},
            )
        except Exception as e:
            err_str = str(e).lower()
            if "timeout" in err_str or "timed out" in err_str:
                err_msg = f"MCP 工具 '{tool_name}' 執行逾時: {e}"
                logger.error(f"[MCP] {err_msg}")
                return ExecutionResult(
                    task_id=task.task_id,
                    execution_type=ExecutionType.MCP,
                    status=ExecutionStatus.TIMEOUT,
                    source=f"mcp:{tool_name}",
                    error=err_msg,
                    metadata={"tool_name": tool_name},
                )
            err_msg = f"MCP 工具 '{tool_name}' 執行失敗: {e}"
            logger.error(f"[MCP] {err_msg}")
            return ExecutionResult(
                task_id=task.task_id,
                execution_type=ExecutionType.MCP,
                status=ExecutionStatus.FAILED,
                source=f"mcp:{tool_name}",
                error=err_msg,
                metadata={"tool_name": tool_name},
            )

        # 檢查 MCPManager 回傳之標準錯誤前綴
        if isinstance(raw_output, str) and (
            raw_output.startswith("❌ [MCP Manager 錯誤]") or raw_output.startswith("❌ [MCP Manager 調用失敗]")
        ):
            logger.warning(f"[MCP] Execution failed: {raw_output}")
            status = ExecutionStatus.TIMEOUT if ("timed out" in raw_output.lower() or "timeout" in raw_output.lower()) else ExecutionStatus.FAILED
            return ExecutionResult(
                task_id=task.task_id,
                execution_type=ExecutionType.MCP,
                status=status,
                source=f"mcp:{tool_name}",
                error=raw_output,
                metadata={"tool_name": tool_name},
            )

        logger.info(f"[MCP] Tool '{tool_name}' completed successfully")
        return ExecutionResult(
            task_id=task.task_id,
            execution_type=ExecutionType.MCP,
            status=ExecutionStatus.SUCCESS,
            source=f"mcp:{tool_name}",
            result=raw_output,
            metadata={"tool_name": tool_name},
        )
