import json
import logging
from typing import List, Dict, Any, Optional, Type
from pydantic import BaseModel
from openai import OpenAI, APIError, APIConnectionError, RateLimitError, APITimeoutError, InternalServerError

from app.llm.models import (
    ChatMessage, ToolCall, LLMResponse,
    LLMError, LLMProviderError, LLMRateLimitError, 
    LLMTimeoutError, LLMUnavailableError, LLMInvalidResponseError
)
from app.config import get_settings

logger = logging.getLogger(__name__)

def map_openai_error(e: Exception) -> LLMError:
    if isinstance(e, RateLimitError):
        return LLMRateLimitError(str(e))
    elif isinstance(e, APITimeoutError):
        return LLMTimeoutError(str(e))
    elif isinstance(e, InternalServerError):
        return LLMUnavailableError(str(e))
    elif isinstance(e, APIConnectionError):
        return LLMUnavailableError(str(e))
    elif isinstance(e, APIError):
        # Could be 502, 503, 504 mapped to generic APIError or specific
        if getattr(e, 'status_code', None) in [500, 502, 503, 504]:
            return LLMUnavailableError(str(e))
        return LLMProviderError(str(e))
    return LLMError(str(e))

def convert_messages(messages: List[ChatMessage]) -> List[Dict[str, Any]]:
    result = []
    for m in messages:
        d = {"role": m.role}
        if m.content is not None:
            d["content"] = m.content
        if m.tool_calls:
            d["tool_calls"] = [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {
                        "name": tc.name,
                        "arguments": json.dumps(tc.arguments)
                    }
                }
                for tc in m.tool_calls
            ]
        if m.tool_call_id is not None:
            d["tool_call_id"] = m.tool_call_id
        if m.name is not None:
            d["name"] = m.name
        result.append(d)
    return result

class BaseOpenAIProvider:
    def __init__(self, client: OpenAI):
        self.client = client

    def generate_text(self, model: str, prompt: str, temperature: float = 0.7) -> str:
        try:
            response = self.client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                temperature=temperature
            )
            
            if not response.choices:
                raise LLMInvalidResponseError("Empty choices returned")
                
            content = response.choices[0].message.content
            if not content:
                raise LLMInvalidResponseError("Empty message content returned")
                
            return content
        except LLMError:
            raise
        except Exception as e:
            raise map_openai_error(e)

    def generate_json(self, model: str, prompt: str, schema: Optional[Type[BaseModel]] = None, temperature: float = 0.0) -> Any:
        try:
            kwargs = {
                "model": model,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": temperature,
                "response_format": {"type": "json_object"}
            }
            
            # Note: Many OpenRouter models do not support structured outputs natively via response_format schema yet.
            # So we use json_object and rely on Pydantic to parse it afterwards.
            response = self.client.chat.completions.create(**kwargs)
            
            if not response.choices:
                raise LLMInvalidResponseError("Empty choices returned")
                
            content = response.choices[0].message.content
            if not content:
                raise LLMInvalidResponseError("Empty message content returned")
                
            if schema:
                try:
                    return schema.model_validate_json(content)
                except Exception as e:
                    raise LLMInvalidResponseError(f"JSON validation failed: {str(e)}")
            else:
                try:
                    return json.loads(content)
                except Exception as e:
                    raise LLMInvalidResponseError(f"Invalid JSON: {str(e)}")
        except LLMError:
            raise
        except Exception as e:
            raise map_openai_error(e)

    def chat(self, model: str, messages: List[ChatMessage], tools: Optional[List[Dict[str, Any]]] = None, temperature: float = 0.7) -> LLMResponse:
        try:
            kwargs = {
                "model": model,
                "messages": convert_messages(messages),
                "temperature": temperature
            }
            if tools:
                # Convert tools to OpenAI format
                openai_tools = []
                for t in tools:
                    if callable(t):
                        from app.llm.tool_parser import callable_to_openai_tool
                        openai_tools.append(callable_to_openai_tool(t))
                    else:
                        openai_tools.append(
                            {
                                "type": "function",
                                "function": {
                                    "name": t.get("name") or t.get("function_declarations", [{}])[0].get("name", ""),
                                    "description": t.get("description") or t.get("function_declarations", [{}])[0].get("description", ""),
                                    "parameters": t.get("parameters") or t.get("function_declarations", [{}])[0].get("parameters", {})
                                }
                            }
                        )
                kwargs["tools"] = openai_tools

            response = self.client.chat.completions.create(**kwargs)
            
            if not response.choices:
                raise LLMInvalidResponseError("Empty choices returned")
                
            msg = response.choices[0].message
            
            tool_calls = None
            if msg.tool_calls:
                tool_calls = []
                for tc in msg.tool_calls:
                    try:
                        args = json.loads(tc.function.arguments)
                    except:
                        args = {}
                    tool_calls.append(ToolCall(
                        id=tc.id,
                        name=tc.function.name,
                        arguments=args
                    ))
            
            return LLMResponse(
                text=msg.content,
                tool_calls=tool_calls
            )
            
        except LLMError:
            raise
        except Exception as e:
            raise map_openai_error(e)

class OpenRouterProvider(BaseOpenAIProvider):
    def __init__(self):
        settings = get_settings()
        client = OpenAI(
            base_url=settings.openrouter_base_url,
            api_key=settings.openrouter_api_key or "missing_key",
            timeout=settings.openrouter_timeout_seconds,
        )
        super().__init__(client)

class OllamaProvider(BaseOpenAIProvider):
    def __init__(self):
        settings = get_settings()
        client = OpenAI(
            base_url=settings.ollama_base_url,
            api_key="ollama",
            timeout=settings.ollama_timeout_seconds,
        )
        super().__init__(client)
