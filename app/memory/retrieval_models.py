from pydantic import BaseModel, Field
from typing import List, Optional
from app.memory.models import MemoryType, MemoryScope, MemoryImportance

class MemoryRetrievalItem(BaseModel):
    memory_id: int
    content: str
    memory_type: MemoryType
    scope: MemoryScope
    importance: MemoryImportance
    keyword_score: int
    semantic_score: float = 0.0
    relevance_score: float
    matched_keywords: List[str]
    retrieval_method: str
    retrieval_reason: str

class MemoryRetrievalResult(BaseModel):
    selected_memories: List[MemoryRetrievalItem] = Field(default_factory=list)
    session_memories: List[MemoryRetrievalItem] = Field(default_factory=list)
    personal_memories: List[MemoryRetrievalItem] = Field(default_factory=list)

class MemoryContextTrace(BaseModel):
    query: str
    selected_memory_ids: List[int]
    session_memory_ids: List[int]
    personal_memory_ids: List[int]
    total_items: int
    total_characters: int
    retrieval_method: str = "keyword_overlap"
    threshold_applied: Optional[float] = None
    items: List[MemoryRetrievalItem] = Field(default_factory=list)
