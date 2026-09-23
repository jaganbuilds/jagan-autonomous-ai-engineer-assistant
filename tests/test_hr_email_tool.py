import pytest
import json
from unittest.mock import MagicMock, patch
from app.tools.registry import registry
from app.agents.state import state_manager
from app.profile.manager import profile_manager
from app.profile.models import CandidateProfile
from app.job_sources.base import Job
from app.workflows.models import JobMatchPair
import app.tools.hr_email_tool

@pytest.fixture
def dummy_profile():
    return CandidateProfile(
        name="Email User",
        experience_level="Mid",
        education="BS",
        skills=["Python"],
        target_roles=[],
        preferred_locations=[],
        programming_languages=[],
        frameworks=[],
        databases=[],
        ai_ml_technologies=[],
        projects=[]
    )

@pytest.fixture
def dummy_job_pair():
    job = Job(title="Dev", company="Corp", description="Desc", location="R", experience="Mid", url="")
    return JobMatchPair(job=job)

@patch("app.tools.hr_email_tool.get_settings")
@patch("app.llm_client.get_llm_client_or_raise")
def test_hr_email_tool_success(mock_client, mock_settings, dummy_profile, dummy_job_pair):
    mock_settings.return_value.gemini_api_key = "fake_key"
    
    session_id = "test_email_success"
    state_manager.clear_session(session_id)
    profile_manager.delete_profile(session_id)
    
    profile_manager.save_profile(session_id, dummy_profile)
    state_manager.store_job_results(session_id, [dummy_job_pair])
    
    mock_response = MagicMock()
    mock_response.text = '{"subject": "Application", "body": "Hi there.", "recipient": null, "job_id": "job_1"}'
    mock_client.return_value.models.generate_content.return_value = mock_response
    
    tool = registry.get_tool("draft_hr_email")
    res_str = tool(session_id=session_id, job_reference="job_1")
    res = json.loads(res_str)
    
    assert res["status"] == "success"
    result = res["result"]
    assert result["status"] == "success"
    assert result["draft"]["body"] == "Hi there."
    
    # Check strict prompt rules
    call_args = mock_client.return_value.models.generate_content.call_args[1]["contents"]
    assert "DO NOT invent or hallucinate" in call_args
    assert "Email User" in call_args

def test_hr_email_tool_no_jobs_in_session():
    session_id = "test_email_no_jobs"
    state_manager.clear_session(session_id)
    
    tool = registry.get_tool("draft_hr_email")
    res_str = tool(session_id=session_id, job_reference="job_1")
    res = json.loads(res_str)
    
    assert res["result"]["status"] == "no_jobs_in_session"

def test_hr_email_tool_job_not_found(dummy_job_pair):
    session_id = "test_email_not_found"
    state_manager.clear_session(session_id)
    state_manager.store_job_results(session_id, [dummy_job_pair])
    
    tool = registry.get_tool("draft_hr_email")
    res_str = tool(session_id=session_id, job_reference="job_99")
    res = json.loads(res_str)
    
    assert res["result"]["status"] == "job_not_found"

def test_hr_email_tool_profile_required(dummy_job_pair):
    session_id = "test_email_no_profile"
    state_manager.clear_session(session_id)
    profile_manager.delete_profile(session_id)
    
    state_manager.store_job_results(session_id, [dummy_job_pair])
    
    tool = registry.get_tool("draft_hr_email")
    res_str = tool(session_id=session_id, job_reference="job_1")
    res = json.loads(res_str)
    
    assert res["result"]["status"] == "profile_required"

@patch("app.tools.hr_email_tool.get_settings")
def test_hr_email_tool_missing_api_key(mock_settings, dummy_job_pair, dummy_profile):
    mock_settings.return_value.gemini_api_key = None
    session_id = "test_email_no_key"
    
    state_manager.store_job_results(session_id, [dummy_job_pair])
    profile_manager.save_profile(session_id, dummy_profile)
    
    tool = registry.get_tool("draft_hr_email")
    res_str = tool(session_id=session_id, job_reference="job_1")
    res = json.loads(res_str)
    
    assert res["result"]["status"] == "error"
    assert "Gemini API key is required" in res["result"]["message"]
