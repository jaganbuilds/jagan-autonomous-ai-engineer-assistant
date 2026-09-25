from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field

# ==========================================
# Exceptions
# ==========================================

class LLMError(Exception):
    """Base exception for all LLM errors."""
    pass

class LLMProviderError(LLMError):
    """Error raised when the provider API returns an error."""
    pass

class LLMRateLimitError(LLMError):
    """Error raised when rate limited by the provider."""
    pass

class LLMTimeoutError(LLMError):
    """Error raised when the provider request times out."""
    pass

class LLMUnavailableError(LLMError):
    """Error raised when the provider or model is unavailable/offline."""
    pass

class LLMInvalidResponseError(LLMError):
    """Error raised when the response is invalid, empty, or unparseable."""
    pass

# ==========================================
# Chat & Tool Models
# ==========================================

class ToolCall(BaseModel):
    id: str
    name: str
    arguments: Dict[str, Any]

class ChatMessage(BaseModel):
    role: str
    content: Optional[str] = None
    tool_calls: Optional[List[ToolCall]] = None
    tool_call_id: Optional[str] = None
    name: Optional[str] = None

class LLMResponse(BaseModel):
    text: Optional[str] = None
    tool_calls: Optional[List[ToolCall]] = None
