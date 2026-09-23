import pytest
from unittest.mock import MagicMock, patch
from app.digest.service import JobDigestService
from app.job_sources.base import Job
from app.matching.models import MatchResult
from app.workflows.models import JobMatchPair
from app.agents.state import state_manager
from app.database.models import DiscoveryRun, DiscoveryRunJob, PersistedJob

@pytest.fixture
def digest_service():
    return JobDigestService()

@patch("app.digest.service.get_job_repository")
def test_digest_new_jobs_only(mock_repo_getter, digest_service):
    mock_repo = MagicMock()
    mock_repo_getter.return_value = mock_repo
    
    # Discovery run contains 2 new jobs, 1 existing
    # But list_discovery_run_jobs(new_only=True) should only return the 2 new ones
    mock_repo.get_discovery_run.return_value = DiscoveryRun(
        id=12, role="Dev", location="", experience="", started_at="", completed_at="",
        total_found=3, new_jobs=2, existing_jobs=1, jobs_processed=3, jobs_skipped=0, status="completed"
    )
    
    mock_repo.list_discovery_run_jobs.return_value = [
        DiscoveryRunJob(discovery_run_id=12, job_id=1, is_new=True),
        DiscoveryRunJob(discovery_run_id=12, job_id=2, is_new=True)
    ]
    
    mock_repo.get_jobs_by_ids.return_value = [
        PersistedJob(id=1, job_key="k1", external_id="", source="src", title="J1", company="C1", location="L1", experience="", description="", url="", discovered_at="", updated_at=""),
        PersistedJob(id=2, job_key="k2", external_id="", source="src", title="J2", company="C2", location="L2", experience="", description="", url="", discovered_at="", updated_at="")
    ]
    
    digest = digest_service.get_digest(12, "sess_none")
    
    assert digest.status == "success"
    assert digest.total_new_jobs == 2
    assert len(digest.items) == 2
    assert digest.jobs_without_match_data == 2
    assert digest.jobs_with_profile_match == 0

@patch("app.digest.service.get_job_repository")
def test_digest_with_match_data(mock_repo_getter, digest_service):
    mock_repo = MagicMock()
    mock_repo_getter.return_value = mock_repo
    
    mock_repo.get_discovery_run.return_value = DiscoveryRun(
        id=1, role="", location="", experience="", started_at="", completed_at="",
        total_found=1, new_jobs=1, existing_jobs=0, jobs_processed=1, jobs_skipped=0, status="completed"
    )
    
    mock_repo.list_discovery_run_jobs.return_value = [
        DiscoveryRunJob(discovery_run_id=1, job_id=1, is_new=True)
    ]
    
    job_p = PersistedJob(id=1, job_key="k1", external_id="", source="src", title="J1", company="C1", location="L1", experience="", description="", url="", discovered_at="", updated_at="")
    mock_repo.get_jobs_by_ids.return_value = [job_p]
    
    app_job = job_p.to_app_job()
    match_result = MatchResult(
        matched_skills=["Python"], missing_skills=["Docker"],
        matching_programming_languages=[], matching_frameworks=[], matching_ai_ml_technologies=[],
        location_match="", experience_match="", education_match="", explanation="Good match"
    )
    
    state_manager.clear_session("sess_match")
    state = state_manager.get_session("sess_match")
    state.job_results["job_1"] = JobMatchPair(job=app_job, match_result=match_result)
    
    digest = digest_service.get_digest(1, "sess_match")
    
    assert digest.jobs_with_profile_match == 1
    assert digest.items[0].match_explanation == "Good match"
    assert digest.items[0].matched_skills == ["Python"]
    assert digest.items[0].missing_skills == ["Docker"]

@patch("app.digest.service.get_job_repository")
def test_digest_session_isolation(mock_repo_getter, digest_service):
    mock_repo = MagicMock()
    mock_repo_getter.return_value = mock_repo
    
    mock_repo.get_discovery_run.return_value = DiscoveryRun(
        id=1, role="", location="", experience="", started_at="", completed_at="",
        total_found=1, new_jobs=1, existing_jobs=0, jobs_processed=1, jobs_skipped=0, status="completed"
    )
    mock_repo.list_discovery_run_jobs.return_value = [DiscoveryRunJob(discovery_run_id=1, job_id=1, is_new=True)]
    job_p = PersistedJob(id=1, job_key="k1", external_id="", source="src", title="J1", company="C1", location="L1", experience="", description="", url="", discovered_at="", updated_at="")
    mock_repo.get_jobs_by_ids.return_value = [job_p]
    
    # Session A has match data
    app_job = job_p.to_app_job()
    state_manager.clear_session("sess_A")
    state_A = state_manager.get_session("sess_A")
    state_A.job_results["job_1"] = JobMatchPair(job=app_job, match_result=MatchResult(matched_skills=["A"], missing_skills=[], matching_programming_languages=[], matching_frameworks=[], matching_ai_ml_technologies=[], location_match="", experience_match="", education_match="", explanation="A"))
    
    # Session B requests digest
    state_manager.clear_session("sess_B")
    digest = digest_service.get_digest(1, "sess_B")
    
    assert digest.jobs_with_profile_match == 0
    assert digest.items[0].match_explanation is None

@patch("app.digest.service.get_job_repository")
def test_digest_invalid_run(mock_repo_getter, digest_service):
    mock_repo = MagicMock()
    mock_repo_getter.return_value = mock_repo
    
    mock_repo.get_discovery_run.return_value = None
    
    digest = digest_service.get_digest(999, "sess")
    assert digest.status == "discovery_run_not_found"
    assert digest.total_new_jobs == 0
