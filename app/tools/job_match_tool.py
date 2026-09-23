from typing import Dict
from app.tools.registry import registry
from app.job_sources.base import Job
from app.matching.matcher import JobCandidateMatcher
from app.profile.mock_profile import MOCK_CANDIDATE

# Instantiate the matcher globally for the tool
matcher = JobCandidateMatcher()

@registry.register(requires_confirmation=False)
def match_job_to_candidate(
    title: str,
    company: str,
    description: str,
    location: str = "Not specified",
    experience: str = "Not specified",
    url: str = ""
) -> dict:
    """
    Evaluates how well a specific job posting aligns with the current candidate's profile.
    Returns an explainable match result detailing matched skills, missing skills, and location/experience alignment.
    
    Args:
        title: The job title.
        company: The company offering the job.
        description: The full text description of the job posting.
        location: The location of the job.
        experience: The required experience level.
        url: The URL to the job posting.
    """
    job = Job(
        title=title,
        company=company,
        location=location,
        experience=experience,
        description=description,
        url=url
    )
    
    # Delegate matching entirely to the deterministic matcher logic
    # using the local mock candidate for Phase 4B
    match_result = matcher.match(job, MOCK_CANDIDATE)
    
    # Return as primitive dicts so the Tool Registry can serialize it cleanly to JSON
    return match_result.model_dump()
