import pytest
from app.database.models import ApplicationStatus
from app.job_sources.base import Job

def test_create_application(mock_db_repository):
    job = Job(title="E1", company="C", location="L", experience="", description="", url="", source="test", external_id="ext")
    _, saved_job = mock_db_repository.save_job(job)
    
    app_id = mock_db_repository.create_application(saved_job.db_id, "session_test", ApplicationStatus.PREPARED)
    assert app_id > 0
    
    app = mock_db_repository.get_application(app_id)
    assert app is not None
    assert app.job_id == saved_job.db_id
    assert app.session_id == "session_test"
    assert app.status == ApplicationStatus.PREPARED

def test_update_application_status(mock_db_repository):
    job = Job(title="E2", company="C", location="L", experience="", description="", url="", source="test", external_id="ext2")
    _, saved_job = mock_db_repository.save_job(job)
    
    app_id = mock_db_repository.create_application(saved_job.db_id, "session_update", ApplicationStatus.PREPARED)
    
    success = mock_db_repository.update_application_status(app_id, ApplicationStatus.APPLIED, "session_update")
    assert success is True
    
    app = mock_db_repository.get_application(app_id)
    assert app.status == ApplicationStatus.APPLIED

def test_session_isolation(mock_db_repository):
    job = Job(title="E3", company="C", location="L", experience="", description="", url="", source="test", external_id="ext3")
    _, saved_job = mock_db_repository.save_job(job)
    
    app_id = mock_db_repository.create_application(saved_job.db_id, "session_A", ApplicationStatus.PREPARED)
    
    # Should not be able to retrieve it using session_B
    app_b = mock_db_repository.get_application(app_id, "session_B")
    assert app_b is None
    
    # Should not be able to update it using session_B
    success = mock_db_repository.update_application_status(app_id, ApplicationStatus.REJECTED, "session_B")
    assert success is False
    
    # Verify it was not updated
    app_a = mock_db_repository.get_application(app_id, "session_A")
    assert app_a.status == ApplicationStatus.PREPARED

def test_missing_job_handling(mock_db_repository):
    # Depending on sqlite PRAGMA foreign_keys, this might fail or not.
    # We just ensure it behaves deterministically (often sqlite in memory ignores FK by default unless enabled).
    # If it ignores, it saves. We'll just verify the DB repo handles standard execution.
    app_id = mock_db_repository.create_application(9999, "session_missing", ApplicationStatus.PREPARED)
    assert app_id > 0
    app = mock_db_repository.get_application(app_id)
    assert app.job_id == 9999
