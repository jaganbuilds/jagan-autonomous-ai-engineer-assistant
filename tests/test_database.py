import pytest
from app.job_sources.base import Job
from app.database.connection import get_db_connection, init_db
from app.database.repository import JobRepository
from app.database.models import PersistedJob

def test_db_initialization(mock_db_repository):
    with get_db_connection(mock_db_repository.db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='jobs'")
        assert cursor.fetchone() is not None

def test_save_and_retrieve_job(mock_db_repository):
    job = Job(title="T1", company="C1", location="L1", experience="E1", description="D1", url="U1", source="mock", external_id="ext_1")
    
    status, saved_job = mock_db_repository.save_job(job)
    assert status == "created"
    assert saved_job.db_id is not None
    assert saved_job.job_key is not None
    
    retrieved = mock_db_repository.get_job(saved_job.db_id)
    assert retrieved is not None
    assert retrieved.title == "T1"
    assert retrieved.company == "C1"

def test_duplicate_detection(mock_db_repository):
    job1 = Job(title="T2", company="C2", location="L2", experience="E2", description="D2", url="U2", source="mock", external_id="ext_2")
    job2 = Job(title="T2_updated", company="C2", location="L2", experience="E2", description="D2_updated", url="U2", source="mock", external_id="ext_2")
    
    status1, saved1 = mock_db_repository.save_job(job1)
    assert status1 == "created"
    
    status2, saved2 = mock_db_repository.save_job(job2)
    assert status2 == "updated"
    assert saved1.db_id == saved2.db_id # Same internal ID
    
    # Verify update actually occurred
    retrieved = mock_db_repository.get_job(saved2.db_id)
    assert retrieved.title == "T2_updated"

def test_stable_job_key_generation(mock_db_repository):
    job = Job(title="T3", company="C3", location="L3", experience="E3", description="D3", url="U3", source="mock")
    
    # Without external_id, it hashes source+company+title+location
    key1 = mock_db_repository.generate_job_key(job)
    key2 = mock_db_repository.generate_job_key(job)
    
    assert key1 == key2
    
    job_diff = Job(title="T4", company="C3", location="L3", experience="E3", description="D3", url="U3", source="mock")
    key3 = mock_db_repository.generate_job_key(job_diff)
    
    assert key1 != key3

def test_list_jobs(mock_db_repository):
    jobs = [
        Job(title="Backend Dev", company="C", location="Chennai", experience="E", description="D", url="U", source="S", external_id="1"),
        Job(title="Frontend Dev", company="C", location="Bangalore", experience="E", description="D", url="U", source="S", external_id="2"),
        Job(title="AI Engineer", company="C", location="Chennai", experience="E", description="D", url="U", source="S", external_id="3"),
    ]
    
    mock_db_repository.save_jobs(jobs)
    
    # Test location filter
    chennai_jobs = mock_db_repository.list_jobs(location="chennai")
    assert len(chennai_jobs) == 2
    
    # Test text filter
    ai_jobs = mock_db_repository.list_jobs(search_text="ai engineer")
    assert len(ai_jobs) == 1
    assert ai_jobs[0].title == "AI Engineer"
    
    # Test limit
    all_jobs = mock_db_repository.list_jobs(limit=2)
    assert len(all_jobs) == 2

def test_job_exists(mock_db_repository):
    job = Job(title="E1", company="C", location="L", experience="", description="", url="", source="test", external_id="ext")
    key = mock_db_repository.generate_job_key(job)
    
    assert not mock_db_repository.job_exists(key)
    mock_db_repository.save_job(job)
    assert mock_db_repository.job_exists(key)

def test_discovery_run_lifecycle(mock_db_repository):
    run_id = mock_db_repository.create_discovery_run("Dev", "Remote", "Mid")
    assert run_id > 0
    
    # Complete it
    mock_db_repository.complete_discovery_run(run_id, total_found=5, new_jobs=3, existing_jobs=2, jobs_processed=5, jobs_skipped=0, status="completed")
    
    # Verify in DB
    from app.database.connection import get_db_connection
    with get_db_connection(mock_db_repository.db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM discovery_runs WHERE id = ?", (run_id,))
        row = cursor.fetchone()
        assert row is not None
        assert row["status"] == "completed"
        assert row["new_jobs"] == 3

def test_record_discovery_job(mock_db_repository):
    run_id = mock_db_repository.create_discovery_run("Dev", None, None)
    job = Job(title="T", company="C", location="L", experience="E", description="D", url="U", source="S")
    _, saved_job = mock_db_repository.save_job(job)
    
    mock_db_repository.record_discovery_job(run_id, saved_job.db_id, is_new=True)
    
    from app.database.connection import get_db_connection
    with get_db_connection(mock_db_repository.db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM discovery_run_jobs WHERE discovery_run_id = ? AND job_id = ?", (run_id, saved_job.db_id))
        row = cursor.fetchone()
        assert row is not None
        assert row["is_new"] == 1
