"""Tests for M.Ber Unified LLM & ChatModel Factory (模型工廠測試).

驗證項目：
1. OpenAI 在未設定 OPENAI_BASE_URL 時，維持官方預設行為（不帶 base_url 參數）。
2. OpenAI 在設定 OPENAI_BASE_URL 時，正確傳入 custom base_url（支援連接本機 llama.cpp / vLLM）。
3. 本地 OpenAI-compatible server 仍使用 MODEL_PROVIDER=openai，並可接受 dummy/non-empty OPENAI_API_KEY。
4. 當 Provider 或 API Key 缺失/未指定/未知時，維持原有安全降級行為（回傳 None）。
5. 當存在多個 API Key 但未指定 MODEL_PROVIDER 時，不盲目猜測並回傳 None。
"""

import types
from typing import Any, Optional
from unittest.mock import patch
import pytest

from app.orchestration.model_factory import get_chat_model


class FakeChatOpenAI:
    """Mock ChatOpenAI class 用於驗證工廠參數傳遞 (不依賴外部連線與套件安裝狀態)."""

    def __init__(
        self,
        model: str,
        api_key: Optional[str] = None,
        temperature: float = 0.7,
        timeout: float = 30.0,
        base_url: Optional[str] = None,
        **kwargs: Any,
    ) -> None:
        self.model_name = model
        self.api_key = api_key
        self.temperature = temperature
        self.timeout = timeout
        self.base_url = base_url
        self.openai_api_base = base_url
        self.extra_kwargs = kwargs


@pytest.fixture(autouse=True)
def mock_langchain_openai():
    """自動注入 mock langchain_openai 模組供測試驗證."""
    fake_module = types.SimpleNamespace(ChatOpenAI=FakeChatOpenAI)
    with patch.dict("sys.modules", {"langchain_openai": fake_module}):
        yield fake_module


def test_openai_without_base_url_default_behavior(monkeypatch):
    """驗證未提供 OPENAI_BASE_URL 時，ChatOpenAI 維持官方預設行為（不傳遞 base_url）."""
    monkeypatch.setenv("MODEL_PROVIDER", "openai")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-valid-openai-key-test")
    monkeypatch.delenv("OPENAI_BASE_URL", raising=False)

    model = get_chat_model(model_name="gpt-4o-mini")
    assert model is not None
    assert model.model_name == "gpt-4o-mini"
    assert model.api_key == "sk-valid-openai-key-test"
    # 未設定 OPENAI_BASE_URL 時，不傳入 base_url，維持 None
    assert model.base_url is None
    assert model.openai_api_base is None


def test_openai_with_custom_base_url(monkeypatch):
    """驗證提供 OPENAI_BASE_URL 時，ChatOpenAI 正確傳入自訂 base_url (如本機 llama.cpp)."""
    custom_url = "http://localhost:8080/v1"
    monkeypatch.setenv("MODEL_PROVIDER", "openai")
    monkeypatch.setenv("OPENAI_API_KEY", "dummy-key-for-local-llama")
    monkeypatch.setenv("OPENAI_BASE_URL", custom_url)
    monkeypatch.setenv("MODEL_NAME", "qwen2.5-7b-instruct")

    model = get_chat_model()
    assert model is not None
    assert model.model_name == "qwen2.5-7b-instruct"
    assert model.api_key == "dummy-key-for-local-llama"
    assert model.base_url == custom_url
    assert model.openai_api_base == custom_url


def test_openai_with_blank_base_url_ignored(monkeypatch):
    """驗證 OPENAI_BASE_URL 為純空白字串時，視為未設定並忽略."""
    monkeypatch.setenv("MODEL_PROVIDER", "openai")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-valid-key")
    monkeypatch.setenv("OPENAI_BASE_URL", "   ")

    model = get_chat_model()
    assert model is not None
    assert model.base_url is None
    assert model.openai_api_base is None


def test_missing_model_provider_and_no_keys(monkeypatch):
    """驗證無任何 API 金鑰時，安全回傳 None 走離線降級."""
    monkeypatch.delenv("MODEL_PROVIDER", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    model = get_chat_model()
    assert model is None


def test_unknown_model_provider(monkeypatch):
    """驗證未知 MODEL_PROVIDER 時回傳 None."""
    monkeypatch.setenv("MODEL_PROVIDER", "unsupported_provider_xyz")
    model = get_chat_model()
    assert model is None


def test_explicit_provider_missing_key(monkeypatch):
    """驗證明確指定 provider 但缺少對應 API Key 時回傳 None."""
    monkeypatch.setenv("MODEL_PROVIDER", "openai")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    model = get_chat_model()
    assert model is None


def test_ambiguous_multiple_keys_without_provider(monkeypatch):
    """驗證存在多個有效 API Key 但未設定 MODEL_PROVIDER 時，不盲目猜測並回傳 None."""
    monkeypatch.delenv("MODEL_PROVIDER", raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-key")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test-key")

    model = get_chat_model()
    assert model is None
