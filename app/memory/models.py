from pydantic import BaseModel, Field
from typing import Optional
from enum import Enum
from datetime import datetime, timezone

class MemoryType(str, Enum):
    PREFERENCE = "preference"
    PROJECT = "project"
    CAREER = "career"
    LEARNING = "learning"
    WORKFLOW = "workflow"
    GENERAL = "general"

class MemorySource(str, Enum):
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"

class MemoryScope(str, Enum):
    SESSION = "session"
    PERSONAL = "personal"

class MemoryImportance(str, Enum):
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"

class Memory(BaseModel):
    id: Optional[int] = None
    session_id: str
    owner_id: str = "default_owner"
    memory_type: MemoryType
    content: str
    source: MemorySource
    scope: MemoryScope = MemoryScope.SESSION
    importance: MemoryImportance = MemoryImportance.NORMAL
    confidence: Optional[float] = None
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

class MemoryCandidate(BaseModel):
    memory_type: MemoryType
    content: str
    source: MemorySource
    scope: MemoryScope = MemoryScope.SESSION
    importance: MemoryImportance = MemoryImportance.NORMAL
    confidence: float
    reason: str
    category: Optional[str] = None

class MemoryExtractionResult(BaseModel):
    has_memory: bool
    candidates: list[MemoryCandidate] = Field(default_factory=list)

