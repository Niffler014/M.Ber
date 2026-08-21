"""M.Ber Orchestration Domain Models (調度領域模型與資料契約).

【新手教學 / 觀念解析】：
1. 什麼是 Orchestration Domain Model（調度領域模型）？
   - 在多代理人（Multi-Agent）與多工具架構中，使用者的一個請求可能需要經過：
     ① 規劃拆解（Planner -> TaskPlan -> 包含多個 SubTask）
     ② 分派路由（Router -> 依據 SubTask 的 ExecutionType: LOCAL / MCP / A2A 分派）
     ③ 執行與記錄成果（Executor -> ExecutionResult）
     ④ 彙整反饋（Aggregator -> AggregatedResult）
   - 本模組定義這套流程中所有結構化合約，確保各模組傳遞資料時型別安全、意圖明確且容易測試。

2. 核心設計原則：
   - 核心執行類型（ExecutionType）僅包含 LOCAL、MCP、A2A，保持協定邊界乾淨，不將內部功能（如 Memory）混充為傳輸協定。
   - 內部狀態（ExecutionStatus）獨立於 A2A 協定狀態（A2A TaskStatus），避免不同系統的狀態語意互相污染。
   - 任務命名採 `SubTask` 與 `TaskPlan`，避免與 A2A 規範中的 `Task` 命名混淆。
   - 語意中性的 `target` 欄位，由 `execution_type` 決定其代表意義（A2A 為 Agent/Skill，MCP 為 Tool Name，LOCAL 為 Local Capability）。
   - TaskPlan 具備內建依賴性驗證：防止重複 Task ID、防止自我依賴、防止遺失相依目標、防止循環依賴（Cycle Detection）。
   - AggregatedResult 以 `results` 作為唯一真理來源（Single Source of Truth），統計欄位採計算屬性（Computed Properties）確保資料一致性。
   - ExecutionContext 封裝前置依賴結果傳遞（Dependency Propagation），不汙染原本靜態計畫模型。
"""

from collections import defaultdict
from enum import Enum
from typing import Any, Dict, List, Optional, Set
import uuid
from langchain_core.messages import AIMessage
from pydantic import BaseModel, ConfigDict, Field, computed_field, field_validator, model_validator


class ExecutionType(str, Enum):
    """任務執行路由類型枚舉 (Execution Route Type)."""

    LOCAL = "local"  # 本地推理解析、內部服務調用 (例如 MemoryService、本地 Logic)
    MCP = "mcp"      # Model Context Protocol 工具調用 (例如 SQLite MCP Server、Calendar MCP Server)
    A2A = "a2a"      # Agent-to-Agent 代理人間協定委派 (例如 PCforge Peer Agent)


class ExecutionStatus(str, Enum):
    """內部調度執行狀態枚舉 (Internal Orchestration Status)."""

    PENDING = "pending"  # 任務排隊中，尚未執行
    RUNNING = "running"  # 任務執行中
    SUCCESS = "success"  # 任務順利執行完成
    FAILED = "failed"    # 任務執行發生錯誤或外部異常
    SKIPPED = "skipped"  # 因前置依賴任務失敗而被略過
    TIMEOUT = "timeout"  # 執行逾時


class AggregateStatus(str, Enum):
    """整體計畫執行狀態枚舉 (Overall Plan Aggregation Status)."""

    SUCCESS = "success"                  # 計畫內所有任務均順利完成
    PARTIAL_SUCCESS = "partial_success"  # 計畫內至少一項任務成功，但有其他任務失敗/略過/逾時
    FAILED = "failed"                    # 計畫內所有任務均失敗或略過，無任何成功產出


class SubTask(BaseModel):
    """調度計畫中的單一子任務實體 (Plan SubTask).

    【依賴性語意（Dependency Semantics）說明】：
    - `depends_on`: 存放本子任務所依賴的前置子任務 ID 清單。
    - 語意規則：
      1. 若 `depends_on` 為空，代表可立即並行或按序執行。
      2. 前置依賴任務狀態必須為 SUCCESS，本任務方可執行。
      3. 若任一前置依賴任務狀態為 FAILED、TIMEOUT 或 SKIPPED，本任務必須被標記為 SKIPPED（SKIPPED_DEPENDENCY_FAILED）。
    """

    task_id: str = Field(
        default_factory=lambda: f"task_{uuid.uuid4().hex[:8]}",
        description="子任務唯一識別碼 (不可為空)",
    )
    execution_type: ExecutionType = Field(
        ...,
        description="子任務執行路由類型 (LOCAL / MCP / A2A)",
    )
    goal: str = Field(..., description="子任務目標描述 (自然語言或意圖說明)")
    target: Optional[str] = Field(
        default=None,
        description="執行目標識別 (MCP 時為 Tool Name，A2A 時為 Skill/Agent 識別，LOCAL 時為 Local Capability)",
    )
    parameters: Dict[str, Any] = Field(
        default_factory=dict,
        description="子任務執行參數",
    )
    depends_on: List[str] = Field(
        default_factory=list,
        description="前置依賴子任務 ID 清單",
    )

    @field_validator("task_id")
    @classmethod
    def validate_task_id(cls, v: str) -> str:
        """驗證 task_id 不得為空白字串."""
        if not v or not v.strip():
            raise ValueError("task_id 不可為空字串")
        return v.strip()


