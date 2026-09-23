from app.integrations.models import (
    ActionRequest,
    ActionResult,
    ActionType,
    ActionStatus,
    ActionRiskLevel,
    get_action_risk_level
)
from app.integrations.gateway import ActionGateway, BaseIntegration, action_gateway
from app.integrations.gmail import GmailIntegration
from app.integrations.github import GitHubIntegration
from app.integrations.local_system import LocalSystemIntegration

# Register global integrations
action_gateway.register_integration(GmailIntegration())
action_gateway.register_integration(GitHubIntegration())
action_gateway.register_integration(LocalSystemIntegration())

__all__ = [
    "ActionRequest",
    "ActionResult",
    "ActionType",
    "ActionStatus",
    "ActionRiskLevel",
    "get_action_risk_level",
    "ActionGateway",
    "BaseIntegration",
    "action_gateway"
]
