"""M.Ber A2A (Agent-to-Agent) Protocol Domain Models (A2A 1.0.0).

【新手教學 / 觀念解析】：
1. 什麼是 A2A (Agent-to-Agent Protocol)？
   - A2A 是 Linux Foundation 主導的開源標準協定，專門用於「不同 AI 代理人（Agents）之間的溝通、協作與任務委派」。
   - 就像人類工作時有「自我介紹名片」、「任務交辦信件」與「工作進度狀態」一樣，A2A 定義了機器可讀的標準資料結構。

2. 核心實體架構：
   - `AgentCard`：代理人的數位名片，記載名稱、說明、端點 URL、支援技能（Skills）與認證要求。
   - `AgentSkill`：代理人聲明自己擅長處理的專業能力（如研究、寫程式、審查）。
   - `Message` & `TextPart`：代理人間對話與訊息信封，以多段式（Parts）結構承載內容。
   - `Task` & `TaskStatus`：狀態化的任務實體，紀錄任務 ID、生命週期狀態（submitted, working, completed, failed, canceled）、訊息歷史與產出產物（Artifacts）。
   - `JSONRPCRequest` / `JSONRPCResponse`：基於 JSON-RPC 2.0 的標準傳輸封包。
"""

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Literal, Optional, Union
import uuid
from pydantic import BaseModel, ConfigDict, Field


# ============================================================================
# 1. 訊息內容與多段結構 (Content Parts & Messages)
# ============================================================================

class TextPart(BaseModel):
    """純文字內容區段 (A2A TextPart)."""

    type: Literal["text"] = "text"
    text: str = Field(..., description="文字內容")


# Phase 6 最小實作嚴格支援 TextPart，拒絕無型別約束之任意字典
Part = TextPart


class Artifact(BaseModel):
    """任務執行過程產出之不可變成果物 (A2A Artifact)."""

    id: str = Field(default_factory=lambda: uuid.uuid4().hex[:12], description="產物唯一識別碼")
    name: Optional[str] = Field(default=None, description="產物名稱 (例如: report.md)")
    description: Optional[str] = Field(default=None, description="產物描述說明")
    parts: List[Part] = Field(default_factory=list, description="產物內容區段清單")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="附加元數據")


class Message(BaseModel):
    """A2A 任務對話回合訊息 (A2A Message)."""

    role: Literal["user", "agent"] = Field(..., description="發送者角色 (user 或 agent)")
    parts: List[Part] = Field(default_factory=list, description="訊息內容區段清單")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="附加元數據")

    @classmethod
    def from_text(cls, text: str, role: Literal["user", "agent"] = "user") -> "Message":
        """便利輔助函式：自純文字字串快速建立單一 TextPart 訊息."""
        return cls(role=role, parts=[TextPart(text=text)])

    @property
    def text_content(self) -> str:
        """提取訊息中所有 TextPart 之合併文字內容."""
        return "\n".join(part.text for part in self.parts if isinstance(part, TextPart))


# ============================================================================
# 2. 任務生命週期與狀態 (Task Lifecycle & Status)
# ============================================================================

class TaskState(str, Enum):
    """A2A 1.0.0 官方標準任務生命週期狀態."""

    SUBMITTED = "submitted"            # 任務已提交，等待處理
    WORKING = "working"                # 任務正在處理/執行中
    INPUT_REQUIRED = "input_required"  # 代理人需要呼叫者補充更多資訊或授權
    COMPLETED = "completed"            # 任務已成功圓滿完成
    FAILED = "failed"                  # 任務執行失敗
    CANCELED = "canceled"              # 任務已被取消


class TaskStatus(BaseModel):
    """A2A 任務狀態容器."""

    state: TaskState = Field(default=TaskState.SUBMITTED, description="當前任務狀態")
    message: Optional[Message] = Field(default=None, description="狀態附加說明或最新回覆訊息")
    timestamp: datetime = Field(default_factory=datetime.now, description="狀態更新時間戳記")


class Task(BaseModel):
    """A2A 核心狀態化工作單元 (A2A Task)."""

    id: str = Field(default_factory=lambda: uuid.uuid4().hex, description="任務全局唯一 ID")
    status: TaskStatus = Field(default_factory=TaskStatus, description="任務當前狀態")
    history: List[Message] = Field(default_factory=list, description="任務對話訊息歷程")
    artifacts: List[Artifact] = Field(default_factory=list, description="任務產出之成果物清單")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="任務自訂元數據")