class TaskPlan(BaseModel):
    """由 Planner 產生之結構化任務執行計畫 (Task Execution Plan)."""

    plan_id: str = Field(
        default_factory=lambda: f"plan_{uuid.uuid4().hex[:8]}",
        description="計畫唯一識別碼",
    )
    user_goal: str = Field(..., description="使用者原始目標請求")
    tasks: List[SubTask] = Field(
        default_factory=list,
        description="子任務清單",
    )

    @field_validator("plan_id", "user_goal")
    @classmethod
    def validate_non_empty_identity(cls, v: str, info) -> str:
        """驗證 plan_id 與 user_goal 不得為空字串或純空白字元."""
        if not v or not v.strip():
            raise ValueError(f"{info.field_name} 不可為空字串")
        return v.strip()

    @model_validator(mode="after")
    def validate_plan_integrity(self) -> "TaskPlan":
        """驗證計畫完整性與相依性拓撲結構 (重複性、自我依賴、遺失依賴、循環依賴)."""
        tasks = self.tasks
        if not tasks:
            return self

        # 預先建立全體 task_id 集合 (僅建構一次)
        existing_ids: Set[str] = set()
        for task in tasks:
            if task.task_id in existing_ids:
                raise ValueError(f"TaskPlan 包含重複的 task_id: '{task.task_id}'")
            existing_ids.add(task.task_id)

        # 驗證自我依賴與遺失相依目標
        for task in tasks:
            # 檢查自我依賴 (Self-dependency)
            if task.task_id in task.depends_on:
                raise ValueError(
                    f"Task '{task.task_id}' 不可依賴自身 (Self-dependency detected)"
                )

            # 檢查遺失相依目標 (Missing dependency)
            for dep in task.depends_on:
                if dep not in existing_ids:
                    raise ValueError(
                        f"Task '{task.task_id}' 依賴不存在的任務: '{dep}'"
                    )

        # 檢查循環依賴 (Cycle Detection via DFS)
        graph: Dict[str, List[str]] = defaultdict(list)
        for task in tasks:
            for dep in task.depends_on:
                graph[dep].append(task.task_id)

        visited: Dict[str, int] = {}  # 0: visiting, 1: visited

        def has_cycle(node: str) -> bool:
            visited[node] = 0  # Visiting in current DFS path
            for neighbor in graph[node]:
                if neighbor in visited:
                    if visited[neighbor] == 0:
                        return True
                else:
                    if has_cycle(neighbor):
                        return True
            visited[node] = 1  # Visited
            return False

        for tid in existing_ids:
            if tid not in visited:
                if has_cycle(tid):
                    raise ValueError("TaskPlan 中存在循環依賴 (Dependency cycle detected)")

        return self


class ExecutionResult(BaseModel):
    """單一子任務執行成果 (SubTask Execution Result)."""

    task_id: str = Field(..., description="對應之子任務識別碼")
    execution_type: ExecutionType = Field(..., description="執行路由類型 (LOCAL / MCP / A2A)")
    status: ExecutionStatus = Field(..., description="執行狀態 (PENDING / RUNNING / SUCCESS / FAILED / SKIPPED / TIMEOUT)")
    source: Optional[str] = Field(
        default=None,
        description="執行來源識別 (例如 a2a:PCforge, mcp:calendar_server, local:memory)",
    )
    result: Optional[Any] = Field(default=None, description="成功產出資料或回傳內容")
    error: Optional[str] = Field(default=None, description="錯誤訊息 (若執行失敗)")
    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="額外執行元數據 (如 duration_ms, remote_task_id, tool_name 等)",
    )


