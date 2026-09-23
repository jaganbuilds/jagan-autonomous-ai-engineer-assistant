import pytest
import json
from unittest.mock import MagicMock, patch

from app.tools.registry import registry
from app.agents.state import state_manager
from app.job_sources.base import Job
from app.matching.models import MatchResult, SemanticMatchResult
from app.workflows.models import JobMatchPair
import app.tools.get_job_details_tool # Ensure registered

@pytest.fixture
def dummy_job_pair():
    job = Job(title="Python Dev", company="TechCorp", description="Desc", location="Remote", experience="Mid", url="")
    match_result = MatchResult(
        matched_skills=["Python"],
        missing_skills=["Docker"],
        location_match="Matched",
        experience_match="Matched",
        education_match="Matched",
        explanation="Exactly matched 1 core skills."
    )
    return JobMatchPair(job=job, match_result=match_result)

def test_get_job_details_success(dummy_job_pair):
    session_id = "test_get_job_success"
    state_manager.clear_session(session_id)
    
    # Store job
    state_manager.store_job_results(session_id, [dummy_job_pair])
    
    tool = registry.get_tool("get_job_details")
    res_str = tool(session_id=session_id, job_reference="job_1")
    res = json.loads(res_str)
    
    assert res["status"] == "success"
    assert res["result"]["status"] == "success"
    assert res["result"]["job_details"]["job"]["title"] == "Python Dev"

def test_get_job_details_natural_reference(dummy_job_pair):
    session_id = "test_get_job_natural"
    state_manager.clear_session(session_id)
    
    state_manager.store_job_results(session_id, [dummy_job_pair, dummy_job_pair])
    
    tool = registry.get_tool("get_job_details")
    
    # "1" -> "job_1"
    res_str = tool(session_id=session_id, job_reference="1")
    res = json.loads(res_str)
    assert res["result"]["status"] == "success"
    
    # "job 2" -> "job_2"
    res_str2 = tool(session_id=session_id, job_reference="job 2")
    res2 = json.loads(res_str2)
    assert res2["result"]["status"] == "success"

def test_get_job_details_not_found(dummy_job_pair):
    session_id = "test_get_job_not_found"
    state_manager.clear_session(session_id)
    state_manager.store_job_results(session_id, [dummy_job_pair])
    
    tool = registry.get_tool("get_job_details")
    res_str = tool(session_id=session_id, job_reference="job_99")
    res = json.loads(res_str)
    
    assert res["result"]["status"] == "job_not_found"
    assert "Could not find" in res["result"]["message"]

def test_get_job_details_no_jobs_in_session():
    session_id = "test_get_job_empty"
    state_manager.clear_session(session_id)
    
    tool = registry.get_tool("get_job_details")
    res_str = tool(session_id=session_id, job_reference="job_1")
    res = json.loads(res_str)
    
    assert res["result"]["status"] == "no_jobs_in_session"

def test_get_job_details_session_isolation(dummy_job_pair):
    session_a = "test_sess_a"
    session_b = "test_sess_b"
    state_manager.clear_session(session_a)
    state_manager.clear_session(session_b)
    
    state_manager.store_job_results(session_a, [dummy_job_pair])
    
    tool = registry.get_tool("get_job_details")
    
    # Session A can access
    res_a = json.loads(tool(session_id=session_a, job_reference="job_1"))
    assert res_a["result"]["status"] == "success"
    
    # Session B cannot access Session A's jobs
    res_b = json.loads(tool(session_id=session_b, job_reference="job_1"))
    assert res_b["result"]["status"] == "no_jobs_in_session"
