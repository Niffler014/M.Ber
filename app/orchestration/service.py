"""M.Ber Orchestration Integration Service (多代理人與多工具調度整合服務).

【新手教學 / 觀念解析】：
1. 什麼是 OrchestrationService？
   - `OrchestrationService` 是 LangGraph 與 Phase 7 調度核心之間的橋樑（Application Boundary & Composition Root）。
   - 它的職責：
     ① 彙整並管理 Planner、Orchestrator、Router、Executors (LOCAL, MCP, A2A) 與 ResultAggregator。
     ② 從 LangGraph 對話訊息中提取最新使用者意圖（HumanMessage）。
     ③ 由 Planner 進行「唯一頂層路由決策」（Single Routing Authority）。
     ④ 調度執行子任務並透過 ResultAggregator 彙整成果。
     ⑤ 產出結構化且對使用者友善的最終 `AIMessage`。
"""

import json
import logging
from typing import Any, Dict, List, Optional, Union

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage

from app.a2a.client import TransportHandler
from app.a2a.discovery import AgentDiscoveryService
from app.mcp.manager import MCPManager
from app.orchestration.aggregator import ResultAggregator
from app.orchestration.events import (
    CompositeEventSink,
    ListEventSink,
    OrchestrationEvent,
    OrchestrationEventType,
    TraceSink,
)
from app.orchestration.executors import A2AExecutor, LocalExecutor, MCPExecutor
from app.orchestration.local_reasoning import LocalReasoningAdapter
from app.orchestration.memory_adapter import (
    CANONICAL_MEMORY_CAPABILITY,
    MemoryAdapter,
    register_memory_capability,
)
from app.orchestration.model_factory import get_chat_model
from app.orchestration.models import (
    AggregatedResult,
    AggregateStatus,
    ExecutionContext,
    ExecutionResult,
    ExecutionStatus,
    ExecutionType,
    OrchestrationResponse,
    SubTask,
    TaskPlan,
)
from app.orchestration.orchestrator import Orchestrator
from app.orchestration.planner import (
    CapabilitySummary,
    Planner,
)
from app.orchestration.router import Router
from memory.service import MemoryService

logger = logging.getLogger("mber.orchestration")


def default_local_reasoning_handler(
    task: SubTask,
    context: Optional[ExecutionContext] = None,
    llm: Optional[Any] = None,
) -> str:
    """處理一般本地推理解析任務 (General Local Reasoning)."""
    adapter = LocalReasoningAdapter(llm=llm)
    return adapter.handle_reasoning(task, context=context)