class ExecutionContext(BaseModel):
    """子任務執行運行期上下文 (Runtime Execution Context).

    用以在任務相依鏈中傳遞前置依賴任務之執行產出 (Dependency Results Propagation)，
    避免直接 mutate 靜態的 SubTask.parameters。
    """

    dependency_results: Dict[str, ExecutionResult] = Field(
        default_factory=dict,
        description="前置依賴任務之執行成果映射表 (以 task_id 為鍵)",
    )

    def get_result(self, task_id: str) -> Optional[Any]:
        """取得指定前置任務之產出結果 (若不存在或未產出回傳 None)."""
        if task_id in self.dependency_results:
            return self.dependency_results[task_id].result
        return None

    def get_first_result(self) -> Optional[Any]:
        """取得第一個依賴任務之產出結果 (常用於單一前置任務鏈)."""
        if self.dependency_results:
            first_res = next(iter(self.dependency_results.values()))
            return first_res.result
        return None


class AggregatedResult(BaseModel):
    """彙整後的整體計畫執行報告 (Aggregated Plan Result - 確定性無 LLM 依賴).

    【Single Source of Truth 原則】：
    `results` 列表為唯一事實來源，所有統計數據（success_count, failure_count,
    skipped_count, has_partial_failure）均以 @computed_field 動態衍生，杜絕狀態矛盾。
    """

    plan_id: str = Field(..., description="所屬計畫識別碼")
    results: List[ExecutionResult] = Field(
        default_factory=list,
        description="各子任務執行結果清單 (唯一事實來源)",
    )

    @computed_field
    @property
    def success_count(self) -> int:
        """成功任務數量."""
        return sum(1 for r in self.results if r.status == ExecutionStatus.SUCCESS)

    @computed_field
    @property
    def failure_count(self) -> int:
        """失敗與逾時任務數量."""
        return sum(
            1
            for r in self.results
            if r.status in (ExecutionStatus.FAILED, ExecutionStatus.TIMEOUT)
        )

    @computed_field
    @property
    def skipped_count(self) -> int:
        """略過任務數量."""
        return sum(1 for r in self.results if r.status == ExecutionStatus.SKIPPED)

    @computed_field
    @property
    def has_partial_failure(self) -> bool:
        """是否包含部分失敗 (有成功且有失敗或略過)."""
        return (self.success_count > 0) and (
            self.failure_count > 0 or self.skipped_count > 0
        )

    @computed_field
    @property
    def overall_status(self) -> AggregateStatus:
        """整體計畫執行狀態判定 (SUCCESS / PARTIAL_SUCCESS / FAILED)."""
        if not self.results:
            return AggregateStatus.FAILED
        if self.success_count == len(self.results):
            return AggregateStatus.SUCCESS
        if self.success_count > 0:
            return AggregateStatus.PARTIAL_SUCCESS
        return AggregateStatus.FAILED

    @property
    def failed_task_ids(self) -> List[str]:
        """失敗或逾時之任務 ID 清單."""
        return [
            r.task_id
            for r in self.results
            if r.status in (ExecutionStatus.FAILED, ExecutionStatus.TIMEOUT)
        ]

    @property
    def skipped_task_ids(self) -> List[str]:
        """略過之任務 ID 清單."""
        return [r.task_id for r in self.results if r.status == ExecutionStatus.SKIPPED]

    def to_context_text(self) -> str:
        """將彙整結果轉換為清晰、確定性文字摘要 (供上層 Final Response Layer 使用)."""
        lines = [f"Plan ID: {self.plan_id} (Overall Status: {self.overall_status.value})"]
        for idx, r in enumerate(self.results, 1):
            src = r.source or "unknown"
            lines.append(f"- Task {idx} [{r.task_id}]: type={r.execution_type.value}, status={r.status.value}, source={src}")
            if r.status == ExecutionStatus.SUCCESS:
                lines.append(f"  Result: {r.result}")
            elif r.error:
                lines.append(f"  Error: {r.error}")
        return "\n".join(lines)
    

class OrchestrationResponse(BaseModel):
    """M.Ber 調度服務應用層完整回傳成果模型 (Application-Level Orchestration Response)."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    message: AIMessage = Field(..., description="最終合成之 AIMessage")
    plan: TaskPlan = Field(..., description="調度規劃計畫實體")
    aggregated: AggregatedResult = Field(..., description="各子任務彙整執行報告")
    events: List[Any] = Field(
        default_factory=list,
        description="調度過程產出之結構化事件清單 (Orchestration Events)",
    )


