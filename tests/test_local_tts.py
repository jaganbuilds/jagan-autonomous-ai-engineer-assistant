import pytest
import os
from unittest.mock import MagicMock
from app.voice.providers.local_tts import LocalTTSProvider
from app.config import get_settings

@pytest.fixture
def mock_pyttsx3(monkeypatch, tmp_path):
    mock_engine = MagicMock()
    
    # Setup the mock for save_to_file
    def mock_save_to_file(text, filename):
        # Create a dummy file to simulate engine behavior
        with open(filename, "w") as f:
            f.write("mock audio content")
    
    mock_engine.save_to_file.side_effect = mock_save_to_file
    
    import sys
    mock_module = MagicMock()
    mock_module.init.return_value = mock_engine
    sys.modules["pyttsx3"] = mock_module
    
    yield mock_engine
    
    del sys.modules["pyttsx3"]

def test_local_tts_initialization():
    provider = LocalTTSProvider()
    assert provider._engine is None
    
def test_local_tts_empty_text():
    provider = LocalTTSProvider()
    with pytest.raises(ValueError, match="empty"):
        provider._validate_text("")
    with pytest.raises(ValueError, match="empty"):
        provider._validate_text("   \n ")

def test_local_tts_max_length(monkeypatch):
    provider = LocalTTSProvider()
    monkeypatch.setattr(provider._settings, "tts_max_text_length", 10)
    with pytest.raises(ValueError, match="exceeds maximum allowed length"):
        provider._validate_text("this is too long")

def test_local_tts_missing_dependency():
    provider = LocalTTSProvider()
    import sys
    if "pyttsx3" in sys.modules:
        del sys.modules["pyttsx3"]
        
    with pytest.raises(ImportError, match="pyttsx3 is not installed"):
        provider._initialize_engine()

def test_local_tts_synthesize_success(mock_pyttsx3, tmp_path, monkeypatch):
    provider = LocalTTSProvider()
    # Override settings explicitly for the test instance
    provider._settings.tts_output_dir = str(tmp_path)
    
    result = provider.synthesize("hello world", language="en")
    
    assert result.audio_reference.endswith(".wav")
    assert result.audio_reference.startswith(str(tmp_path))
    assert result.language == "en"
    assert result.provider == "local_pyttsx3"
    assert result.duration is None
    assert result.metadata["char_length"] == 11
    
    assert mock_pyttsx3.save_to_file.called
    assert mock_pyttsx3.runAndWait.called
    assert os.path.exists(result.audio_reference)
    
    # Test lazy loading reuse
    result2 = provider.synthesize("test reuse")
    # init should have been called only once (handled by our mock setup intercepting it)
    # the provider._engine should remain the same
    import sys
    assert sys.modules["pyttsx3"].init.call_count == 1

def test_local_tts_synthesis_failure(mock_pyttsx3, tmp_path):
    provider = LocalTTSProvider()
    provider._settings.tts_output_dir = str(tmp_path)
    
    mock_pyttsx3.runAndWait.side_effect = Exception("Mock Engine Failure")
    
    with pytest.raises(RuntimeError, match="TTS synthesis failed"):
        provider.synthesize("fail me")

def test_local_tts_tamil_and_tanglish(mock_pyttsx3, tmp_path):
    provider = LocalTTSProvider()
    provider._settings.tts_output_dir = str(tmp_path)
    
    # Tamil Unicode
    result_ta = provider.synthesize("வணக்கம்", language="ta")
    assert result_ta.language == "ta"
    assert os.path.exists(result_ta.audio_reference)
    
    # Tanglish
    result_mixed = provider.synthesize("Chennai la jobs", language="mixed")
    assert result_mixed.language == "mixed"
    
    # The original text was preserved in save_to_file calls
    calls = mock_pyttsx3.save_to_file.call_args_list
    assert calls[0][0][0] == "வணக்கம்"
    assert calls[1][0][0] == "Chennai la jobs"
