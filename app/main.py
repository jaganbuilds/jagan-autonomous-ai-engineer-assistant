from fastapi import FastAPI
import logging

from app.schemas import ChatRequest, ChatResponse
from app.agents.manager import ManagerAgent
from app.config import get_settings

# Configure basic logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="Jagan AI API",
    description="Backend API for Jagan AI - Autonomous AI Engineer Assistant",
    version="0.1.0"
)

# Initialize Manager Agent
manager_agent = ManagerAgent()

@app.get("/")
def read_root():
    return {"message": "Welcome to Jagan AI API (Phase 1 MVP)"}

@app.post("/chat", response_model=ChatResponse)
def chat(request: ChatRequest):
    """
    Main endpoint for text interaction with Jagan AI.
    """
    logger.info(f"Received message from session {request.session_id}: {request.message}")
    
    # Process message through Manager Agent
    reply = manager_agent.process_message(request.message, session_id=request.session_id)
    
    from app.agents.state import state_manager
    current_status = state_manager.get_session(request.session_id).status.value
    
    # Check for configuration errors (returned as strings in MVP)
    if reply.startswith("Configuration Error") or reply.startswith("Error"):
        return ChatResponse(response="", error=reply, status="error")
        
    return ChatResponse(response=reply, status=current_status)

from app.voice.models import VoiceInput, VoiceInteraction
from app.voice.service import voice_service
from app.voice.providers import LocalSTTProvider, LocalTTSProvider

# Configure VoiceService Providers
def configure_voice_service():
    settings = get_settings()
    if settings.stt_provider == "local":
        voice_service.set_stt_provider(LocalSTTProvider())
    if settings.tts_provider == "local":
        voice_service.set_tts_provider(LocalTTSProvider())

configure_voice_service()

@app.post("/voice/interact", response_model=VoiceInteraction)
def voice_interact(request: VoiceInput):
    """
    Endpoint for voice-based interaction (Phase 8).
    Currently supports transcript-first interactions to decouple from real STT/TTS hardware during testing.
    """
    settings = get_settings()
    if not settings.voice_enabled:
        return VoiceInteraction(
            session_id=request.session_id,
            input=request,
            status="failed",
            message="Voice features are currently disabled in configuration."
        )
        
    logger.info(f"Received voice interaction for session {request.session_id}")
    interaction = voice_service.process_voice_input(request)
    return interaction
