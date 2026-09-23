import pytest
from unittest.mock import patch, MagicMock
from app.tools.registry import registry
import app.tools.job_digest_tool

def get_tool():
    return registry.get_tool("get_new_job_digest")

def test_job_digest_tool_registered():
    assert get_tool() is not None

@patch("app.tools.job_digest_tool.digest_service.get_digest")
def test_job_digest_tool_execution(mock_get_digest):
    mock_result = MagicMock()
    mock_result.model_dump.return_value = {
        "status": "success",
        "total_new_jobs": 2
    }
    mock_get_digest.return_value = mock_result
    
    tool = get_tool()
    res = tool(discovery_run_id=1, session_id="sess")
    
    import json
    res = json.loads(res)
    res = res["result"]
    
    assert res["status"] == "success"
    assert res["total_new_jobs"] == 2
    
    mock_get_digest.assert_called_once_with(
        discovery_run_id=1,
        session_id="sess"
    )
