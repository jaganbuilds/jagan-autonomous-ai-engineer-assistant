
from app.application.service import ApplicationPreparationService
from app.agents.state import StateManager
from app.profile.manager import ProfileManager
from app.profile.models import CandidateProfile
from app.job_sources.base import Job
from app.matching.models import MatchResult
from app.workflows.models import JobMatchPair
from app.tools.hr_email_tool import EmailDraft


def test_application_preparation_requires_profile():
    service = ApplicationPreparationService(
        profile_manager=ProfileManager(),
        state_manager=StateManager(),
        job_repository=None,
    )

    result = service.prepare(
        session_id="test-session",
        job_reference="job_1",
    )

    assert result.status == "profile_required"


def test_application_preparation_resolves_session_job():
    profile_manager = ProfileManager()
    state_manager = StateManager()

    profile_manager.update_profile(
        "test-session",
        CandidateProfile(
            name="Jagan",
            experience_level="Fresher",
            education="B.E. Robotics & Automation Engineering",
        ),
    )

    profile = profile_manager.get_profile("test-session")

    job = Job(
        title="AI Engineer",
        company="Test Company",
        location="Chennai",
        experience="Fresher",
        description="Python, FastAPI and AI/ML role",
        url="https://example.com/job",
        source="test",
        external_id="test-001",
        db_id=1,
        job_key="test:test-001",
    )

    match_result = MatchResult(
        matched_skills=["Python", "FastAPI"],
        missing_skills=["Docker"],
        matching_programming_languages=["Python"],
        matching_frameworks=["FastAPI"],
        matching_ai_ml_technologies=["AI/ML"],
        location_match="match",
        experience_match="match",
        education_match="match",
        explanation="The candidate has relevant Python and FastAPI skills.",
        next_steps=["Review Docker requirements"],
    )

    state_manager.store_job_results(
        "test-session",
        [
            JobMatchPair(
                job=job,
                match_result=match_result,
            )
        ],
    )

    assert profile is not None
    assert profile.name == "Jagan"
    assert state_manager.get_job_result(
        "test-session",
        "job_1",
    ) is not None

def test_application_preparation_resolves_persisted_job(mock_db_repository):
    profile_manager = ProfileManager()
    state_manager = StateManager()

    profile_manager.update_profile(
        "db-session",
        CandidateProfile(
            name="Jagan",
            experience_level="Fresher",
            education="B.E. Robotics & Automation Engineering",
        ),
    )

    job = Job(
        title="AI Engineer",
        company="Test Company",
        location="Chennai",
        experience="Fresher",
        description="Python AI Engineer role",
        url="https://example.com/db-job",
        source="test",
        external_id="db-001",
    )

    job_key, saved_job = mock_db_repository.save_job(job)

    service = ApplicationPreparationService(
        profile_manager=profile_manager,
        state_manager=state_manager,
        job_repository=mock_db_repository,
    )

    result = service.prepare(
        session_id="db-session",
        job_reference=str(saved_job.db_id),
    )

    assert result.status == "email_draft_unavailable"
    assert result.job_id == saved_job.db_id
    assert result.title == "AI Engineer"
    assert result.company == "Test Company"

def test_application_preparation_creates_full_package(mock_db_repository, monkeypatch):
    profile_manager = ProfileManager()
    state_manager = StateManager()

    profile_manager.update_profile(
        "package-session",
        CandidateProfile(
            name="Jagan",
            experience_level="Fresher",
            education="B.E. Robotics & Automation Engineering",
            skills=["Python", "REST API"],
            programming_languages=["Python"],
            frameworks=["FastAPI"],
            ai_ml_technologies=["Machine Learning"],
        ),
    )

    job = Job(
        title="AI Engineer",
        company="Test AI Company",
        location="Chennai",
        experience="Fresher",
        description="Python, FastAPI and Machine Learning role",
        url="https://example.com/ai-job",
        source="test",
        external_id="package-001",
    )

    job_key, saved_job = mock_db_repository.save_job(job)

    match_result = MatchResult(
        matched_skills=["Python", "FastAPI"],
        missing_skills=["Docker"],
        matching_programming_languages=["Python"],
        matching_frameworks=["FastAPI"],
        matching_ai_ml_technologies=["Machine Learning"],
        location_match="match",
        experience_match="match",
        education_match="match",
        explanation="The candidate has relevant Python and FastAPI experience.",
        next_steps=["Review Docker requirements"],
    )

    state_manager.store_job_results(
        "package-session",
        [
            JobMatchPair(
                job=Job(
                    title=job.title,
                    company=job.company,
                    location=job.location,
                    experience=job.experience,
                    description=job.description,
                    url=job.url,
                    source=job.source,
                    external_id=job.external_id,
                    db_id=saved_job.db_id,
                    job_key=job_key,
                ),
                match_result=match_result,
            )
        ],
    )

    def fake_draft_hr_email(session_id, job_reference):
        return {
            "status": "success",
            "job_id": job_reference,
            "draft": EmailDraft(
                subject="Application for AI Engineer",
                body="Dear Hiring Team, I am interested in the AI Engineer opportunity.",
                recipient="hr@testcompany.com",
                job_id=job_reference,
            ).model_dump(),
        }

    monkeypatch.setattr(
        "app.tools.hr_email_tool.draft_hr_email",
        fake_draft_hr_email,
    )

    service = ApplicationPreparationService(
        profile_manager=profile_manager,
        state_manager=state_manager,
        job_repository=mock_db_repository,
    )

    result = service.prepare(
        session_id="package-session",
        job_reference="job_1",
    )

    assert result.status == "success"
    assert result.job_id == saved_job.db_id
    assert result.title == "AI Engineer"
    assert result.company == "Test AI Company"
    assert result.candidate_name == "Jagan"
    assert result.matched_skills == ["Python", "FastAPI"]
    assert result.missing_skills == ["Docker"]
    assert result.match_explanation is not None
    assert result.next_steps == ["Review Docker requirements"]
    assert result.email_subject == "Application for AI Engineer"
    assert result.email_body is not None
    assert result.recipient == "hr@testcompany.com"
    assert len(result.application_checklist) > 0



