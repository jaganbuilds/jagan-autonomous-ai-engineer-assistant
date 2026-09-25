import pytest
from unittest.mock import patch, MagicMock

from app.llm.gateway import LLMGateway
from app.llm.models import LLMUnavailableError, LLMProviderError, LLMRateLimitError, LLMTimeoutError

@pytest.fixture
def gateway():
    with patch("app.llm.gateway.get_settings") as mock_settings:
        mock_settings.return_value.openrouter_api_key = "test_key"
        mock_settings.return_value.ollama_model = "qwen3:4b"
        
        gw = LLMGateway()
        gw.openrouter = MagicMock()
        gw.ollama = MagicMock()
        return gw

def test_gateway_fallback_success(gateway):
    # First model fails, second succeeds
    gateway.openrouter.generate_text.side_effect = [
        LLMRateLimitError("429"),
        "Success from second model"
    ]
    
    result = gateway.generate_text("Hello")
    assert result == "Success from second model"
    assert gateway.openrouter.generate_text.call_count == 2
    gateway.ollama.generate_text.assert_not_called()

def test_gateway_all_openrouter_fail_ollama_success(gateway):
    # All 5 OpenRouter models fail
    gateway.openrouter.generate_text.side_effect = [
        LLMTimeoutError("timeout"),
        LLMRateLimitError("429"),
        LLMProviderError("500"),
        LLMProviderError("502"),
        LLMProviderError("503")
    ]
    
    gateway.ollama.generate_text.return_value = "Success from Ollama"
    
    result = gateway.generate_text("Hello")
    assert result == "Success from Ollama"
    assert gateway.openrouter.generate_text.call_count == 5
    gateway.ollama.generate_text.assert_called_once()

def test_gateway_all_fail(gateway):
    gateway.openrouter.generate_text.side_effect = LLMUnavailableError("Unavailable")
    gateway.ollama.generate_text.side_effect = LLMUnavailableError("Ollama failed")
    
    with pytest.raises(LLMUnavailableError):
        gateway.generate_text("Hello")

def test_gateway_chat_fallback(gateway):
    gateway.openrouter.chat.side_effect = [
        LLMProviderError("503"),
        "Chat Success"
    ]
    
    res = gateway.chat([{"role": "user", "content": "Hello"}])
    assert res == "Chat Success"

def test_manager_llm_unavailable_error():
    from app.agents.manager import ManagerAgent
    with patch("app.agents.manager.gateway") as mock_gw:
        mock_gw.chat.side_effect = LLMUnavailableError("All models offline")
        
        mgr = ManagerAgent()
        reply = mgr.process_message("Hello", "test_session")
        assert "temporarily unavailable" in reply
        
        from app.agents.state import state_manager, SessionStatus
        session = state_manager.get_session("test_session")
        assert session.status == SessionStatus.ERROR
