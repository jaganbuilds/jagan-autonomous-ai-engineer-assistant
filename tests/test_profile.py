import pytest
from pydantic import ValidationError
from app.profile.models import CandidateProfile, Project
from app.profile.mock_profile import MOCK_CANDIDATE

def test_profile_creation_valid():
    profile = CandidateProfile(
        name="Test User",
        experience_level="Entry Level",
        education="B.A. English"
    )
    assert profile.name == "Test User"
    assert profile.experience_level == "Entry Level"
    # Ensure lists default to empty
    assert profile.skills == []
    assert profile.projects == []

def test_profile_validation_missing_fields():
    with pytest.raises(ValidationError):
        # Missing required core fields (education, experience_level)
        CandidateProfile(name="Incomplete User")

def test_profile_serialization():
    dump = MOCK_CANDIDATE.model_dump()
    
    # Check core fields
    assert dump["name"] == "Jane Doe"
    assert "FastAPI" in dump["frameworks"]
    
    # Check nested projects
    assert len(dump["projects"]) == 2
    assert dump["projects"][0]["name"] == "Autonomous Agent"
    assert dump["projects"][0]["url"] == "https://github.com/janedoe/agent"

def test_project_empty_optional_fields():
    proj = Project(
        name="Simple Script",
        description="Just a simple script."
    )
    assert proj.url is None
    assert proj.technologies == []
