import pytest
from app.agents.state import StateManager, SessionStatus

@pytest.fixture
def manager():
    return StateManager()

def test_get_session_creates_new(manager):
    session = manager.get_session("test_session_1")
    assert session.session_id == "test_session_1"
    assert session.status == SessionStatus.IDLE
    assert session.pending_tool_call is None
    assert len(session.history) == 0

def test_update_status(manager):
    manager.update_status("test_session_1", SessionStatus.PROCESSING)
    session = manager.get_session("test_session_1")
    assert session.status == SessionStatus.PROCESSING

def test_set_and_clear_pending_tool(manager):
    # Set pending tool
    manager.set_pending_tool("test_session_1", "delete_file", {"filename": "test.txt"})
    session = manager.get_session("test_session_1")
    
    assert session.status == SessionStatus.WAITING_FOR_CONFIRMATION
    assert session.pending_tool_call is not None
    assert session.pending_tool_call["name"] == "delete_file"
    assert session.pending_tool_call["args"] == {"filename": "test.txt"}
    
    # Clear pending tool
    manager.clear_pending_tool("test_session_1")
    assert session.status == SessionStatus.IDLE
    assert session.pending_tool_call is None

def test_add_to_history(manager):
    manager.add_to_history("test_session_1", "user", "Hello")
    manager.add_to_history("test_session_1", "assistant", "Hi there")
    
    session = manager.get_session("test_session_1")
    assert len(session.history) == 2
    assert session.history[0]["role"] == "user"
    assert session.history[0]["content"] == "Hello"

def test_clear_session(manager):
    manager.get_session("test_session_1")
    assert "test_session_1" in manager._sessions
    
    manager.clear_session("test_session_1")
    assert "test_session_1" not in manager._sessions
