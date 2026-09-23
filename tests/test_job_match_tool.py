import pytest
import json
from app.tools.registry import registry
import app.tools.job_match_tool # Ensure registered

def get_tool():
    return registry.get_tool("match_job_to_candidate")

def test_job_match_tool_registered():
    tool = get_tool()
    assert tool is not None
    
    # Matching is a safe, read-only operation and doesn't require confirmation
    req_conf = registry.requires_confirmation("match_job_to_candidate")
    assert req_conf is False

def test_job_match_tool_execution():
    tool = get_tool()
    
    # Pass all required kwargs that represent a Job
    res_str = tool(
        title="Python API Developer",
        company="TechCorp",
        description="Looking for an experienced Python developer familiar with FastAPI and PostgreSQL.",
        location="Remote",
        experience="Senior"
    )
    
    res = json.loads(res_str)
    assert res["status"] == "success"
    
    result = res["result"]
    assert "Python" in result["matched_skills"]
    assert "FastAPI" in result["matching_frameworks"]
    assert result["location_match"] == "Matched"

def test_job_match_tool_missing_skills():
    tool = get_tool()
    
    res_str = tool(
        title="Full Stack Java",
        company="EnterpriseInc",
        description="Must have Java, Spring, Docker, and Kubernetes experience.",
        location="Remote"
    )
    
    res = json.loads(res_str)
    assert res["status"] == "success"
    
    result = res["result"]
    assert "java" in result["missing_skills"]
    assert "docker" in result["missing_skills"]
    assert "kubernetes" in result["missing_skills"]
    
def test_job_match_tool_no_match():
    tool = get_tool()
    
    res_str = tool(
        title="Physical Trainer",
        company="Gym",
        description="Need fitness experience.",
        location="Mars"
    )
    
    res = json.loads(res_str)
    assert res["status"] == "success"
    
    result = res["result"]
    assert len(result["matched_skills"]) == 0
    assert result["location_match"] == "Not Matched"
