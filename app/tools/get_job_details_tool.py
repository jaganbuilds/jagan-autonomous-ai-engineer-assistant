from app.tools.registry import registry
from app.agents.state import state_manager

@registry.register(requires_confirmation=False)
def get_job_details(session_id: str, job_reference: str) -> dict:
    """
    Retrieves the detailed analysis of a previously searched job from the current session.
    Use this when the user asks to "analyze job 2", "tell me more about the first job", or refers to a job by ID.
    
    Args:
        session_id: Passed automatically. Do not modify.
        job_reference: The ID or position of the job (e.g., 'job_1', '1', 'job 2').
    """
    session = state_manager.get_session(session_id)
    
    if not session.job_results:
        return {
            "status": "no_jobs_in_session",
            "message": "No jobs found in the current session. Please search for jobs first."
        }
        
    job_pair = state_manager.get_job_result(session_id, job_reference)
    
    if not job_pair:
        return {
            "status": "job_not_found",
            "message": f"Could not find a job matching '{job_reference}'. Please specify a valid job ID like 'job_1'."
        }
        
    # Return the full stored JobMatchPair
    return {
        "status": "success",
        "job_id": job_reference,
        "job_details": job_pair.model_dump()
    }
