import pytest
from unittest.mock import patch, MagicMock
from app.tools.registry import registry
import app.tools.job_discovery_tool

def get_tool():
    return registry.get_tool("discover_new_jobs")

def test_job_discovery_tool_registered():
    assert get_tool() is not None

@patch("app.tools.job_discovery_tool.discovery_service.run")
def test_job_discovery_tool_execution(mock_run):
    mock_run_result = MagicMock()
    mock_run_result.model_dump.return_value = {
        "status": "completed",
        "new_jobs": 5
    }
    mock_run.return_value = mock_run_result
    
    tool = get_tool()
    res = tool(role="Dev", session_id="test_sess")
    
    # Tool output is a dict
    import json
    res = json.loads(res)
    res = res["result"]
    assert res["status"] == "completed"
    assert res["new_jobs"] == 5
    
    mock_run.assert_called_once_with(
        role="Dev",
        location=None,
        experience=None,
        session_id="test_sess"
    )
