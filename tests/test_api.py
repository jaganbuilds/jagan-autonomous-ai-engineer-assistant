import pytest
import json
from app.llm.models import LLMResponse, ToolCall
from fastapi.testclient import TestClient
from unittest.mock import MagicMock, patch

from app.main import app
from app.agents.state import state_manager, SessionStatus
from app.tools.registry import registry

client = TestClient(app)




@pytest.fixture
def mock_gateway_fixture():
    with patch("app.agents.manager.get_settings") as mock_settings:
        mock_settings.return_value.openrouter_api_key = "test_key"
        with patch("app.agents.manager.gateway") as mock_gateway:
            from app.main import manager_agent
            manager_agent._chats = {}
            yield mock_gateway

def test_api_normal_chat(mock_gateway_fixture):
    session_id = "test_api_chat"
    state_manager.clear_session(session_id)
    
    # Mock LLM response
    
    mock_response = LLMResponse(text="", tool_calls=None)
    mock_response.tool_calls = None
    mock_response.text = "Hello from AI"
    mock_gateway_fixture.chat.return_value = mock_response
    
    
    response = client.post("/chat", json={"message": "Hi", "session_id": session_id})
    assert response.status_code == 200
    data = response.json()
    
    assert data["response"] == "Hello from AI"
    assert data["status"] == SessionStatus.IDLE.value
    assert data["error"] is None

def test_api_tool_execution(mock_gateway_fixture):
    session_id = "test_api_tool"
    state_manager.clear_session(session_id)
    
    
    
    # Mock tool call response
    tool_call = ToolCall(id="t1", name="test", arguments={})
    tool_call.name = "calculate"
    tool_call.arguments = {"expression": "10 * 10"}
    call_response = LLMResponse(text="", tool_calls=None)
    call_response.tool_calls = [tool_call]
    
    # Mock final text response
    final_response = LLMResponse(text="", tool_calls=None)
    final_response.tool_calls = None
    final_response.text = "The answer is 100."
    
    mock_gateway_fixture.chat.side_effect = [call_response, final_response]
    
    
    response = client.post("/chat", json={"message": "10 * 10", "session_id": session_id})
    assert response.status_code == 200
    data = response.json()
    
    assert data["response"] == "The answer is 100."
    assert data["status"] == SessionStatus.IDLE.value

def test_api_confirmation_flow(mock_gateway_fixture):
    session_id = "test_api_confirm"
    state_manager.clear_session(session_id)
    
    # Register sensitive tool
    @registry.register(name="destroy_world", requires_confirmation=True)
    def destroy_world():
        return "Boom"
        
    
    
    # Mock LLM wants to use the sensitive tool
    tool_call = ToolCall(id="t1", name="test", arguments={})
    tool_call.name = "destroy_world"
    tool_call.arguments = {}
    call_response = LLMResponse(text="", tool_calls=None)
    call_response.tool_calls = [tool_call]
    mock_gateway_fixture.chat.return_value = call_response
    
    
    # 1. Trigger the confirmation intercept
    res1 = client.post("/chat", json={"message": "Destroy the world", "session_id": session_id})
    data1 = res1.json()
    
    assert "Shall I proceed?" in data1["response"]
    assert data1["status"] == SessionStatus.WAITING_FOR_CONFIRMATION.value
    
    # 2. Approve the action
    final_response = LLMResponse(text="", tool_calls=None)
    final_response.tool_calls = None
    final_response.text = "World destroyed."
    mock_gateway_fixture.chat.side_effect = [final_response] # This is for the resume
    
    res2 = client.post("/chat", json={"message": "Yes", "session_id": session_id})
    data2 = res2.json()
    
    assert data2["response"] == "World destroyed."
    assert data2["status"] == SessionStatus.IDLE.value

def test_api_confirmation_rejection(mock_gateway_fixture):
    session_id = "test_api_reject"
    state_manager.clear_session(session_id)
    
    state_manager.set_pending_tool(session_id, "dummy_tool", {})
    
    res = client.post("/chat", json={"message": "No", "session_id": session_id})
    data = res.json()
    
    assert data["response"] == "Action cancelled."
    assert data["status"] == SessionStatus.IDLE.value

def test_api_session_isolation(mock_gateway_fixture):
    state_manager.clear_session("user1")
    state_manager.clear_session("user2")
    
    # Put user1 in WAITING
    state_manager.set_pending_tool("user1", "tool_x", {})
    
    
    mock_response = LLMResponse(text="", tool_calls=None)
    mock_response.tool_calls = None
    mock_response.text = "Normal message"
    mock_gateway_fixture.chat.return_value = mock_response
    
    
    # Send normal message to user2
    res_user2 = client.post("/chat", json={"message": "Hi", "session_id": "user2"})
    data2 = res_user2.json()
    
    assert data2["response"] == "Normal message"
    assert data2["status"] == SessionStatus.IDLE.value
    
    # Verify user1 is still waiting
    assert state_manager.get_session("user1").status == SessionStatus.WAITING_FOR_CONFIRMATION
