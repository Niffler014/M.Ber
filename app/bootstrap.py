"""M.Ber Unified Application Composition Root (統一應用程式組裝工廠).
Phase 8 - P8-05A: Multi-Channel Integration (Web, LINE, CLI)

【新手教學 / 觀念解析】：
1. 為什麼需要統一 Composition Root (Bootstrap)？
   - 避免各個 Channel (Web Gateway, LINE Gateway, CLI) 各自實例化獨立的 OrchestrationService、
     MCPManager、DiscoveryService 或 Planner。
   - 確保所有通道共用同一套：
     - ChatModel
     - MCPManager (包含本機與第三方 MCP 工具)
     - AgentDiscoveryService (A2A 外部 Peer 探索)
     - MemoryService (語意與長期記憶儲存)
     - Planner & Orchestrator (單一調度權威)
"""

import logging
from typing import Any, Optional

from app.a2a.discovery import AgentDiscoveryService
from app.mcp.manager import MCPManager
from app.orchestration.service import OrchestrationService
from memory.service import MemoryService

logger = logging.getLogger("mber.bootstrap")

_global_orchestration_service: Optional[OrchestrationService] = None


def create_orchestration_service(
    llm: Optional[Any] = None,
    mcp_manager: Optional[MCPManager] = None,
    discovery_service: Optional[AgentDiscoveryService] = None,
    memory_service: Optional[MemoryService] = None,
) -> OrchestrationService:
    """建立新的 OrchestrationService 實例 (工廠函式)."""
    logger.info("[Bootstrap] Creating new OrchestrationService instance")
    return OrchestrationService(
        llm=llm,
        mcp_manager=mcp_manager,
        discovery_service=discovery_service,
        memory_service=memory_service,
    )


def get_orchestration_service(
    llm: Optional[Any] = None,
    mcp_manager: Optional[MCPManager] = None,
    discovery_service: Optional[AgentDiscoveryService] = None,
    memory_service: Optional[MemoryService] = None,
    force_new: bool = False,
) -> OrchestrationService:
    """取得或建立全域共享之 OrchestrationService 實例 (Singleton / Dependency Injection).

    Args:
        llm: 自訂 ChatModel 實例
        mcp_manager: 自訂 MCPManager 實例
        discovery_service: 自訂 AgentDiscoveryService 實例
        memory_service: 自訂 MemoryService 實例
        force_new: 是否強制重新建立新實例

    Returns:
        OrchestrationService 實例
    """
    global _global_orchestration_service
    if _global_orchestration_service is None or force_new:
        _global_orchestration_service = create_orchestration_service(
            llm=llm,
            mcp_manager=mcp_manager,
            discovery_service=discovery_service,
            memory_service=memory_service,
        )
    return _global_orchestration_service


def reset_orchestration_service() -> None:
    """重設全域 OrchestrationService 實例 (供測試環境重置狀態使用)."""
    global _global_orchestration_service
    _global_orchestration_service = None
