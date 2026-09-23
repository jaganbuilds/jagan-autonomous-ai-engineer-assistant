import pytest
from unittest.mock import patch, MagicMock
from google.genai.errors import APIError

@pytest.fixture
def manager():
    with patch("app.agents.manager.get_settings") as mock_settings:
        mock_settings.return_value.gemini_api_key = "test_key"
        with patch("app.llm_client.get_llm_client") as mock_llm_client:
            mock_llm_client.return_value = MagicMock()
            from app.agents.manager import ManagerAgent
            mgr = ManagerAgent()
            mgr._get_chat = MagicMock()
            return mgr

def test_manager_api_error_503(manager):
    # Setup session
    from app.agents.state import state_manager
    session_id = "test_503"
    state_manager.clear_session(session_id)
    mock_chat = manager._get_chat(session_id)
    
    # Mock chat to raise APIError 503
    mock_chat.send_message.side_effect = APIError(503, {"error": "503 Service Unavailable"})
    
    reply = manager.process_message("Hello", session_id)
    assert reply == "The AI model is temporarily unavailable. Please try again later."
    
    session = state_manager.get_session(session_id)
    from app.agents.state import SessionStatus
    assert session.status == SessionStatus.ERROR

def test_manager_api_error_401(manager):
    from app.agents.state import state_manager
    session_id = "test_401"
    state_manager.clear_session(session_id)
    mock_chat = manager._get_chat(session_id)
    
    mock_chat.send_message.side_effect = APIError(401, {"error": "401 Unauthorized"})
    
    reply = manager.process_message("Hello", session_id)
    assert reply == "The AI model is temporarily unavailable. Please try again later."
    
def test_manager_api_error_429(manager):
    from app.agents.state import state_manager
    session_id = "test_429"
    state_manager.clear_session(session_id)
    mock_chat = manager._get_chat(session_id)
    
    mock_chat.send_message.side_effect = APIError(429, {"error": "429 Too Many Requests"})
    
    reply = manager.process_message("Hello", session_id)
    assert reply == "The AI model is temporarily unavailable. Please try again later."

def test_semantic_matcher_api_error():
    from app.matching.semantic_matcher import SemanticJobMatcher
    from app.job_sources.base import Job
    from app.profile.models import CandidateProfile
    from app.matching.models import MatchResult
    
    with patch('app.llm_client.get_llm_client') as mock_llm:
        matcher = SemanticJobMatcher()
        matcher.client = MagicMock()
        matcher.client.models.generate_content.side_effect = APIError(503, {"error": "503 error"})
        
        job = Job(title="T", company="C", description="Long enough description here to pass validation check", location="L", experience="E", url="")
        profile = CandidateProfile(name="N", experience_level="E", education="E", skills=[])
        determ = MatchResult(matched_skills=[], missing_skills=[], location_match="Unknown", experience_match="Unknown", education_match="Unknown", explanation="")
        
        res = matcher.analyze(job, profile, determ)
        assert res is None # Should fail safely without crashing
