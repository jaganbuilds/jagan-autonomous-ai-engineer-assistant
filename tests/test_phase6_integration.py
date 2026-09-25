import pytest
from unittest.mock import MagicMock
from app.tools.registry import registry
from app.database.models import ApplicationStatus
from app.job_sources.base import Job
from app.profile.manager import profile_manager
from app.profile.models import CandidateProfile
from app.agents.state import state_manager

# Import tools directly for lifecycle testing
from app.tools.job_discovery_tool import discover_new_jobs
from app.tools.job_digest_tool import get_new_job_digest
from app.tools.application_preparation_tool import prepare_job_application
from app.tools.application_tracking_tool import (
    create_application_tracking,
    get_application_tracking,
    update_application_status,
    list_application_tracking
)

def test_phase_6_end_to_end_lifecycle(mock_db_repository, monkeypatch):
    """
    Simulates the entire Phase 6 lifecycle.
    Discovery -> Digest -> Prepare -> Track -> Update -> List
    """
    session_id = "phase6_e2e_session"

    # Set up candidate profile
    profile_manager.update_profile(session_id, CandidateProfile(
        name="Jagan",
        experience_level="Fresher",
        education="B.E. Robotics & Automation Engineering",
        skills=["Python"]
    ))

    # Mock job aggregator
    from app.job_sources.base import AggregatedJobSearchResult
    fake_aggregator = MagicMock()
    fake_job = Job(title="AI Engineer", company="AI Corp", location="Chennai", experience="Fresher", description="Python needed", url="http://aicorp", source="test", external_id="t1")
    fake_aggregator.search.return_value = AggregatedJobSearchResult(
        jobs=[fake_job],
        sources_attempted=1,
        sources_succeeded=1,
        source_errors=[],
        total_results_before_deduplication=1,
        total_results_after_deduplication=1
    )
    
    monkeypatch.setattr("app.discovery.service.source_registry.get_aggregator", MagicMock(return_value=fake_aggregator))
    
    # Mock LLM for Semantic Matcher since job discovery does matching for new jobs
    from app.matching.semantic_matcher import SemanticMatchResult
    fake_match_result = SemanticMatchResult(
        semantically_related_skills=["Machine Learning"],
        additional_missing_skills=[],
        reasoning="Fits well",
        confidence="high",
        next_steps=[]
    )
    monkeypatch.setattr("app.matching.semantic_matcher.SemanticJobMatcher.analyze", MagicMock(return_value=fake_match_result))
    
    # Ensure tracking service uses the mocked DB
    from app.tools import application_tracking_tool
    monkeypatch.setattr(application_tracking_tool.tracking_service, "job_repository", mock_db_repository)
    
    from app.tools import application_preparation_tool
    monkeypatch.setattr(application_preparation_tool.application_service, "job_repository", mock_db_repository)
    
    # Mock LLM call in HR email draft
    monkeypatch.setattr("app.tools.hr_email_tool.draft_hr_email", MagicMock(return_value={
        "status": "success",
        "draft": {
            "subject": "Application for AI Engineer",
            "body": "Dear HR...",
            "recipient": "hr@aicorp.com",
            "job_id": 1
        }
    }))

    # 1. Job Lifecycle: Discovery
    discovery_res = discover_new_jobs(session_id=session_id)
    assert discovery_res["status"] == "completed"
    assert discovery_res["new_jobs"] == 1
    run_id = discovery_res["run_id"]

    # 2. Job Lifecycle: Digest
    digest_res = get_new_job_digest(discovery_run_id=run_id, session_id=session_id)
    assert digest_res["status"] == "success"
    
    # Get the job reference from the digest
    assert len(digest_res["items"]) == 1
    job_id = digest_res["items"][0]["job_id"]
    job_ref = f"job_{job_id}"

    # 3. Application Lifecycle: Preparation
    prep_res = prepare_job_application(session_id=session_id, job_reference=job_ref)
    assert prep_res["status"] == "success"
    db_job_id = prep_res["job_id"]
    assert db_job_id is not None
    assert prep_res["email_subject"] == "Application for AI Engineer"

    # 4. Application Lifecycle: Tracking Creation
    track_res = create_application_tracking(
        session_id=session_id,
        job_id=db_job_id,
        status="PREPARED",
        notes="Looks like a good fit."
    )
    assert track_res["status"] == "success", f"Tracking creation failed: {track_res}"
    app_id = track_res["application_id"]

    # 5. Tracking Lifecycle: Update
    update_res = update_application_status(
        session_id=session_id,
        application_id=app_id,
        status="APPLIED"
    )
    assert update_res["status"] == "success"

    # 6. Tracking Lifecycle: Retrieve
    get_res = get_application_tracking(session_id=session_id, application_id=app_id)
    assert get_res["status"] == "success"
    assert get_res["data"]["status"] == ApplicationStatus.APPLIED

    # 7. Tracking Lifecycle: List
    list_res = list_application_tracking(session_id=session_id)
    assert list_res["status"] == "success"
    assert any(app["id"] == app_id for app in list_res["data"])

def test_safety_boundaries_and_confirmation():
    # Email confirmation is enforced by the custom ConfirmationManager putting the session in WAITING_FOR_CONFIRMATION
    
    # Tracking tools do NOT require confirmation (they merely record local state)
    assert registry.requires_confirmation("create_application_tracking") is False
    assert registry.requires_confirmation("update_application_status") is False
    assert registry.requires_confirmation("list_application_tracking") is False
    assert registry.requires_confirmation("get_application_tracking") is False
    
    # Application preparation does NOT require confirmation
    assert registry.requires_confirmation("prepare_job_application") is False

def test_session_isolation_in_tracking(mock_db_repository, monkeypatch):
    from app.tools.application_tracking_tool import create_application_tracking, get_application_tracking
    from app.tools import application_tracking_tool
    
    monkeypatch.setattr(application_tracking_tool.tracking_service, "job_repository", mock_db_repository)
    
    # Create DB job
    job = Job(title="Isolated Job", company="Corp", location="Chennai", experience="Fresher", description="Test", url="http", source="test", external_id="iso1")
    job_key, db_job = mock_db_repository.save_job(job)

    # Session A creates a tracking record
    res_a = create_application_tracking(session_id="session_A", job_id=db_job.db_id, status="PREPARED")
    assert res_a["status"] == "success", res_a
    app_id = res_a["application_id"]
    
    # Session B tries to access it
    res_b = get_application_tracking(session_id="session_B", application_id=app_id)
    assert res_b["status"] == "error"
    assert "not found" in res_b["message"]

def test_failure_handling():
    from app.tools.application_tracking_tool import update_application_status
    
    # Invalid status
    res = update_application_status(session_id="session_A", application_id=1, status="FAKE_STATUS")
    assert res["status"] == "error"
    assert "Invalid status" in res["message"]
