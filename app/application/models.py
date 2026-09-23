from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class ApplicationPackage(BaseModel):
    status: str
    job_id: Optional[int] = None
    job_key: Optional[str] = None

    title: Optional[str] = None
    company: Optional[str] = None
    location: Optional[str] = None
    experience: Optional[str] = None
    url: Optional[str] = None

    candidate_name: Optional[str] = None
    candidate_email: Optional[str] = None

    matched_skills: list[str] = Field(default_factory=list)
    missing_skills: list[str] = Field(default_factory=list)
    match_explanation: Optional[str] = None
    next_steps: list[str] = Field(default_factory=list)

    email_subject: Optional[str] = None
    email_body: Optional[str] = None
    recipient: Optional[str] = None

    application_checklist: list[str] = Field(default_factory=list)

    message: str