from typing import List, Optional
from pydantic import BaseModel
from app.integrations.models import ActionType, ActionRiskLevel

class ActionCapability(BaseModel):
    action_type: ActionType
    risk_level: ActionRiskLevel
    requires_confirmation: bool

class IntegrationCapability(BaseModel):
    integration_name: str
    display_name: str
    available: bool
    authenticated: bool
    healthy: bool
    supported_actions: List[ActionCapability]
    unavailable_reason: Optional[str] = None
    health_message: Optional[str] = None

class CapabilityDiscoveryResponse(BaseModel):
    integrations: List[IntegrationCapability]
