import sys
import os

# Add the project root to the sys path to allow importing app modules
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../')))

from app.email.gmail_client import GmailClient

def run_manual_gmail_send():
    """
    WARNING: THIS WILL SEND A REAL EMAIL FROM YOUR GOOGLE ACCOUNT.
    
    To run this test:
    1. Ensure credentials.json is in the project root.
    2. Ensure token.json is created (or it will trigger OAuth flow).
    3. Run this file explicitly: python tests/manual/test_gmail_send.py
    
    This test is ignored by normal pytest runs due to its location and lack of pytest configuration here.
    """
    print("WARNING: This test will send a real email using the Gmail API.")
    print("Make sure you are comfortable with this before proceeding.")
    response = input("Do you want to proceed? (yes/no): ")
    
    if response.lower() != 'yes':
        print("Cancelled.")
        return
        
    recipient = input("Enter the recipient email address: ")
    if not recipient:
        print("Recipient is required. Cancelled.")
        return
        
    print("\nInitializing GmailClient...")
    client = GmailClient(credentials_path="credentials.json", token_path="token.json")
    
    print(f"\nSending test email to {recipient}...")
    result = client.send_email(
        to=recipient,
        subject="Jagan AI - Manual Gmail API Test",
        body="If you are receiving this, the Jagan AI Gmail API integration is working successfully!"
    )
    
    if result.success:
        print(f"\nSUCCESS! Email sent successfully. Message ID: {result.message_id}")
    else:
        print(f"\nFAILED! Error Code: {result.error_code}")
        print(f"Error Message: {result.error_message}")

if __name__ == "__main__":
    run_manual_gmail_send()
