import os
import uuid
import logging
from typing import Optional

try:
    import sounddevice as sd
    import numpy as np
    import soundfile as sf
    _SOUNDDEVICE_AVAILABLE = True
except ImportError:
    _SOUNDDEVICE_AVAILABLE = False

from app.voice.interfaces import MicrophoneProvider
from app.config import get_settings

logger = logging.getLogger(__name__)

class LocalMicrophoneProvider(MicrophoneProvider):
    def __init__(self):
        self._settings = get_settings()
        self._recording = False
        self._frames = []
        self._stream = None
        
        # Ensure temp directory exists
        self.temp_dir = self._settings.microphone_temp_dir
        if not os.path.isabs(self.temp_dir):
            self.temp_dir = os.path.abspath(self.temp_dir)
        os.makedirs(self.temp_dir, exist_ok=True)
        
    def _audio_callback(self, indata, frames, time, status):
        if status:
            logger.warning(f"Microphone status: {status}")
        if self._recording:
            # We copy because indata might be reused
            self._frames.append(indata.copy())
            
            # Check duration limits
            current_samples = sum(len(f) for f in self._frames)
            max_samples = self._settings.microphone_sample_rate * self._settings.microphone_max_duration_seconds
            if current_samples >= max_samples:
                logger.info("Maximum recording duration reached.")
                # We can't synchronously stop from within the callback in sounddevice easily 
                # without blocking, but setting recording to False stops accumulating.
                self._recording = False

    def start_recording(self) -> None:
        if not _SOUNDDEVICE_AVAILABLE:
            raise RuntimeError("Microphone capture requires 'sounddevice' and 'soundfile' libraries.")
            
        if not self._settings.microphone_enabled:
            raise RuntimeError("Microphone is disabled in configuration.")
            
        if self._recording:
            logger.warning("Already recording.")
            return
            
        self._frames = []
        self._recording = True
        
        try:
            self._stream = sd.InputStream(
                samplerate=self._settings.microphone_sample_rate,
                channels=self._settings.microphone_channels,
                callback=self._audio_callback
            )
            self._stream.start()
            logger.info("Started microphone recording.")
        except Exception as e:
            self._recording = False
            self._stream = None
            logger.error(f"Failed to start microphone: {e}")
            raise RuntimeError(f"Microphone initialization failed: {str(e)}")
            
    def stop_recording(self) -> str:
        if not self._stream:
            raise RuntimeError("Not currently recording.")
            
        self._recording = False
        
        try:
            self._stream.stop()
            self._stream.close()
        except Exception as e:
            logger.error(f"Error stopping stream: {e}")
        finally:
            self._stream = None
                
        if not self._frames:
            raise RuntimeError("No audio frames captured.")
            
        # Write to WAV securely
        filename = f"{uuid.uuid4().hex}.wav"
        filepath = os.path.join(self.temp_dir, filename)
        
        try:
            audio_data = np.concatenate(self._frames, axis=0)
            
            # Write to disk
            sf.write(
                filepath, 
                audio_data, 
                self._settings.microphone_sample_rate,
                subtype='PCM_16'
            )
            logger.info(f"Saved recording to {filepath}")
            return filepath
            
        except Exception as e:
            logger.error(f"Failed to save audio file: {e}")
            raise RuntimeError(f"Audio save failed: {str(e)}")
