import pytest
from app.voice.models import VoiceInput, VoiceOutput, VoiceInteraction, STTResult, TTSResult
from app.voice.interfaces import SpeechToTextProvider, TextToSpeechProvider
from app.voice.service import VoiceService
from app.agents.state import state_manager, SessionStatus

class MockSTTProvider(SpeechToTextProvider):
    def transcribe(self, audio_reference: str, language: str = None, metadata: dict = None) -> STTResult:
        if audio_reference == "error.wav":
            raise ValueError("STT Mock Error")
        return STTResult(
            text=f"transcribed: {audio_reference}",
            provider="mock",
            model="mock_model"
        )

class MockTTSProvider(TextToSpeechProvider):
    def synthesize(self, text: str, language: str = None, metadata: dict = None) -> TTSResult:
        if "error" in text.lower():
            raise ValueError("TTS Mock Error")
        return TTSResult(
            audio_reference=f"audio:{text[:10]}",
            language=language,
            provider="mock_tts",
            model="mock_model",
            format="wav"
        )

def test_voice_models():
    v_in = VoiceInput(session_id="s1", transcript="hello", language="ta", metadata={"accent": "chennai"})
    assert v_in.session_id == "s1"
    assert v_in.language == "ta"
    assert v_in.metadata["accent"] == "chennai"
    
    v_out = VoiceOutput(session_id="s1", text="world", audio_reference="url", language="en")
    assert v_out.audio_reference == "url"
    
    v_int = VoiceInteraction(session_id="s1", input=v_in, output=v_out, status="completed", message="ok")
    assert v_int.status == "completed"

def test_transcript_only_interaction(monkeypatch):
    from app.agents.manager import ManagerAgent
    monkeypatch.setattr(ManagerAgent, "process_message", lambda self, msg, sess: "mock response")
    
    svc = VoiceService()
    v_in = VoiceInput(session_id="test_t_only", transcript="find jobs")
    interaction = svc.process_voice_input(v_in)
    
    assert interaction.status == "completed"
    assert interaction.output is not None
    assert interaction.output.text == "mock response"
    assert interaction.output.audio_reference is None

def test_stt_manager_flow(monkeypatch):
    from app.agents.manager import ManagerAgent
    monkeypatch.setattr(ManagerAgent, "process_message", lambda self, msg, sess: "mock response")
    
    svc = VoiceService()
    svc.set_stt_provider(MockSTTProvider())
    
    v_in = VoiceInput(session_id="test_stt_flow", audio_reference="hello.wav")
    interaction = svc.process_voice_input(v_in)
    
    assert interaction.status == "completed"
    assert interaction.input.transcript == "transcribed: hello.wav"
    assert interaction.output is not None
    assert interaction.output.audio_reference is None

def test_stt_manager_tts_flow(monkeypatch):
    from app.agents.manager import ManagerAgent
    monkeypatch.setattr(ManagerAgent, "process_message", lambda self, msg, sess: "mock response")
    
    svc = VoiceService()
    svc.set_stt_provider(MockSTTProvider())
    svc.set_tts_provider(MockTTSProvider())
    
    v_in = VoiceInput(session_id="test_stt_tts", audio_reference="hello.wav")
    interaction = svc.process_voice_input(v_in)
    
    assert interaction.status == "completed"
    assert interaction.output.audio_reference is not None

def test_missing_stt_provider():
    svc = VoiceService()
    v_in = VoiceInput(session_id="test_no_stt", audio_reference="hello.wav")
    interaction = svc.process_voice_input(v_in)
    
    assert interaction.status == "failed"
    assert "no STT provider" in interaction.message

def test_stt_error_handling():
    svc = VoiceService()
    svc.set_stt_provider(MockSTTProvider())
    v_in = VoiceInput(session_id="test_stt_err", audio_reference="error.wav")
    interaction = svc.process_voice_input(v_in)
    
    assert interaction.status == "failed"
    assert "failed" in interaction.message.lower()

def test_tts_error_handling_is_safe(monkeypatch):
    from app.agents.manager import ManagerAgent
    monkeypatch.setattr(ManagerAgent, "process_message", lambda self, msg, sess: "simulate error in text")
    
    svc = VoiceService()
    svc.set_tts_provider(MockTTSProvider())
    
    # Text that causes mock TTS to throw
    v_in = VoiceInput(session_id="test_tts_err", transcript="simulate error in text")
    interaction = svc.process_voice_input(v_in)
    
    # Should not fail interaction, just omit audio_ref
    assert interaction.status == "completed"
    assert interaction.output.text != ""
    assert interaction.output.audio_reference is None

def test_language_metadata_preservation(monkeypatch):
    from app.agents.manager import ManagerAgent
    monkeypatch.setattr(ManagerAgent, "process_message", lambda self, msg, sess: "mock response")
    
    svc = VoiceService()
    svc.set_tts_provider(MockTTSProvider())
    v_in = VoiceInput(session_id="test_lang", transcript="சென்னை வேலைகள்", language="ta")
    interaction = svc.process_voice_input(v_in)
    
    assert interaction.input.language == "ta"
    assert interaction.output.language == "ta"

