import os
import base64
from typing import Optional
from pydantic import BaseModel
from email.message import EmailMessage

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
import logging

logger = logging.getLogger(__name__)

# Scope strictly limited to sending email
SCOPES = ['https://www.googleapis.com/auth/gmail.send']

class GmailSendResult(BaseModel):
    success: bool
    message_id: Optional[str] = None
    recipient: Optional[str] = None
    error_code: Optional[str] = None
    error_message: Optional[str] = None

class GmailClient:
    """
    Client for interacting with the Gmail API via OAuth 2.0.
    Handles token refreshing and sending MIME messages.
    """
    def __init__(self, credentials_path: str = 'credentials.json', token_path: str = 'token.json'):
        self.credentials_path = credentials_path
        self.token_path = token_path
        
    def _get_credentials(self) -> Credentials | None:
        creds = None
        if os.path.exists(self.token_path):
            creds = Credentials.from_authorized_user_file(self.token_path, SCOPES)
            
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                try:
                    creds.refresh(Request())
                except Exception as e:
                    logger.error(f"Failed to refresh token: {e}")
                    creds = None
            else:
                if not os.path.exists(self.credentials_path):
                    logger.error(f"Missing {self.credentials_path}. Cannot start OAuth flow.")
                    return None
                try:
                    flow = InstalledAppFlow.from_client_secrets_file(self.credentials_path, SCOPES)
                    creds = flow.run_local_server(port=0)
                except Exception as e:
                    logger.error(f"OAuth flow failed: {e}")
                    return None
                    
            if creds:
                # Save the credentials for the next run
                with open(self.token_path, 'w') as token:
                    token.write(creds.to_json())
                    
        return creds
        
    def check_credentials_state(self) -> dict:
        if not os.path.exists(self.credentials_path):
            return {"configured": False, "authenticated": False, "reason": "Missing credentials.json"}
            
        if not os.path.exists(self.token_path):
            return {"configured": True, "authenticated": False, "reason": "Missing token.json"}
            
        try:
            creds = Credentials.from_authorized_user_file(self.token_path, SCOPES)
            if creds.valid:
                return {"configured": True, "authenticated": True, "reason": "Authenticated"}
                
            if creds.expired and creds.refresh_token:
                try:
                    creds.refresh(Request())
                    with open(self.token_path, 'w') as token:
                        token.write(creds.to_json())
                    return {"configured": True, "authenticated": True, "reason": "Authenticated (token refreshed)"}
                except Exception as e:
                    return {"configured": True, "authenticated": False, "reason": "Token refresh failed"}
            
            return {"configured": True, "authenticated": False, "reason": "Token invalid or expired"}
        except Exception as e:
            return {"configured": True, "authenticated": False, "reason": "Token parsing failed"}

    def send_email(self, to: str, subject: str, body: str) -> GmailSendResult:
        if not to or not to.strip():
            return GmailSendResult(
                success=False,
                error_code="INVALID_RECIPIENT",
                error_message="Recipient address is missing or invalid."
            )
            
        creds = self._get_credentials()
        if not creds:
            return GmailSendResult(
                success=False,
                error_code="AUTH_FAILED",
                error_message="Could not obtain valid Gmail OAuth credentials."
            )
            
        try:
            service = build('gmail', 'v1', credentials=creds)
            
            message = EmailMessage()
            message.set_content(body)
            message['To'] = to
            message['Subject'] = subject
            
            # Encoded message
            encoded_message = base64.urlsafe_b64encode(message.as_bytes()).decode()
            
            create_message = {
                'raw': encoded_message
            }
            
            # Send message
            send_message = (service.users().messages().send(userId="me", body=create_message).execute())
            
            return GmailSendResult(
                success=True,
                message_id=send_message.get('id'),
                recipient=to
            )
            
        except HttpError as error:
            logger.error(f"Gmail API HttpError: {error}")
            return GmailSendResult(
                success=False,
                error_code=str(error.resp.status),
                error_message=f"Gmail API error: {error._get_reason()}"
            )
        except Exception as e:
            logger.error(f"Unexpected error sending email: {e}")
            return GmailSendResult(
                success=False,
                error_code="UNKNOWN_ERROR",
                error_message="An unexpected error occurred while sending the email."
            )
