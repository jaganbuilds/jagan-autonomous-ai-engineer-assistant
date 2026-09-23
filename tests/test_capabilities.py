import pytest
from unittest.mock import patch, MagicMock
from app.integrations.models import ActionType
from app.integrations.gateway import action_gateway
from app.tools.integration_tools import list_integrations, get_integration_capabilities, check_integration_health

@pytest.fixture(autouse=True)
def setup_mock_integration():
    from app.integrations.mock import MockIntegration
    integration = MockIntegration()
    action_gateway.register_integration(integration)
    yield

def test_mock_capability():
    res = get_integration_capabilities("mock_integration")
    assert "error" not in res
    assert res["integration_name"] == "mock_integration"
    assert res["healthy"] == True
    assert res["available"] == True
    
    actions = res["supported_actions"]
    types = [a["action_type"] for a in actions]
    assert ActionType.READ in types
    assert ActionType.WRITE in types

@patch("os.path.exists")
def test_gmail_capability_missing_credentials(mock_exists):
    mock_exists.return_value = False
    res = get_integration_capabilities("gmail")
    assert res["available"] == False
    assert res["authenticated"] == False
    assert res["healthy"] == False
    assert "Missing credentials.json" in res["health_message"]

@patch("os.path.exists")
def test_gmail_capability_missing_token(mock_exists):
    # Returns True for credentials.json, False for token.json
    mock_exists.side_effect = lambda path: "credentials" in path
    res = get_integration_capabilities("gmail")
    assert res["available"] == True
    assert res["authenticated"] == False
    assert res["healthy"] == False
    assert "Missing token.json" in res["health_message"]

@patch("app.integrations.github_client.GitHubClient.check_credentials_state")
def test_github_capability_healthy(mock_state):
    mock_state.return_value = {"configured": True, "authenticated": True, "reason": "Authenticated"}
    res = get_integration_capabilities("github")
    assert res["available"] == True
    assert res["authenticated"] == True
    assert res["healthy"] == True
    
    actions = res["supported_actions"]
    for a in actions:
        if a["action_type"] == ActionType.WRITE:
            assert a["risk_level"] == "HIGH"
            assert a["requires_confirmation"] == True
        elif a["action_type"] == ActionType.READ:
            assert a["risk_level"] == "LOW"
            assert a["requires_confirmation"] == False

@patch("app.integrations.github_client.GitHubClient.check_credentials_state")
def test_github_capability_missing_token(mock_state):
    mock_state.return_value = {"configured": False, "authenticated": False, "reason": "Missing token"}
    res = get_integration_capabilities("github")
    assert res["available"] == False
    assert res["authenticated"] == False
    assert res["healthy"] == False

def test_list_integrations():
    res = list_integrations()
    assert "integrations" in res
    names = [i["integration_name"] for i in res["integrations"]]
    assert "gmail" in names
    assert "github" in names
    assert "mock_integration" in names

def test_check_health():
    res = check_integration_health("mock_integration")
    assert res["integration_name"] == "mock_integration"
    assert "available" in res
    assert "healthy" in res

def test_unknown_integration():
    res = get_integration_capabilities("unknown_foo")
    assert "error" in res
    
    res = check_integration_health("unknown_foo")
    assert "error" in res

@patch("app.integrations.github_client.requests.get")
def test_github_client_check_credentials_state(mock_get):
    from app.integrations.github_client import GitHubClient
    
    # Needs a token
    client = GitHubClient()
    client.token = "ghp_123"
    
    # Valid
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_get.return_value = mock_resp
    
    state = client.check_credentials_state()
    assert state["authenticated"] == True
    
    # Invalid token
    mock_resp.status_code = 401
    state2 = client.check_credentials_state()
    assert state2["authenticated"] == False
    
    # Missing token
    client.token = None
    state3 = client.check_credentials_state()
    assert state3["configured"] == False
    assert state3["authenticated"] == False
    
