"""Pytest Configuration and Test Isolation Fixtures."""

import pytest


@pytest.fixture(autouse=True)
def clean_test_environment(monkeypatch):
    """確保單元測試在純淨、無外部伺服器依賴的環境下運行 (避免受開發者本機 .env 影響)."""
    monkeypatch.setenv("MODEL_PROVIDER", "")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_BASE_URL", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
