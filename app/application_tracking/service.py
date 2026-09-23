import logging
from typing import Optional, List, Dict, Any
from app.database.repository import JobRepository
from app.database.models import ApplicationStatus, JobApplication

logger = logging.getLogger(__name__)

class ApplicationTrackingService:
    def __init__(self, job_repository: JobRepository):
        self.job_repository = job_repository

    def create_application_record(
        self,
        session_id: str,
        job_id: int,
        status: ApplicationStatus = ApplicationStatus.PREPARED,
        notes: Optional[str] = None,
        next_action: Optional[str] = None,
        follow_up_at: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Creates a new application tracking record if the job exists.
        """
        # Validate that the job exists
        job = self.job_repository.get_job(job_id)
        if not job:
            return {
                "status": "error",
                "message": f"Job ID {job_id} not found in the database."
            }

        try:
            app_id = self.job_repository.create_application(
                job_id=job_id,
                session_id=session_id,
                status=status.value,
                notes=notes,
                next_action=next_action,
                follow_up_at=follow_up_at
            )
            return {
                "status": "success",
                "application_id": app_id,
                "message": f"Tracking record created for job {job_id}."
            }
        except Exception as e:
            logger.error(f"Error creating application tracking record: {e}")
            return {
                "status": "error",
                "message": "Failed to create application tracking record."
            }

    def get_application_record(
        self,
        session_id: str,
        application_id: int
    ) -> Dict[str, Any]:
        """
        Retrieves a tracking record, strictly scoped to the current session.
        """
        record = self.job_repository.get_application(
            application_id=application_id,
            session_id=session_id
        )
        if not record:
            return {
                "status": "error",
                "message": f"Application {application_id} not found or belongs to a different session."
            }
        return {
            "status": "success",
            "data": record
        }

    def update_application_status(
        self,
        session_id: str,
        application_id: int,
        new_status: ApplicationStatus
    ) -> Dict[str, Any]:
        """
        Updates the status of an application safely within the session.
        """
        record = self.job_repository.get_application(application_id, session_id=session_id)
        if not record:
            return {
                "status": "error",
                "message": f"Application {application_id} not found or belongs to a different session."
            }

        # Basic deterministic validation (e.g. don't go backwards from WITHDRAWN/REJECTED easily)
        terminal_states = [ApplicationStatus.WITHDRAWN, ApplicationStatus.REJECTED]
        if record.status in terminal_states and new_status not in terminal_states:
             logger.warning(f"Moving out of terminal state {record.status} to {new_status}")
             # We allow it, but log a warning.

        success = self.job_repository.update_application_status(
            application_id=application_id,
            status=new_status.value,
            session_id=session_id
        )

        if success:
            return {
                "status": "success",
                "message": f"Application {application_id} updated to {new_status.value}."
            }
        else:
            return {
                "status": "error",
                "message": "Failed to update application status."
            }

    def list_applications(
        self,
        session_id: str,
        status: Optional[ApplicationStatus] = None
    ) -> Dict[str, Any]:
        """
        Lists all tracking records for the session, optionally filtered by status.
        """
        status_val = status.value if status else None
        records = self.job_repository.list_applications(
            session_id=session_id,
            status=status_val
        )
        return {
            "status": "success",
            "count": len(records),
            "data": records
        }
