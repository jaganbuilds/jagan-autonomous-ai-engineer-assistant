import pytest
import json
from unittest.mock import MagicMock, patch
from pydantic import ValidationError
from app.job_sources.base import Job
from app.profile.models import CandidateProfile
from app.matching.models import MatchResult, SemanticMatchResult
from app.matching.semantic_matcher import SemanticJobMatcher

@pytest.fixture
def matcher():
    with patch('app.matching.semantic_matcher.get_settings') as mock_settings:
        mock_settings.return_value.gemini_api_key = "fake_key"
        with patch('app.llm_client.get_llm_client') as mock_client:
            sem_matcher = SemanticJobMatcher()
            sem_matcher.client = MagicMock()
            return sem_matcher

@pytest.fixture
def dummy_job():
    return Job(
        title="AI Engineer",
        company="TechCorp",
        description="Requires Neural Networks and deep understanding of backend.",
        location="Remote",
        experience="Mid",
        url="http://test.com"
    )

@pytest.fixture
def dummy_profile():
    return CandidateProfile(
        name="John",
        experience_level="Mid",
        education="BS",
        skills=["Deep Learning", "Backend APIs"],
        target_roles=[],
        preferred_locations=[],
        programming_languages=[],
        frameworks=[],
        databases=[],
        ai_ml_technologies=[]
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
    mock_response = MagicMock()
    mock_response.text = '''{
        "semantically_related_skills": ["Neural Networks (matches Deep Learning)"],
        "additional_missing_skills": [],
        "reasoning": "Deep learning implies neural networks.",
        "confidence": "high"
    }'''
    matcher.client.models.generate_content.return_value = mock_response
    
    result = matcher.analyze(dummy_job, dummy_profile, dummy_match_result)
    
    assert result is not None
    assert isinstance(result, SemanticMatchResult)
    assert len(result.semantically_related_skills) == 1
    assert result.confidence == "high"

def test_no_semantic_relationship(matcher, dummy_job, dummy_profile, dummy_match_result):
    mock_response = MagicMock()
    mock_response.text = '''{
        "semantically_related_skills": [],
        "additional_missing_skills": ["Go", "Kubernetes"],
        "reasoning": "Candidate doesn't have the required tech.",
        "confidence": "high"
    }'''
    matcher.client.models.generate_content.return_value = mock_response
    
    result = matcher.analyze(dummy_job, dummy_profile, dummy_match_result)
    assert len(result.semantically_related_skills) == 0
    assert len(result.additional_missing_skills) == 2

def test_invalid_gemini_response(matcher, dummy_job, dummy_profile, dummy_match_result):
    mock_response = MagicMock()
    mock_response.text = '{"bad_key": "val"}'
    matcher.client.models.generate_content.return_value = mock_response
    
    result = matcher.analyze(dummy_job, dummy_profile, dummy_match_result)
    # Should safely fail and return None
    assert result is None

def test_gemini_api_failure(matcher, dummy_job, dummy_profile, dummy_match_result):
    matcher.client.models.generate_content.side_effect = Exception("API down")
    
    result = matcher.analyze(dummy_job, dummy_profile, dummy_match_result)
    assert result is None

def test_missing_api_key(dummy_job, dummy_profile, dummy_match_result):
    with patch('app.matching.semantic_matcher.get_settings') as mock_settings:
        mock_settings.return_value.gemini_api_key = None
        matcher = SemanticJobMatcher()
        
        result = matcher.analyze(dummy_job, dummy_profile, dummy_match_result)
        assert result is None

def test_hallucination_rejected_prompt_check(matcher, dummy_job, dummy_profile, dummy_match_result):
    mock_response = MagicMock()
    mock_response.text = '{"semantically_related_skills": [], "additional_missing_skills": [], "reasoning": "OK", "confidence": "high"}'
    matcher.client.models.generate_content.return_value = mock_response
    
    matcher.analyze(dummy_job, dummy_profile, dummy_match_result)
    
    call_args = matcher.client.models.generate_content.call_args
    prompt = call_args[1]['contents']
    
    assert "DO NOT invent or hallucinate" in prompt
    assert "Do NOT convert uncertain relationships" in prompt
