from typing import List, Optional
from app.integrations.capabilities import IntegrationCapability, CapabilityDiscoveryResponse
from app.integrations.gateway import action_gateway

class CapabilityService:
    def list_integrations(self) -> CapabilityDiscoveryResponse:
        integrations = []
        for name, integration in action_gateway._integrations.items():
            # Check capabilities safely
            try:
                cap = integration.check_health()
                integrations.append(cap)
            except Exception as e:
                # Fallback if an integration fails during check_health
                from app.integrations.capabilities import ActionCapability
                from app.integrations.models import get_action_risk_level
                
                actions = []
                try:
                    for a in integration.supported_actions:
                        risk = get_action_risk_level(a)
                        actions.append(ActionCapability(
                            action_type=a,
                            risk_level=risk,
                            requires_confirmation=risk.value == "HIGH"
                        ))
                except:
                    pass
                    
                integrations.append(IntegrationCapability(
                    integration_name=name,
                    display_name=name.capitalize(),
                    available=True,
                    authenticated=False,
                    healthy=False,
                    supported_actions=actions,
                    unavailable_reason="Health check failed",
                    health_message="Internal error during health check"
                ))
                
        return CapabilityDiscoveryResponse(integrations=integrations)
        
    def get_integration_capabilities(self, integration_name: str) -> Optional[IntegrationCapability]:
        integration = action_gateway._integrations.get(integration_name)
        if not integration:
            return None
        
        try:
            return integration.check_health()
        except Exception:
            return None

capability_service = CapabilityService()
