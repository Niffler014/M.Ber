"""M.Ber Unified LLM & ChatModel Factory (大型語言模型統一工廠模組).
Phase 8 - P8-03.5: Real Conversation Integration

【新手教學 / 觀念解析】：
1. 為什麼需要 Model Factory？
   - 避免在各個模組中散落模型初始化與金鑰讀取邏輯。
   - 採用明確 Provider 選擇機制（透過 `MODEL_PROVIDER` 與 `MODEL_NAME` 設定），絕不猜測。
   - 預設產出「純文字、無工具綁定（Tool-Free）」的標準 LangChain ChatModel，
     專供 `LocalReasoningAdapter` 與 `Planner` 使用，避免產生雙重路由權威。
"""

import logging
import os
from typing import Any, Optional

logger = logging.getLogger("mber.orchestration")


def get_chat_model(
    provider: Optional[str] = None,
    model_name: Optional[str] = None,
    temperature: float = 0.7,
    timeout: float = 30.0,
) -> Optional[Any]:
    """根據明確的環境變數或參數建立並回傳預設的 LangChain ChatModel 實例 (Tool-Free).

    明確選擇原則：
    1. 優先使用傳入的 `provider` 參數，或讀取 `MODEL_PROVIDER` 環境變數 (可為 'google', 'openai', 'anthropic')。
    2. 若未設定 `MODEL_PROVIDER`：
       - 若僅有單一 API Key 存在，則明確選用該唯一 Provider；
       - 若有複數或無任何 API Key 存在，不作盲目猜測，回傳 None 並記錄日誌。

    Args:
        provider: 明確指定之模型供應商 (例如 'google', 'openai', 'anthropic')
        model_name: 自訂模型名稱 (例如 'gemini-1.5-flash', 'gpt-4o-mini')
        temperature: 溫度參數 (預設 0.7)
        timeout: 請求逾時秒數 (預設 30.0 秒)

    Returns:
        LangChain BaseChatModel 實例或 None (若未設定則走離線降級)
    """
    target_provider = (provider or os.getenv("MODEL_PROVIDER", "")).strip().lower()
    custom_model = model_name or os.getenv("MODEL_NAME")

    google_key = os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")
    openai_key = os.getenv("OPENAI_API_KEY")
    anthropic_key = os.getenv("ANTHROPIC_API_KEY")

    # 檢驗金鑰是否為有效值（非範本佔位符號）
    def is_valid(key: Optional[str]) -> bool:
        return bool(key and key.strip() and not key.strip().startswith("your_"))

    has_google = is_valid(google_key)
    has_openai = is_valid(openai_key)
    has_anthropic = is_valid(anthropic_key)

    # 若未明確指定 provider，檢查是否只有唯一一個有效金鑰
    if not target_provider:
        valid_providers = []
        if has_google:
            valid_providers.append("google")
        if has_openai:
            valid_providers.append("openai")
        if has_anthropic:
            valid_providers.append("anthropic")

        if len(valid_providers) == 1:
            target_provider = valid_providers[0]
            logger.info(f"[ModelFactory] Inferred single valid provider: '{target_provider}'")
        elif len(valid_providers) > 1:
            logger.warning(
                f"[ModelFactory] Multiple API keys detected ({valid_providers}) but MODEL_PROVIDER is not set. "
                f"Please set MODEL_PROVIDER explicitly in .env to choose your model."
            )
            return None
        else:
            logger.info("[ModelFactory] No valid cloud LLM API key detected. Model disabled (offline mode).")
            return None

    # 依明確 Provider 進行初始化
    if target_provider in ["google", "gemini"]:
        if not has_google:
            logger.warning("[ModelFactory] Google provider requested but GOOGLE_API_KEY is missing.")
            return None
        try:
            from langchain_google_genai import ChatGoogleGenerativeAI
            m_name = custom_model or "gemini-1.5-flash"
            logger.info(f"[ModelFactory] Initializing Google Gemini model: {m_name}")
            return ChatGoogleGenerativeAI(
                model=m_name,
                google_api_key=google_key,
                temperature=temperature,
                request_timeout=timeout,
            )
        except ImportError:
            logger.warning("[ModelFactory] langchain_google_genai package not installed.")
        except Exception as e:
            logger.error(f"[ModelFactory] Failed to initialize Google Gemini: {e}")
        return None

    elif target_provider in ["openai"]:
        if not has_openai:
            logger.warning("[ModelFactory] OpenAI provider requested but OPENAI_API_KEY is missing.")
            return None
        try:
            from langchain_openai import ChatOpenAI
            m_name = custom_model or "gpt-4o-mini"
            logger.info(f"[ModelFactory] Initializing OpenAI model: {m_name}")
            return ChatOpenAI(
                model=m_name,
                api_key=openai_key,
                temperature=temperature,
                timeout=timeout,
            )
        except ImportError:
            logger.warning("[ModelFactory] langchain_openai package not installed.")
        except Exception as e:
            logger.error(f"[ModelFactory] Failed to initialize OpenAI: {e}")
        return None

    elif target_provider in ["anthropic", "claude"]:
        if not has_anthropic:
            logger.warning("[ModelFactory] Anthropic provider requested but ANTHROPIC_API_KEY is missing.")
            return None
        try:
            from langchain_anthropic import ChatAnthropic
            m_name = custom_model or "claude-3-5-haiku-20241022"
            logger.info(f"[ModelFactory] Initializing Anthropic model: {m_name}")
            return ChatAnthropic(
                model=m_name,
                api_key=anthropic_key,
                temperature=temperature,
                timeout=timeout,
            )
        except ImportError:
            logger.warning("[ModelFactory] langchain_anthropic package not installed.")
        except Exception as e:
            logger.error(f"[ModelFactory] Failed to initialize Anthropic: {e}")
        return None

    else:
        logger.warning(f"[ModelFactory] Unknown MODEL_PROVIDER: '{target_provider}'")
        return None
