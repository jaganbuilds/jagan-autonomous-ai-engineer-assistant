import pytest
from unittest.mock import MagicMock
import os
from app.voice.providers.local_stt import LocalSTTProvider
from app.config import get_settings, Settings

@pytest.fixture
def mock_whisper_module(monkeypatch):
    """Mocks the faster_whisper module to avoid real downloads during tests."""
    mock_model_class = MagicMock()
    
    # Setup the mock instance returned by WhisperModel()
    mock_instance = MagicMock()
    
    # Mock segments and info returned by transcribe()
    mock_segment = MagicMock()
    mock_segment.text = "this is a mock transcription"
    
    mock_info = MagicMock()
    mock_info.language = "en"
    mock_info.language_probability = 0.99
    mock_info.duration = 5.0
    
    mock_instance.transcribe.return_value = ([mock_segment], mock_info)
    mock_model_class.return_value = mock_instance
    
    import sys
    mock_faster_whisper = MagicMock()
    mock_faster_whisper.WhisperModel = mock_model_class
    sys.modules["faster_whisper"] = mock_faster_whisper
    
    yield mock_model_class
    
    del sys.modules["faster_whisper"]

@pytest.fixture
def mock_audio_file(monkeypatch):
    monkeypatch.setattr(os.path, "exists", lambda path: True)
    monkeypatch.setattr(os.path, "isfile", lambda path: True)
    monkeypatch.setattr(os.path, "getsize", lambda path: 1024 * 1024) # 1 MB

def test_local_stt_provider_initialization():
    provider = LocalSTTProvider()
    assert provider._model is None
    assert provider._settings is not None

def test_local_stt_missing_audio():
    provider = LocalSTTProvider()
    with pytest.raises(FileNotFoundError, match="Audio file not found"):
        provider._validate_audio("temp_audio/missing_file.wav")

def test_local_stt_invalid_format(monkeypatch):
    monkeypatch.setattr(os.path, "exists", lambda path: True)
    monkeypatch.setattr(os.path, "isfile", lambda path: True)
    provider = LocalSTTProvider()
    with pytest.raises(ValueError, match="Unsupported audio format"):
        provider._validate_audio("temp_audio/test.txt")

def test_local_stt_oversized_audio(monkeypatch):
    monkeypatch.setattr(os.path, "exists", lambda path: True)
    monkeypatch.setattr(os.path, "isfile", lambda path: True)
    # Mock file size to be 20 MB, which is > 10 MB default
    monkeypatch.setattr(os.path, "getsize", lambda path: 20 * 1024 * 1024)
    provider = LocalSTTProvider()
    with pytest.raises(ValueError, match="too large"):
        provider._validate_audio("temp_audio/test.wav")

def test_local_stt_transcribe_success(mock_whisper_module, mock_audio_file):
    provider = LocalSTTProvider()
    
    result = provider.transcribe("temp_audio/test.wav")
    
    assert result.text == "this is a mock transcription"
    assert result.language == "en"
    assert result.confidence == 0.99
    assert result.provider == "local_faster_whisper"
    assert result.model == "tiny"
    
    # Model should be reused on second call
    result2 = provider.transcribe("temp_audio/test2.wav")
    assert mock_whisper_module.call_count == 1

def test_local_stt_language_hint(mock_whisper_module, mock_audio_file):
    provider = LocalSTTProvider()
    provider.transcribe("temp_audio/test.wav", language="ta")
    
    mock_instance = mock_whisper_module.return_value
    mock_instance.transcribe.assert_called_with("temp_audio/test.wav", language="ta", beam_size=5)

def test_local_stt_tanglish_hint(mock_whisper_module, mock_audio_file):
    provider = LocalSTTProvider()
    provider.transcribe("temp_audio/test.wav", language=None)
    
    mock_instance = mock_whisper_module.return_value
    mock_instance.transcribe.assert_called_with("temp_audio/test.wav", language=None, beam_size=5)

def test_local_stt_missing_dependency(monkeypatch):
    provider = LocalSTTProvider()
    
    # Mock __import__ to raise ImportError for faster_whisper
    original_import = __import__
    def mock_import(name, *args, **kwargs):
        if name == "faster_whisper":
            raise ImportError("faster-whisper is not installed")
        return original_import(name, *args, **kwargs)
        
    monkeypatch.setattr("builtins.__import__", mock_import)
        
    with pytest.raises(ImportError, match="faster-whisper is not installed"):
        provider._initialize_model()
