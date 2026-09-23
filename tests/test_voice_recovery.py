import pytest
import os
import unittest.mock as mock

from app.voice.service import VoiceService, VoiceConversationSession
from app.voice.interfaces import STTResult, TTSResult
from app.agents.state import state_manager, SessionStatus
from app.agents.checkpoint import checkpoint_repository, OrchestrationCheckpoint
from app.agents.orchestration import orchestrator, AgentPlan, PlanStep, TaskState
from tests.test_voice_multiturn import MockSTT, MockTTS, MockMicrophone

@pytest.fixture
def clean_db():
    # Setup clean db
    with app.database.connection.get_db_connection() as conn:
        conn.execute("DELETE FROM orchestration_checkpoints")
        conn.execute("DELETE FROM execution_traces")
        conn.commit()

@pytest.fixture
def voice_env():
    svc = VoiceService()
    svc.set_stt_provider(MockSTT())
    svc.set_tts_provider(MockTTS())
    mic = MockMicrophone()
    return svc, mic

@pytest.fixture(autouse=True)
def clean_sessions():
    state_manager._sessions.clear()
    yield
    state_manager._sessions.clear()

import app.database.connection

def test_attach_fresh_session(voice_env):
    svc, mic = voice_env
    # Should just return an instance
    session = VoiceConversationSession.attach("fresh_sess", svc, mic)
    assert session.session_id == "fresh_sess"
    assert state_manager.get_session("fresh_sess").status == SessionStatus.IDLE

def test_attach_recovers_waiting_for_confirmation(voice_env, monkeypatch):
    svc, mic = voice_env
    session_id = "recover_sess"
    
    # 1. Manually create a checkpoint in the DB representing a paused orchestration
    step = PlanStep(
        id=1,
        description="Protected action",
        tool_name="mock_tool",
        tool_args={"arg": "val"},
        status=TaskState.WAITING_FOR_CONFIRMATION
    )
    plan = AgentPlan(goal="Test goal", steps=[step], status=TaskState.WAITING_FOR_CONFIRMATION)
    
    checkpoint = OrchestrationCheckpoint(
        run_id="test_run_123",
        session_id=session_id,
        goal="Test goal",
        plan=plan,
        status=TaskState.WAITING_FOR_CONFIRMATION
    )
    checkpoint_repository.create_or_update_checkpoint(checkpoint)
    
    # 2. Mock orchestrator dependencies to prevent actually running side effects during test
    monkeypatch.setattr(orchestrator, "run_orchestration", lambda sess: type("OrchRes", (), {"terminal": True, "steps": []}))
    from app.agents.orchestration_response import OrchestrationResponseMapper
    monkeypatch.setattr(OrchestrationResponseMapper, "map_to_natural_response", lambda r: "Action complete")
    
    # Ensure memory is clear
    state_manager.clear_session(session_id)
    
    # 3. Attach! This should recover the checkpoint into state_manager
    v_session = VoiceConversationSession.attach(session_id, svc, mic)
    
    # Verify state manager was correctly restored natively
    sess_state = state_manager.get_session(session_id)
    assert sess_state.status == SessionStatus.WAITING_FOR_CONFIRMATION
    assert sess_state.pending_tool_call["name"] == "mock_tool"
    
    # 4. Now user speaks "yes"
    svc.stt_provider.transcribe = lambda audio_reference=None, language=None, metadata=None: STTResult(text="yes", provider="mock", model="mock")
    
    v_session.start_turn()
    interaction = v_session.end_turn()
    
    assert interaction.status == "completed"
    
    # Cleanup DB
    checkpoint_repository.delete_checkpoint(checkpoint.run_id)

