import pytest
from unittest.mock import MagicMock
from app.tools.registry import registry
from app.database.models import ApplicationStatus
from app.job_sources.base import Job

@pytest.fixture
def mock_tracking_service(monkeypatch):
    service_mock = MagicMock()
    monkeypatch.setattr("app.tools.application_tracking_tool.tracking_service", service_mock)
    return service_mock

def test_tool_registration():
    tools = [t.__name__ for t in registry.get_all_tools()]
    assert "create_application_tracking" in tools
    assert "get_application_tracking" in tools
    assert "update_application_status" in tools
    assert "list_application_tracking" in tools

def test_create_application_tracking(mock_tracking_service):
    from app.tools.application_tracking_tool import create_application_tracking
    mock_tracking_service.create_application_record.return_value = {"status": "success", "application_id": 1}

    result = create_application_tracking(session_id="session_1", job_id=1, status="PREPARED")
    assert result["status"] == "success"
    assert result["application_id"] == 1
    mock_tracking_service.create_application_record.assert_called_once_with(
        session_id="session_1",
        job_id=1,
        status=ApplicationStatus.PREPARED,
        notes=None,
        next_action=None,
        follow_up_at=None
    )

def test_create_application_tracking_invalid_status():
    from app.tools.application_tracking_tool import create_application_tracking
    result = create_application_tracking(session_id="session_1", job_id=1, status="INVALID")
    assert result["status"] == "error"
    assert "Invalid status" in result["message"]

def test_get_application_tracking(mock_tracking_service):
    from app.tools.application_tracking_tool import get_application_tracking
    fake_record = MagicMock()
    fake_record.model_dump.return_value = {"id": 1, "status": "PREPARED"}
    mock_tracking_service.get_application_record.return_value = {"status": "success", "data": fake_record}

    result = get_application_tracking(session_id="session_1", application_id=1)
    assert result["status"] == "success"
    assert result["data"]["id"] == 1
    mock_tracking_service.get_application_record.assert_called_once_with(session_id="session_1", application_id=1)

def test_update_application_status(mock_tracking_service):
    from app.tools.application_tracking_tool import update_application_status
    mock_tracking_service.update_application_status.return_value = {"status": "success"}

    result = update_application_status(session_id="session_1", application_id=1, status="APPLIED")
    assert result["status"] == "success"
    mock_tracking_service.update_application_status.assert_called_once_with(
        session_id="session_1",
        application_id=1,
        new_status=ApplicationStatus.APPLIED
    )

def test_list_application_tracking(mock_tracking_service):
    from app.tools.application_tracking_tool import list_application_tracking
    fake_record = MagicMock()
    fake_record.model_dump.return_value = {"id": 1}
    mock_tracking_service.list_applications.return_value = {"status": "success", "count": 1, "data": [fake_record]}

    result = list_application_tracking(session_id="session_1", status="PREPARED")
    assert result["status"] == "success"
    assert result["data"] == [{"id": 1}]
    mock_tracking_service.list_applications.assert_called_once_with(
        session_id="session_1",
        status=ApplicationStatus.PREPARED
    )
    
def test_tool_confirmation_metadata():
    assert registry.requires_confirmation("create_application_tracking") is False
    assert registry.requires_confirmation("get_application_tracking") is False
    assert registry.requires_confirmation("update_application_status") is False
    assert registry.requires_confirmation("list_application_tracking") is False

def test_tool_invalid_job_id(mock_db_repository, monkeypatch):
    # Integration style test for invalid job
    from app.tools.application_tracking_tool import create_application_tracking
    mock_db_repository.get_job = MagicMock(return_value=None)
    
    result = create_application_tracking(session_id="session_test", job_id=999)
    assert result["status"] == "error"
    assert "not found" in result["message"]

def test_tool_invalid_application_id_or_session(mock_db_repository, monkeypatch):
    # Integration style test for getting invalid app
    from app.tools.application_tracking_tool import get_application_tracking
    mock_db_repository.get_application = MagicMock(return_value=None)
    
    result = get_application_tracking(session_id="session_test", application_id=999)
    assert result["status"] == "error"
    assert "not found" in result["message"]

