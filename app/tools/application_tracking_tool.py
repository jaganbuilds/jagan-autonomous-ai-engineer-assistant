from typing import Dict, Any, Optional

from app.tools.registry import registry
from app.application_tracking.service import ApplicationTrackingService
from app.database.repository import get_job_repository
from app.database.models import ApplicationStatus

tracking_service = ApplicationTrackingService(
    job_repository=get_job_repository()
)

@registry.register(requires_confirmation=False)
def create_application_tracking(
    session_id: str,
    job_id: int,
    status: str = "PREPARED",
    notes: Optional[str] = None,
    next_action: Optional[str] = None,
    follow_up_at: Optional[str] = None
) -> Dict[str, Any]:
    """
    Creates a new tracking record for a valid persisted job.
    Does NOT imply that an application was actually submitted.
    """
    try:
        app_status = ApplicationStatus(status.upper())
    except ValueError:
        return {"status": "error", "message": f"Invalid status: {status}"}

    return tracking_service.create_application_record(
        session_id=session_id,
        job_id=job_id,
        status=app_status,
        notes=notes,
        next_action=next_action,
        follow_up_at=follow_up_at
    )

@registry.register(requires_confirmation=False)
def get_application_tracking(
    session_id: str,
    application_id: int
) -> Dict[str, Any]:
    """
    Retrieves an existing application tracking record.
    """
    result = tracking_service.get_application_record(
        session_id=session_id,
        application_id=application_id
    )
    if result["status"] == "success":
        result["data"] = result["data"].model_dump()
    return result

@registry.register(requires_confirmation=False)
def update_application_status(
    session_id: str,
    application_id: int,
    status: str
) -> Dict[str, Any]:
    """
    Updates the status of an application tracking record.
    Do NOT infer that a user applied just because a draft was created. 
    Only transition to APPLIED if the user explicitly confirmed submission.
    """
    try:
        new_status = ApplicationStatus(status.upper())
    except ValueError:
        return {"status": "error", "message": f"Invalid status: {status}"}

    return tracking_service.update_application_status(
        session_id=session_id,
        application_id=application_id,
        new_status=new_status
    )

@registry.register(requires_confirmation=False)
def list_application_tracking(
    session_id: str,
    status: Optional[str] = None
) -> Dict[str, Any]:
    """
    Lists application tracking records for the current session.
    Optionally filter by status (e.g., 'PREPARED', 'APPLIED', 'REJECTED').
    """
    app_status = None
    if status:
        try:
            app_status = ApplicationStatus(status.upper())
        except ValueError:
            return {"status": "error", "message": f"Invalid status filter: {status}"}

    result = tracking_service.list_applications(
        session_id=session_id,
        status=app_status
    )
    
    if result["status"] == "success":
        result["data"] = [record.model_dump() for record in result["data"]]
    
    return result
