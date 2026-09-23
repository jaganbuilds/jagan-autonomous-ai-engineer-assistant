from typing import Optional
from pydantic import BaseModel
from app.integrations.models import ActionRequest, get_action_risk_level, ActionRiskLevel
from app.integrations.capability_service import capability_service
from app.database.action_repository import action_repository

class PreflightResult(BaseModel):
    allowed: bool
    action_id: str
    integration_name: str
    action_type: str
    risk_level: str
    requires_confirmation: bool
    integration_available: bool
    integration_authenticated: bool
    integration_healthy: bool
    reason: str
    safe_message: str

def validate_preflight(request: ActionRequest) -> PreflightResult:
    # 1. Check idempotency
    existing = action_repository.get_action(request.action_id, request.session_id, request.owner_id)
    if existing:
        status = existing["status"]
        if status in ("SUCCESS", "FAILED", "REJECTED", "VALIDATION_ERROR", "NOT_SUPPORTED", "UNAUTHORIZED", "FAILED_RECOVERY"):
            return PreflightResult(
                allowed=False,
                action_id=request.action_id,
                integration_name=request.integration,
                action_type=request.action_type.value,
                risk_level=get_action_risk_level(request.action_type).value,
                requires_confirmation=False,
                integration_available=True,
                integration_authenticated=True,
                integration_healthy=True,
                reason="ALREADY_COMPLETED",
                safe_message=f"Action {request.action_id} is already in terminal state {status}."
            )
            
    # 2. Check capabilities
    cap = capability_service.get_integration_capabilities(request.integration)
    if not cap:
        return PreflightResult(
            allowed=False,
            action_id=request.action_id,
            integration_name=request.integration,
            action_type=request.action_type.value,
            risk_level=get_action_risk_level(request.action_type).value,
            requires_confirmation=False,
            integration_available=False,
            integration_authenticated=False,
            integration_healthy=False,
            reason="UNKNOWN_INTEGRATION",
            safe_message=f"Integration '{request.integration}' is not recognized or not registered."
        )
        
    if not cap.available:
        return PreflightResult(
            allowed=False,
            action_id=request.action_id,
            integration_name=request.integration,
            action_type=request.action_type.value,
            risk_level=get_action_risk_level(request.action_type).value,
            requires_confirmation=False,
            integration_available=False,
            integration_authenticated=cap.authenticated,
            integration_healthy=cap.healthy,
            reason="INTEGRATION_UNAVAILABLE",
            safe_message=cap.health_message or "Integration is not configured."
        )
        
    if not cap.authenticated:
        return PreflightResult(
            allowed=False,
            action_id=request.action_id,
            integration_name=request.integration,
            action_type=request.action_type.value,
            risk_level=get_action_risk_level(request.action_type).value,
            requires_confirmation=False,
            integration_available=True,
            integration_authenticated=False,
            integration_healthy=cap.healthy,
            reason="AUTHENTICATION_REQUIRED",
            safe_message=cap.health_message or f"{cap.display_name} is not authenticated. Connect {cap.display_name} before attempting this action."
        )
        
    if not cap.healthy:
        return PreflightResult(
            allowed=False,
            action_id=request.action_id,
            integration_name=request.integration,
            action_type=request.action_type.value,
            risk_level=get_action_risk_level(request.action_type).value,
            requires_confirmation=False,
            integration_available=True,
            integration_authenticated=True,
            integration_healthy=False,
            reason="INTEGRATION_UNHEALTHY",
            safe_message=cap.health_message or f"{cap.display_name} is currently unhealthy or unreachable."
        )
        
    # 3. Check supported action
    supported_action = next((a for a in cap.supported_actions if a.action_type == request.action_type), None)
    if not supported_action:
        return PreflightResult(
            allowed=False,
            action_id=request.action_id,
            integration_name=request.integration,
            action_type=request.action_type.value,
            risk_level=get_action_risk_level(request.action_type).value,
            requires_confirmation=False,
            integration_available=True,
            integration_authenticated=True,
            integration_healthy=True,
            reason="UNSUPPORTED_ACTION",
            safe_message=f"Action {request.action_type.value} is not supported by {cap.display_name}."
        )
        
    # 4. Check validation (using gateway logic indirectly, but we can't easily import gateway if it depends on us)
    # Actually, the preflight can be called BY the ActionGateway, which will also do validation.
    # The requirement says: "Preflight should validate the ActionRequest before execution... Reuse integration-level argument validation where possible."
    from app.integrations.gateway import action_gateway
    integration = action_gateway._integrations.get(request.integration)
    if integration:
        is_valid, val_err = integration.validate_arguments(request.action_type, request.arguments)
        if not is_valid:
            return PreflightResult(
                allowed=False,
                action_id=request.action_id,
                integration_name=request.integration,
                action_type=request.action_type.value,
                risk_level=supported_action.risk_level.value,
                requires_confirmation=supported_action.requires_confirmation,
                integration_available=True,
                integration_authenticated=True,
                integration_healthy=True,
                reason="INVALID_REQUEST",
                safe_message=f"Validation failed: {val_err}"
            )
            
    # Everything is good
    return PreflightResult(
        allowed=True,
        action_id=request.action_id,
        integration_name=request.integration,
        action_type=request.action_type.value,
        risk_level=supported_action.risk_level.value,
        requires_confirmation=supported_action.requires_confirmation,
        integration_available=True,
        integration_authenticated=True,
        integration_healthy=True,
        reason="POLICY_PASSED",
        safe_message="Action is valid and permitted to proceed."
    )
