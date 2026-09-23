import pytest
from unittest.mock import patch, MagicMock
from app.agents.confirmation import confirmation_manager
from app.agents.state import state_manager, SessionStatus
from app.email.gmail_client import GmailSendResult

def test_create_pending_email():
    session_id = "test_confirm_create"
    state_manager.clear_session(session_id)
    
    res = confirmation_manager.create_pending_email(session_id, "job_1", "Subj", "Body", "rec@ip.com")
    
    assert res["status"] == "waiting_for_confirmation"
    assert res["job_id"] == "job_1"
    
    session = state_manager.get_session(session_id)
    assert session.status == SessionStatus.WAITING_FOR_CONFIRMATION
    assert getattr(session, "pending_gateway_action", None) is not None
    assert confirmation_manager.has_pending_email(session_id) is True

@patch('app.email.gmail_client.GmailClient.send_email')
def test_confirm_email_success(mock_send):
    mock_send.return_value = GmailSendResult(success=True, message_id="123")
    
    session_id = "test_confirm_yes"
    state_manager.clear_session(session_id)
    
    confirmation_manager.create_pending_email(session_id, "job_1", "Subj", "Body", "rec@ip.com")
    res = confirmation_manager.confirm_email(session_id)
    
    assert res["status"] == "sent"
    assert res["message_id"] == "123"
    
    session = state_manager.get_session(session_id)
    assert getattr(session, "pending_gateway_action", None) is None
    assert confirmation_manager.has_pending_email(session_id) is False
    mock_send.assert_called_once_with(to="rec@ip.com", subject="Subj", body="Body")

@patch('app.email.gmail_client.GmailClient.send_email')
def test_confirm_email_failure(mock_send):
    mock_send.return_value = GmailSendResult(success=False, error_code="API_ERROR", error_message="Fail")
    
    session_id = "test_confirm_fail"
    state_manager.clear_session(session_id)
    
    confirmation_manager.create_pending_email(session_id, "job_1", "Subj", "Body", "rec@ip.com")
    res = confirmation_manager.confirm_email(session_id)
    
    assert res["status"] == "send_failed"
    assert res["error"] == "API_ERROR"
    
    # State should clean up the pending action on failure
    session = state_manager.get_session(session_id)
    assert getattr(session, "pending_gateway_action", None) is None

def test_confirm_email_no_recipient():
    session_id = "test_confirm_no_recip"
    state_manager.clear_session(session_id)
    
    # Notice recipient is None
    res = confirmation_manager.create_pending_email(session_id, "job_1", "Subj", "Body", None)
    
    assert res["status"] == "error"
    
    session = state_manager.get_session(session_id)
    assert getattr(session, "pending_gateway_action", None) is None

def test_reject_email():
    session_id = "test_confirm_no"
    state_manager.clear_session(session_id)
    
    confirmation_manager.create_pending_email(session_id, "job_1", "Subj", "Body", None)
    res = confirmation_manager.reject_email(session_id)
    
    assert res["status"] == "rejected"
    assert "cancelled" in res["message"]
    
    session = state_manager.get_session(session_id)
    assert session.status == SessionStatus.IDLE
    assert getattr(session, "pending_gateway_action", None) is None
