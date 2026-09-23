from typing import List, Optional
from pydantic import BaseModel, Field

class Project(BaseModel):
    """Represents a portfolio project created by the candidate."""
    name: str
    description: str
    technologies: List[str] = Field(default_factory=list)
    url: Optional[str] = None

class CandidateProfile(BaseModel):
    """
    Generic candidate profile structured for resume-to-JD matching.
    Fields are designed to easily map against common job posting requirements.
    """
    # Core Identity
    name: str
    experience_level: str
    education: str
    
    # Goals
    target_roles: List[str] = Field(default_factory=list)
    preferred_locations: List[str] = Field(default_factory=list)
    
    # Skills Breakdown
    skills: List[str] = Field(default_factory=list, description="General skills e.g., System Design, CI/CD")
    programming_languages: List[str] = Field(default_factory=list)
    frameworks: List[str] = Field(default_factory=list)
    databases: List[str] = Field(default_factory=list)
    ai_ml_technologies: List[str] = Field(default_factory=list)
    
    # Portfolio
    projects: List[Project] = Field(default_factory=list)
