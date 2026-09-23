from typing import Optional, Dict, Any
from pydantic import BaseModel, Field

class VoiceInput(BaseModel):
    session_id: str
    audio_reference: Optional[str] = None
    transcript: Optional[str] = None
    language: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)

class VoiceOutput(BaseModel):
    session_id: str
    text: str
    audio_reference: Optional[str] = None
    language: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)

class VoiceInteraction(BaseModel):
    session_id: str
    input: VoiceInput
    output: Optional[VoiceOutput] = None
    status: str = "pending"
    message: str = ""

class STTResult(BaseModel):
    text: str
    language: Optional[str] = None
    duration: Optional[float] = None
    confidence: Optional[float] = None
    provider: str
    model: str
    metadata: Dict[str, Any] = Field(default_factory=dict)

class TTSResult(BaseModel):
    audio_reference: str
    language: Optional[str] = None
    duration: Optional[float] = None
    provider: str
    model: str
    format: str
    metadata: Dict[str, Any] = Field(default_factory=dict)

