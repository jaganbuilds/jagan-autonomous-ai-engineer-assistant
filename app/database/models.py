from typing import Optional
from pydantic import BaseModel
from app.job_sources.base import Job

class PersistedJob(BaseModel):
    """
    Representation of a job as stored in the SQLite database.
    """
    id: int
    job_key: str
    external_id: str
    source: str
    title: str
    company: str
    location: str
    experience: str
    description: str
    url: str
    discovered_at: str
    updated_at: str

    def to_app_job(self) -> Job:
        """Converts to the application-layer Job model."""
        return Job(
            title=self.title,
            company=self.company,
            location=self.location,
            experience=self.experience,
            description=self.description,
            url=self.url,
            source=self.source,
            external_id=self.external_id,
            db_id=self.id,
            job_key=self.job_key,
            discovered_at=self.discovered_at,
            updated_at=self.updated_at
        )

class DiscoveryRun(BaseModel):
    id: int
    role: Optional[str]
    location: Optional[str]
    experience: Optional[str]
    started_at: str
    completed_at: Optional[str]
    total_found: int
    new_jobs: int
    existing_jobs: int
    jobs_processed: int
    jobs_skipped: int
    status: str

class DiscoveryRunJob(BaseModel):
    discovery_run_id: int
    job_id: int
    is_new: bool

from enum import Enum

class ApplicationStatus(str, Enum):
    PREPARED = 'PREPARED'
    APPLIED = 'APPLIED'
    UNDER_REVIEW = 'UNDER_REVIEW'
    INTERVIEW = 'INTERVIEW'
    OFFER = 'OFFER'
    REJECTED = 'REJECTED'
    WITHDRAWN = 'WITHDRAWN'

class JobApplication(BaseModel):
    id: int
    job_id: int
    session_id: str
    status: ApplicationStatus
    applied_at: Optional[str] = None
    created_at: str
    updated_at: str
    notes: Optional[str] = None
    next_action: Optional[str] = None
    follow_up_at: Optional[str] = None

