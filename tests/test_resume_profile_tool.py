import pytest
import json
from unittest.mock import MagicMock, patch
from app.tools.registry import registry
from app.profile.manager import profile_manager
from app.profile.models import CandidateProfile
import app.tools.resume_profile_tool # Ensure registered

@pytest.fixture
def dummy_profile():
    return CandidateProfile(
        name="John Doe",
        experience_level="Senior",
        education="B.S. CS",
        target_roles=["Engineer"],
        preferred_locations=["Remote"],
        skills=["Python"]
    )

@patch("app.tools.resume_profile_tool._parser.extract_text")
@patch("app.tools.resume_profile_tool._extractor.extract_profile")
def test_resume_tool_success(mock_extract_profile, mock_extract_text, dummy_profile):
    mock_extract_text.return_value = "Mocked Resume Text"
    mock_extract_profile.return_value = dummy_profile
    
    session_id = "test_sess_resume"
    
    # Ensure profile does not exist yet
    profile_manager.delete_profile(session_id)
    assert not profile_manager.has_profile(session_id)
    
    tool = registry.get_tool("extract_and_save_profile")
    res_str = tool(session_id=session_id, file_path="dummy.pdf")
    res = json.loads(res_str)
    
    assert res["status"] == "success"
    result_data = res["result"]
    assert result_data["status"] == "success"
    assert result_data["profile"]["name"] == "John Doe"
    
    # Ensure it was saved to the ProfileManager
    assert profile_manager.has_profile(session_id)
    saved_profile = profile_manager.get_profile(session_id)
    assert saved_profile.name == "John Doe"
    
    # Cleanup
    profile_manager.delete_profile(session_id)

@patch("app.tools.resume_profile_tool._parser.extract_text")
def test_resume_tool_missing_or_invalid_pdf(mock_extract_text):
    mock_extract_text.return_value = "" # Parser returns empty string on failure
    
    tool = registry.get_tool("extract_and_save_profile")
    res_str = tool(session_id="test_sess_invalid", file_path="invalid.pdf")
    res = json.loads(res_str)
    
    assert res["status"] == "success"
    assert res["result"]["status"] == "error"
    assert "Failed to read resume" in res["result"]["error"]
    assert not profile_manager.has_profile("test_sess_invalid")

@patch("app.tools.resume_profile_tool._parser.extract_text")
@patch("app.tools.resume_profile_tool._extractor.extract_profile")
def test_resume_tool_extraction_failure(mock_extract_profile, mock_extract_text):
    mock_extract_text.return_value = "Valid text but bad extraction"
    mock_extract_profile.return_value = None # Extractor fails
    
    # Mock the extractor client being present so we hit the generic error
    if True:
        tool = registry.get_tool("extract_and_save_profile")
        res_str = tool(session_id="test_sess_fail", file_path="dummy.pdf")
        res = json.loads(res_str)
        
        assert res["status"] == "success"
        assert res["result"]["status"] == "error"
        assert "Failed to extract" in res["result"]["error"]

@patch("app.tools.resume_profile_tool._parser.extract_text")
@patch("app.tools.resume_profile_tool._extractor.extract_profile")
def test_resume_tool_missing_api_key(mock_extract_profile, mock_extract_text, monkeypatch):
    mock_extract_text.return_value = "Valid text"
    mock_extract_profile.return_value = None
    
    # Force api_key to be empty on the globally instantiated extractor
    import app.tools.resume_profile_tool as rpt
    monkeypatch.setattr(rpt._extractor, "api_key", "")
    
    tool = registry.get_tool("extract_and_save_profile")
    res_str = tool(session_id="test_sess_fail", file_path="dummy.pdf")
    res = json.loads(res_str)
    
    assert res["status"] == "success"
    assert res["result"]["status"] == "error"
    assert "API key is missing" in res["result"]["error"] or "configuration error" in res["result"]["error"].lower()

def test_resume_tool_safety():
    assert registry.requires_confirmation("extract_and_save_profile") is False
