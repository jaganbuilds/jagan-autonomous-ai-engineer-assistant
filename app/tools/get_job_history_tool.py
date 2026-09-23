from typing import Optional, List, Dict, Any
from app.tools.registry import registry
from app.database import get_job_repository

@registry.register(requires_confirmation=False)
def get_job_history(
    limit: int = 10,
    location: Optional[str] = None,
    source: Optional[str] = None,
    search_text: Optional[str] = None
) -> Dict[str, Any]:
    """
    Retrieves previously discovered and persisted jobs from the database.
    Does NOT search the internet. Only returns jobs found in previous searches.
    
    Args:
        limit: Max number of jobs to return. Default 10. Max 50.
        location: Filter by location (e.g. 'Chennai').
        source: Filter by job source (e.g. 'arbeitnow').
        search_text: Filter by text appearing in title, company, or description.
    """
    limit = min(limit, 50)
    repo = get_job_repository()
    
    try:
        jobs = repo.list_jobs(
            limit=limit,
            location=location,
            source=source,
            search_text=search_text
        )
        
        return {
            "status": "success",
            "count": len(jobs),
            "jobs": [
                {
                    "title": job.title,
                    "company": job.company,
                    "location": job.location,
                    "experience": job.experience,
                    "source": job.source,
                    "discovered_at": job.discovered_at,
                    # We omit the full description here to keep context size manageable
                }
                for job in jobs
            ]
        }
    except Exception as e:
        return {
            "status": "error",
            "error": str(e)
        }
