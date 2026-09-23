import pytest
from unittest.mock import patch, MagicMock
from app.integrations.models import ActionRequest, ActionType, ActionStatus
from app.integrations.gateway import action_gateway, BaseIntegration, ActionResult
from app.database.action_repository import action_repository

class DummyMockIntegration(BaseIntegration):
    @property
    def integration_name(self) -> str:
        return "mock_integration"
    @property
    def supported_actions(self) -> list:
        return [ActionType.WRITE, ActionType.READ]
    def validate_arguments(self, action_type, arguments):
        return True, ""
    def execute(self, request):
        return ActionResult(
            action_id=request.action_id,
            integration=self.integration_name,
            action_type=request.action_type,
            status=ActionStatus.SUCCESS,
            message="Mock executed",
            data={"foo": "bar"}
        )

@pytest.fixture(autouse=True)
def setup_mock_integration():
    integration = DummyMockIntegration()
    action_gateway.register_integration(integration)
    yield
    # No need to unregister since we re-use

def test_persistence_action_creation():
    req = ActionRequest(integration="mock_integration", action_type=ActionType.WRITE, session_id="sess_1", owner_id="owner_1", arguments={"test": "data"})
    res = action_gateway.execute_action(req)
    assert res.status == ActionStatus.WAITING_FOR_CONFIRMATION
    
    # Check DB
    db_act = action_repository.get_action(req.action_id, "sess_1", "owner_1")
    assert db_act is not None
    assert db_act["status"] == "PENDING_CONFIRMATION"
    assert db_act["request_payload"]["test"] == "data"
    
def test_persistence_status_transitions_and_result():
    req = ActionRequest(integration="mock_integration", action_type=ActionType.WRITE, session_id="sess_2", owner_id="owner_2")
    action_gateway.execute_action(req)
    
    res = action_gateway.confirm_pending_action("sess_2")
    assert res.status == ActionStatus.SUCCESS
    
    db_act = action_repository.get_action(req.action_id, "sess_2", "owner_2")
    assert db_act["status"] == "SUCCESS"
    assert db_act["result_payload"]["foo"] == "bar"

def test_persistence_rejection():
    req = ActionRequest(integration="mock_integration", action_type=ActionType.WRITE, session_id="sess_3", owner_id="owner_3")
    action_gateway.execute_action(req)
    
    res = action_gateway.reject_pending_action("sess_3")
    assert res.status == ActionStatus.REJECTED
    
    db_act = action_repository.get_action(req.action_id, "sess_3", "owner_3")
    assert db_act["status"] == "REJECTED"

def test_idempotency_duplicate_completed_action():
    req = ActionRequest(integration="mock_integration", action_type=ActionType.WRITE, session_id="sess_4", owner_id="owner_4")
    action_gateway.execute_action(req)
    action_gateway.confirm_pending_action("sess_4")
    
    # Resubmit exact same request
    res2 = action_gateway.execute_action(req)
    assert res2.status == ActionStatus.SUCCESS
    assert "Loaded from persistent cache" in res2.message

def test_idempotency_duplicate_pending_action():
    req = ActionRequest(integration="mock_integration", action_type=ActionType.WRITE, session_id="sess_5", owner_id="owner_5")
    action_gateway.execute_action(req)
    
    # Resubmit exact same request
    res2 = action_gateway.execute_action(req)
    assert res2.status == ActionStatus.WAITING_FOR_CONFIRMATION
    
def test_concurrency_two_confirmations():
    req = ActionRequest(integration="mock_integration", action_type=ActionType.WRITE, session_id="sess_6", owner_id="owner_6")
    action_gateway.execute_action(req)
    
    # Confirm first time
    res1 = action_gateway.confirm_pending_action("sess_6")
    assert res1.status == ActionStatus.SUCCESS
    
    # Confirm second time - no pending action
    res2 = action_gateway.confirm_pending_action("sess_6")
    assert res2.status == ActionStatus.FAILED
    assert res2.message == "No pending action to confirm."

def test_isolation_session_and_owner():
    req = ActionRequest(integration="mock_integration", action_type=ActionType.WRITE, session_id="sess_7", owner_id="owner_7")
    action_gateway.execute_action(req)
    
    # Wrong session
    assert action_gateway.confirm_pending_action("sess_wrong").status == ActionStatus.FAILED
    
    db_act = action_repository.get_action(req.action_id, "sess_7", "wrong_owner")
    assert db_act is None

def test_security_secrets_never_persisted():
    req = ActionRequest(integration="mock_integration", action_type=ActionType.READ, session_id="sess_8", owner_id="owner_8", arguments={
        "github_token": "ghp_12345",
        "password": "secretpassword",
        "safe_data": "hello"
    })
    action_gateway.execute_action(req)
    
    db_act = action_repository.get_action(req.action_id, "sess_8", "owner_8")
    assert db_act["request_payload"]["github_token"] == "***"
    assert db_act["request_payload"]["password"] == "***"
    assert db_act["request_payload"]["safe_data"] == "hello"

def test_restart_executing_recovery():
    # Simulate an action stuck in EXECUTING due to crash
    req = ActionRequest(integration="mock_integration", action_type=ActionType.WRITE, session_id="sess_9", owner_id="owner_9")
    action_repository.create_action(req.action_id, "sess_9", "owner_9", "mock_integration", "WRITE", "HIGH", "EXECUTING", {})
    
    # Resubmit after restart
    res = action_gateway.execute_action(req)
    assert res.status == ActionStatus.FAILED
    assert "FAILED_RECOVERY" in res.message