def test_attach_recovers_rejection(voice_env, monkeypatch):
    svc, mic = voice_env
    session_id = "reject_sess"
    
    step = PlanStep(
        id=1,
        description="Protected action",
        tool_name="mock_tool",
        tool_args={"arg": "val"},
        status=TaskState.WAITING_FOR_CONFIRMATION
    )
    plan = AgentPlan(goal="Test goal", steps=[step], status=TaskState.WAITING_FOR_CONFIRMATION)
    checkpoint = OrchestrationCheckpoint(run_id="test_run_456", session_id=session_id, goal="Test", plan=plan, status=TaskState.WAITING_FOR_CONFIRMATION)
    checkpoint_repository.create_or_update_checkpoint(checkpoint)
    from tests.test_voice_multiturn import _setup_mock_orchestrator
    _setup_mock_orchestrator(monkeypatch, session_id)
    
    state_manager.clear_session(session_id)
    
    v_session = VoiceConversationSession.attach(session_id, svc, mic)
    
    # Speak "no"
    svc.stt_provider.transcribe = lambda audio_reference=None, language=None, metadata=None: STTResult(text="no", provider="mock", model="mock")
    
    v_session.start_turn()
    interaction = v_session.end_turn()
    
    assert interaction.status == "completed"
    assert "complete" in interaction.output.text.lower()
    
    # Verify state is cleared
    sess_state = state_manager.get_session(session_id)
    assert sess_state.status == SessionStatus.IDLE
    
    checkpoint_repository.delete_checkpoint(checkpoint.run_id)

def test_attach_recovers_completed_run_without_replaying(voice_env):
    svc, mic = voice_env
    session_id = "comp_sess"
    
    # A completed plan
    step = PlanStep(id=1, description="action", tool_name="mock", tool_args={}, status=TaskState.COMPLETED)
    plan = AgentPlan(goal="Test goal", steps=[step], status=TaskState.COMPLETED, current_step_index=1)
    checkpoint = OrchestrationCheckpoint(run_id="test_run_789", session_id=session_id, goal="Test", plan=plan, status=TaskState.COMPLETED)
    checkpoint_repository.create_or_update_checkpoint(checkpoint)
    
    state_manager.clear_session(session_id)
    
    # Attach should safely recover it as COMPLETED
    v_session = VoiceConversationSession.attach(session_id, svc, mic)
    
    sess_state = state_manager.get_session(session_id)
    assert sess_state.status == SessionStatus.COMPLETED
    assert sess_state.pending_tool_call is None
    
    checkpoint_repository.delete_checkpoint(checkpoint.run_id)

def test_attach_does_not_override_active_memory(voice_env):
    svc, mic = voice_env
    session_id = "active_sess"
    
    # Create DB checkpoint
    checkpoint = OrchestrationCheckpoint(
        run_id="test_run_active", session_id=session_id, goal="Test", 
        plan=AgentPlan(goal="DB Goal", steps=[]), status=TaskState.WAITING_FOR_CONFIRMATION
    )
    checkpoint_repository.create_or_update_checkpoint(checkpoint)
    
    # Create active memory state that contradicts DB (e.g. user started new flow before DB check)
    sess = state_manager.get_session(session_id)
    sess.status = SessionStatus.PROCESSING
    sess.history = [{"role": "user", "content": "hi"}]
    
    # Attach should NOT overwrite active memory with DB!
    v_session = VoiceConversationSession.attach(session_id, svc, mic)
    
    assert state_manager.get_session(session_id).status == SessionStatus.PROCESSING
    assert state_manager.get_session(session_id).pending_tool_call is None
    
    checkpoint_repository.delete_checkpoint(checkpoint.run_id)

def test_session_isolation_during_recovery(voice_env):
    svc, mic = voice_env
    
    # DB checkpoint for session_A
    step = PlanStep(id=1, description="action", tool_name="mock", tool_args={}, status=TaskState.WAITING_FOR_CONFIRMATION)
    plan = AgentPlan(goal="Test goal", steps=[step], status=TaskState.WAITING_FOR_CONFIRMATION)
    chk = OrchestrationCheckpoint(run_id="test_run_a", session_id="session_A", goal="Test", plan=plan, status=TaskState.WAITING_FOR_CONFIRMATION)
    checkpoint_repository.create_or_update_checkpoint(chk)
    
    state_manager.clear_session("session_A")
    state_manager.clear_session("session_B")
    
    # Attach B
    v_session_b = VoiceConversationSession.attach("session_B", svc, mic)
    assert state_manager.get_session("session_B").status == SessionStatus.IDLE
    
    # Attach A
    v_session_a = VoiceConversationSession.attach("session_A", svc, mic)
    assert state_manager.get_session("session_A").status == SessionStatus.WAITING_FOR_CONFIRMATION
    
    checkpoint_repository.delete_checkpoint(chk.run_id)

