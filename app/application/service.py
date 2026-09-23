
from app.application.models import ApplicationPackage
from app.database.repository import JobRepository
from app.profile.manager import ProfileManager
from app.agents.state import StateManager


class ApplicationPreparationService:
    def __init__(
        self,
        profile_manager: ProfileManager,
        state_manager: StateManager,
        job_repository: JobRepository,
    ):
        self.profile_manager = profile_manager
        self.state_manager = state_manager
        self.job_repository = job_repository

    def prepare(
        self,
        session_id: str,
        job_reference: str,
    ) -> ApplicationPackage:

        # 1. Candidate profile must exist for this session.
        profile = self.profile_manager.get_profile(session_id)

        if profile is None:
            return ApplicationPackage(
                status="profile_required",
                message=(
                    "A candidate profile is required before "
                    "preparing a job application."
                ),
            )

        # 2. Resolve the selected job.
        session_pair = self.state_manager.get_job_result(
            session_id,
            job_reference,
        )

        persisted_job = None

        if session_pair is not None:
            # Session reference such as job_1.
            session_job = session_pair.job

            if session_job.db_id is not None:
                persisted_job = self.job_repository.get_job(
                    session_job.db_id
                )

        elif str(job_reference).strip().isdigit():
            # Direct persistent database ID.
            persisted_job = self.job_repository.get_job(
                int(str(job_reference).strip())
            )

        if persisted_job is None:
            return ApplicationPackage(
                status="job_not_found",
                message=(
                    f"Could not resolve job reference "
                    f"'{job_reference}'."
                ),
            )

        # 3. Extract existing match information.
        matched_skills = []
        missing_skills = []
        match_explanation = None
        next_steps = []

        if session_pair is not None:
            match_result = session_pair.match_result

            if match_result is not None:
                matched_skills = match_result.matched_skills
                missing_skills = match_result.missing_skills
                match_explanation = match_result.explanation
                next_steps = match_result.next_steps

        # 4. Reuse the existing HR email drafting tool.
        #
        # draft_hr_email works with the session job reference.
        # Therefore it is only called when the selected job
        # exists inside the current session.
        if session_pair is None:
            return ApplicationPackage(
                status="email_draft_unavailable",
                job_id=persisted_job.id,
                job_key=persisted_job.job_key,
                title=persisted_job.title,
                company=persisted_job.company,
                location=persisted_job.location,
                experience=persisted_job.experience,
                url=persisted_job.url,
                candidate_name=profile.name,
                candidate_email=getattr(profile, "email", None),
                matched_skills=matched_skills,
                missing_skills=missing_skills,
                match_explanation=match_explanation,
                next_steps=next_steps,
                message=(
                    "The job exists in persistent storage, but "
                    "an HR email draft requires the job to be "
                    "available in the current session."
                ),
            )

        from app.tools.hr_email_tool import draft_hr_email
        email_result = draft_hr_email(
            session_id=session_id,
            job_reference=job_reference,
        )

        if email_result.get("status") != "success":
            return ApplicationPackage(
                status="email_draft_error",
                job_id=persisted_job.id,
                job_key=persisted_job.job_key,
                title=persisted_job.title,
                company=persisted_job.company,
                location=persisted_job.location,
                experience=persisted_job.experience,
                url=persisted_job.url,
                candidate_name=profile.name,
                candidate_email=getattr(profile, "email", None),
                matched_skills=matched_skills,
                missing_skills=missing_skills,
                match_explanation=match_explanation,
                next_steps=next_steps,
                message=email_result.get(
                    "message",
                    "Failed to prepare the HR email draft.",
                ),
            )

        draft = email_result["draft"]

        # 5. Human-review checklist.
        checklist = [
            "Review the job description",
            "Review matched and missing skills",
            "Verify the resume is suitable for this role",
            "Review the HR email draft",
            "Confirm recipient information",
            "Manually submit the application",
        ]

        # 6. Return the complete application package.
        return ApplicationPackage(
            status="success",
            job_id=persisted_job.id,
            job_key=persisted_job.job_key,
            title=persisted_job.title,
            company=persisted_job.company,
            location=persisted_job.location,
            experience=persisted_job.experience,
            url=persisted_job.url,
            candidate_name=profile.name,
            candidate_email=getattr(profile, "email", None),
            matched_skills=matched_skills,
            missing_skills=missing_skills,
            match_explanation=match_explanation,
            next_steps=next_steps,
            email_subject=draft.get("subject"),
            email_body=draft.get("body"),
            recipient=draft.get("recipient"),
            application_checklist=checklist,
            message="Application package prepared for human review.",
        )