def test_confirmation_compatibility():
    from app.agents.manager import ManagerAgent
    from unittest.mock import MagicMock
    from app.tools.registry import registry
    
    svc = VoiceService()
    
    # We'll patch registry to force require_confirmation on a dummy tool
    original = registry.requires_confirmation
    registry.requires_confirmation = MagicMock(return_value=True)
    
    try:
        state_manager.clear_session("test_voice_conf")
        # Ensure the mock sets the session status just like the real agent would
        def mock_process_message(msg, sess):
            state_manager.update_status(sess, SessionStatus.WAITING_FOR_CONFIRMATION)
            return "Orchestration paused. Waiting for confirmation on step 1."
            
        svc.agent.process_message = MagicMock(side_effect=mock_process_message)
        
        v_in = VoiceInput(session_id="test_voice_conf", transcript="use fake_tool")
        interaction = svc.process_voice_input(v_in)
        
        assert interaction.status == "waiting_for_confirmation"
        assert "paused" in interaction.output.text.lower()
    finally:
        registry.requires_confirmation = original

def test_no_secret_leakage():
    v_in = VoiceInput(session_id="s1", transcript="test")
    # VoiceInput dumped shouldn't have arbitrary properties
    dump = v_in.model_dump()
    assert "api_key" not in dump

def test_api_endpoint_disabled(monkeypatch):
    from fastapi.testclient import TestClient
    from app.main import app
    from app.config import get_settings, Settings
    
    client = TestClient(app)
    
    # Patch settings to disable voice
    monkeypatch.setattr("app.main.get_settings", lambda: Settings(voice_enabled=False))
    
    response = client.post("/voice/interact", json={"session_id": "test_api", "transcript": "hello"})
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "failed"
    assert "disabled" in data["message"]

def test_api_endpoint_enabled(monkeypatch):
    from fastapi.testclient import TestClient
    from app.main import app
    from app.config import get_settings, Settings
    from app.agents.manager import ManagerAgent
    
    monkeypatch.setattr(ManagerAgent, "process_message", lambda self, msg, sess: "mock api response")
    client = TestClient(app)
    
    # Patch settings to enable voice
    monkeypatch.setattr("app.main.get_settings", lambda: Settings(voice_enabled=True))
    
    response = client.post("/voice/interact", json={"session_id": "test_api", "transcript": "hello"})
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "completed"
    assert data["output"]["text"] != ""

def test_normalization_and_empty_transcript(monkeypatch):
    from app.agents.manager import ManagerAgent
    # Track the exact transcript passed
    received = []
    monkeypatch.setattr(ManagerAgent, "process_message", lambda self, msg, sess: received.append(msg) or "mock")
    
    svc = VoiceService()
    
    # 1. Whitespace only should fail
    v_in = VoiceInput(session_id="s_empty", transcript="   \t\n  ")
    interaction = svc.process_voice_input(v_in)
    assert interaction.status == "failed"
    assert interaction.message == "empty_transcript"
    assert len(received) == 0
    
    # 2. Normalization of extra spaces
    v_in2 = VoiceInput(session_id="s_norm", transcript="  hello   world  ")
    interaction2 = svc.process_voice_input(v_in2)
    assert interaction2.status == "completed"
    assert received[-1] == "hello world"

def test_multilingual_transcript_preservation(monkeypatch):
    from app.agents.manager import ManagerAgent
    received = []
    monkeypatch.setattr(ManagerAgent, "process_message", lambda self, msg, sess: received.append(msg) or "mock")
    
    svc = VoiceService()
    
    # Tamil
    tamil_text = "எனக்கு சென்னைல AI Engineer jobs தேடு"
    v_in_ta = VoiceInput(session_id="s_ta", transcript=tamil_text, language="ta")
    interaction_ta = svc.process_voice_input(v_in_ta)
    assert interaction_ta.input.language == "ta"
    assert interaction_ta.output.language == "ta"
    assert received[-1] == tamil_text # Preserved perfectly
    
    # Tanglish (mixed)
    tanglish_text = "Chennai la AI Engineer jobs find pannu"
    v_in_mixed = VoiceInput(session_id="s_mixed", transcript=tanglish_text, language="mixed")
    interaction_mixed = svc.process_voice_input(v_in_mixed)
    assert interaction_mixed.input.language == "mixed"
    assert interaction_mixed.output.language == "mixed"
    assert received[-1] == tanglish_text

def test_stt_language_detection_override(monkeypatch):
    from app.agents.manager import ManagerAgent
    monkeypatch.setattr(ManagerAgent, "process_message", lambda self, msg, sess: "mock")
    
    # Setup mock STT that detects 'ta'
    class DetectTaSTTProvider(SpeechToTextProvider):
        def transcribe(self, audio_reference: str, language: str = None, metadata: dict = None) -> STTResult:
            return STTResult(
                text="detected tamil text",
                language="ta",
                provider="mock",
                model="mock"
            )
            
    svc = VoiceService()
    svc.set_stt_provider(DetectTaSTTProvider())
    
    # Input has no language
    v_in = VoiceInput(session_id="s_detect", audio_reference="dummy.wav", language=None)
    interaction = svc.process_voice_input(v_in)
    
    assert interaction.input.language == "ta" # Inherited from detection
    assert interaction.output.language == "ta" # Output matches

def test_architecture_boundary():
    """
    Proves ManagerAgent does not need to know anything about audio files, TTS, or STT.
    ManagerAgent.process_message purely takes strings and returns strings.
    """
    import inspect
    from app.agents.manager import ManagerAgent
    
    # Inspect ManagerAgent.process_message signature
    sig = inspect.signature(ManagerAgent.process_message)
    params = list(sig.parameters.keys())
    
    # Should only know about 'self', 'message', 'session_id' (or similar text/session args)
    assert "audio_reference" not in params
    assert "stt_provider" not in params
    assert "tts_provider" not in params
    
    # Also verify the return type is not an audio binary
    assert sig.return_annotation is str or sig.return_annotation == inspect.Signature.empty

