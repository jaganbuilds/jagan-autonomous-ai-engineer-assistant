import pytest
import unittest.mock as mock
from app.agents.manager import ManagerAgent
from app.agents.state import state_manager, SessionStatus
from app.voice.service import VoiceService
from app.voice.models import VoiceInput
from app.agents.orchestration import orchestrator, TaskState

@pytest.fixture
def clean_session():
    state_manager.clear_session("test_sess")
    yield "test_sess"
    state_manager.clear_session("test_sess")

def _setup_mock_orchestrator(monkeypatch, clean_session):
    # Set a pending tool call
    state_manager.set_pending_tool(clean_session, "mock_tool", {"arg": "val"})
    
    # Mock orchestrator plan
    plan_mock = type("Plan", (), {"status": TaskState.WAITING_FOR_CONFIRMATION})
    monkeypatch.setattr(orchestrator, "get_plan", lambda sess: plan_mock)
    monkeypatch.setattr(orchestrator, "resume_after_confirmation", lambda sess, approved, native_result=None: None)
    monkeypatch.setattr(orchestrator, "run_orchestration", lambda sess: type("OrchRes", (), {"terminal": True, "steps": []}))
    
    from app.agents.orchestration_response import OrchestrationResponseMapper
    monkeypatch.setattr(OrchestrationResponseMapper, "map_to_natural_response", lambda r: "Action complete")

def test_english_approval(clean_session, monkeypatch):
    agent = ManagerAgent()
    _setup_mock_orchestrator(monkeypatch, clean_session)
    
    response = agent.process_message("Yes", clean_session)
    session = state_manager.get_session(clean_session)
    assert session.status == SessionStatus.IDLE

def test_english_rejection(clean_session, monkeypatch):
    agent = ManagerAgent()
    _setup_mock_orchestrator(monkeypatch, clean_session)
    
    response = agent.process_message("No", clean_session)
    session = state_manager.get_session(clean_session)
    assert session.status == SessionStatus.IDLE

def test_tamil_approval(clean_session, monkeypatch):
    agent = ManagerAgent()
    _setup_mock_orchestrator(monkeypatch, clean_session)
    
    response = agent.process_message("ஆமாம்", clean_session)
    session = state_manager.get_session(clean_session)
    assert session.status == SessionStatus.IDLE

def test_tamil_rejection(clean_session, monkeypatch):
    agent = ManagerAgent()
    _setup_mock_orchestrator(monkeypatch, clean_session)
    
    response = agent.process_message("வேண்டாம்", clean_session)
    session = state_manager.get_session(clean_session)
    assert session.status == SessionStatus.IDLE

def test_tanglish_approval(clean_session, monkeypatch):
    agent = ManagerAgent()
    _setup_mock_orchestrator(monkeypatch, clean_session)
    
    response = agent.process_message("aama", clean_session)
    session = state_manager.get_session(clean_session)
    assert session.status == SessionStatus.IDLE

def test_tanglish_rejection(clean_session, monkeypatch):
    agent = ManagerAgent()
    _setup_mock_orchestrator(monkeypatch, clean_session)
    
    response = agent.process_message("vendam", clean_session)
    session = state_manager.get_session(clean_session)
    assert session.status == SessionStatus.IDLE

def test_ambiguous_response(clean_session, monkeypatch):
    agent = ManagerAgent()
    _setup_mock_orchestrator(monkeypatch, clean_session)
    
    response = agent.process_message("maybe", clean_session)
    session = state_manager.get_session(clean_session)
    
    # Must remain waiting for confirmation
    assert session.status == SessionStatus.WAITING_FOR_CONFIRMATION
    assert session.pending_tool_call is not None
    assert "clearly reply" in response.lower()

def test_approval_with_no_pending_action(clean_session, monkeypatch):
    agent = ManagerAgent()
    state_manager.update_status(clean_session, SessionStatus.IDLE)
    
    # Mock chat
    mock_chat = mock.MagicMock()
    mock_chat.send_message.return_value = type("Res", (), {"function_calls": [], "text": "mock yes"})()
    monkeypatch.setattr(agent, "_get_chat", lambda sess: mock_chat)
    
    agent.process_message("yes", clean_session)
    session = state_manager.get_session(clean_session)
    assert session.status == SessionStatus.IDLE

