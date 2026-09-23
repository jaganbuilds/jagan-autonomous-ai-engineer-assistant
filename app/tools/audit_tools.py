from typing import Optional, Dict, Any, List
from app.tools.registry import registry
from app.integrations.audit import audit_service
from app.agents.state import state_manager

@registry.register(requires_confirmation=False)
def list_action_history(session_id: str, integration_name: Optional[str] = None, 
                        action_type: Optional[str] = None, status: Optional[str] = None, 
                        limit: int = 50, offset: int = 0) -> List[Dict[str, Any]]:
    """
    Lists historical actions for the current session. Use this to inspect what side effects or external API calls have occurred.
    
    Args:
        session_id: Passed automatically. Do not modify.
        integration_name: Filter by integration (e.g. 'github', 'gmail').
        action_type: Filter by action type (e.g. 'WRITE', 'READ', 'SEND').
        status: Filter by status (e.g. 'SUCCESS', 'FAILED', 'REJECTED', 'PENDING_CONFIRMATION').
        limit: Maximum number of records to return (max 100). Default is 50.
        offset: Offset for pagination. Default is 0.
    """
    # Fetch owner_id from memory or session, or default
    owner_id = "default_owner"
    
    # Safe bounded limit
    safe_limit = min(max(1, limit), 100)
    
    return audit_service.list_actions(
        session_id=session_id,
        owner_id=owner_id,
        integration_name=integration_name,
        action_type=action_type,
        status=status,
        limit=safe_limit,
        offset=offset
    )

@registry.register(requires_confirmation=False)
def get_action_audit(session_id: str, action_id: str) -> Dict[str, Any]:
    """
    Retrieves the detailed audit record for a specific action by its action_id.
    
    Args:
        session_id: Passed automatically. Do not modify.
        action_id: The unique identifier of the action to retrieve.
    """
    owner_id = "default_owner"
    record = audit_service.get_action_audit(session_id=session_id, owner_id=owner_id, action_id=action_id)
    if not record:
        return {"error": f"Action {action_id} not found or access denied."}
    return record

@registry.register(requires_confirmation=False)
def get_action_statistics(session_id: str) -> Dict[str, Any]:
    """
    Retrieves execution statistics for historical actions in the current session.
    Provides counts grouped by status, integration, and action type, as well as success/failure rates.
    
    Args:
        session_id: Passed automatically. Do not modify.
    """
    owner_id = "default_owner"
    return audit_service.get_action_statistics(session_id=session_id, owner_id=owner_id)
