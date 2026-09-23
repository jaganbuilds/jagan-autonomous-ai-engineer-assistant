import pytest
import os
import unittest.mock as mock

from app.voice.service import VoiceService, VoiceConversationSession
from app.voice.models import VoiceInput, VoiceOutput, VoiceInteraction
from app.voice.interfaces import SpeechToTextProvider, TextToSpeechProvider, MicrophoneProvider, STTResult, TTSResult
from app.agents.manager import ManagerAgent
from app.agents.state import state_manager, SessionStatus
from app.agents.orchestration import orchestrator, TaskState

# Mocks
class MockMicrophone(MicrophoneProvider):
    def __init__(self):
        self.is_recording = False
        self.fail_start = False
        self.audio_path = "test_audio.wav"
        
    def start_recording(self) -> None:
        if self.fail_start:
            raise RuntimeError("Hardware failure")
        self.is_recording = True
        
    def stop_recording(self) -> str:
        self.is_recording = False
        # Create dummy file to test cleanup
        with open(self.audio_path, "w") as f:
            f.write("mock audio data")
        return self.audio_path

class MockSTT(SpeechToTextProvider):
    def __init__(self):
        self.fail = False
        self.empty = False
        
    def transcribe(self, audio_reference: str, language=None, metadata=None) -> STTResult:
        if self.fail:
            raise Exception("STT Error")
        if self.empty:
            return STTResult(text="", provider="mock", model="mock")
        return STTResult(text="mock transcript", provider="mock", model="mock")

class MockTTS(TextToSpeechProvider):
    def __init__(self):
        self.fail = False
        
    def synthesize(self, text: str, language=None, metadata=None) -> TTSResult:
        if self.fail:
            raise Exception("TTS Error")
        return TTSResult(audio_reference="mock_tts.wav", format="wav", provider="mock", model="mock", duration=1.0)

@pytest.fixture
def clean_session():
    state_manager.clear_session("multi_turn_sess")
    yield "multi_turn_sess"
    state_manager.clear_session("multi_turn_sess")
    if os.path.exists("test_audio.wav"):
        os.remove("test_audio.wav")

@pytest.fixture
def voice_env():
    svc = VoiceService()
    svc.set_stt_provider(MockSTT())
    svc.set_tts_provider(MockTTS())
    mic = MockMicrophone()
    return svc, mic

def _setup_mock_orchestrator(monkeypatch, clean_session):
    state_manager.set_pending_tool(clean_session, "mock_tool", {"arg": "val"})
    plan_mock = type("Plan", (), {"status": TaskState.WAITING_FOR_CONFIRMATION})
    monkeypatch.setattr(orchestrator, "get_plan", lambda sess: plan_mock)
    monkeypatch.setattr(orchestrator, "resume_after_confirmation", lambda sess, approved, native_result=None: None)
    monkeypatch.setattr(orchestrator, "run_orchestration", lambda sess: type("OrchRes", (), {"terminal": True, "steps": []}))
    from app.agents.orchestration_response import OrchestrationResponseMapper
    monkeypatch.setattr(OrchestrationResponseMapper, "map_to_natural_response", lambda r: "Action complete")

def test_multi_turn_basic_flow(clean_session, voice_env, monkeypatch):
    svc, mic = voice_env
    # Mock manager agent to just return what it got
    monkeypatch.setattr(ManagerAgent, "process_message", lambda self, text, sess: f"Echo: {text}")
    
    session = VoiceConversationSession(clean_session, svc, mic)
    
    # Turn 1
    session.start_turn()
    assert mic.is_recording
    interaction1 = session.end_turn()
    assert interaction1.status == "completed"
    assert interaction1.input.transcript == "mock transcript"
    assert interaction1.output.text == "Echo: mock transcript"
    assert not os.path.exists(mic.audio_path) # cleaned up
    assert not mic.is_recording # stopped automatically
    
    # Turn 2
    session.start_turn()
    interaction2 = session.end_turn()
    assert interaction2.status == "completed"
    assert interaction2.input.session_id == clean_session
    assert not os.path.exists(mic.audio_path)

def test_concurrent_protection(clean_session, voice_env):
    svc, mic = voice_env
    session = VoiceConversationSession(clean_session, svc, mic)
    
    session.start_turn()
    with pytest.raises(RuntimeError, match="Already inside a voice turn"):
        session.start_turn()
        
    session.end_turn()

def test_end_without_start(clean_session, voice_env):
    svc, mic = voice_env
    session = VoiceConversationSession(clean_session, svc, mic)
    
    with pytest.raises(RuntimeError, match="No active voice turn"):
        session.end_turn()

