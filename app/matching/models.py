from typing import List, Optional
from pydantic import BaseModel, Field

class SemanticMatchResult(BaseModel):
    """Semantic analysis of job matching provided by LLM."""
    semantically_related_skills: List[str] = Field(default_factory=list)
    additional_missing_skills: List[str] = Field(default_factory=list)
    reasoning: str
    confidence: str  # e.g., "high", "medium", "low"
    next_steps: List[str] = Field(default_factory=list)

class MatchResult(BaseModel):
    """Structured result of comparing a CandidateProfile against a Job."""
    matched_skills: List[str] = Field(default_factory=list)
    missing_skills: List[str] = Field(default_factory=list)
    
    matching_programming_languages: List[str] = Field(default_factory=list)
    matching_frameworks: List[str] = Field(default_factory=list)
    matching_ai_ml_technologies: List[str] = Field(default_factory=list)
    
    location_match: str  # "Matched", "Not Matched", "Unknown"
    experience_match: str  # "Matched", "Not Matched", "Unknown"
    education_match: str  # "Matched", "Not Matched", "Unknown"
    
    explanation: str
    next_steps: List[str] = Field(default_factory=list)
    
    semantic_analysis: Optional[SemanticMatchResult] = None
