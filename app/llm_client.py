import logging
from typing import Optional
from google import genai
from google.genai import types

from app.config import get_settings

logger = logging.getLogger(__name__)

def get_llm_client() -> Optional[genai.Client]:
    settings = get_settings()
    api_key = settings.gemini_api_key
    if not api_key:
        logger.warning("Gemini API key is missing. LLM client cannot be initialized.")
        return None

    http_options = types.HttpOptions(
        timeout=settings.gemini_timeout_seconds,
        retry_options=types.HttpRetryOptions(
            attempts=settings.gemini_max_retries,
            initial_delay=1.0,
            max_delay=10.0,
            exp_base=2.0,
            jitter=1.0,
            http_status_codes=[429, 500, 502, 503, 504]
        )
    )
    return genai.Client(api_key=api_key, http_options=http_options)

def get_llm_client_or_raise() -> genai.Client:
    client = get_llm_client()
    if not client:
        raise ValueError("Configuration Error: Gemini API key is missing. Please set GEMINI_API_KEY in the .env file.")
    return client