def test_microphone_failure(clean_session, voice_env):
    svc, mic = voice_env
    mic.fail_start = True
    session = VoiceConversationSession(clean_session, svc, mic)
    
    with pytest.raises(RuntimeError, match="Hardware failure"):
        session.start_turn()
    
    assert session._in_turn is False

def test_stt_failure_recovers_next_turn(clean_session, voice_env, monkeypatch):
    svc, mic = voice_env
    svc.stt_provider.fail = True
    monkeypatch.setattr(ManagerAgent, "process_message", lambda self, text, sess: f"Echo: {text}")
    
    session = VoiceConversationSession(clean_session, svc, mic)
    
    # Turn 1 (Fails STT)
    session.start_turn()
    interaction1 = session.end_turn()
    assert interaction1.status == "failed"
    assert "Transcription failed" in interaction1.message
    
    # Session shouldn't be locked
    svc.stt_provider.fail = False
    
    # Turn 2 (Succeeds)
    session.start_turn()
    interaction2 = session.end_turn()
    assert interaction2.status == "completed"
    assert interaction2.output.text == "Echo: mock transcript"

def test_tts_failure_preserves_text(clean_session, voice_env, monkeypatch):
    svc, mic = voice_env
    svc.tts_provider.fail = True
    monkeypatch.setattr(ManagerAgent, "process_message", lambda self, text, sess: f"Echo: {text}")
    
    session = VoiceConversationSession(clean_session, svc, mic)
    
    session.start_turn()
    interaction = session.end_turn()
    
    # TTS failed, but interaction succeeds and text is there
    assert interaction.status == "completed"
    assert interaction.output.text == "Echo: mock transcript"
    assert interaction.output.audio_reference is None

def test_confirmation_flow(clean_session, voice_env, monkeypatch):
    svc, mic = voice_env
    session = VoiceConversationSession(clean_session, svc, mic)
    
    _setup_mock_orchestrator(monkeypatch, clean_session)
    state_manager.update_status(clean_session, SessionStatus.WAITING_FOR_CONFIRMATION)
    
    # Turn 1: user says "yes" (via STT mock override)
    svc.stt_provider.transcribe = lambda audio_reference=None, language=None, metadata=None: STTResult(text="yes", provider="mock", model="mock")
    
    session.start_turn()
    interaction = session.end_turn()
    
    assert state_manager.get_session(clean_session).status == SessionStatus.IDLE
    assert interaction.status == "completed"

def test_empty_transcript(clean_session, voice_env):
    svc, mic = voice_env
    svc.stt_provider.empty = True
    session = VoiceConversationSession(clean_session, svc, mic)
    
    session.start_turn()
    interaction = session.end_turn()
    
    assert interaction.status == "failed"
    assert interaction.message == "empty_transcript"

def test_ambiguous_confirmation_stays_pending(clean_session, voice_env, monkeypatch):
    svc, mic = voice_env
    session = VoiceConversationSession(clean_session, svc, mic)
    
    _setup_mock_orchestrator(monkeypatch, clean_session)
    state_manager.update_status(clean_session, SessionStatus.WAITING_FOR_CONFIRMATION)
    
    svc.stt_provider.transcribe = lambda audio_reference=None, language=None, metadata=None: STTResult(text="maybe", provider="mock", model="mock")
    
    session.start_turn()
    interaction = session.end_turn()
    
    assert interaction.status == "waiting_for_confirmation"
    assert "clearly reply" in interaction.output.text.lower()
    
    # Verify next turn works
    svc.stt_provider.transcribe = lambda audio_reference=None, language=None, metadata=None: STTResult(text="yes", provider="mock", model="mock")
    
    session.start_turn()
    interaction2 = session.end_turn()
    
    assert interaction2.status == "completed"
    assert state_manager.get_session(clean_session).status == SessionStatus.IDLE

def test_session_isolation(voice_env, monkeypatch):
    svc, mic = voice_env
    session1 = VoiceConversationSession("sess1", svc, mic)
    session2 = VoiceConversationSession("sess2", svc, mic)
    
    monkeypatch.setattr(ManagerAgent, "process_message", lambda self, text, sess: f"Session {sess}")
    
    session1.start_turn()
    i1 = session1.end_turn()
    
    session2.start_turn()
    i2 = session2.end_turn()
    
    assert i1.output.text == "Session sess1"
    assert i2.output.text == "Session sess2"
