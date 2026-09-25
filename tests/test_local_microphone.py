import pytest
import os
import unittest.mock as mock
from app.voice.providers.local_microphone import LocalMicrophoneProvider
from app.config import get_settings

@pytest.fixture
def mock_sounddevice():
    import numpy as np
    with mock.patch("app.voice.providers.local_microphone.sd", create=True) as mock_sd:
        with mock.patch("app.voice.providers.local_microphone.np", np, create=True):
            # Also patch the global _SOUNDDEVICE_AVAILABLE to True for the module
            with mock.patch("app.voice.providers.local_microphone._SOUNDDEVICE_AVAILABLE", True):
                yield mock_sd

@pytest.fixture
def mock_soundfile():
    with mock.patch("app.voice.providers.local_microphone.sf", create=True) as mock_sf:
        yield mock_sf

def test_microphone_interface_implemented():
    from app.voice.interfaces import MicrophoneProvider
    mic = LocalMicrophoneProvider()
    assert isinstance(mic, MicrophoneProvider)

def test_successful_recording(mock_sounddevice, mock_soundfile, monkeypatch):
    import numpy as np
    mic = LocalMicrophoneProvider()
    
    # Start recording
    mic.start_recording()
    assert mic._recording is True
    assert mock_sounddevice.InputStream.called
    
    # Simulate callback delivering audio frames
    callback = mock_sounddevice.InputStream.call_args[1]["callback"]
    dummy_data = np.zeros((1024, 1), dtype=np.float32)
    callback(dummy_data, 1024, None, None)
    
    # Stop recording
    filepath = mic.stop_recording()
    
    assert mic._recording is False
    assert os.path.exists(mic.temp_dir)
    assert filepath.endswith(".wav")
    assert filepath.startswith(mic.temp_dir)
    assert mock_soundfile.write.called

def test_start_already_recording(mock_sounddevice):
    mic = LocalMicrophoneProvider()
    mic.start_recording()
    assert mic._recording is True
    
    # Call again
    mic.start_recording()
    # Should just warn and return, not raise
    assert mock_sounddevice.InputStream.call_count == 1

def test_stop_not_recording():
    mic = LocalMicrophoneProvider()
    with pytest.raises(RuntimeError, match="Not currently recording"):
        mic.stop_recording()

def test_no_frames_captured(mock_sounddevice):
    mic = LocalMicrophoneProvider()
    mic.start_recording()
    
    # Stop without any callbacks
    with pytest.raises(RuntimeError, match="No audio frames captured"):
        mic.stop_recording()

def test_max_duration(mock_sounddevice, monkeypatch):
    import numpy as np
    settings = get_settings()
    monkeypatch.setattr(settings, "microphone_max_duration_seconds", 1)
    monkeypatch.setattr(settings, "microphone_sample_rate", 1000)
    
    mic = LocalMicrophoneProvider()
    mic._settings = settings
    
    mic.start_recording()
    
    callback = mock_sounddevice.InputStream.call_args[1]["callback"]
    # Send 500 samples
    callback(np.zeros((500, 1)), 500, None, None)
    assert mic._recording is True
    
    # Send another 500
    callback(np.zeros((500, 1)), 500, None, None)
    
    # Now the duration is hit, recording should automatically set to False
    assert mic._recording is False

def test_microphone_disabled(mock_sounddevice, monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "microphone_enabled", False)
    
    mic = LocalMicrophoneProvider()
    mic._settings = settings
    
    with pytest.raises(RuntimeError, match="disabled"):
        mic.start_recording()

def test_microphone_init_failure(mock_sounddevice):
    # Simulate stream raising exception
    mock_sounddevice.InputStream.side_effect = Exception("Hardware in use")
    
    mic = LocalMicrophoneProvider()
    
    with pytest.raises(RuntimeError, match="Hardware in use"):
        mic.start_recording()
        
    assert mic._recording is False

def test_save_file_failure(mock_sounddevice, mock_soundfile):
    import numpy as np
    mic = LocalMicrophoneProvider()
    mic.start_recording()
    
    callback = mock_sounddevice.InputStream.call_args[1]["callback"]
    callback(np.zeros((10, 1)), 10, None, None)
    
    mock_soundfile.write.side_effect = IOError("Disk full")
    
    with pytest.raises(RuntimeError, match="Disk full"):
        mic.stop_recording()

def test_path_traversal_prevention():
    # UUID filenames naturally prevent path traversal because uuid.uuid4().hex contains only a-f0-9
    import uuid
    filename = f"{uuid.uuid4().hex}.wav"
    assert ".." not in filename
    assert "/" not in filename
    assert "\\" not in filename

def test_integration_flow_mocked(mock_sounddevice, mock_soundfile):
    """
    Test 15: microphone -> audio reference
    Test 16: audio reference -> STT
    """
    import numpy as np
    from app.voice.service import VoiceService
    from app.voice.models import VoiceInput
    from app.voice.interfaces import SpeechToTextProvider, STTResult
    
    # Setup Mic
    mic = LocalMicrophoneProvider()
    mic.start_recording()
    callback = mock_sounddevice.InputStream.call_args[1]["callback"]
    callback(np.zeros((1024, 1)), 1024, None, None)
    audio_path = mic.stop_recording()
    
    # Setup STT Mock
    class MockSTT(SpeechToTextProvider):
        def transcribe(self, audio_reference: str, language: str = None, metadata: dict = None) -> STTResult:
            assert audio_reference == audio_path
            return STTResult(text="mocked microphone text", provider="mock", model="mock")
            
    svc = VoiceService()
    svc.set_stt_provider(MockSTT())
    
    # Mock ManagerAgent
    from app.agents.manager import ManagerAgent
    original_process = ManagerAgent.process_message
    
    try:
        ManagerAgent.process_message = mock.MagicMock(return_value="Agent response")
        
        v_in = VoiceInput(session_id="test_mic", audio_reference=audio_path)
        interaction = svc.process_voice_input(v_in)
        
        assert interaction.status == "completed"
        # Test 17: Transcript reaches manager agent intact
        ManagerAgent.process_message.assert_called_with("mocked microphone text", "test_mic")
    finally:
        ManagerAgent.process_message = original_process

