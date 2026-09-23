from abc import ABC, abstractmethod
from typing import Optional, Dict, Any
from app.voice.models import STTResult, TTSResult

class SpeechToTextProvider(ABC):
    """
    Abstract interface for converting speech audio into text transcripts.
    Does not depend on any specific ML model or API provider.
    """
    
    @abstractmethod
    def transcribe(self, audio_reference: str, language: Optional[str] = None, metadata: Optional[Dict[str, Any]] = None) -> STTResult:
        """
        Converts audio from the given reference into a text transcript.
        
        Args:
            audio_reference: A path, URI, or identifier for the audio data.
            language: Optional language hint (e.g. 'en', 'ta').
            metadata: Provider-specific metadata.
            
        Returns:
            An STTResult containing the transcribed text and metadata.
        """
        pass

class TextToSpeechProvider(ABC):
    """
    Abstract interface for converting text into speech audio.
    Does not depend on any specific ML model or API provider.
    """
    
    @abstractmethod
    def synthesize(self, text: str, language: Optional[str] = None, metadata: Optional[Dict[str, Any]] = None) -> TTSResult:
        """
        Converts text into audio and returns a reference to the audio data.
        
        Args:
            text: The text to synthesize.
            language: Optional language hint.
            metadata: Provider-specific metadata.
            
        Returns:
            A TTSResult containing the audio reference and metadata.
        """
        pass

class MicrophoneProvider(ABC):
    """
    Abstract interface for capturing audio directly from hardware microphones.
    """
    
    @abstractmethod
    def start_recording(self) -> None:
        """Starts capturing audio from the microphone."""
        pass
        
    @abstractmethod
    def stop_recording(self) -> str:
        """
        Stops capturing audio and returns a reference to the temporary audio file.
        
        Returns:
            audio_reference (str): Path to the temporary WAV file containing the recording.
        """
        pass
