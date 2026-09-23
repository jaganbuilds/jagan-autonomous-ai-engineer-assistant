from typing import Optional
from app.tools.registry import registry
from app.workflows.job_matching_workflow import JobMatchingWorkflow

# Instantiate workflow with safe defaults
workflow = JobMatchingWorkflow(max_jobs=5)

@registry.register(requires_confirmation=False)
def search_and_match_jobs(session_id: str, role: Optional[str] = None, location: Optional[str] = None, experience: Optional[str] = None) -> dict:
    """
    Searches for current job postings and immediately evaluates how well they align with the current candidate's profile.
    Returns a structured list of jobs paired with their exact match results (matched skills, missing skills, etc).
    
    Args:
        session_id: Passed automatically. Do not modify.
        role: The job title or role keyword to filter by (e.g., 'AI Engineer', 'Python').
        location: The city or work model to filter by (e.g., 'Berlin', 'Remote').
        experience: The experience level required.
    """
    res = workflow.execute(session_id=session_id, role=role, location=location, experience=experience)
    
    # Store results in session for later retrieval
    from app.agents.state import state_manager
    if res.results:
        state_manager.store_job_results(session_id, res.results)
        
    res_dict = res.model_dump()
    
    # Inject job_id into the results for the LLM to see
    if res.results:
        for i, result_dict in enumerate(res_dict.get("results", []), start=1):
            result_dict["job_id"] = f"job_{i}"
            
    # Return as primitive dicts so the Tool Registry can serialize it cleanly to JSON
    return res_dict
