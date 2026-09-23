import os
import uuid
import logging
from typing import Optional, Dict, Any
from app.voice.interfaces import TextToSpeechProvider
from app.voice.models import TTSResult
from app.config import get_settings

logger = logging.getLogger(__name__)

class LocalTTSProvider(TextToSpeechProvider):
    """
    Local Text-to-Speech Provider using pyttsx3.
    Chosen for zero-dependency CPU efficiency without large ML model downloads.
    """
    
    def __init__(self):
        self._engine = None
        self._settings = get_settings()
        
    def _initialize_engine(self):
        """
        Lazily initializes the pyttsx3 engine.
        """
        if self._engine is not None:
            return
            
        try:
            import pyttsx3
        except ImportError:
            raise ImportError(
                "pyttsx3 is not installed. "
                "Please install it using 'pip install pyttsx3'."
            )
            
        logger.info(f"Initializing local pyttsx3 TTS engine...")
        self._engine = pyttsx3.init()
        logger.info("Local TTS engine initialized successfully.")
        
    def _validate_text(self, text: str) -> None:
        if not text or not text.strip():
            raise ValueError("Text to synthesize is empty.")
            
        if len(text) > self._settings.tts_max_text_length:
            raise ValueError(f"Text exceeds maximum allowed length of {self._settings.tts_max_text_length} characters.")

    def synthesize(self, text: str, language: Optional[str] = None, metadata: Optional[Dict[str, Any]] = None) -> TTSResult:
        """
        Synthesizes text into audio and saves it safely in the configured output directory.
        """
        self._validate_text(text)
        self._initialize_engine()
        
        # Ensure output directory exists and is absolute to prevent path traversal
        output_dir = os.path.abspath(self._settings.tts_output_dir)
        os.makedirs(output_dir, exist_ok=True)
        
        # Generate safe filename
        filename = f"response_{uuid.uuid4().hex}.wav"
        output_path = os.path.join(output_dir, filename)
        
        # We don't try to force translate Tanglish/Tamil here. We let the OS voice handle it.
        # This honors the architectural boundary of not re-translating content.
        
        try:
            self._engine.save_to_file(text, output_path)
            self._engine.runAndWait()
        except Exception as e:
            logger.error(f"pyttsx3 synthesis failed: {str(e)}")
            raise RuntimeError("TTS synthesis failed.") from e
            
        if not os.path.exists(output_path):
            raise RuntimeError("TTS synthesis completed but output file was not found.")
            
        return TTSResult(
            audio_reference=output_path,
            language=language,
            duration=None, # pyttsx3 does not easily provide duration without parsing the file
            provider="local_pyttsx3",
            model=self._settings.tts_model,
            format="wav",
            metadata={
                "char_length": len(text)
            }
        )
