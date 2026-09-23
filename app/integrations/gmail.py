from typing import Dict, Any, Tuple
import re

from app.integrations.gateway import BaseIntegration
from app.integrations.models import ActionType, ActionRequest, ActionResult, ActionStatus, get_action_risk_level
from app.integrations.capabilities import IntegrationCapability, ActionCapability

class GmailIntegration(BaseIntegration):
    @property
    def integration_name(self) -> str:
        return "gmail"
        
    @property
    def supported_actions(self) -> list[ActionType]:
        return [ActionType.SEND]
        
    def validate_arguments(self, action_type: ActionType, arguments: Dict[str, Any]) -> Tuple[bool, str]:
        if action_type == ActionType.SEND:
            to = arguments.get("to")
            subject = arguments.get("subject")
            body = arguments.get("body")
            
            if not to or not isinstance(to, str) or not to.strip():
                return False, "Missing or invalid recipient address ('to')."
            if not subject or not isinstance(subject, str) or not subject.strip():
                return False, "Missing or invalid 'subject'."
            if not body or not isinstance(body, str) or not body.strip():
                return False, "Missing or invalid 'body'."
                
            # Basic email regex
            if not re.match(r"[^@]+@[^@]+\.[^@]+", to.strip()):
                return False, f"Invalid email format: {to}"
                
        return True, ""
        
    def check_health(self) -> IntegrationCapability:
        from app.email.gmail_client import GmailClient
        
        client = GmailClient()
        state = client.check_credentials_state()
        
        actions = [
            ActionCapability(
                action_type=a,
                risk_level=get_action_risk_level(a),
                requires_confirmation=get_action_risk_level(a).value == "HIGH"
            ) for a in self.supported_actions
        ]
        
        return IntegrationCapability(
            integration_name=self.integration_name,
            display_name="Gmail",
            available=state["configured"],
            authenticated=state["authenticated"],
            healthy=state["authenticated"],  # For Gmail, authenticated means healthy since we don't ping the API for health
            supported_actions=actions,
            unavailable_reason=None if state["configured"] else state["reason"],
            health_message=state["reason"]
        )
        
    def execute(self, request: ActionRequest) -> ActionResult:
        from app.email.gmail_client import GmailClient
        
        # Defensive programming: it should be validated already, but we guard.
        if request.action_type != ActionType.SEND:
            return ActionResult(
                action_id=request.action_id,
                integration=self.integration_name,
                action_type=request.action_type,
                status=ActionStatus.NOT_SUPPORTED,
                message=f"Action {request.action_type} is not supported by Gmail."
            )
            
        client = GmailClient()
        
        # We don't log the body/subject here; just send it.
        result = client.send_email(
            to=request.arguments.get("to", ""),
            subject=request.arguments.get("subject", ""),
            body=request.arguments.get("body", "")
        )
        
        if result.success:
            return ActionResult(
                action_id=request.action_id,
                integration=self.integration_name,
                action_type=ActionType.SEND,
                status=ActionStatus.SUCCESS,
                message="Email sent successfully.",
                data={"message_id": result.message_id, "recipient": result.recipient}
            )
        else:
            return ActionResult(
                action_id=request.action_id,
                integration=self.integration_name,
                action_type=ActionType.SEND,
                status=ActionStatus.FAILED,
                message=f"Email could not be sent: {result.error_message}",
                data={"error_code": result.error_code}
            )
