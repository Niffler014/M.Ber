"""Phase 8 P8-03.5 Local Reasoning Adapter Unit Test Suite.

驗證項目：
1. 具備 ChatModel 時正常調用模型產生自然語言回答
2. 傳回模型實際文字回答，絕不包含「已為您處理完成：{goal}」佔位文字
3. 模型例外拋出時，由 LocalExecutor 封裝為 FAILED 狀態
4. 呼叫逾時（TimeoutError）時，由 LocalExecutor 封裝為 TIMEOUT 狀態
5. 歷史訊息與上下文（messages）正確注入至 Prompt
6. 未配置 ChatModel 且無離線知識庫時，拋出明確例外（FAILED），絕不產生假成功
7. 離線預設知識（如問候語、DI 解釋）正常回覆
"""

import socket
from typing import Any, List, Optional
import pytest
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage

from app.orchestration.executors import LocalExecutor
from app.orchestration.local_reasoning import LocalReasoningAdapter
from app.orchestration.models import (
    ExecutionContext,
    ExecutionResult,
    ExecutionStatus,
    ExecutionType,
    SubTask,
)


class FakeListChatModel:
    """測試專用輕量 Fake ChatModel (可自訂回覆序列與例外拋出)."""

    def __init__(
        self,
        responses: Optional[List[str]] = None,
        error_to_raise: Optional[Exception] = None,
    ) -> None:
        self.responses = responses or ["這是一則由語言模型產生的真實分析與回答。"]
        self.call_count = 0
        self.invoked_prompts: List[List[BaseMessage]] = []
        self.error_to_raise = error_to_raise

    def invoke(self, messages: List[BaseMessage]) -> AIMessage:
        self.call_count += 1
        self.invoked_prompts.append(messages)
        if self.error_to_raise is not None:
            raise self.error_to_raise
        idx = min(self.call_count - 1, len(self.responses) - 1)
        return AIMessage(content=self.responses[idx])


def test_local_reasoning_uses_chat_model() -> None:
    """驗證 LocalReasoningAdapter 呼叫注入之 ChatModel."""
    fake_model = FakeListChatModel(responses=["肚子餓可以先吃個三明治或麵包墊胃！"])
    adapter = LocalReasoningAdapter(llm=fake_model)
    task = SubTask(
        task_id="task_001",
        execution_type=ExecutionType.LOCAL,
        goal="我肚子很餓",
        target="general_qa",
    )

    output = adapter.handle_reasoning(task)

    assert fake_model.call_count == 1
    assert "肚子餓可以先吃個三明治" in output
    assert "已為您處理完成" not in output


def test_local_reasoning_returns_model_response_via_local_executor() -> None:
    """驗證經由 LocalExecutor 封裝後為 ExecutionStatus.SUCCESS 並保留模型輸出."""
    fake_model = FakeListChatModel(responses=["【Dependency Injection】是一種軟體設計模式。"])
    adapter = LocalReasoningAdapter(llm=fake_model)

    executor = LocalExecutor()
    executor.register_handler("general_qa", adapter.handle_reasoning)

    task = SubTask(
        task_id="task_002",
        execution_type=ExecutionType.LOCAL,
        goal="什麼是 dependency injection",
        target="general_qa",
    )

    result: ExecutionResult = executor.execute(task)

    assert result.status == ExecutionStatus.SUCCESS
    assert result.execution_type == ExecutionType.LOCAL
    assert result.result == "【Dependency Injection】是一種軟體設計模式。"
    assert result.error is None


def test_local_reasoning_does_not_return_placeholder_template() -> None:
    """驗證本地推理回覆絕不使用舊版佔位模版."""
    fake_model = FakeListChatModel(responses=["天氣很好，出門散步是個好主意。"])
    adapter = LocalReasoningAdapter(llm=fake_model)
    task = SubTask(
        task_id="task_003",
        execution_type=ExecutionType.LOCAL,
        goal="今天天氣真好",
        target="general_qa",
    )

    output = adapter.handle_reasoning(task)
    assert output == "天氣很好，出門散步是個好主意。"
    assert "已為您處理完成" not in output