class OrchestrationService:
    """M.Ber 調度總管服務 (Single Routing Authority)."""

    def __init__(
        self,
        planner: Optional[Planner] = None,
        orchestrator: Optional[Orchestrator] = None,
        aggregator: Optional[ResultAggregator] = None,
        router: Optional[Router] = None,
        local_executor: Optional[LocalExecutor] = None,
        mcp_executor: Optional[MCPExecutor] = None,
        a2a_executor: Optional[A2AExecutor] = None,
        llm: Optional[Any] = None,
        mcp_manager: Optional[MCPManager] = None,
        discovery_service: Optional[AgentDiscoveryService] = None,
        memory_service: Optional[MemoryService] = None,
        rpc_transport: Optional[TransportHandler] = None,
    ) -> None:
        """初始化 OrchestrationService 並完成各層依賴接線."""
        self.llm = llm if llm is not None else get_chat_model()
        self.mcp_manager = mcp_manager if mcp_manager is not None else MCPManager()
        self.discovery_service = discovery_service if discovery_service is not None else AgentDiscoveryService()
        self.memory_service = memory_service

        # 預設啟動時安全進行 A2A 探索 (若外部 Peer 離線則記錄警告，不中斷整體系統初始化)
        if discovery_service is None and self.discovery_service is not None:
            try:
                self.discovery_service.discover_configured_peers()
            except Exception as e:
                logger.warning(f"[OrchestrationService] A2A peer discovery failed during startup: {e}")

        # 1. 初始化各協定執行器
        self.local_executor = local_executor or LocalExecutor()
        self.mcp_executor = mcp_executor or MCPExecutor(mcp_manager=self.mcp_manager)
        self.a2a_executor = a2a_executor or A2AExecutor(
            discovery_service=self.discovery_service,
            rpc_transport=rpc_transport,
        )

        # 2. 註冊 LocalExecutor 標準 Capabilities
        self._setup_local_executor()

        # 3. 初始化 Router 與 Orchestrator
        self.router = router or Router(
            local_executor=self.local_executor,
            a2a_executor=self.a2a_executor,
            mcp_executor=self.mcp_executor,
        )
        self.aggregator = aggregator or ResultAggregator()
        self.orchestrator = orchestrator or Orchestrator(
            router=self.router,
            aggregator=self.aggregator,
        )

        # 4. 初始化 Planner 與能力快照 (在 MCP 與 A2A 發現完成後建置 Snapshot)
        if planner is not None:
            self.planner = planner
        else:
            caps = self._build_capability_summary()
            if self.llm is not None:
                logger.info("[Planner] backend=structured_llm")
                self.planner = Planner(llm=self.llm, capability_summary=caps)
            else:
                logger.info("[Planner] backend=deterministic_offline")
                self.planner = Planner(capability_summary=caps)

    def _setup_local_executor(self) -> None:
        """為 LocalExecutor 註冊標準 Local Capabilities (Reasoning, Memory, Utilities)."""
        # A. 記憶能力 (memory_store)
        register_memory_capability(
            self.local_executor,
            memory_service=self.memory_service,
            capability_name=CANONICAL_MEMORY_CAPABILITY,
        )

        # B. 通用推理能力 (Default / general_qa / agent_reasoning)
        self.local_reasoning_adapter = LocalReasoningAdapter(llm=self.llm)

        self.local_executor.register_handler(
            "general_qa", self.local_reasoning_adapter.handle_reasoning
        )
        self.local_executor.register_handler(
            "agent_reasoning", self.local_reasoning_adapter.handle_reasoning
        )

        # 註冊預設未指定 target 之 fallback 處理常式
        self.local_executor.register_handler(
            "default", self.local_reasoning_adapter.handle_reasoning
        )

    def _build_capability_summary(self) -> CapabilitySummary:
        """動態彙整當前系統已知可用能力清單."""
        a2a_skills = []
        if self.discovery_service:
            peers = self.discovery_service.list_agents()
            for p in peers:
                for s in p.skills:
                    a2a_skills.append({
                        "id": s.id,
                        "name": s.name,
                        "description": s.description,
                        "tags": s.tags,
                        "agent_name": p.name,
                    })

        mcp_tools = []
        if self.mcp_manager:
            mcp_tools = self.mcp_manager.list_all_tools()

        return CapabilitySummary(
            a2a_skills=a2a_skills,
            mcp_tools=mcp_tools,
            local_capabilities=["memory_store", "general_qa", "agent_reasoning"],
        )

    def extract_latest_user_goal(self, messages: List[BaseMessage]) -> str:
        """從 LangGraph 對話歷史中提取最新使用者訊息內容."""
        for msg in reversed(messages):
            if isinstance(msg, HumanMessage):
                content = msg.content
                if isinstance(content, str):
                    return content.strip()
                return str(content).strip()
        return "空使用者請求"

    def invoke_with_details(
        self,
        messages: List[BaseMessage],
        event_sink: Optional[TraceSink] = None,
    ) -> OrchestrationResponse:
        """執行 LangGraph 調度週期並回傳完整具名 OrchestrationResponse (Single Routing Authority).

        流程：
        User Messages ➔ Extract Goal ➔ Planner ➔ Orchestrator ➔ ResultAggregator ➔ Final Synthesis ➔ OrchestrationResponse
        """
        # 建立內部事件收集器以保留完整軌跡，並支援向外部 event_sink (如 SSE 即時串流) 廣播事件
        collector = ListEventSink()
        active_sink = CompositeEventSink([collector, event_sink]) if event_sink else collector

        user_goal = self.extract_latest_user_goal(messages)
        logger.info(f"[OrchestrationService] Received user goal: '{user_goal}'")
        active_sink.emit(
            OrchestrationEvent(
                event_type=OrchestrationEventType.REQUEST_RECEIVED,
                message=user_goal,
            )
        )

        # 1. 任務規劃 (Planning)
        active_sink.emit(
            OrchestrationEvent(
                event_type=OrchestrationEventType.PLANNING_STARTED,
                status="running",
                message="Planner started analyzing intent",
            )
        )
        plan: TaskPlan = self.planner.plan(user_goal)
        logger.info(f"[OrchestrationService] Planner generated plan: {plan.plan_id} with {len(plan.tasks)} tasks")
        active_sink.emit(
            OrchestrationEvent(
                event_type=OrchestrationEventType.PLAN_CREATED,
                plan_id=plan.plan_id,
                status="success",
                message=f"Plan created with {len(plan.tasks)} tasks",
                metadata={"task_count": len(plan.tasks)},
            )
        )

        # 2. 任務調度執行 (Execution)
        exec_ctx = ExecutionContext(metadata={"messages": messages})
        results: List[ExecutionResult] = self.orchestrator.execute_plan(
            plan, context=exec_ctx, event_sink=active_sink
        )

        # 3. 成果彙整 (Aggregation)
        aggregated: AggregatedResult = self.aggregator.aggregate(plan, results)
        logger.info(f"[OrchestrationService] Aggregated result status: {aggregated.overall_status.value}")
        active_sink.emit(
            OrchestrationEvent(
                event_type=OrchestrationEventType.AGGREGATION_COMPLETED,
                plan_id=plan.plan_id,
                status=aggregated.overall_status.value,
                message=f"Aggregation completed with status: {aggregated.overall_status.value}",
            )
        )

        # 4. 最終回覆合成 (Response Synthesis)
        response_content = self.synthesize_response(plan, aggregated)
        ai_message = AIMessage(content=response_content)
        active_sink.emit(
            OrchestrationEvent(
                event_type=OrchestrationEventType.RESPONSE_READY,
                plan_id=plan.plan_id,
                status=aggregated.overall_status.value,
                message="Final synthesized response ready",
            )
        )

        return OrchestrationResponse(
            message=ai_message,
            plan=plan,
            aggregated=aggregated,
            events=collector.get_events(),
        )

    def invoke(self, messages: List[BaseMessage]) -> AIMessage:
        """執行 LangGraph 調度週期 (Single Routing Authority 保持向後相容)."""
        return self.invoke_with_details(messages).message

    def synthesize_response(self, plan: TaskPlan, aggregated: AggregatedResult) -> str:
        """根據 AggregatedResult 確定性合成給使用者的最終回應."""
        # 情況 A：單一任務
        if len(aggregated.results) == 1:
            res = aggregated.results[0]
            if res.status == ExecutionStatus.SUCCESS:
                # 若是 MCP 呼叫
                if res.execution_type == ExecutionType.MCP:
                    return f"已成功透過 MCP 工具為您處理完畢！執行結果如下：\n{res.result}\n請問還需要其他協助嗎？"
                # LOCAL 或 A2A 輸出
                return str(res.result)
            elif res.status == ExecutionStatus.TIMEOUT:
                return f"⚠️ 任務執行逾時：{res.error or '遠端伺服器或工具連線超時。'}"
            else:
                return f"⚠️ 任務執行失敗：{res.error or '發生非預期錯誤。'}"

        # 情況 B：多步驟工作流全成功 (Full Success)
        if aggregated.overall_status == AggregateStatus.SUCCESS:
            body_parts = []
            for idx, res in enumerate(aggregated.results, 1):
                if res.execution_type == ExecutionType.LOCAL and res.source == "local:memory_store":
                    body_parts.append(f"💾 【記憶庫】: 已為您成功記住這項資訊。")
                elif res.execution_type == ExecutionType.A2A:
                    body_parts.append(str(res.result))
                elif res.execution_type == ExecutionType.MCP:
                    body_parts.append(f"🔧 【MCP 工具成果】:\n{res.result}")
                else:
                    body_parts.append(str(res.result))
            return "\n\n".join(body_parts)

        # 情況 C：部分成功 (Partial Failure)
        if aggregated.overall_status == AggregateStatus.PARTIAL_SUCCESS:
            success_parts = []
            failed_parts = []
            for res in aggregated.results:
                if res.status == ExecutionStatus.SUCCESS:
                    if res.execution_type == ExecutionType.LOCAL and res.source == "local:memory_store":
                        success_parts.append("💾 記憶庫儲存已完成。")
                    else:
                        success_parts.append(str(res.result))
                else:
                    err_desc = res.error or "執行異常"
                    failed_parts.append(f"- 任務 [{res.task_id}] 執行失敗: {err_desc}")

            response_lines = []
            if success_parts:
                response_lines.append("\n\n".join(success_parts))
            response_lines.append("\n⚠️ 【注意】：部分步驟執行發生問題：")
            response_lines.extend(failed_parts)
            return "\n".join(response_lines)

        # 情況 D：全失敗 (Full Failure)
        error_lines = ["⚠️ 任務無法順利完成，各步驟錯誤詳情如下："]
        for res in aggregated.results:
            error_lines.append(f"- 任務 [{res.task_id}] ({res.status.value}): {res.error or '未執行或被略過'}")
        return "\n".join(error_lines)
