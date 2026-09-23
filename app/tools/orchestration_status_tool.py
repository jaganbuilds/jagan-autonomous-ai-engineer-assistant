from app.tools.registry import registry

@registry.register(requires_confirmation=False, retryable=False)
def get_orchestration_status(session_id: str, run_id: str) -> dict:
    """
    Retrieves the current safe status of a specific orchestration run.
    Does not execute tools or modify state.
    
    Args:
        session_id: The session string ID.
        run_id: The specific orchestration run ID.
    """
    from app.agents.run_control import run_controller
    status = run_controller.get_status(run_id, session_id)
    if not status:
        return {"status": "error", "message": "Run not found or session mismatch."}
        
    return status.model_dump()
