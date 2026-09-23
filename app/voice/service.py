import logging
import unicodedata
from typing import Optional, Dict, Any
from app.voice.models import VoiceInput, VoiceOutput, VoiceInteraction
from app.voice.interfaces import SpeechToTextProvider, TextToSpeechProvider
from app.agents.manager import ManagerAgent

logger = logging.getLogger(__name__)

def normalize_transcript(text: str) -> str:
    """
    Safely normalizes transcript text by stripping whitespace and ensuring consistent Unicode representation.
    Does NOT translate, summarize, or alter words (preserves Tamil and Tanglish verbatim).
    """
    if not text:
        return ""
    # NFKC normalizes compatibility characters, NFC is safer for preserving original characters 
    # but NFC is standard.
    normalized = unicodedata.normalize("NFC", text)
    # Strip leading/trailing whitespace and control chars
    return " ".join(normalized.split())

class VoiceService:
    """
    Coordinates voice interactions (STT -> ManagerAgent -> TTS)
    Provides a stable text-first pipeline for when providers are unavailable.
    """
    
    def __init__(self):
        self.stt_provider: Optional[SpeechToTextProvider] = None
        self.tts_provider: Optional[TextToSpeechProvider] = None
        self.agent = ManagerAgent()
        
    def set_stt_provider(self, provider: SpeechToTextProvider):
        self.stt_provider = provider
        
    def set_tts_provider(self, provider: TextToSpeechProvider):
        self.tts_provider = provider
        
    def process_voice_input(self, voice_input: VoiceInput) -> VoiceInteraction:
        """
        Main pipeline:
        1. Transcribe audio if needed
        2. Pass to ManagerAgent
        3. Synthesize response text if needed
        """
        interaction = VoiceInteraction(
            session_id=voice_input.session_id,
            input=voice_input,
            status="processing"
        )
        
        try:
            transcript = voice_input.transcript
            
            # Step 1: Transcribe if we have audio but no transcript
            if not transcript and voice_input.audio_reference:
                if not self.stt_provider:
                    interaction.status = "failed"
                    interaction.message = "Audio provided but no STT provider is configured."
                    return interaction
                
                try:
                    result = self.stt_provider.transcribe(
                        voice_input.audio_reference,
                        language=voice_input.language,
                        metadata=voice_input.metadata
                    )
                    transcript = result.text
                    interaction.input.transcript = transcript
                    
                    # Update session language metadata based on detection
                    if result.language:
                        interaction.input.language = result.language
                        
                except Exception as e:
                    logger.error(f"STT Error: {str(e)}")
                    interaction.status = "failed"
                    interaction.message = f"Transcription failed."
                    return interaction
                    
            if transcript is None:
                interaction.status = "failed"
                interaction.message = "No transcript or audio provided."
                return interaction
                
            # Normalize transcript safely
            transcript = normalize_transcript(transcript)
            interaction.input.transcript = transcript
            
            if not transcript:
                interaction.status = "failed"
                interaction.message = "empty_transcript"
                return interaction
                
            # Step 2: Pass text to ManagerAgent
            agent_response_text = self.agent.process_message(transcript, voice_input.session_id)
            
            # Use the detected or hinted language for TTS
            output_lang = interaction.input.language
            
            # Step 3: Synthesize audio response if TTS is configured
            audio_ref = None
            if self.tts_provider:
                try:
                    tts_result = self.tts_provider.synthesize(
                        agent_response_text,
                        language=output_lang
                    )
                    audio_ref = tts_result.audio_reference
                except Exception as e:
                    logger.error(f"TTS Error: {str(e)}")
                    # We don't fail the interaction if TTS fails, we just omit audio_ref
                    
            interaction.output = VoiceOutput(
                session_id=voice_input.session_id,
                text=agent_response_text,
                audio_reference=audio_ref,
                language=output_lang
            )
            
            # Fetch underlying session status from state manager
            from app.agents.state import state_manager
            session = state_manager.get_session(voice_input.session_id)
            if session and session.status.value == "waiting_for_confirmation":
                interaction.status = "waiting_for_confirmation"
            else:
                interaction.status = "completed"
                
            interaction.message = "Interaction successful."
            
        except Exception as e:
            logger.error(f"Voice pipeline error: {str(e)}")
            interaction.status = "failed"
            interaction.message = "Internal voice service error."
            
        return interaction

voice_service = VoiceService()

from app.voice.interfaces import MicrophoneProvider
import os

class VoiceConversationSession:
    """
    Manages a multi-turn voice interaction loop on behalf of a specific session.
    Provides methods to easily execute push-to-talk iterations while preserving context.
    Does not contain business logic or automatically restart recording.
    """
    def __init__(self, session_id: str, voice_svc: VoiceService, microphone: MicrophoneProvider):
        self.session_id = session_id
        self.voice_svc = voice_svc
        self.microphone = microphone
        self._in_turn = False
        
    @classmethod
    def attach(cls, session_id: str, voice_svc: VoiceService, microphone: MicrophoneProvider) -> 'VoiceConversationSession':
        """
        Attaches a voice session to an existing session_id.
        If the process restarted, this will natively recover pending orchestration state
        via the existing checkpoint infrastructure to prevent side-effect replay.
        """
        from app.agents.state import state_manager
        from app.agents.checkpoint import checkpoint_repository
        from app.agents.orchestration import orchestrator
        
        session = state_manager.get_session(session_id)
        
        # If the session appears to be a fresh in-memory object (no history, idle),
        # check if there's persistent state we should recover.
        if session.status.value == "idle" and not session.history and not session.pending_tool_call:
            latest_checkpoint = checkpoint_repository.get_latest_checkpoint_for_session(session_id)
            if latest_checkpoint:
                orchestrator.restore_orchestration(latest_checkpoint.run_id, session_id)
                
        return cls(session_id, voice_svc, microphone)
        
    def start_turn(self):
        """User presses Push-to-Talk"""
        if self._in_turn:
            raise RuntimeError("Already inside a voice turn.")
        self._in_turn = True
        try:
            self.microphone.start_recording()
        except Exception as e:
            self._in_turn = False
            raise e
        
    def end_turn(self) -> VoiceInteraction:
        """
        User releases Push-to-Talk.
        Returns the completed VoiceInteraction containing transcript, response, and status.
        """
        if not self._in_turn:
            raise RuntimeError("No active voice turn to end.")
            
        try:
            audio_path = self.microphone.stop_recording()
            v_in = VoiceInput(
                session_id=self.session_id,
                audio_reference=audio_path
            )
            interaction = self.voice_svc.process_voice_input(v_in)
            
            # Cleanup temporary microphone file now that STT is done
            if os.path.exists(audio_path):
                try:
                    os.remove(audio_path)
                except Exception as e:
                    logger.error(f"Failed to cleanup {audio_path}: {e}")
                    
            return interaction
        finally:
            self._in_turn = False

