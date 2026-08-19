"""M.Ber A2A (Agent-to-Agent) Interoperability Package (Phase 6).

提供符合 A2A 1.0.0 規範之核心資料模型、發現服務與 JSON-RPC 2.0 客戶端：
- AgentCard, AgentSkill, AgentCapabilities: 代理人名片與技能宣告
- Task, TaskStatus, TaskState: 任務實體與生命週期狀態
- Message, TextPart, Artifact: 多段式訊息與成果產物
- JSONRPCRequest, JSONRPCResponse, JSONRPCError: JSON-RPC 2.0 協定封包
- AgentDiscoveryService: 代理人配置載入與探索服務
- A2AClient, A2AClientError: JSON-RPC 2.0 遠端通訊客戶端
"""

from app.a2a.models import (
    AgentCapabilities,
    AgentCard,
    AgentSkill,
    Artifact,
    JSONRPCError,
    JSONRPCRequest,
    JSONRPCResponse,
    Message,
    Part,
    SendMessageResponse,
    Task,
    TaskState,
    TaskStatus,
    TextPart,
)
from app.a2a.discovery import AgentDiscoveryService
from app.a2a.client import A2AClient, A2AClientError

__all__ = [
    "AgentCapabilities",
    "AgentCard",
    "AgentSkill",
    "Artifact",
    "JSONRPCError",
    "JSONRPCRequest",
    "JSONRPCResponse",
    "Message",
    "Part",
    "SendMessageResponse",
    "Task",
    "TaskState",
    "TaskStatus",
    "TextPart",
    "AgentDiscoveryService",
    "A2AClient",
    "A2AClientError",
]
