import pytest
import json
from app.tools.registry import registry
import app.tools.job_search_tool 
from app.job_sources.mock_source import MockJobSource

# Force mock source for deterministic tool tests regardless of import order
import os
os.environ['USE_MOCK_JOBS'] = 'True'

def get_tool():
    return registry.get_tool("search_jobs")

def test_job_search_tool_registered():
    assert get_tool() is not None

def test_job_search_no_filters():
    tool = get_tool()
    res = json.loads(tool())
    assert res["status"] == "success"
    # The mock DB currently has 4 jobs
    assert len(res["result"]) == 4

def test_job_search_role_filter():
    tool = get_tool()
    # 'AI' should match AI Engineer Fresher
    res = json.loads(tool(role="AI"))
    assert res["status"] == "success"
    assert len(res["result"]) >= 1
    assert "AI Engineer Fresher" in [job["title"] for job in res["result"]]
    
    # 'GenAI' should match GenAI Developer
    res2 = json.loads(tool(role="GenAI"))
    assert len(res2["result"]) >= 1

def test_job_search_location_filter():
    tool = get_tool()
    res = json.loads(tool(location="Chennai"))
    assert res["status"] == "success"
    # We have 2 jobs in Chennai
    assert len(res["result"]) == 2
    for job in res["result"]:
        assert "Chennai" in job["location"]

def test_job_search_experience_filter():
    tool = get_tool()
    # Test fresher logic
    res = json.loads(tool(experience="fresher"))
    assert res["status"] == "success"
    assert len(res["result"]) >= 1
    
    res2 = json.loads(tool(experience="5+ years"))
    assert len(res2["result"]) == 1
    assert res2["result"][0]["title"] == "Senior ML Engineer"

def test_job_search_combined_filters():
    tool = get_tool()
    res = json.loads(tool(role="Developer", location="Remote"))
    assert res["status"] == "success"
    assert len(res["result"]) == 1
    assert res["result"][0]["title"] == "Python Backend Developer"

def test_job_search_no_matches():
    tool = get_tool()
    res = json.loads(tool(role="Astronaut", location="Mars"))
    assert res["status"] == "success"
    assert len(res["result"]) == 0

def test_job_search_result_structure():
    tool = get_tool()
    res = json.loads(tool(role="AI Engineer"))
    assert res["status"] == "success"
    job = res["result"][0]
    
    expected_keys = {"title", "company", "location", "experience", "description", "url"}
    assert expected_keys.issubset(job.keys())
    assert isinstance(job["title"], str)
