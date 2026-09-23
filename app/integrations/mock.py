from typing import Dict, Any
from app.integrations.gateway import BaseIntegration
from app.integrations.models import ActionType, ActionRequest, ActionResult, ActionStatus

class MockIntegration(BaseIntegration):
    @property
    def integration_name(self) -> str:
        return "mock_integration"
        
    @property
    def supported_actions(self) -> list[ActionType]:
        return [ActionType.READ, ActionType.WRITE, ActionType.EXECUTE]
        
    def validate_arguments(self, action_type: ActionType, arguments: Dict[str, Any]) -> tuple[bool, str]:
        if action_type == ActionType.WRITE:
            if "content" not in arguments:
                return False, "Missing 'content' argument for WRITE action."
        if action_type == ActionType.EXECUTE:
            if "command" not in arguments:
                return False, "Missing 'command' argument for EXECUTE action."
        return True, ""
        
    def check_health(self) -> 'IntegrationCapability':
        from app.integrations.capabilities import IntegrationCapability, ActionCapability
        from app.integrations.models import get_action_risk_level
        
        actions = [
            ActionCapability(
                action_type=a,
                risk_level=get_action_risk_level(a),
                requires_confirmation=get_action_risk_level(a).value == "HIGH"
            ) for a in self.supported_actions
        ]
        
        # We can configure mock health via some global or just return healthy
        # Let's say healthy by default. We can monkeypatch it in tests if needed.
        return IntegrationCapability(
            integration_name=self.integration_name,
            display_name="Mock Service",
            available=True,
            authenticated=True,
            healthy=True,
            supported_actions=actions,
            health_message="Mock integration is healthy."
        )
        
    def execute(self, request: ActionRequest) -> ActionResult:
        if request.arguments.get("fail_mode") == True:
            raise RuntimeError("Simulated provider failure")
            
        data = {"executed_by": "mock"}
        # If there's a secret passed, make sure we don't leak it in result data!
        if "secret" in request.arguments:
            data["secret_safe"] = True
            
        return ActionResult(
            action_id=request.action_id,
            integration=self.integration_name,
            action_type=request.action_type,
            status=ActionStatus.SUCCESS,
            message=f"Successfully executed {request.action_type.value}",
            data=data
        )
