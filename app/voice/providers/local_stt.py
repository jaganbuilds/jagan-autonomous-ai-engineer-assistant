import os
import time
import logging
from typing import Optional, Dict, Any
from app.voice.interfaces import SpeechToTextProvider
from app.voice.models import STTResult
from app.config import get_settings

logger = logging.getLogger(__name__)

class LocalSTTProvider(SpeechToTextProvider):
    """
    Local Speech-to-Text Provider using faster-whisper.
    Chosen for its CPU efficiency and lightweight footprint on hardware without a dedicated GPU.
    """
    
    def __init__(self):
        self._model = None
        self._settings = get_settings()
        
    def _initialize_model(self):
        """
        Lazily initializes the faster-whisper model.
        """
        if self._model is not None:
            return
            
        try:
            from faster_whisper import WhisperModel
        except ImportError:
            raise ImportError(
                "faster-whisper is not installed. "
                "Please install it using 'pip install faster-whisper'."
            )
            
        logger.info(f"Loading faster-whisper model '{self._settings.stt_model_size}' on {self._settings.stt_device}...")
        self._model = WhisperModel(
            self._settings.stt_model_size,
            device=self._settings.stt_device,
            compute_type=self._settings.stt_compute_type
        )
        logger.info("Local STT model loaded successfully.")

    def _validate_audio(self, audio_reference: str) -> None:
        """
        Validates the audio file for security and size limits.
        """
        # Restrict to configured upload directory to prevent path traversal
        upload_dir = os.path.abspath(self._settings.stt_upload_dir)
        audio_path = os.path.abspath(audio_reference)
        
        if not audio_path.startswith(upload_dir):
            raise ValueError(f"Audio path must be within the approved upload directory: {self._settings.stt_upload_dir}")
            
        if not os.path.exists(audio_path):
            raise FileNotFoundError("Audio file not found.")
            
        if not os.path.isfile(audio_path):
            raise ValueError("Audio reference is not a file.")
            
        # Basic extension check
        ext = os.path.splitext(audio_reference)[1].lower()
        if ext not in [".wav", ".mp3", ".m4a", ".ogg", ".flac"]:
            raise ValueError(f"Unsupported audio format: {ext}")
            
        # Size check
        size_mb = os.path.getsize(audio_reference) / (1024 * 1024)
        max_mb = self._settings.stt_max_audio_mb
        if size_mb > max_mb:
            raise ValueError(f"Audio file is too large ({size_mb:.2f} MB). Max allowed is {max_mb} MB.")
            
    def transcribe(self, audio_reference: str, language: Optional[str] = None, metadata: Optional[Dict[str, Any]] = None) -> STTResult:
        """
        Transcribes the audio file using the local faster-whisper model.
        """
        self._validate_audio(audio_reference)
        self._initialize_model()
        
        start_time = time.time()
        
        # faster-whisper expects language to be None for auto-detection, or a string code
        segments, info = self._model.transcribe(
            audio_reference,
            language=language if language else None,
            beam_size=5
        )
        
        # Generator evaluation
        text = " ".join([segment.text for segment in segments]).strip()
        duration = time.time() - start_time
        
        return STTResult(
            text=text,
            language=info.language,
            duration=duration,
            confidence=info.language_probability,
            provider="local_faster_whisper",
            model=self._settings.stt_model_size,
            metadata={
                "language_probability": info.language_probability,
                "duration_seconds": info.duration
            }
        )
