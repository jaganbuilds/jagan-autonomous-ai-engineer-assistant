import pytest
from unittest.mock import MagicMock, patch
from pydantic import ValidationError
from app.resume.profile_extractor import ResumeProfileExtractor
from app.profile.models import CandidateProfile, Project

@pytest.fixture
def extractor():
    with patch('app.resume.profile_extractor.get_settings') as mock_settings:
        mock_settings.return_value.gemini_api_key = "fake_key"
        # We also want to patch genai.Client so it doesn't try to connect
        with patch('app.resume.profile_extractor.genai.Client') as mock_client:
            ext = ResumeProfileExtractor()
            ext.client = MagicMock()
            return ext

def test_extractor_success(extractor):
    mock_response = MagicMock()
    mock_response.text = '''{
        "name": "John Doe",
        "experience_level": "Senior",
        "education": "B.S. CS",
        "target_roles": ["Backend"],
        "preferred_locations": ["Remote"],
        "skills": ["API Design"],
        "programming_languages": ["Python"],
        "frameworks": ["FastAPI"],
        "databases": ["SQL"],
        "ai_ml_technologies": ["OpenCV"],
        "projects": [
            {
                "name": "CV App",
                "description": "An app",
                "technologies": ["OpenCV", "Python"],
                "url": "http"
            }
        ]
    }'''
    extractor.client.models.generate_content.return_value = mock_response
    
    profile = extractor.extract_profile("John Doe Python FastAPI SQL OpenCV CV App")
    
    assert profile is not None
    assert isinstance(profile, CandidateProfile)
    assert profile.name == "John Doe"
    assert "Python" in profile.programming_languages
    assert "FastAPI" in profile.frameworks
    assert "SQL" in profile.databases
    assert "OpenCV" in profile.ai_ml_technologies
    assert len(profile.projects) == 1
    assert profile.projects[0].name == "CV App"

def test_extractor_multiple_projects(extractor):
    mock_response = MagicMock()
    mock_response.text = '''{
        "name": "Jane",
        "experience_level": "Mid",
        "education": "M.S.",
        "target_roles": [],
        "preferred_locations": [],
        "skills": [],
        "programming_languages": [],
        "frameworks": [],
        "databases": [],
        "ai_ml_technologies": [],
        "projects": [
            {"name": "Proj 1", "description": "D1", "technologies": ["T1"]},
            {"name": "Proj 2", "description": "D2", "technologies": ["T2"]}
        ]
    }'''
    extractor.client.models.generate_content.return_value = mock_response
    
    profile = extractor.extract_profile("Jane 2 projects")
    assert len(profile.projects) == 2
    assert profile.projects[0].name == "Proj 1"
    assert profile.projects[1].name == "Proj 2"

def test_extractor_missing_information(extractor):
    mock_response = MagicMock()
    # Pydantic defaults for list are empty arrays, so we can omit them
    mock_response.text = '''{
        "name": "Alex",
        "experience_level": "Unknown",
        "education": "Unknown"
    }'''
    extractor.client.models.generate_content.return_value = mock_response
    
    profile = extractor.extract_profile("Alex")
    assert profile is not None
    assert profile.name == "Alex"
    # Verify no invented location
    assert len(profile.preferred_locations) == 0

def test_extractor_invalid_gemini_response(extractor):
    mock_response = MagicMock()
    # Missing required 'name', 'experience_level', 'education'
    mock_response.text = '{"some_random_field": "value"}'
    extractor.client.models.generate_content.return_value = mock_response
    
    profile = extractor.extract_profile("Bad JSON")
    
    # Should handle ValidationError gracefully and return None
    assert profile is None

def test_extractor_empty_resume(extractor):
    profile = extractor.extract_profile("")
    
    # Should not call Gemini
    extractor.client.models.generate_content.assert_not_called()
    assert profile is None
    
    profile = extractor.extract_profile("   \n  ")
    assert profile is None

def test_extractor_no_hallucination(extractor):
    # This test verifies the prompt has the right instructions
    # Since we are mocking Gemini, we check the actual prompt sent to ensure the rule is there
    mock_response = MagicMock()
    mock_response.text = '{"name": "test", "experience_level": "a", "education": "b"}'
    extractor.client.models.generate_content.return_value = mock_response
    
    extractor.extract_profile("Only Python and SQL")
    
    # Check the prompt sent
    call_args = extractor.client.models.generate_content.call_args
    prompt_sent = call_args[1]['contents']
    
    assert "DO NOT invent, guess, or hallucinate" in prompt_sent
    assert "DO NOT infer unsupported technologies" in prompt_sent
