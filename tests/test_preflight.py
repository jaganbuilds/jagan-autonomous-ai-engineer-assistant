import pytest
from unittest.mock import patch, MagicMock
from app.integrations.models import ActionRequest, ActionType, ActionStatus
from app.integrations.preflight import validate_preflight
from app.tools.integration_tools import preflight_action
from app.integrations.gateway import action_gateway
from app.database.action_repository import action_repository

@pytest.fixture(autouse=True)
def setup_integrations(tmp_path):
    from app.integrations.mock import MockIntegration
    action_gateway.register_integration(MockIntegration())
    
    # We clear db since action_repository is used
    action_repository.get_action = MagicMock(return_value=None)
    yield

def test_preflight_valid_request():
    req = ActionRequest(
        integration="mock_integration",
        action_type=ActionType.READ,
        session_id="test_sess",
        arguments={}
    )
    res = validate_preflight(req)
    assert res.allowed == True
    assert res.reason == "POLICY_PASSED"
    assert res.requires_confirmation == False
    
def test_preflight_write_requires_confirmation():
    req = ActionRequest(
        integration="mock_integration",
        action_type=ActionType.WRITE,
        session_id="test_sess",
        arguments={"content": "hello"}
    )
    res = validate_preflight(req)
    assert res.allowed == True
    assert res.requires_confirmation == True
    
def test_preflight_invalid_request():
    req = ActionRequest(
        integration="mock_integration",
        action_type=ActionType.WRITE,
        session_id="test_sess",
        arguments={} # Missing content
    )
    res = validate_preflight(req)
    assert res.allowed == False
    assert res.reason == "INVALID_REQUEST"
    assert "Missing 'content'" in res.safe_message

def test_preflight_unknown_integration():
    req = ActionRequest(
        integration="unknown_foo",
        action_type=ActionType.READ,
        session_id="test_sess",
        arguments={}
    )
    res = validate_preflight(req)
    assert res.allowed == False
    assert res.reason == "UNKNOWN_INTEGRATION"
    
def test_preflight_unsupported_action():
    req = ActionRequest(
        integration="mock_integration",
        action_type=ActionType.DELETE,
        session_id="test_sess",
        arguments={}
    )
    res = validate_preflight(req)
    assert res.allowed == False
    assert res.reason == "UNSUPPORTED_ACTION"
    
@patch("app.integrations.capability_service.CapabilityService.get_integration_capabilities")
def test_preflight_authentication_required(mock_caps):
    from app.integrations.capabilities import IntegrationCapability, ActionCapability
    mock_caps.return_value = IntegrationCapability(
        integration_name="mock_integration",
        display_name="Mock Service",
        available=True,
        authenticated=False,
        healthy=False,
        supported_actions=[ActionCapability(action_type=ActionType.READ, risk_level="LOW", requires_confirmation=False)],
        health_message="Not logged in."
    )
    req = ActionRequest(
        integration="mock_integration",
        action_type=ActionType.READ,
        session_id="test_sess",
        arguments={}
    )
    res = validate_preflight(req)
    assert res.allowed == False
    assert res.reason == "AUTHENTICATION_REQUIRED"
    
@patch("app.integrations.capability_service.CapabilityService.get_integration_capabilities")
def test_preflight_unhealthy(mock_caps):
    from app.integrations.capabilities import IntegrationCapability, ActionCapability
    mock_caps.return_value = IntegrationCapability(
        integration_name="mock_integration",
        display_name="Mock Service",
        available=True,
        authenticated=True,
        healthy=False,
        supported_actions=[ActionCapability(action_type=ActionType.READ, risk_level="LOW", requires_confirmation=False)],
        health_message="API timeout."
    )
    req = ActionRequest(
        integration="mock_integration",
        action_type=ActionType.READ,
        session_id="test_sess",
        arguments={}
    )
    res = validate_preflight(req)
    assert res.allowed == False
    assert res.reason == "INTEGRATION_UNHEALTHY"

def test_preflight_idempotency_already_completed():
    action_repository.get_action = MagicMock(return_value={"status": "SUCCESS"})
    req = ActionRequest(
        integration="mock_integration",
        action_type=ActionType.READ,
        session_id="test_sess",
        arguments={}
    )
    res = validate_preflight(req)
    assert res.allowed == False
    assert res.reason == "ALREADY_COMPLETED"
    
def test_preflight_tool():
    res = preflight_action(
        integration="mock_integration",
        action_type="WRITE",
        session_id="test_sess",
        arguments={"content": "hello"}
    )
    assert "error" not in res
    assert res["allowed"] == True
    assert res["requires_confirmation"] == True
    
    res_bad = preflight_action(
        integration="mock_integration",
        action_type="INVALID_TYPE",
        session_id="test_sess",
        arguments={}
    )
    assert "error" in res_bad
