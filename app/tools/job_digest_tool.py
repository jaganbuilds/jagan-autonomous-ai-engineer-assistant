from typing import Optional, Dict, Any
from app.tools.registry import registry
from app.digest.service import JobDigestService

digest_service = JobDigestService()

@registry.register(requires_confirmation=False)
def get_new_job_digest(
    discovery_run_id: int,
    session_id: Optional[str] = None
) -> Dict[str, Any]:
    """
    Retrieves a human-readable digest of strictly NEW jobs found in a specific discovery run.
    This digest includes relevant match data (if the job was matched against the user's profile)
    but does not contain scores or full job descriptions.
    
    Args:
        discovery_run_id: The ID of the discovery run to review (returned by discover_new_jobs).
    """
    
    result = digest_service.get_digest(
        discovery_run_id=discovery_run_id,
        session_id=session_id
    )
    
    return result.model_dump()
