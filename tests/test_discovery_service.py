import pytest
from unittest.mock import patch, MagicMock
from app.discovery.service import JobDiscoveryService
from app.job_sources.base import Job, AggregatedJobSearchResult
from app.profile.models import CandidateProfile

@pytest.fixture
def mock_profile():
    return CandidateProfile(name="Test", experience_level="Fresher", education="BS", skills=["Python"])

@patch("app.job_sources.aggregator.JobSourceAggregator.search")
def test_discovery_service_first_run(mock_search, mock_db_repository, mock_profile):
    from app.profile.manager import profile_manager
    profile_manager.save_profile("sess_disc_1", mock_profile)
    
    mock_jobs = [
        Job(title="J1", company="C1", location="L1", experience="", description="", url="", source="S", external_id="1"),
        Job(title="J2", company="C2", location="L2", experience="", description="", url="", source="S", external_id="2")
    ]
    
    mock_search.return_value = AggregatedJobSearchResult(
        jobs=mock_jobs, sources_attempted=1, sources_succeeded=1, source_errors=[],
        total_results_before_deduplication=2, total_results_after_deduplication=2
    )
    
    service = JobDiscoveryService()
    service.matcher = MagicMock()
    from app.matching.models import MatchResult
    service.matcher.match.return_value = MatchResult(matched_skills=[], missing_skills=[], matching_programming_languages=[], matching_frameworks=[], matching_ai_ml_technologies=[], location_match='', experience_match='', education_match='', explanation='test')
    service.semantic_matcher = MagicMock()
    
    res = service.run(session_id="sess_disc_1")
    
    assert res.status == "completed"
    assert res.total_found == 2
    assert res.new_jobs == 2
    assert res.existing_jobs == 0
    assert len(res.jobs) == 2
    
    for job in res.jobs:
        assert job.is_new is True
        
    # Matcher should be called 2 times for new jobs
    assert service.matcher.match.call_count == 2

@patch("app.job_sources.aggregator.JobSourceAggregator.search")
def test_discovery_service_duplicate_run(mock_search, mock_db_repository, mock_profile):
    from app.profile.manager import profile_manager
    profile_manager.save_profile("sess_disc_2", mock_profile)
    
    mock_jobs = [
        Job(title="J1", company="C1", location="L1", experience="", description="", url="", source="S", external_id="1"),
    ]
    
    mock_search.return_value = AggregatedJobSearchResult(
        jobs=mock_jobs, sources_attempted=1, sources_succeeded=1, source_errors=[],
        total_results_before_deduplication=1, total_results_after_deduplication=1
    )
    
    service = JobDiscoveryService()
    service.matcher = MagicMock()
    from app.matching.models import MatchResult
    service.matcher.match.return_value = MatchResult(matched_skills=[], missing_skills=[], matching_programming_languages=[], matching_frameworks=[], matching_ai_ml_technologies=[], location_match='', experience_match='', education_match='', explanation='test')
    service.semantic_matcher = MagicMock()
    
    # Run 1 (New)
    res1 = service.run(session_id="sess_disc_2")
    assert res1.new_jobs == 1
    assert service.matcher.match.call_count == 1
    
    # Run 2 (Existing)
    service.matcher.reset_mock()
    res2 = service.run(session_id="sess_disc_2")
    assert res2.new_jobs == 0
    assert res2.existing_jobs == 1
    assert res2.jobs[0].is_new is False
    
    # Matcher should NOT be called for existing jobs
    assert service.matcher.match.call_count == 0

@patch("app.job_sources.aggregator.JobSourceAggregator.search")
def test_discovery_service_missing_profile(mock_search, mock_db_repository):
    mock_jobs = [
        Job(title="J1", company="C1", location="L1", experience="", description="", url="", source="S", external_id="1"),
    ]
    
    mock_search.return_value = AggregatedJobSearchResult(
        jobs=mock_jobs, sources_attempted=1, sources_succeeded=1, source_errors=[],
        total_results_before_deduplication=1, total_results_after_deduplication=1
    )
    
    service = JobDiscoveryService()
    service.matcher = MagicMock()
    from app.matching.models import MatchResult
    service.matcher.match.return_value = MatchResult(matched_skills=[], missing_skills=[], matching_programming_languages=[], matching_frameworks=[], matching_ai_ml_technologies=[], location_match='', experience_match='', education_match='', explanation='test')
    
    res = service.run(session_id="sess_missing_prof")
    
    assert res.status == "profile_not_available"
    assert res.total_found == 1
    assert res.new_jobs == 1
    assert res.existing_jobs == 0
    
    # DB persistence still happened
    assert mock_db_repository.job_exists(mock_db_repository.generate_job_key(mock_jobs[0]))
    
    # But matcher was not called
    assert service.matcher.match.call_count == 0
