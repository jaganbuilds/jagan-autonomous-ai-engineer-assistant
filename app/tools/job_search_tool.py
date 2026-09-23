from typing import List, Optional
import os
from app.tools.registry import registry
from app.job_sources import source_registry

@registry.register()
def search_jobs(role: Optional[str] = None, location: Optional[str] = None, experience: Optional[str] = None) -> List[dict]:
    """
    Searches for current job postings based on role, location, and experience criteria.
    Returns a list of structured job dictionaries.
    
    Args:
        role: The job title or role keyword to filter by (e.g., 'AI Engineer', 'Python').
        location: The city or work model to filter by (e.g., 'Chennai', 'Remote').
        experience: The experience level required (e.g., 'fresher', '0-1 years', '5+ years').
    """
    if os.environ.get("USE_MOCK_JOBS", "False").lower() == "true":
        from app.job_sources.mock_source import MockJobSource
        jobs = MockJobSource().search(role=role, location=location, experience=experience)
    else:
        aggregator = source_registry.get_aggregator()
        agg_result = aggregator.search(role=role, location=location, experience=experience)
        jobs = agg_result.jobs
    
    return [job.model_dump() for job in jobs]
