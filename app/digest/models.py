from typing import List, Optional
from pydantic import BaseModel
from datetime import datetime

class JobDigestItem(BaseModel):
    job_id: int
    job_key: str
    title: str
    company: str
    location: str
    experience: str
    url: str
    match_explanation: Optional[str] = None
    matched_skills: List[str] = []
    missing_skills: List[str] = []
    next_steps: List[str] = []
    source: Optional[str] = None
    discovered_at: Optional[str] = None

class JobDigest(BaseModel):
    status: str
    discovery_run_id: int
    role: Optional[str] = None
    location: Optional[str] = None
    experience: Optional[str] = None
    total_new_jobs: int
    jobs_with_profile_match: int
    jobs_without_match_data: int
    items: List[JobDigestItem]
    source_errors: List[str] = []
    message: Optional[str] = None
