import pytest
from app.integrations.models import ActionRequest, ActionType, ActionStatus, ActionRiskLevel, get_action_risk_level
from app.integrations.gmail import GmailIntegration
from app.integrations.gateway import action_gateway as gw
from app.agents.state import state_manager, SessionStatus
from app.agents.confirmation import confirmation_manager

@pytest.fixture
def gateway():
    gw.register_integration(GmailIntegration())
    return gw

@pytest.fixture
def session_id():
    sid = "test_gmail_session"
    state_manager.clear_session(sid)
    return sid

def test_gmail_validation_success(gateway, session_id):
    req = ActionRequest(
        integration="gmail",
        action_type=ActionType.SEND,
        session_id=session_id,
        arguments={
            "to": "test@example.com",
            "subject": "Hello",
            "body": "World"
        }
    )
    result = gateway.execute_action(req)
    # SEND is high risk, so it should pause for confirmation
    assert result.status == ActionStatus.WAITING_FOR_CONFIRMATION
    assert state_manager.get_session(session_id).status == SessionStatus.WAITING_FOR_CONFIRMATION

def test_gmail_validation_missing_to(gateway, session_id):
    req = ActionRequest(
        integration="gmail",
        action_type=ActionType.SEND,
        session_id=session_id,
        arguments={
            "subject": "Hello",
            "body": "World"
        }
    )
    result = gateway.execute_action(req)
    assert result.status == ActionStatus.VALIDATION_ERROR
    assert "recipient" in result.message

def test_gmail_validation_invalid_email(gateway, session_id):
    req = ActionRequest(
        integration="gmail",
        action_type=ActionType.SEND,
        session_id=session_id,
        arguments={
            "to": "not-an-email",
            "subject": "Hello",
            "body": "World"
        }
    )
    result = gateway.execute_action(req)
    assert result.status == ActionStatus.VALIDATION_ERROR
    assert "Invalid email format" in result.message

def test_gmail_validation_missing_subject(gateway, session_id):
    req = ActionRequest(
        integration="gmail",
        action_type=ActionType.SEND,
        session_id=session_id,
        arguments={
            "to": "test@example.com",
            "body": "World"
        }
    )
    result = gateway.execute_action(req)
    assert result.status == ActionStatus.VALIDATION_ERROR
    assert "subject" in result.message

def test_gmail_validation_missing_body(gateway, session_id):
    req = ActionRequest(
        integration="gmail",
        action_type=ActionType.SEND,
        session_id=session_id,
        arguments={
            "to": "test@example.com",
            "subject": "Hello",
        }
    )
    result = gateway.execute_action(req)
    assert result.status == ActionStatus.VALIDATION_ERROR
    assert "body" in result.message

class MockGmailResult:
    def __init__(self, success: bool, message_id=None, recipient=None, error_code=None, error_message=None):
        self.success = success
        self.message_id = message_id
        self.recipient = recipient
        self.error_code = error_code
        self.error_message = error_message

def test_gmail_execution_success(gateway, session_id, monkeypatch):
    # Mock GmailClient
    def mock_send_email(*args, **kwargs):
        return MockGmailResult(success=True, message_id="mock_id_123", recipient=kwargs.get("to"))
        
    import app.email.gmail_client
    class MockGmailClient:
        def send_email(self, to, subject, body):
            return mock_send_email(to=to, subject=subject, body=body)
            
    monkeypatch.setattr(app.email.gmail_client, "GmailClient", MockGmailClient)

    req = ActionRequest(
        integration="gmail",
        action_type=ActionType.SEND,
        session_id=session_id,
        arguments={
            "to": "test@example.com",
            "subject": "Hello",
            "body": "World"
        }
    )
    gateway.execute_action(req)
    
    # Confirm it
    result = gateway.confirm_pending_action(session_id)
    assert result.status == ActionStatus.SUCCESS
    assert result.data["message_id"] == "mock_id_123"
    assert result.data["recipient"] == "test@example.com"
    assert state_manager.get_session(session_id).status == SessionStatus.COMPLETED

def test_gmail_execution_failure(gateway, session_id, monkeypatch):
    def mock_send_email(*args, **kwargs):
        return MockGmailResult(success=False, error_code="AUTH_FAILED", error_message="Mock auth failure")
        
    import app.email.gmail_client
    class MockGmailClient:
        def send_email(self, to, subject, body):
            return mock_send_email(to=to, subject=subject, body=body)
            
    monkeypatch.setattr(app.email.gmail_client, "GmailClient", MockGmailClient)

    req = ActionRequest(
        integration="gmail",
        action_type=ActionType.SEND,
        session_id=session_id,
        arguments={
            "to": "test@example.com",
            "subject": "Hello",
            "body": "World"
        }
    )
    gateway.execute_action(req)
    
    # Confirm it
    result = gateway.confirm_pending_action(session_id)
    assert result.status == ActionStatus.FAILED
    assert result.data["error_code"] == "AUTH_FAILED"
    assert "Mock auth failure" in result.message
    
def test_gmail_confirm_via_confirmation_manager(session_id, monkeypatch):
    # Ensure confirm_email routes correctly
    def mock_send_email(*args, **kwargs):
        return MockGmailResult(success=True, message_id="mock_id_manager", recipient=kwargs.get("to"))
        
    import app.email.gmail_client
    class MockGmailClient:
        def send_email(self, to, subject, body):
            return mock_send_email(to=to, subject=subject, body=body)
            
    monkeypatch.setattr(app.email.gmail_client, "GmailClient", MockGmailClient)
    
    from app.tools.send_email_tool import send_email
    
    res = send_email(session_id, "job_1", "Subj", "Body", "test@example.com")
    assert res["status"] == "waiting_for_confirmation"
    
    confirm_res = confirmation_manager.confirm_email(session_id)
    assert confirm_res["status"] == "sent"
    assert confirm_res["message_id"] == "mock_id_manager"