def test_wrong_session(clean_session, monkeypatch):
    agent = ManagerAgent()
    _setup_mock_orchestrator(monkeypatch, clean_session)
    
    state_manager.clear_session("other_sess")
    
    mock_chat = mock.MagicMock()
    mock_chat.send_message.return_value = type("Res", (), {"function_calls": [], "text": "mock yes"})()
    monkeypatch.setattr(agent, "_get_chat", lambda sess: mock_chat)
    
    agent.process_message("yes", "other_sess")
    
    # Original session must remain WAITING
    session1 = state_manager.get_session(clean_session)
    assert session1.status == SessionStatus.WAITING_FOR_CONFIRMATION
    
    session2 = state_manager.get_session("other_sess")
    assert session2.status == SessionStatus.IDLE

def test_duplicate_approval(clean_session, monkeypatch):
    agent = ManagerAgent()
    _setup_mock_orchestrator(monkeypatch, clean_session)
    
    # First yes -> approves
    agent.process_message("yes", clean_session)
    session = state_manager.get_session(clean_session)
    assert session.status == SessionStatus.IDLE
    
    # Second yes -> standard chat
    mock_chat = mock.MagicMock()
    mock_chat.send_message.return_value = type("Res", (), {"function_calls": [], "text": "mock yes"})()
    monkeypatch.setattr(agent, "_get_chat", lambda sess: mock_chat)
    
    agent.process_message("yes", clean_session)
    assert state_manager.get_session(clean_session).status == SessionStatus.IDLE

def test_checkpoint_restoration(clean_session, monkeypatch):
    _setup_mock_orchestrator(monkeypatch, clean_session)
    session = state_manager.get_session(clean_session)
    
    # Save checkpoint
    from app.agents.checkpoint import checkpoint_repository, OrchestrationCheckpoint
    from app.agents.orchestration import AgentPlan, TaskState
    
    plan = AgentPlan(goal="test", steps=[], status=TaskState.WAITING_FOR_CONFIRMATION)
    cp = OrchestrationCheckpoint(
        session_id=clean_session,
        goal="test",
        plan=plan,
        status=TaskState.WAITING_FOR_CONFIRMATION
    )
    checkpoint_repository.create_or_update_checkpoint(cp)
    
    # Clear memory explicitly
    state_manager.clear_session(clean_session)
    
    # Restore checkpoint
    restored_cp = checkpoint_repository.get_latest_checkpoint_for_session(clean_session)
    # Rebuild session
    state_manager.update_status(clean_session, SessionStatus.WAITING_FOR_CONFIRMATION)
    # The orchestration run controller usually re-hydrates the plan. 
    # For our mock, setup_mock_orchestrator already does what we need.
    _setup_mock_orchestrator(monkeypatch, clean_session)
    
    # Now send confirmation
    agent = ManagerAgent()
    agent.process_message("yes", clean_session)
    
    # Success
    final_session = state_manager.get_session(clean_session)
    assert final_session.status == SessionStatus.IDLE

def test_voice_integration(clean_session, monkeypatch):
    svc = VoiceService()
    _setup_mock_orchestrator(monkeypatch, clean_session)
    
    v_in = VoiceInput(session_id=clean_session, transcript="yes")
    interaction = svc.process_voice_input(v_in)
    
    assert interaction.status == "completed"
    assert interaction.output.text == "Action complete"
    assert state_manager.get_session(clean_session).status == SessionStatus.IDLE

def test_tts_failure_during_confirmation(clean_session, monkeypatch):
    svc = VoiceService()
    _setup_mock_orchestrator(monkeypatch, clean_session)
    
    class FailTTS:
        def synthesize(self, text, language=None, metadata=None):
            raise Exception("Mock TTS Error")
            
    svc.set_tts_provider(FailTTS())
    
    v_in = VoiceInput(session_id=clean_session, transcript="maybe")
    interaction = svc.process_voice_input(v_in)
    
    assert interaction.status == "waiting_for_confirmation"
    assert "clearly reply" in interaction.output.text.lower()
    assert interaction.output.audio_reference is None
