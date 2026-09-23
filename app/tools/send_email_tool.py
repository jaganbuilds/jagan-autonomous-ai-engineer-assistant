from typing import Optional
from app.tools.registry import registry
from app.agents.confirmation import confirmation_manager

@registry.register(requires_confirmation=False)
def send_email(session_id: str, job_id: str, subject: str, body: str, recipient: Optional[str] = None) -> dict:
    """
    Initiates the process to send an HR application email.
    The system will immediately pause and ask the user for explicit confirmation before actually sending.
    
    Args:
        session_id: Passed automatically. Do not modify.
        job_id: The job reference (e.g., 'job_1').
        subject: The email subject.
        body: The email body.
        recipient: The recruiter's email address, if known.
    """
    from app.integrations.gateway import action_gateway
    from app.integrations.models import ActionRequest, ActionType
    
    request = ActionRequest(
        integration="gmail",
        action_type=ActionType.SEND,
        session_id=session_id,
        arguments={
            "to": recipient,
            "subject": subject,
            "body": body,
            "job_id": job_id
        }
    )
    
    result = action_gateway.execute_action(request)
    
    if result.status.value == "WAITING_FOR_CONFIRMATION":
        return {
            "status": "waiting_for_confirmation",
            "action": "send_email", # Keeping backward compatibility for orchestrator tools parsing
            "job_id": job_id,
            "message": "The email draft is ready. Do you want to send it?"
        }
    return {
        "status": result.status.value,
        "message": result.message
    }