# A2A 1.0 SendMessage 回應可以是狀態化 Task 或直接 Message 回應
SendMessageResponse = Union[Task, Message]


# ============================================================================
# 3. 代理人名片與技能聲明 (Agent Card & Skills)
# ============================================================================

class AgentSkill(BaseModel):
    """A2A 官方標準 AgentSkill 技能能力聲明."""

    id: str = Field(..., description="技能唯一標識符 (如 deep_research, code_review)")
    name: str = Field(..., description="技能易讀名稱")
    description: str = Field(..., description="技能功能與適用場景說明")
    tags: List[str] = Field(default_factory=list, description="分類與檢索標籤")
    examples: List[str] = Field(default_factory=list, description="範例 Prompt 或使用情境")
    input_modes: List[str] = Field(default_factory=lambda: ["text/plain"], description="支援輸入 MIME 類型")
    output_modes: List[str] = Field(default_factory=lambda: ["text/plain"], description="支援輸出 MIME 類型")


class AgentCapabilities(BaseModel):
    """A2A 協定進階特性支援能力聲明."""

    streaming: bool = Field(default=False, description="是否支援 SSE 即時串流 (SendStreamingMessage)")
    push_notifications: bool = Field(default=False, description="是否支援 Webhook 推播通知")


class AgentCard(BaseModel):
    """A2A 1.0.0 官方標準 Agent Card (代理人名片)."""

    name: str = Field(..., description="代理人名稱 (例如: M.Ber, ResearchAgent)")
    description: str = Field(..., description="代理人職責簡介與角色定位")
    url: str = Field(..., description="A2A 伺服器通訊基底 URL")
    version: str = Field(default="1.0.0", description="代理人實作版本")
    protocol_version: str = Field(default="1.0.0", description="支援的 A2A 協定版本")
    capabilities: AgentCapabilities = Field(default_factory=AgentCapabilities, description="支援特性能力")
    skills: List[AgentSkill] = Field(default_factory=list, description="具備的專業技能清單")
    default_input_modes: List[str] = Field(default_factory=lambda: ["text/plain"], description="預設支援之輸入 MIME 格式")
    default_output_modes: List[str] = Field(default_factory=lambda: ["text/plain"], description="預設支援之輸出 MIME 格式")
    security_schemes: Dict[str, Any] = Field(default_factory=dict, description="OpenAPI 風格安全認證架構宣告")
    security: List[Dict[str, List[str]]] = Field(default_factory=list, description="套用之安全認證清單")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="擴充元數據")


# ============================================================================
# 4. JSON-RPC 2.0 傳輸信封 (Wire Protocol Envelopes)
# ============================================================================

class JSONRPCRequest(BaseModel):
    """標準 JSON-RPC 2.0 請求信封."""

    jsonrpc: Literal["2.0"] = "2.0"
    method: str = Field(..., description="遠端調用方法名稱 (如 SendMessage, GetTask, CancelTask)")
    params: Dict[str, Any] = Field(default_factory=dict, description="方法參數字典")
    id: Union[str, int] = Field(default_factory=lambda: uuid.uuid4().hex, description="請求關聯 ID")


class JSONRPCError(BaseModel):
    """標準 JSON-RPC 2.0 錯誤物件."""

    code: int = Field(..., description="錯誤代碼 (如 -32600 Invalid Request, -32601 Method Not Found)")
    message: str = Field(..., description="錯誤原因說明")
    data: Optional[Any] = Field(default=None, description="附加除錯資料")


class JSONRPCResponse(BaseModel):
    """標準 JSON-RPC 2.0 回應信封."""

    jsonrpc: Literal["2.0"] = "2.0"
    id: Optional[Union[str, int]] = Field(default=None, description="對應之請求關聯 ID")
    result: Optional[Any] = Field(default=None, description="成功執行之結果物件")
    error: Optional[JSONRPCError] = Field(default=None, description="執行失敗時之錯誤物件")

    @property
    def is_success(self) -> bool:
        """判斷回應是否成功且無錯誤."""
        return self.error is None and self.result is not None
