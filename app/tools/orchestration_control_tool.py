from app.tools.registry import registry

@registry.register(requires_confirmation=False, retryable=False)
def control_orchestration(session_id: str, run_id: str, action: str) -> dict:
    """
    Safely controls the lifecycle of an orchestration run.
    Allowed actions: 'resume', 'cancel'.
    Does not allow bypassing human confirmation.
    
    Args:
        session_id: The session string ID.
        run_id: The specific orchestration run ID.
        action: The action to perform ('resume' or 'cancel').
    """
    from app.agents.run_control import run_controller
    if action == "resume":
        result = run_controller.resume(run_id, session_id)
        return result.model_dump()
    elif action == "cancel":
        result = run_controller.cancel(run_id, session_id)
        return result.model_dump()
    else:
        return {"status": "error", "message": f"Invalid action: {action}. Allowed actions: resume, cancel."}
