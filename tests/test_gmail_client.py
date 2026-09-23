import pytest
from unittest.mock import patch, MagicMock
from app.email.gmail_client import GmailClient
from googleapiclient.errors import HttpError
import base64
from email.message import EmailMessage

@pytest.fixture
def client():
    # Use dummy paths so it doesn't touch local files during testing
    return GmailClient(credentials_path="dummy_cred.json", token_path="dummy_token.json")

@patch('app.email.gmail_client.os.path.exists')
@patch('app.email.gmail_client.Credentials')
@patch('app.email.gmail_client.build')
def test_send_email_success(mock_build, mock_credentials, mock_exists, client):
    # Setup auth mock
    mock_exists.return_value = True
    mock_creds = MagicMock()
    mock_creds.valid = True
    mock_credentials.from_authorized_user_file.return_value = mock_creds
    
    # Setup Gmail service mock
    mock_service = MagicMock()
    mock_users = MagicMock()
    mock_messages = MagicMock()
    mock_send = MagicMock()
    
    mock_send.execute.return_value = {'id': 'msg_123'}
    mock_messages.send.return_value = mock_send
    mock_users.messages.return_value = mock_messages
    mock_service.users.return_value = mock_users
    mock_build.return_value = mock_service
    
    # Execute
    res = client.send_email(to="test@example.com", subject="Test Subj", body="Test Body")
    
    assert res.success is True
    assert res.message_id == "msg_123"
    assert res.recipient == "test@example.com"
    
    # Verify the message structure
    call_args = mock_messages.send.call_args[1]
    assert call_args['userId'] == 'me'
    
    raw = call_args['body']['raw']
    decoded_bytes = base64.urlsafe_b64decode(raw)
    
    # Can't easily parse the whole MIME without email module, but we can check strings
    decoded_str = decoded_bytes.decode('utf-8')
    assert "To: test@example.com" in decoded_str
    assert "Subject: Test Subj" in decoded_str
    assert "Test Body" in decoded_str

def test_send_email_missing_recipient(client):
    res = client.send_email(to="", subject="S", body="B")
    assert res.success is False
    assert res.error_code == "INVALID_RECIPIENT"

@patch('app.email.gmail_client.os.path.exists')
def test_send_email_no_credentials(mock_exists, client):
    mock_exists.return_value = False # token and credentials don't exist
    
    res = client.send_email(to="test@example.com", subject="S", body="B")
    
    assert res.success is False
    assert res.error_code == "AUTH_FAILED"

@patch('app.email.gmail_client.os.path.exists')
@patch('app.email.gmail_client.Credentials')
def test_expired_token_refresh(mock_credentials, mock_exists, client):
    mock_exists.side_effect = [True, False] # token exists, creds file doesn't
    mock_creds = MagicMock()
    mock_creds.valid = False
    mock_creds.expired = True
    mock_creds.refresh_token = "valid_refresh"
    mock_credentials.from_authorized_user_file.return_value = mock_creds
    
    # We want refresh to fail in this test to see if it returns AUTH_FAILED
    mock_creds.refresh.side_effect = Exception("Refresh failed")
    
    res = client.send_email(to="test@example.com", subject="S", body="B")
    
    assert res.success is False
    assert res.error_code == "AUTH_FAILED"

@patch('app.email.gmail_client.os.path.exists')
@patch('app.email.gmail_client.Credentials')
@patch('app.email.gmail_client.build')
def test_http_error(mock_build, mock_credentials, mock_exists, client):
    mock_exists.return_value = True
    mock_creds = MagicMock()
    mock_creds.valid = True
    mock_credentials.from_authorized_user_file.return_value = mock_creds
    
    mock_service = MagicMock()
    mock_build.return_value = mock_service
    
    # Setup HTTP Error
    resp = MagicMock()
    resp.status = 403
    resp.reason = "Forbidden"
    mock_service.users().messages().send().execute.side_effect = HttpError(resp=resp, content=b"{}", uri="")
    
    res = client.send_email(to="test@example.com", subject="S", body="B")
    
    assert res.success is False
    assert res.error_code == "403"
