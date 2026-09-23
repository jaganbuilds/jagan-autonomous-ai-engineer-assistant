from typing import List, Optional
from pydantic import BaseModel
from app.job_sources.base import SourceError
from app.matching.models import MatchResult

class DiscoveredJobSummary(BaseModel):
    job_id: int
    title: str
    company: str
    location: str
    url: str
    source: str
    is_new: bool
    match_result: Optional[MatchResult] = None
    error: Optional[str] = None

class JobDiscoveryResult(BaseModel):
    status: str
    role: Optional[str]
    location: Optional[str]
    experience: Optional[str]
    run_id: int
    sources_attempted: int
    sources_succeeded: int
    source_errors: List[SourceError]
    total_found: int
    new_jobs: int
    existing_jobs: int
    jobs_processed: int
    jobs_skipped: int
    jobs: List[DiscoveredJobSummary]
