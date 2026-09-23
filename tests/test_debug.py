import pytest
from app.integrations.gateway import action_gateway as gw, BaseIntegration
from app.integrations.models import ActionType, ActionRequest, ActionStatus

class DummyIntegration(BaseIntegration):
    @property
    def integration_name(self) -> str:
        return "mock_integration"
        
    @property
    def supported_actions(self) -> list:
        return [ActionType.READ, ActionType.WRITE, ActionType.EXECUTE]
        
    def validate_arguments(self, action_type: ActionType, arguments: dict):
        return True, ""
        
    def execute(self, request: ActionRequest):
        from app.integrations.models import ActionResult
        return ActionResult(
            action_id=request.action_id,
            integration=self.integration_name,
            action_type=request.action_type,
            status=ActionStatus.SUCCESS,
            message="Mock action succeeded",
            data={"echo": request.arguments}
        )

def test_debug_execute():
    gw.register_integration(DummyIntegration())
    req = ActionRequest(integration="mock_integration", action_type=ActionType.READ, session_id="s")
    res = gw.execute_action(req)
    print(res)
    assert res.status == ActionStatus.SUCCESS
