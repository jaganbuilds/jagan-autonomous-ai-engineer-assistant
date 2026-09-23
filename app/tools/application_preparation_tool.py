
from typing import Dict, Any

from app.tools.registry import registry
from app.application.service import ApplicationPreparationService
from app.profile.manager import profile_manager
from app.agents.state import state_manager
from app.database.repository import get_job_repository


application_service = ApplicationPreparationService(
    profile_manager=profile_manager,
    state_manager=state_manager,
    job_repository=get_job_repository(),
)


@registry.register(requires_confirmation=False)
def prepare_job_application(
    session_id: str,
    job_reference: str,
) -> Dict[str, Any]:
    """
    Prepares a selected job application package for human review.

    The tool does not submit the application and does not send email.
    """

    result = application_service.prepare(
        session_id=session_id,
        job_reference=job_reference,
    )

    return result.model_dump()