def test_local_reasoning_model_failure_returns_failed() -> None:
    """驗證模型調用失敗（例如 API Error）時由 LocalExecutor 映射為 FAILED."""
    fake_model = FakeListChatModel(error_to_raise=RuntimeError("Provider API rate limit exceeded"))
    adapter = LocalReasoningAdapter(llm=fake_model)

    executor = LocalExecutor()
    executor.register_handler("general_qa", adapter.handle_reasoning)

    task = SubTask(
        task_id="task_004",
        execution_type=ExecutionType.LOCAL,
        goal="請幫我寫一首詩",
        target="general_qa",
    )

    result: ExecutionResult = executor.execute(task)

    assert result.status == ExecutionStatus.FAILED
    assert "Provider API rate limit exceeded" in (result.error or "")


def test_local_reasoning_timeout_returns_timeout() -> None:
    """驗證模型調用逾時（TimeoutError / socket.timeout）時映射為 TIMEOUT."""
    fake_model = FakeListChatModel(error_to_raise=TimeoutError("Model response timed out after 30s"))
    adapter = LocalReasoningAdapter(llm=fake_model)

    executor = LocalExecutor()
    executor.register_handler("general_qa", adapter.handle_reasoning)

    task = SubTask(
        task_id="task_005",
        execution_type=ExecutionType.LOCAL,
        goal="處理超長文本分析",
        target="general_qa",
    )

    result: ExecutionResult = executor.execute(task)

    assert result.status == ExecutionStatus.TIMEOUT
    assert "timed out" in (result.error or "").lower()


def test_local_reasoning_receives_relevant_messages() -> None:
    """驗證 ExecutionContext 中的歷史訊息正確傳遞至 Prompt."""
    fake_model = FakeListChatModel(responses=["在軟體工程中，SOLID 代表物件導向設計的五大原則。"])
    adapter = LocalReasoningAdapter(llm=fake_model)

    history = [
        HumanMessage(content="我們剛剛聊到物件導向設計"),
        AIMessage(content="是的，物件導向有封裝、繼承與多型。"),
        HumanMessage(content="那 SOLID 原則是什麼？"),
    ]
    context = ExecutionContext(metadata={"messages": history})

    task = SubTask(
        task_id="task_006",
        execution_type=ExecutionType.LOCAL,
        goal="那 SOLID 原則是什麼？",
        target="general_qa",
    )

    adapter.handle_reasoning(task, context=context)

    assert fake_model.call_count == 1
    passed_msgs = fake_model.invoked_prompts[0]
    # 包含 SystemMessage + 3 筆歷史訊息
    assert len(passed_msgs) == 4
    assert any("物件導向設計" in m.content for m in passed_msgs)
    assert any("SOLID 原則" in m.content for m in passed_msgs)


def test_no_model_config_does_not_return_placeholder_success() -> None:
    """驗證若未配置 ChatModel 且請求無對應離線知識庫，拋出例外並標記 FAILED (絕不以佔位假成功欺騙)."""
    adapter = LocalReasoningAdapter(llm=None)
    executor = LocalExecutor()
    executor.register_handler("general_qa", adapter.handle_reasoning)

    task = SubTask(
        task_id="task_007",
        execution_type=ExecutionType.LOCAL,
        goal="隨機無離線對應之未知主題 123456",
        target="general_qa",
    )

    result: ExecutionResult = executor.execute(task)

    assert result.status == ExecutionStatus.FAILED
    assert "未設定語言模型" in (result.error or "")
    assert result.result is None


def test_local_reasoning_offline_knowledge_fallback() -> None:
    """驗證無模型時之常見問答（如 DI / Decorator / 飢餓）具備友善自然語言回覆."""
    adapter = LocalReasoningAdapter(llm=None)

    task_di = SubTask(
        task_id="t_di",
        execution_type=ExecutionType.LOCAL,
        goal="dependency injection 是什麼",
        target="general_qa",
    )
    res_di = adapter.handle_reasoning(task_di)
    assert "依賴注入" in res_di
    assert "解耦" in res_di

    task_hunger = SubTask(
        task_id="t_hunger",
        execution_type=ExecutionType.LOCAL,
        goal="我肚子很餓",
        target="general_qa",
    )
    res_hunger = adapter.handle_reasoning(task_hunger)
    assert "肚子餓" in res_hunger or "熱食" in res_hunger
