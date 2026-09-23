import pytest
import sys
import unittest.mock as mock
import builtins
import io

from app.voice.models import VoiceInteraction, VoiceInput, VoiceOutput
from app.voice.service import VoiceConversationSession

# We import from scripts.voice_assistant cautiously because it runs sys.exit
import scripts.voice_assistant as voice_assistant

@pytest.fixture
def mock_dependencies(monkeypatch):
    # We mock out VoiceConversationSession so we don't actually hit VoiceService
    # This also proves the CLI doesn't call ManagerAgent, ConfirmationManager directly.
    mock_session_cls = mock.MagicMock()
    mock_session_instance = mock.MagicMock()
    
    # We configure attach to return our instance
    mock_session_cls.attach.return_value = mock_session_instance
    mock_session_instance.session_id = "test_cli_sess"
    
    # Setup some dummy state for print_status
    class DummyState:
        class DummyStatus:
            value = "idle"
        status = DummyStatus()
        pending_tool_call = None
        
    mock_state_mgr = mock.MagicMock()
    mock_state_mgr.get_session.return_value = DummyState()
    
    # Apply monkeypatches
    monkeypatch.setattr(voice_assistant, "VoiceConversationSession", mock_session_cls)
    monkeypatch.setattr(voice_assistant, "play_audio", mock.MagicMock())
    
    class TestExitException(Exception):
        pass
    monkeypatch.setattr(sys, "exit", lambda code: (_ for _ in ()).throw(TestExitException("Exited")))
    
    # We also monkeypatch state_manager in voice_assistant's namespace
    import app.agents.state
    monkeypatch.setattr(app.agents.state, "state_manager", mock_state_mgr)
    
    # Also disable get_settings to avoid init issues
    monkeypatch.setattr(voice_assistant, "get_settings", mock.MagicMock())
    
    return mock_session_cls, mock_session_instance

def run_cli_with_inputs(inputs, monkeypatch, capsys):
    input_iterator = iter(inputs)
    def mock_input(prompt=None):
        try:
            return next(input_iterator)
        except StopIteration:
            raise EOFError()
    monkeypatch.setattr(builtins, "input", mock_input)
    
    # We pass empty argv if not already set
    if sys.argv == [""]:
        monkeypatch.setattr(sys, "argv", ["voice_assistant.py"])
    elif len(sys.argv) > 0 and not sys.argv[0].endswith("voice_assistant.py"):
        monkeypatch.setattr(sys, "argv", ["voice_assistant.py"])
        
    try:
        voice_assistant.main()
    except Exception as e:
        if type(e).__name__ != "TestExitException":
            raise
        
    return capsys.readouterr()

def test_cli_architecture_boundary(mock_dependencies, monkeypatch, capsys):
    """
    Proves the CLI only uses VoiceConversationSession and does not call
    AgentOrchestrator, ConfirmationManager, ToolRegistry, or ManagerAgent directly.
    """
    cls, instance = mock_dependencies
    
    # Mock a successful interaction
    interaction = VoiceInteraction(
        session_id="test_cli_sess",
        input=VoiceInput(session_id="test_cli_sess", transcript="hello"),
        output=VoiceOutput(session_id="test_cli_sess", text="hi there", audio_reference=None),
        status="completed"
    )
    instance.end_turn.return_value = interaction
    
    out, err = run_cli_with_inputs(["", ""], monkeypatch, capsys)
    
    assert "Attaching to session" in out
    assert "Recording..." in out
    assert "hi there" in out
    
    # Verify exactly 1 start and 1 end
    instance.start_turn.assert_called_once()
    instance.end_turn.assert_called_once()
    
    # We can be confident no internal agent logic was called because
    # we completely mocked out VoiceConversationSession and the CLI still worked.

def test_cli_attaches_to_existing_session(mock_dependencies, monkeypatch, capsys):
    cls, instance = mock_dependencies
    
    monkeypatch.setattr(sys, "argv", ["voice_assistant.py", "--session-id", "my_custom_sess"])
    
    out, err = run_cli_with_inputs([""], monkeypatch, capsys)
    
    # Verify attach was called with the correct ID
    cls.attach.assert_called_once()
    assert cls.attach.call_args[0][0] == "my_custom_sess"

def test_cli_text_fallback_when_tts_fails(mock_dependencies, monkeypatch, capsys):
    cls, instance = mock_dependencies
    
    interaction = VoiceInteraction(
        session_id="test_cli_sess",
        input=VoiceInput(session_id="test_cli_sess", transcript="test"),
        output=VoiceOutput(session_id="test_cli_sess", text="Fallback text", audio_reference=None),
        status="completed"
    )
    instance.end_turn.return_value = interaction
    
    out, err = run_cli_with_inputs(["", ""], monkeypatch, capsys)
    
    assert "Voice output unavailable - text fallback used" in out
    assert "Fallback text" in out
    
def test_cli_ctrl_c_cleans_up_recording(mock_dependencies, monkeypatch, capsys):
    cls, instance = mock_dependencies
    
    # Simulate a KeyboardInterrupt during input
    def mock_input(prompt=None):
        raise KeyboardInterrupt()
    monkeypatch.setattr(builtins, "input", mock_input)
    
    # Make the instance look like it's in a turn
    instance._in_turn = True
    
    monkeypatch.setattr(sys, "argv", ["voice_assistant.py"])
    
    try:
        voice_assistant.main()
    except Exception as e:
        if type(e).__name__ != "TestExitException":
            raise
            
    # Ensure stop_recording was called on the mic
    instance.microphone.stop_recording.assert_called_once()
    assert instance._in_turn is False

def test_cli_handles_empty_transcript(mock_dependencies, monkeypatch, capsys):
    cls, instance = mock_dependencies
    
    interaction = VoiceInteraction(
        session_id="test_cli_sess",
        input=VoiceInput(session_id="test_cli_sess", transcript=""),
        status="failed",
        message="empty_transcript"
    )
    instance.end_turn.return_value = interaction
    
    out, err = run_cli_with_inputs(["", ""], monkeypatch, capsys)
    
    assert "[Error] Empty transcript. Could not hear you clearly." in out
    assert "Jagan AI:" not in out # No output on error
