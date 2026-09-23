import pytest
from app.integrations.models import ActionRequest, ActionType, ActionStatus, ActionRiskLevel, get_action_risk_level
from app.integrations.gateway import action_gateway as gw
from app.integrations.mock import MockIntegration
from app.agents.state import state_manager, SessionStatus
from app.agents.confirmation import confirmation_manager

@pytest.fixture
def gateway():
    gw.register_integration(MockIntegration())
    return gw

@pytest.fixture
def session_id():
    sid = "test_gateway_session"
    state_manager.clear_session(sid)
    return sid

def test_action_risk_classification():
    assert get_action_risk_level(ActionType.READ) == ActionRiskLevel.LOW
    assert get_action_risk_level(ActionType.WRITE) == ActionRiskLevel.HIGH
    assert get_action_risk_level(ActionType.SEND) == ActionRiskLevel.HIGH
    assert get_action_risk_level(ActionType.DELETE) == ActionRiskLevel.HIGH
    assert get_action_risk_level(ActionType.EXECUTE) == ActionRiskLevel.HIGH

def test_validation_missing_integration(gateway, session_id):
    req = ActionRequest(
        integration="unknown",
        action_type=ActionType.READ,
        session_id=session_id
    )
    result = gateway.execute_action(req)
    assert result.status == ActionStatus.NOT_SUPPORTED
    assert "unknown" in result.message

def test_validation_unsupported_action(gateway, session_id):
    req = ActionRequest(
        integration="mock_integration",
        action_type=ActionType.DELETE,
        session_id=session_id
    )
    result = gateway.execute_action(req)
    assert result.status == ActionStatus.NOT_SUPPORTED

def test_validation_invalid_arguments(gateway, session_id):
    req = ActionRequest(
        integration="mock_integration",
        action_type=ActionType.WRITE,
        session_id=session_id,
        arguments={} # Missing content
    )
    result = gateway.execute_action(req)
    assert result.status == ActionStatus.VALIDATION_ERROR

def test_read_action_succeeds_without_confirmation(gateway, session_id):
    req = ActionRequest(
        integration="mock_integration",
        action_type=ActionType.READ,
        session_id=session_id
    )
    result = gateway.execute_action(req)
    assert result.status == ActionStatus.SUCCESS
    assert state_manager.get_session(session_id).status != SessionStatus.WAITING_FOR_CONFIRMATION

def test_write_action_requires_confirmation(gateway, session_id):
    req = ActionRequest(
        integration="mock_integration",
        action_type=ActionType.WRITE,
        session_id=session_id,
        arguments={"content": "hello"}
    )
    result = gateway.execute_action(req)
    assert result.status == ActionStatus.WAITING_FOR_CONFIRMATION
    assert state_manager.get_session(session_id).status == SessionStatus.WAITING_FOR_CONFIRMATION

def test_confirmation_flow_confirmed(gateway, session_id):
    req = ActionRequest(
        integration="mock_integration",
        action_type=ActionType.WRITE,
        session_id=session_id,
        arguments={"content": "hello"}
    )
    
    res1 = gateway.execute_action(req)
    assert res1.status == ActionStatus.WAITING_FOR_CONFIRMATION
    
    # User confirms
    res2 = gateway.confirm_pending_action(session_id)
    assert res2.status == ActionStatus.SUCCESS
    assert res2.data["executed_by"] == "mock"
    assert state_manager.get_session(session_id).status == SessionStatus.COMPLETED

def test_confirmation_flow_rejected(gateway, session_id):
    req = ActionRequest(
        integration="mock_integration",
        action_type=ActionType.EXECUTE,
        session_id=session_id,
        arguments={"command": "rm -rf"}
    )
    
    gateway.execute_action(req)
    
    # User rejects
    res = gateway.reject_pending_action(session_id)
    assert res.status == ActionStatus.REJECTED
    assert state_manager.get_session(session_id).status == SessionStatus.COMPLETED

def test_confirmation_session_isolation(gateway, session_id):
    req = ActionRequest(
        integration="mock_integration",
        action_type=ActionType.WRITE,
        session_id=session_id,
        arguments={"content": "hello"}
    )
    gateway.execute_action(req)
    
    # Try to confirm from wrong session
    res = gateway.confirm_pending_action("hacker_session")
    assert res.status == ActionStatus.FAILED
    assert "No pending action" in res.message

def test_error_isolation_provider_failure(gateway, session_id):
    req = ActionRequest(
        integration="mock_integration",
        action_type=ActionType.READ,
        session_id=session_id,
        arguments={"fail_mode": True}
    )
    # The integration raises an exception, gateway should catch it
    result = gateway.execute_action(req)
    assert result.status == ActionStatus.FAILED
    # Exception string should not be directly exposed to avoid secrets leak
    assert "Simulated provider failure" not in result.message
    assert "internal provider error" in result.message

def test_secret_protection(gateway, session_id):
    req = ActionRequest(
        integration="mock_integration",
        action_type=ActionType.READ,
        session_id=session_id,
        arguments={"secret": "super_secret_token"}
    )
    result = gateway.execute_action(req)
    
    # Ensure result message does not contain the secret
    assert "super_secret_token" not in result.message
    # Ensure serialized result dict doesn't accidentally log it if data is clean
    if result.data:
        assert "super_secret_token" not in str(result.data)

def test_idempotency_duplicate_execution(gateway, session_id):
    # Idempotency is supported at gateway level if requested and already confirmed.
    # The gateway ensures that if `_is_action_confirmed` passes, it allows execution.
    # In a full distributed setup, we would guard it at execution layer, but here 
    # we ensure deterministic validation.
    
    req = ActionRequest(
        integration="mock_integration",
        action_type=ActionType.WRITE,
        session_id=session_id,
        arguments={"content": "idempotent"}
    )
    gateway.execute_action(req)
    gateway.confirm_pending_action(session_id)
    
    # By default, re-confirming should yield FAILED "No pending action"
    res = gateway.confirm_pending_action(session_id)
    assert res.status == ActionStatus.FAILED


