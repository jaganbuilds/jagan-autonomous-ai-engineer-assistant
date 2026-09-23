from pydantic import BaseModel
from typing import List, Optional
from app.job_sources.base import Job
from app.matching.models import MatchResult

class JobMatchPair(BaseModel):
    """Pairs a single Job with its corresponding MatchResult or an error."""
    job: Job
    match_result: Optional[MatchResult] = None
    error: Optional[str] = None

class WorkflowResult(BaseModel):
    """Structured result of the Search -> Match workflow."""
    status: str = "success"
    message: Optional[str] = None
    jobs_found: int = 0
    jobs_processed: int = 0
    jobs_skipped: int = 0
    results: List[JobMatchPair] = []
