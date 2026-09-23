from typing import Dict, Any, List
from app.tools.registry import registry
from app.integrations.capability_service import capability_service

@registry.register(requires_confirmation=False)
def list_integrations() -> Dict[str, Any]:
    """
    Lists all available external integrations (like GitHub, Gmail) and their overall health status.
    Use this to discover what the system can connect to and whether it is configured.
    """
    resp = capability_service.list_integrations()
    return resp.model_dump()

@registry.register(requires_confirmation=False)
def get_integration_capabilities(integration_name: str) -> Dict[str, Any]:
    """
    Retrieves the specific supported actions (READ, WRITE, etc.) and risk levels for an integration.
    Also returns the authentication and health status.
    
    Args:
        integration_name: The internal name of the integration (e.g., 'github', 'gmail').
    """
    cap = capability_service.get_integration_capabilities(integration_name)
    if not cap:
        return {"error": f"Integration '{integration_name}' is not registered."}
    return cap.model_dump()

@registry.register(requires_confirmation=False)
def check_integration_health(integration_name: str) -> Dict[str, Any]:
    """
    Checks if a specific integration is currently healthy, authenticated, and reachable.
    This does NOT execute any business actions. It only checks connection status.
    
    Args:
        integration_name: The internal name of the integration (e.g., 'github', 'gmail').
    """
    # This maps to the same capability output, which includes health.
    cap = capability_service.get_integration_capabilities(integration_name)
    if not cap:
        return {"error": f"Integration '{integration_name}' is not registered."}
    return {
        "integration_name": cap.integration_name,
        "available": cap.available,
        "authenticated": cap.authenticated,
        "healthy": cap.healthy,
        "health_message": cap.health_message
    }
@registry.register(requires_confirmation=False)
def preflight_action(integration: str, action_type: str, session_id: str, arguments: Dict[str, Any] = None) -> Dict[str, Any]:
    """
    Validates whether an action is currently allowed and ready to execute without actually executing it.
    Use this to check if credentials, health, and policies permit the action before attempting it.
    
    Args:
        integration: The internal name of the integration (e.g., 'github', 'gmail').
        action_type: The action type string (e.g., 'READ', 'WRITE', 'SEND').
        session_id: The current session ID.
        arguments: Optional dictionary of arguments for the action.
    """
    from app.integrations.models import ActionRequest, ActionType
    from app.integrations.preflight import validate_preflight
    import uuid
    
    try:
        a_type = ActionType(action_type.upper())
    except ValueError:
        return {"error": f"Invalid action_type '{action_type}'. Must be one of {[e.value for e in ActionType]}"}
        
    req = ActionRequest(
        action_id=f"preflight_{uuid.uuid4()}",
        integration=integration,
        action_type=a_type,
        session_id=session_id,
        owner_id="default_owner", # In real system, maybe from auth context
        arguments=arguments or {}
    )
    
    res = validate_preflight(req)
    return res.model_dump()
