from abc import ABC, abstractmethod
from typing import List, Optional
from pydantic import BaseModel

class Job(BaseModel):
    """Structured representation of a job posting."""
    title: str
    company: str
    location: str
    experience: str
    description: str
    url: str
    
    # Optional fields for persistence and tracking
    source: str = "unknown"
    external_id: Optional[str] = None
    db_id: Optional[int] = None
    job_key: Optional[str] = None
    discovered_at: Optional[str] = None
    updated_at: Optional[str] = None

class SourceError(BaseModel):
    source: str
    error_type: str
    message: str

class AggregatedJobSearchResult(BaseModel):
    jobs: List[Job]
    sources_attempted: int
    sources_succeeded: int
    source_errors: List[SourceError]
    total_results_before_deduplication: int
    total_results_after_deduplication: int

class BaseJobSource(ABC):
    """
    Abstract interface for job sources.
    Any new platform (e.g., LinkedIn, Indeed) must implement this interface.
    """
    
    @abstractmethod
    def search(self, role: Optional[str] = None, location: Optional[str] = None, experience: Optional[str] = None) -> List[Job]:
        """
        Executes a search against the source and returns normalized Job models.
        """
        pass
