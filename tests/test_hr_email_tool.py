import pytest
import json
from unittest.mock import patch
from app.tools.registry import registry
import app.tools.hr_email_tool # Ensure registered
from app.tools.hr_email_tool import EmailDraft

@pytest.fixture
def mock_job_repo():
    from app.database.repository import JobRepository, set_job_repository_for_testing
    from app.database.connection import init_db
    db_path = "file:memdb_hremail?mode=memory&cache=shared"
    init_db(db_path)
    repo = JobRepository(db_path)
    set_job_repository_for_testing(repo)
    return repo

@patch("app.llm.gateway.gateway.generate_json")
def test_hr_email_tool_success(mock_json, mock_job_repo):
    from app.job_sources.base import Job
    job = Job(
        title="Test Job",
        company="Test Co",
        location="Remote",
        experience="Mid",
        description="We need a python dev.",
        url="https://example.com/job"
    )
    mock_job_repo.save_job(job)
    job_key = job.job_key
    
    mock_json.return_value = EmailDraft(
        subject="Application for Test Job",
        body="Here is my resume.",
        recipient="hr@testco.com",
        job_id=job_key
    )

    tool = registry.get_tool("draft_hr_email")
    session_id = "test_hr_email_sess"
    
    # Store dummy profile
    from app.profile.manager import profile_manager
    from app.profile.models import CandidateProfile
    profile_manager.save_profile(session_id, CandidateProfile(name="Test", experience_level="Mid", education="BS"))

    # Also store the job in the session state manager, because draft_hr_email expects it
    from app.agents.state import state_manager
    from app.workflows.models import JobMatchPair
    from app.matching.models import MatchResult
    match_result = MatchResult(
        matched_skills=[], missing_skills=[], location_match="Unknown", 
        experience_match="Unknown", education_match="Unknown", explanation=""
    )
    pair = JobMatchPair(job=job, match_result=match_result)
    state_manager.store_job_results(session_id, [pair])

    res_str = tool(session_id=session_id, job_reference="job_1")
    res = json.loads(res_str)

    assert res["status"] == "success"
    assert res["result"]["status"] == "success"
    assert res["result"]["draft"]["subject"] == "Application for Test Job"
