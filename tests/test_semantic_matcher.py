import pytest
from unittest.mock import MagicMock, patch
from pydantic import ValidationError
from app.matching.semantic_matcher import SemanticJobMatcher, SemanticMatchResult
from app.job_sources.base import Job
from app.profile.models import CandidateProfile
from app.matching.models import MatchResult
from app.llm.gateway import gateway

@pytest.fixture
def matcher(monkeypatch):
    monkeypatch.setattr("app.matching.semantic_matcher.get_settings", MagicMock(return_value=MagicMock(openrouter_api_key="test")))
    return SemanticJobMatcher()

@pytest.fixture
def dummy_job():
    return Job(
        title="AI Engineer",
        company="TechCorp",
        location="Remote",
        experience="Mid",
        description="Requires Neural Networks and Deep Learning.",
        url="https://example.com/job"
    )

@pytest.fixture
def dummy_profile():
    return CandidateProfile(
        name="John",
        experience_level="Mid",
        education="BS",
        skills=["Deep Learning", "Backend APIs"]
    )

@pytest.fixture
def dummy_match_result():
    return MatchResult(
        matched_skills=[],
        missing_skills=["Neural Networks"],
        location_match="Matched",
        experience_match="Matched",
        education_match="Unknown",
        explanation="Deterministic result"
    )

def test_semantic_relationship_detected(matcher, dummy_job, dummy_profile, dummy_match_result):
    gateway.generate_json.return_value = SemanticMatchResult(
        semantically_related_skills=["Neural Networks (matches Deep Learning)"],
        additional_missing_skills=[],
        reasoning="Deep learning implies neural networks.",
        confidence="high",
        next_steps=[]
    )

    result = matcher.analyze(dummy_job, dummy_profile, dummy_match_result)

    assert result is not None
    assert isinstance(result, SemanticMatchResult)
    assert len(result.semantically_related_skills) == 1
    assert "Neural Networks" in result.semantically_related_skills[0]
    assert result.confidence == "high"

def test_no_semantic_relationship(matcher, dummy_job, dummy_profile, dummy_match_result):
    gateway.generate_json.return_value = SemanticMatchResult(
        semantically_related_skills=[],
        additional_missing_skills=["Go", "Kubernetes"],
        reasoning="Candidate doesn't have the required tech.",
        confidence="high",
        next_steps=[]
    )

    result = matcher.analyze(dummy_job, dummy_profile, dummy_match_result)
    assert len(result.semantically_related_skills) == 0
    assert "Go" in result.additional_missing_skills
    assert "Kubernetes" in result.additional_missing_skills

def test_semantic_api_failure(matcher, dummy_job, dummy_profile, dummy_match_result):
    gateway.generate_json.side_effect = Exception("API Error")

    result = matcher.analyze(dummy_job, dummy_profile, dummy_match_result)
    assert result is None
    gateway.generate_json.side_effect = None
