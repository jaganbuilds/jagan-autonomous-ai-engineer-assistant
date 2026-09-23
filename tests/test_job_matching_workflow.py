import pytest
import json
from unittest.mock import MagicMock, patch
from app.job_sources.base import Job
from app.matching.models import MatchResult
from app.workflows.job_matching_workflow import JobMatchingWorkflow
from app.profile.models import CandidateProfile
from app.profile.manager import profile_manager
from app.tools.registry import registry
import app.tools.job_matching_workflow_tool # To ensure registration

from app.job_sources.base import Job, AggregatedJobSearchResult

# Helper to create mock jobs quickly
def create_mock_jobs(count: int):
    return [
        Job(title=f"Job {i}", company=f"Company {i}", description="Desc", location="Remote", experience="Mid", url="")
        for i in range(count)
    ]

def create_mock_agg_result(count: int) -> AggregatedJobSearchResult:
    jobs = create_mock_jobs(count)
    return AggregatedJobSearchResult(
        jobs=jobs, sources_attempted=1, sources_succeeded=1, source_errors=[],
        total_results_before_deduplication=count, total_results_after_deduplication=count
    )

@pytest.fixture
def dummy_profile():
    return CandidateProfile(
        name="Test",
        experience_level="Mid",
        education="BS",
        skills=["Python"]
    )

@patch("app.job_sources.aggregator.JobSourceAggregator.search")
def test_workflow_search_and_match(mock_search, dummy_profile):
    profile_manager.save_profile("sess_1", dummy_profile)
    mock_search.return_value = create_mock_agg_result(3)
    
    workflow = JobMatchingWorkflow(max_jobs=5)
    res = workflow.execute(session_id="sess_1", role="Dev")
    
    assert res.status == "success"
    assert res.jobs_found == 3
    assert res.jobs_processed == 3
    assert res.jobs_skipped == 0
    assert len(res.results) == 3
    
    for pair in res.results:
        assert pair.job is not None
        assert isinstance(pair.match_result, MatchResult)
        assert pair.error is None
        assert not hasattr(pair.match_result, "score")

def test_workflow_missing_profile():
    workflow = JobMatchingWorkflow(max_jobs=5)
    res = workflow.execute(session_id="sess_missing", role="Dev")
    
    assert res.status == "profile_required"
    assert res.jobs_found == 0
    assert res.jobs_processed == 0
    assert len(res.results) == 0

@patch("app.job_sources.aggregator.JobSourceAggregator.search")
def test_workflow_different_sessions(mock_search):
    mock_search.return_value = create_mock_agg_result(1)
    
    p_a = CandidateProfile(name="Alice", experience_level="", education="", skills=["Python"])
    p_b = CandidateProfile(name="Bob", experience_level="", education="", skills=["Java"])
    profile_manager.save_profile("sess_a", p_a)
    profile_manager.save_profile("sess_b", p_b)
    
    workflow = JobMatchingWorkflow(max_jobs=5)
    res_a = workflow.execute(session_id="sess_a", role="Dev")
    res_b = workflow.execute(session_id="sess_b", role="Dev")
    
    # We can check the match_result to verify different profiles were used, but since we mock job descriptions it might be identical.
    # However, we test the logic didn't crash and processed fine.
    assert res_a.status == "success"
    assert res_b.status == "success"

@patch("app.job_sources.aggregator.JobSourceAggregator.search")
def test_workflow_maximum_job_limit(mock_search, dummy_profile):
    profile_manager.save_profile("sess_limit", dummy_profile)
    mock_search.return_value = create_mock_agg_result(10)
    
    workflow = JobMatchingWorkflow(max_jobs=5)
    res = workflow.execute(session_id="sess_limit", role="Dev")
    
    assert res.jobs_found == 10
    assert res.jobs_processed == 5
    assert res.jobs_skipped == 5
    assert len(res.results) == 5

@patch("app.job_sources.aggregator.JobSourceAggregator.search")
def test_workflow_zero_results(mock_search, dummy_profile):
    profile_manager.save_profile("sess_zero", dummy_profile)
    mock_search.return_value = create_mock_agg_result(0)
    
    workflow = JobMatchingWorkflow(max_jobs=5)
    res = workflow.execute(session_id="sess_zero", role="Astronaut")
    
    assert res.jobs_found == 0
    assert res.jobs_processed == 0
    assert res.jobs_skipped == 0
    assert len(res.results) == 0

@patch("app.job_sources.aggregator.JobSourceAggregator.search")
@patch.object(JobMatchingWorkflow, '__init__', return_value=None)
def test_workflow_individual_matcher_failure(mock_init, mock_search, dummy_profile):
    profile_manager.save_profile("sess_fail", dummy_profile)
    workflow = JobMatchingWorkflow()
    workflow.max_jobs = 5
    
    mock_jobs = create_mock_jobs(3)
    mock_search.return_value = create_mock_agg_result(3)
    
    mock_matcher = MagicMock()
    def fake_match(job, candidate):
        if job.title == "Job 1":
            raise ValueError("Something broke inside matcher!")
        return MatchResult(
            matched_skills=[], missing_skills=[], matching_programming_languages=[],
            matching_frameworks=[], matching_ai_ml_technologies=[], location_match="",
            experience_match="", education_match="", explanation="OK"
        )
    mock_matcher.match = fake_match
    workflow.matcher = mock_matcher
    workflow.semantic_matcher = MagicMock()
    workflow.semantic_matcher.analyze.return_value = None
    
    res = workflow.execute(session_id="sess_fail")
    
    assert res.jobs_processed == 3
    assert len(res.results) == 3
    
    assert res.results[0].error is None
    assert res.results[1].error == "Something broke inside matcher!"
    assert res.results[1].match_result is None
    assert res.results[2].error is None

def test_workflow_tool_safety():
    assert registry.requires_confirmation("search_and_match_jobs") is False

@patch("app.job_sources.aggregator.JobSourceAggregator.search")
def test_workflow_tool_execution(mock_search, dummy_profile):
    profile_manager.save_profile("sess_tool", dummy_profile)
    mock_search.return_value = create_mock_agg_result(2)
    tool = registry.get_tool("search_and_match_jobs")
    
    res_str = tool(session_id="sess_tool", role="Dev")
    res_dict = json.loads(res_str)
    
    assert res_dict["status"] == "success"
    assert res_dict["result"]["jobs_found"] == 2
    assert res_dict["result"]["jobs_processed"] == 2

