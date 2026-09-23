import pytest
from unittest.mock import MagicMock
from app.application_tracking.service import ApplicationTrackingService
from app.database.models import ApplicationStatus, JobApplication

@pytest.fixture
def tracking_service(mock_db_repository):
    return ApplicationTrackingService(job_repository=mock_db_repository)

def test_create_tracking_record_valid_job(tracking_service, mock_db_repository):
    # Mocking the repository methods
    mock_db_repository.get_job = MagicMock(return_value={"id": 1, "title": "Test Job"})
    mock_db_repository.create_application = MagicMock(return_value=123)

    result = tracking_service.create_application_record(
        session_id="session_1",
        job_id=1,
        status=ApplicationStatus.PREPARED
    )
    
    assert result["status"] == "success"
    assert result["application_id"] == 123
    mock_db_repository.create_application.assert_called_once_with(
        job_id=1,
        session_id="session_1",
        status="PREPARED",
        notes=None,
        next_action=None,
        follow_up_at=None
    )

def test_create_tracking_record_invalid_job(tracking_service, mock_db_repository):
    mock_db_repository.get_job = MagicMock(return_value=None)
    mock_db_repository.create_application = MagicMock()

    result = tracking_service.create_application_record(
        session_id="session_1",
        job_id=999
    )
    
    assert result["status"] == "error"
    assert "not found" in result["message"]
    mock_db_repository.create_application.assert_not_called()

def test_get_application_record_success(tracking_service, mock_db_repository):
    fake_app = JobApplication(
        id=1,
        job_id=2,
        session_id="sess_1",
        status=ApplicationStatus.APPLIED,
        created_at="time",
        updated_at="time"
    )
    mock_db_repository.get_application = MagicMock(return_value=fake_app)

    result = tracking_service.get_application_record(session_id="sess_1", application_id=1)
    
    assert result["status"] == "success"
    assert result["data"] == fake_app
    mock_db_repository.get_application.assert_called_once_with(
        application_id=1,
        session_id="sess_1"
    )

def test_get_application_record_wrong_session(tracking_service, mock_db_repository):
    # Simulates DB returning None because session_id didn't match
    mock_db_repository.get_application = MagicMock(return_value=None)

    result = tracking_service.get_application_record(session_id="sess_2", application_id=1)
    
    assert result["status"] == "error"
    assert "not found" in result["message"]

def test_update_application_status_success(tracking_service, mock_db_repository):
    fake_app = JobApplication(
        id=1,
        job_id=2,
        session_id="sess_1",
        status=ApplicationStatus.PREPARED,
        created_at="time",
        updated_at="time"
    )
    mock_db_repository.get_application = MagicMock(return_value=fake_app)
    mock_db_repository.update_application_status = MagicMock(return_value=True)

    result = tracking_service.update_application_status(
        session_id="sess_1",
        application_id=1,
        new_status=ApplicationStatus.UNDER_REVIEW
    )
    
    assert result["status"] == "success"
    mock_db_repository.update_application_status.assert_called_once_with(
        application_id=1,
        status="UNDER_REVIEW",
        session_id="sess_1"
    )

def test_update_application_status_wrong_session(tracking_service, mock_db_repository):
    mock_db_repository.get_application = MagicMock(return_value=None)
    mock_db_repository.update_application_status = MagicMock()

    result = tracking_service.update_application_status(
        session_id="sess_2",
        application_id=1,
        new_status=ApplicationStatus.UNDER_REVIEW
    )
    
    assert result["status"] == "error"
    mock_db_repository.update_application_status.assert_not_called()

def test_list_applications(tracking_service, mock_db_repository):
    mock_db_repository.list_applications = MagicMock(return_value=[1, 2, 3])

    result = tracking_service.list_applications(session_id="sess_1", status=ApplicationStatus.INTERVIEW)
    
    assert result["status"] == "success"
    assert result["count"] == 3
    assert result["data"] == [1, 2, 3]
    mock_db_repository.list_applications.assert_called_once_with(
        session_id="sess_1",
        status="INTERVIEW"
    )
