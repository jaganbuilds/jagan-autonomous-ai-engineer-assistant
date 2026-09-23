import pytest
from fastapi.testclient import TestClient
from unittest.mock import MagicMock, patch

from app.main import app
from app.agents.state import state_manager, SessionStatus
from app.tools.registry import registry

client = TestClient(app)

@pytest.fixture
def mock_gemini():
    # Patch the get_settings inside manager to avoid API key requirement
    with patch("app.agents.manager.get_settings") as mock_settings:
        mock_settings.return_value.gemini_api_key = "test_key"
        
        # We need to mock the client and chat session inside the global manager_agent
        from app.main import manager_agent
        
        # Reset the client and chats for clean testing
        mock_client = MagicMock()
        manager_agent.client = mock_client
        manager_agent._chats = {}
        
        yield mock_client
        
        # Teardown
        manager_agent.client = None
        manager_agent._chats = {}

def test_api_normal_chat(mock_gemini):
    session_id = "test_api_chat"
    state_manager.clear_session(session_id)
    
    # Mock LLM response
    mock_chat = MagicMock()
    mock_response = MagicMock()
    mock_response.function_calls = []
    mock_response.text = "Hello from AI"
    mock_chat.send_message.return_value = mock_response
    mock_gemini.chats.create.return_value = mock_chat
    
    response = client.post("/chat", json={"message": "Hi", "session_id": session_id})
    assert response.status_code == 200
    data = response.json()
    
    assert data["response"] == "Hello from AI"
    assert data["status"] == SessionStatus.IDLE.value
    assert data["error"] is None

def test_api_tool_execution(mock_gemini):
    session_id = "test_api_tool"
    state_manager.clear_session(session_id)
    
    mock_chat = MagicMock()
    
    # Mock tool call response
    tool_call = MagicMock()
    tool_call.name = "calculate"
    tool_call.args = {"expression": "10 * 10"}
    call_response = MagicMock()
    call_response.function_calls = [tool_call]
    
    # Mock final text response
    final_response = MagicMock()
    final_response.function_calls = []
    final_response.text = "The answer is 100."
    
    mock_chat.send_message.side_effect = [call_response, final_response]
    mock_gemini.chats.create.return_value = mock_chat
    
    response = client.post("/chat", json={"message": "10 * 10", "session_id": session_id})
    assert response.status_code == 200
    data = response.json()
    
    assert data["response"] == "The answer is 100."
    assert data["status"] == SessionStatus.IDLE.value

def test_api_confirmation_flow(mock_gemini):
    session_id = "test_api_confirm"
    state_manager.clear_session(session_id)
    
    # Register sensitive tool
    @registry.register(name="destroy_world", requires_confirmation=True)
    def destroy_world():
        return "Boom"
        
    mock_chat = MagicMock()
    
    # Mock LLM wants to use the sensitive tool
    tool_call = MagicMock()
    tool_call.name = "destroy_world"
    tool_call.args = {}
    call_response = MagicMock()
    call_response.function_calls = [tool_call]
    mock_chat.send_message.return_value = call_response
    mock_gemini.chats.create.return_value = mock_chat
    
    # 1. Trigger the confirmation intercept
    res1 = client.post("/chat", json={"message": "Destroy the world", "session_id": session_id})
    data1 = res1.json()
    
    assert "Shall I proceed?" in data1["response"]
    assert data1["status"] == SessionStatus.WAITING_FOR_CONFIRMATION.value
    
    # 2. Approve the action
    final_response = MagicMock()
    final_response.function_calls = []
    final_response.text = "World destroyed."
    mock_chat.send_message.side_effect = [final_response] # This is for the resume
    
    res2 = client.post("/chat", json={"message": "Yes", "session_id": session_id})
    data2 = res2.json()
    
    assert data2["response"] == "World destroyed."
    assert data2["status"] == SessionStatus.IDLE.value

def test_api_confirmation_rejection(mock_gemini):
    session_id = "test_api_reject"
    state_manager.clear_session(session_id)
    
    state_manager.set_pending_tool(session_id, "dummy_tool", {})
    
    res = client.post("/chat", json={"message": "No", "session_id": session_id})
    data = res.json()
    
    assert data["response"] == "Action cancelled."
    assert data["status"] == SessionStatus.IDLE.value

def test_api_session_isolation(mock_gemini):
    state_manager.clear_session("user1")
    state_manager.clear_session("user2")
    
    # Put user1 in WAITING
    state_manager.set_pending_tool("user1", "tool_x", {})
    
    mock_chat = MagicMock()
    mock_response = MagicMock()
    mock_response.function_calls = []
    mock_response.text = "Normal message"
    mock_chat.send_message.return_value = mock_response
    mock_gemini.chats.create.return_value = mock_chat
    
    # Send normal message to user2
    res_user2 = client.post("/chat", json={"message": "Hi", "session_id": "user2"})
    data2 = res_user2.json()
    
    assert data2["response"] == "Normal message"
    assert data2["status"] == SessionStatus.IDLE.value
    
    # Verify user1 is still waiting
    assert state_manager.get_session("user1").status == SessionStatus.WAITING_FOR_CONFIRMATION
