"""Unit & Integration Tests for M.Ber Web API Gateway (Phase 8 - P8-01).

驗證項目：
1. GET /api/health 健康檢查端點回傳狀態與規範版本
2. POST /api/chat 正常對話處理與 DTO 契約
3. POST /api/chat 空白訊息、純空白字元與缺少欄位阻擋 (回傳 400 而非 FastAPI 預設 422)
4. POST /api/chat 內部未預期例外回傳 500 與結構化錯誤
5. 應用層執行失敗 (Application-Level FAILED) 語意：HTTP 回傳 200 且 status="failed"
6. 支援依賴注入 (Injected OrchestrationService)
7. 本地推理 (Local Reasoning) 端到端工作流程驗證
8. CORS Headers 驗證 (限定 Localhost Vite 前端)
9. ChatResponse 契約完整性驗證 (包含 conversation_id 與 trace 預留)
10. 防止內部 Domain Model (TaskPlan / ExecutionResult / AggregatedResult) 意外洩漏
"""

from typing import Any, List, Optional
from unittest.mock import MagicMock
import pytest
from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage, BaseMessage

from app import __version__
from app.interfaces.web.gateway import create_web_app
from app.interfaces.web.models import ChatRequest, ChatResponse, HealthResponse
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
from app.orchestration.service import OrchestrationService


@pytest.fixture
def fake_orchestration_service():
    """建立可控制回傳結果的 Mock/Fake OrchestrationService."""
    service = MagicMock(spec=OrchestrationService)

    # 預設成功回覆
    sample_plan = TaskPlan(
        plan_id="plan_test_001",
        user_goal="測試使用者請求",
        tasks=[
            SubTask(
                task_id="task_001",
                execution_type=ExecutionType.LOCAL,
                goal="測試目標",
                target="general_qa",
            )
        ],
    )
    sample_results = [
        ExecutionResult(
            task_id="task_001",
            execution_type=ExecutionType.LOCAL,
            status=ExecutionStatus.SUCCESS,
            source="local:general_qa",
            result="這是測試成功回應。",
        )
    ]
    sample_agg = AggregatedResult(
        plan_id="plan_test_001",
        results=sample_results,
    )
    service.invoke_with_details.return_value = OrchestrationResponse(
        message=AIMessage(content="這是測試成功回應。"),
        plan=sample_plan,
        aggregated=sample_agg,
    )
    return service


@pytest.fixture
def client(fake_orchestration_service):
    """建立綁定 Fake Service 之 TestClient."""
    app = create_web_app(orchestration_service=fake_orchestration_service)
    return TestClient(app)


