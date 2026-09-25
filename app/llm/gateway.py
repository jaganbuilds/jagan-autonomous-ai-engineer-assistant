import logging
from typing import List, Dict, Any, Optional, Type
from pydantic import BaseModel

from app.config import get_settings
from app.llm.models import ChatMessage, LLMResponse, LLMError, LLMUnavailableError
from app.llm.providers import OpenRouterProvider, OllamaProvider

logger = logging.getLogger(__name__)

OPENROUTER_MODELS = [
    "qwen/qwen3.8-27b:free",
    "nvidia/nemotron-3-ultra-550b-a55b:free",
    "inclusionai/ling-3.0-flash-sante:free",
    "poolside/laguna-s-2.1:free",
    "nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free",
]

class LLMGateway:
    def __init__(self):
        self.openrouter = OpenRouterProvider()
        self.ollama = OllamaProvider()
        self.settings = get_settings()

    def generate_text(self, prompt: str, temperature: float = 0.7) -> str:
        for model in OPENROUTER_MODELS:
            try:
                logger.info(f"Trying OpenRouter model: {model}")
                result = self.openrouter.generate_text(model, prompt, temperature)
                logger.info(f"SUCCESS: {model}")
                return result
            except LLMError as e:
                logger.warning(f"FAILED: {model} | Reason: {str(e)}")
        
        # Fallback to Ollama
        try:
            logger.info(f"Falling back to Ollama model: {self.settings.ollama_model}")
            return self.ollama.generate_text(self.settings.ollama_model, prompt, temperature)
        except LLMError as e:
            logger.error(f"Ollama fallback failed: {str(e)}")
            raise LLMUnavailableError("All LLM providers failed")

    def generate_json(self, prompt: str, schema: Optional[Type[BaseModel]] = None, temperature: float = 0.0) -> Any:
        for model in OPENROUTER_MODELS:
            try:
                logger.info(f"Trying OpenRouter model: {model}")
                result = self.openrouter.generate_json(model, prompt, schema, temperature)
                logger.info(f"SUCCESS: {model}")
                return result
            except LLMError as e:
                logger.warning(f"FAILED: {model} | Reason: {str(e)}")
        
        # Fallback to Ollama
        try:
            logger.info(f"Falling back to Ollama model: {self.settings.ollama_model}")
            return self.ollama.generate_json(self.settings.ollama_model, prompt, schema, temperature)
        except LLMError as e:
            logger.error(f"Ollama fallback failed: {str(e)}")
            raise LLMUnavailableError("All LLM providers failed")

    def chat(self, messages: List[ChatMessage], tools: Optional[List[Dict[str, Any]]] = None, temperature: float = 0.7) -> LLMResponse:
        for model in OPENROUTER_MODELS:
            try:
                logger.info(f"Trying OpenRouter model: {model}")
                result = self.openrouter.chat(model, messages, tools, temperature)
                logger.info(f"SUCCESS: {model}")
                return result
            except LLMError as e:
                logger.warning(f"FAILED: {model} | Reason: {str(e)}")
        
        # Fallback to Ollama
        try:
            logger.info(f"Falling back to Ollama model: {self.settings.ollama_model}")
            return self.ollama.chat(self.settings.ollama_model, messages, tools, temperature)
        except LLMError as e:
            logger.error(f"Ollama fallback failed: {str(e)}")
            raise LLMUnavailableError("All LLM providers failed")

# Global singleton
gateway = LLMGateway()
