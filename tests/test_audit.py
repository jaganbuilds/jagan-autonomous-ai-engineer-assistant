import pytest
from unittest.mock import patch
from app.integrations.models import ActionRequest, ActionType, ActionStatus
from app.integrations.gateway import action_gateway, BaseIntegration, ActionResult
from app.database.action_repository import action_repository
from app.integrations.audit import audit_service
from app.tools.audit_tools import list_action_history, get_action_audit, get_action_statistics

class MockAuditIntegration(BaseIntegration):
    @property
    def integration_name(self) -> str:
        return "mock_audit_integration"
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
            data={"secret_key": "hidden_value", "safe_val": 42}
        )

@pytest.fixture(autouse=True)
def setup_mock_audit_integration():
    integration = MockAuditIntegration()
    action_gateway.register_integration(integration)
    yield

def _seed_action(session_id="sess_a", owner_id="default_owner", action_type="WRITE", risk="HIGH", status="SUCCESS", req=None, res=None):
    req_payload = req or {"some_param": 123}
    act_id = f"act_{session_id}_{status}_{action_type}_{req_payload.get('idx', 0)}"
    action_repository.create_action(
        action_id=act_id,
        session_id=session_id,
        owner_id=owner_id,
        integration_name="mock_audit_integration",
        action_type=action_type,
        risk_level=risk,
        status=status,
        request_payload=req_payload
    )
    if status == "SUCCESS" or status == "FAILED":
        action_repository.save_result(act_id, status, res or {"result": "ok"})
    elif status == "EXECUTING":
        action_repository.try_transition_to_executing(act_id, session_id, owner_id)
    return act_id

def test_audit_history_list():
    # Clear anything just in case
    _seed_action(req={"idx": 1})
    _seed_action(req={"idx": 2})
    _seed_action(req={"idx": 3}, session_id="sess_b")
    
    # Tool call
    history = list_action_history(session_id="sess_a")
    assert len(history) == 2
    
    # Filter by session_id/owner_id isolation check
    for item in history:
        assert item["session_id"] == "sess_a"
        assert item["owner_id"] == "default_owner"
        
def test_audit_history_limits():
    for i in range(110):
        _seed_action(session_id="sess_limit", req={"idx": i})
        
    history = list_action_history(session_id="sess_limit", limit=200)
    # Hard maximum is 100
    assert len(history) == 100

def test_audit_history_filters():
    _seed_action(session_id="sess_filter", action_type="READ", status="SUCCESS", req={"idx": 1})
    _seed_action(session_id="sess_filter", action_type="WRITE", status="FAILED", req={"idx": 2})
    _seed_action(session_id="sess_filter", action_type="WRITE", status="SUCCESS", req={"idx": 3})
    
    # Filter by action_type
    history = list_action_history(session_id="sess_filter", action_type="READ")
    assert len(history) == 1
    assert history[0]["action_type"] == "READ"
    
    # Filter by status
    history2 = list_action_history(session_id="sess_filter", status="FAILED")
    assert len(history2) == 1
    assert history2[0]["status"] == "FAILED"

def test_audit_single_action():
    act_id = _seed_action(session_id="sess_single", req={"secret_password": "my_super_secret"}, res={"access_token": "token123"})
    
    record = get_action_audit(session_id="sess_single", action_id=act_id)
    assert record is not None
    assert "error" not in record
    assert record["action_id"] == act_id
    
    # Sanitization checks
    assert record["request_payload"]["secret_password"] == "***"
    assert record["result_payload"]["access_token"] == "***"

def test_audit_single_action_isolation():
    act_id = _seed_action(session_id="sess_iso_1", owner_id="default_owner")
    
    # Cannot access from different session
    record = get_action_audit(session_id="sess_iso_2", action_id=act_id)
    assert "error" in record

def test_audit_statistics():
    _seed_action(session_id="sess_stats", status="SUCCESS", req={"idx": 1})
    _seed_action(session_id="sess_stats", status="SUCCESS", req={"idx": 2})
    _seed_action(session_id="sess_stats", status="FAILED", req={"idx": 3})
    _seed_action(session_id="sess_stats", status="REJECTED", req={"idx": 4})
    
    stats = get_action_statistics(session_id="sess_stats")
    assert stats["total"] == 4
    assert stats["status_counts"]["SUCCESS"] == 2
    assert stats["status_counts"]["FAILED"] == 1
    assert stats["status_counts"]["REJECTED"] == 1
    
    assert stats["success_rate"] == 0.5  # 2 / (2 + 1 + 1)
    assert stats["failure_rate"] == 0.25 # 1 / 4
    
    assert stats["integration_counts"]["mock_audit_integration"] == 4

def test_audit_tools_do_not_execute():
    # Tools should just read DB, no Side Effects
    with patch("app.integrations.gateway.action_gateway.execute_action") as mock_exec:
        list_action_history(session_id="sess_123")
        get_action_statistics(session_id="sess_123")
        mock_exec.assert_not_called()
