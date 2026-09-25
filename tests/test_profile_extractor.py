import pytest
from unittest.mock import MagicMock, patch
from pydantic import ValidationError
from app.resume.profile_extractor import ResumeProfileExtractor
from app.profile.models import CandidateProfile, Project
from app.llm.gateway import gateway

@pytest.fixture
def extractor(monkeypatch):
    monkeypatch.setattr("app.resume.profile_extractor.get_settings", MagicMock(return_value=MagicMock(openrouter_api_key="fake_key")))
    return ResumeProfileExtractor()

def test_extractor_success(extractor):
    gateway.generate_json.return_value = CandidateProfile(
        name="John Doe",
        experience_level="Senior",
        education="B.S. CS",
        target_roles=["Backend"],
        preferred_locations=["Remote"],
        skills=["API Design"],
        programming_languages=["Python"],
        frameworks=["FastAPI"],
        databases=["SQL"],
        ai_ml_technologies=["OpenCV"],
        projects=[
            Project(name="CV App", description="An app", technologies=["OpenCV", "Python"], url="http")
        ]
    )
    
    profile = extractor.extract_profile("John Doe Python FastAPI SQL OpenCV CV App")
    
    assert profile is not None
    assert isinstance(profile, CandidateProfile)
    assert profile.name == "John Doe"
    assert "Python" in profile.programming_languages
    assert len(profile.projects) == 1
    assert profile.projects[0].name == "CV App"

def test_extractor_multiple_projects(extractor):
    gateway.generate_json.return_value = CandidateProfile(
        name="Jane",
        experience_level="Mid",
        education="M.S.",
        projects=[
            Project(name="Proj 1", description="D1", technologies=["T1"]),
            Project(name="Proj 2", description="D2", technologies=["T2"])
        ]
    )
    
    profile = extractor.extract_profile("Jane 2 projects")
    assert len(profile.projects) == 2
    assert profile.projects[0].name == "Proj 1"
    assert profile.projects[1].name == "Proj 2"

def test_extractor_missing_information(extractor):
    gateway.generate_json.return_value = CandidateProfile(
        name="Alex",
        experience_level="Unknown",
        education="Unknown"
    )
    
    profile = extractor.extract_profile("Alex")
    assert profile is not None
    assert profile.name == "Alex"
    assert len(profile.preferred_locations) == 0

def test_extractor_invalid_gemini_response(extractor):
    gateway.generate_json.side_effect = ValidationError.from_exception_data('mock', [])
    
    profile = extractor.extract_profile("Bad JSON")
    assert profile is None
    gateway.generate_json.side_effect = None

def test_extractor_empty_resume(extractor):
    gateway.generate_json.reset_mock()
    profile = extractor.extract_profile("")
    assert profile is None
    profile = extractor.extract_profile("   \n  ")
    assert profile is None
    gateway.generate_json.assert_not_called()

def test_extractor_no_hallucination(extractor):
    gateway.generate_json.return_value = CandidateProfile(
        name="Unknown", experience_level="Unknown", education="Unknown", skills=[]
    )
    profile = extractor.extract_profile("hello")
    assert len(profile.skills) == 0