def test_health_endpoint(client: TestClient) -> None:
    """測試 GET /api/health 回傳 minimal 結構與規範版本."""
    response = client.get("/api/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["service"] == "mber"
    assert data["version"] == __version__
    # 確保 P8-01 未洩漏內部 MCP/A2A 清單 (依使用者調整規範)
    assert "mcp_servers" not in data
    assert "a2a_agents" not in data


def test_chat_endpoint_success(client: TestClient, fake_orchestration_service) -> None:
    """測試 POST /api/chat 成功接收訊息並回傳 ChatResponse."""
    payload = {
        "message": "你好 M.Ber",
        "conversation_id": "session_123",
    }
    response = client.post("/api/chat", json=payload)
    assert response.status_code == 200
    data = response.json()

    assert data["message"] == "這是測試成功回應。"
    assert data["status"] == "success"
    assert data["plan_id"] == "plan_test_001"
    assert data["conversation_id"] == "session_123"
    assert data["trace"] == []

    # 驗證傳遞給 OrchestrationService 的訊息
    fake_orchestration_service.invoke_with_details.assert_called_once()
    called_messages = fake_orchestration_service.invoke_with_details.call_args[0][0]
    assert len(called_messages) == 1
    assert called_messages[0].content == "你好 M.Ber"


def test_chat_endpoint_empty_message(client: TestClient) -> None:
    """測試發送空字串時回傳 400 Bad Request (而非 422)."""
    response = client.post("/api/chat", json={"message": ""})
    assert response.status_code == 400
    data = response.json()
    assert "error" in data
    assert data["error"]["code"] == "invalid_request"
    assert "message" in data["error"]["message"]


def test_chat_endpoint_whitespace_message(client: TestClient) -> None:
    """測試發送純空白字串時回傳 400 Bad Request."""
    response = client.post("/api/chat", json={"message": "   \n\t  "})
    assert response.status_code == 400
    data = response.json()
    assert data["error"]["code"] == "invalid_request"


def test_chat_endpoint_missing_message(client: TestClient) -> None:
    """測試缺少 message 欄位時回傳 400 Bad Request."""
    response = client.post("/api/chat", json={"conversation_id": "123"})
    assert response.status_code == 400
    data = response.json()
    assert data["error"]["code"] == "invalid_request"


def test_chat_endpoint_validation_error_returns_400_not_422(client: TestClient) -> None:
    """明確驗證 FastAPI 預設的 422 Unprocessable Entity 已被替換為 400."""
    response = client.post("/api/chat", json={"message": None})
    assert response.status_code == 400
    assert response.status_code != 422
    data = response.json()
    assert data["error"]["code"] == "invalid_request"


def test_chat_endpoint_orchestration_failure(fake_orchestration_service) -> None:
    """測試後端發生未預期異常時，回傳安全之 HTTP 500 與結構化錯誤回應."""
    fake_orchestration_service.invoke_with_details.side_effect = RuntimeError("資料庫連線爆炸")
    app = create_web_app(orchestration_service=fake_orchestration_service)
    test_client = TestClient(app, raise_server_exceptions=False)

    response = test_client.post("/api/chat", json={"message": "觸發崩潰"})
    assert response.status_code == 500
    data = response.json()
    assert data["error"]["code"] == "internal_error"
    # 確保敏感的內部 Traceback 沒有洩漏給前端
    assert "資料庫連線爆炸" not in data["error"]["message"]
    assert "伺服器內部發生未預期錯誤" in data["error"]["message"]


def test_chat_endpoint_application_failed_result(fake_orchestration_service) -> None:
    """測試應用層執行失敗時 (如 PCforge 離線)，HTTP 仍應為 200 且 status='failed'."""
    failed_plan = TaskPlan(
        plan_id="plan_fail_001",
        user_goal="配一台電腦",
        tasks=[
            SubTask(
                task_id="task_fail",
                execution_type=ExecutionType.A2A,
                goal="pcforge",
                target="pc_recommendation",
            )
        ],
    )
    failed_results = [
        ExecutionResult(
            task_id="task_fail",
            execution_type=ExecutionType.A2A,
            status=ExecutionStatus.FAILED,
            error="Peer PCforge unavailable",
        )
    ]
    failed_agg = AggregatedResult(
        plan_id="plan_fail_001",
        results=failed_results,
    )

    fake_orchestration_service.invoke_with_details.return_value = OrchestrationResponse(
        message=AIMessage(content="⚠️ 任務無法順利完成，各步驟錯誤詳情如下：\n- 任務 [task_fail] (failed): Peer PCforge unavailable"),
        plan=failed_plan,
        aggregated=failed_agg,
    )

    app = create_web_app(orchestration_service=fake_orchestration_service)
    test_client = TestClient(app)

    response = test_client.post("/api/chat", json={"message": "幫我配電腦"})
    # HTTP 傳輸層面正常完成 ➔ 200
    assert response.status_code == 200
    data = response.json()
    # 應用層業務結果標記為 failed
    assert data["status"] == "failed"
    assert "Peer PCforge unavailable" in data["message"]
    assert data["plan_id"] == "plan_fail_001"


def test_web_app_uses_injected_orchestration_service() -> None:
    """驗證 create_web_app 能正確使用注入的自訂 OrchestrationService 實例."""
    custom_service = MagicMock(spec=OrchestrationService)
    custom_service.invoke_with_details.return_value = OrchestrationResponse(
        message=AIMessage(content="來自注入服務的回應"),
        plan=TaskPlan(plan_id="plan_injected", user_goal="測試注入", tasks=[]),
        aggregated=AggregatedResult(plan_id="plan_injected", results=[]),
    )

    app = create_web_app(orchestration_service=custom_service)
    client = TestClient(app)

    response = client.post("/api/chat", json={"message": "測試注入"})
    assert response.status_code == 200
    assert response.json()["message"] == "來自注入服務的回應"
    assert custom_service.invoke_with_details.called


def test_chat_api_local_workflow() -> None:
    """整合測試：使用真實 OrchestrationService 進行本地推理解析工作流程."""
    # 建立無外部依賴之 OrchestrationService 進行確定性推理
    real_service = OrchestrationService()
    app = create_web_app(orchestration_service=real_service)
    client = TestClient(app)

    response = client.post("/api/chat", json={"message": "解釋 dependency injection"})
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert "依賴注入" in data["message"]
    assert data["plan_id"] is not None
    assert isinstance(data["trace"], list)
    assert len(data["trace"]) > 0


def test_chat_api_cors_headers() -> None:
    """測試 CORS 跨來源資源共用標頭設定 (限定 Localhost Vite)."""
    app = create_web_app(allowed_origins=["http://localhost:5173"])
    client = TestClient(app)

    # 模擬來自前端 Vite 的 Preflight OPTIONS 請求
    headers = {
        "Origin": "http://localhost:5173",
        "Access-Control-Request-Method": "POST",
        "Access-Control-Request-Headers": "Content-Type",
    }
    response = client.options("/api/chat", headers=headers)
    assert response.status_code == 200
    assert response.headers.get("access-control-allow-origin") == "http://localhost:5173"
    assert response.headers.get("access-control-allow-credentials") == "true"


def test_chat_response_contract_fields() -> None:
    """驗證 ChatResponse 模型契約欄位結構完整."""
    resp = ChatResponse(
        message="Hello",
        status="success",
        plan_id="p123",
        conversation_id="c456",
    )
    dumped = resp.model_dump()
    assert set(dumped.keys()) == {"message", "status", "plan_id", "conversation_id", "trace"}
    assert dumped["trace"] == []


def test_chat_response_does_not_expose_internal_domain_objects(fake_orchestration_service) -> None:
    """驗證 API 回應未將內部 TaskPlan/ExecutionResult/AggregatedResult 原始結構洩漏給前端."""
    app = create_web_app(orchestration_service=fake_orchestration_service)
    client = TestClient(app)

    response = client.post("/api/chat", json={"message": "查詢"})
    assert response.status_code == 200
    data = response.json()

    # 嚴格確保不會有內部欄位洩漏
    forbidden_keys = [
        "tasks",
        "subtasks",
        "depends_on",
        "dependency_results",
        "overall_status",
        "success_count",
        "failure_count",
        "skipped_count",
        "has_partial_failure",
        "results",
    ]
    for key in forbidden_keys:
        assert key not in data, f"內部領域模型欄位 '{key}' 意外暴露在 HTTP API 回應中"


def test_chat_api_uses_real_local_reasoning_result() -> None:
    """驗證 Web Chat API 使用真實 LLM (FakeChatModel) 回傳自然語言結果，絕非佔位模版."""
    from tests.test_local_reasoning import FakeListChatModel

    fake_model = FakeListChatModel(responses=["肚子餓的話，我推薦先去買一碗熱騰騰的鍋燒意麵！"])
    service = OrchestrationService(llm=fake_model)
    app = create_web_app(orchestration_service=service)
    client = TestClient(app)

    response = client.post("/api/chat", json={"message": "我肚子很餓"})
    assert response.status_code == 200
    data = response.json()

    assert data["status"] == "success"
    assert "鍋燒意麵" in data["message"]
    assert "已為您處理完成" not in data["message"]


def test_chat_api_pc_request_routes_a2a() -> None:
    """驗證口語化配電腦請求經 Web API 發送後，正確規劃至 A2A 並調用外部代理人."""
    from app.a2a.discovery import AgentDiscoveryService
    from app.a2a.models import AgentCard, AgentSkill
    from tests.test_pcforge_a2a import fake_pcforge_rpc_transport

    discovery = AgentDiscoveryService(config_path="non_existent.json")
    discovery.register_agent(
        AgentCard(
            name="PCforge",
            description="PC 配單專家",
            url="http://localhost:8001/rpc",
            skills=[
                AgentSkill(
                    id="pc_recommendation",
                    name="電腦推薦",
                    description="PC硬體推薦",
                    tags=["電腦", "pc"],
                )
            ],
        )
    )

    service = OrchestrationService(
        discovery_service=discovery,
        rpc_transport=fake_pcforge_rpc_transport,
    )
    app = create_web_app(orchestration_service=service)
    client = TestClient(app)

    response = client.post("/api/chat", json={"message": "我想配電腦"})
    assert response.status_code == 200
    data = response.json()

    assert data["status"] == "success"
    # 驗證 Trace 中有 A2A 執行痕跡
    assert any((t.get("execution_type") or "").upper() == "A2A" for t in data["trace"])

