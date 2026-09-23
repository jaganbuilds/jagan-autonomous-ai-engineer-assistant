from typing import Optional, Dict, Any
from app.tools.registry import registry
from app.discovery.service import JobDiscoveryService

discovery_service = JobDiscoveryService()

@registry.register(requires_confirmation=False)
def discover_new_jobs(
    role: Optional[str] = None,
    location: Optional[str] = None,
    experience: Optional[str] = None,
    session_id: Optional[str] = None
) -> Dict[str, Any]:
    """
    Triggers a background job discovery run.
    Aggregates jobs from all enabled sources, persists them, identifies NEW jobs vs existing jobs,
    and matches any new jobs against the candidate profile.
    
    Args:
        role: The job title or role keyword to filter by (e.g., 'AI Engineer', 'Python').
        location: The city or work model to filter by (e.g., 'Chennai', 'Remote').
        experience: The experience level required (e.g., 'fresher', '0-1 years', '5+ years').
    """
    
    result = discovery_service.run(
        role=role,
        location=location,
        experience=experience,
        session_id=session_id
    )
    
    return result.model_dump()
