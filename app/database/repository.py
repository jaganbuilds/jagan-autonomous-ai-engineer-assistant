import hashlib
import sqlite3
from typing import List, Optional, Tuple
from app.job_sources.base import Job
from app.database.connection import get_db_connection
from app.database.models import PersistedJob

class JobRepository:
    """Handles persistent storage of jobs in SQLite."""
    
    def __init__(self, db_path: str):
        self.db_path = db_path
        
    def generate_job_key(self, job: Job) -> str:
        """
        Generates a stable, deterministic key for deduplication.
        If external_id exists, we use: source + external_id.
        Otherwise, we hash normalized title + company + location.
        """
        if job.external_id:
            raw_key = f"{job.source}::{job.external_id}"
        else:
            # Fallback deterministic hash
            norm_title = job.title.strip().lower()
            norm_company = job.company.strip().lower()
            norm_location = job.location.strip().lower() if job.location else ""
            raw_key = f"{job.source}::{norm_company}::{norm_title}::{norm_location}"
            
        return hashlib.sha256(raw_key.encode('utf-8')).hexdigest()

    def save_job(self, job: Job) -> Tuple[str, Job]:
        """
        Saves a single job, handling deduplication.
        Returns a tuple: (status, job)
        status is one of: "created", "already_exists", "updated"
        """
        job_key = self.generate_job_key(job)
        job.job_key = job_key
        
        with get_db_connection(self.db_path) as conn:
            cursor = conn.cursor()
            
            # Check if job exists
            cursor.execute('SELECT id, discovered_at FROM jobs WHERE job_key = ?', (job_key,))
            existing_row = cursor.fetchone()
            
            if existing_row:
                # Update existing job (could update description, URL, etc.)
                cursor.execute('''
                    UPDATE jobs 
                    SET title = ?, company = ?, location = ?, experience = ?, 
                        description = ?, url = ?, source = ?, external_id = ?,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE job_key = ?
                ''', (
                    job.title, job.company, job.location, job.experience,
                    job.description, job.url, job.source, job.external_id,
                    job_key
                ))
                conn.commit()
                
                job.db_id = existing_row['id']
                job.discovered_at = existing_row['discovered_at']
                return ("updated", job)
                
            else:
                # Insert new job
                cursor.execute('''
                    INSERT INTO jobs (
                        job_key, external_id, source, title, company, location, experience, description, url
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    job_key, job.external_id, job.source, job.title, job.company,
                    job.location, job.experience, job.description, job.url
                ))
                conn.commit()
                
                job.db_id = cursor.lastrowid
                return ("created", job)
                
    def save_jobs(self, jobs: List[Job]) -> List[Tuple[str, Job]]:
        """Saves a batch of jobs and returns their deduplication statuses."""
        return [self.save_job(j) for j in jobs]
        
    def get_job(self, db_id: int) -> Optional[PersistedJob]:
        with get_db_connection(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM jobs WHERE id = ?', (db_id,))
            row = cursor.fetchone()
            if row:
                return PersistedJob(**dict(row))
        return None
        
    def get_job_by_key(self, job_key: str) -> Optional[PersistedJob]:
        with get_db_connection(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM jobs WHERE job_key = ?', (job_key,))
            row = cursor.fetchone()
            if row:
                return PersistedJob(**dict(row))
        return None
        
    def list_jobs(self, limit: int = 50, location: Optional[str] = None, source: Optional[str] = None, search_text: Optional[str] = None) -> List[PersistedJob]:
        query = 'SELECT * FROM jobs WHERE 1=1'
        params = []
        
        if location:
            query += ' AND LOWER(location) LIKE ?'
            params.append(f"%{location.lower()}%")
            
        if source:
            query += ' AND source = ?'
            params.append(source)
            
        if search_text:
            query += ' AND (LOWER(title) LIKE ? OR LOWER(description) LIKE ? OR LOWER(company) LIKE ?)'
            search_param = f"%{search_text.lower()}%"
            params.extend([search_param, search_param, search_param])
            
        query += ' ORDER BY discovered_at DESC LIMIT ?'
        params.append(limit)
        
        results = []
        with get_db_connection(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(query, tuple(params))
            for row in cursor.fetchall():
                results.append(PersistedJob(**dict(row)))
                
        return results

    def job_exists(self, job_key: str) -> bool:
        """Quick check if a job exists in the database by job_key."""
        with get_db_connection(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT 1 FROM jobs WHERE job_key = ?', (job_key,))
            return cursor.fetchone() is not None

    def create_discovery_run(self, role: Optional[str], location: Optional[str], experience: Optional[str]) -> int:
        """Creates a new discovery run record and returns its ID."""
        with get_db_connection(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO discovery_runs (role, location, experience, status)
                VALUES (?, ?, ?, 'running')
            ''', (role, location, experience))
            conn.commit()
            return cursor.lastrowid

    def complete_discovery_run(self, run_id: int, total_found: int, new_jobs: int, existing_jobs: int, jobs_processed: int, jobs_skipped: int, status: str):
        """Marks a discovery run as completed and updates its statistics."""
        with get_db_connection(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                UPDATE discovery_runs
                SET completed_at = CURRENT_TIMESTAMP,
                    total_found = ?,
                    new_jobs = ?,
                    existing_jobs = ?,
                    jobs_processed = ?,
                    jobs_skipped = ?,
                    status = ?
                WHERE id = ?
            ''', (total_found, new_jobs, existing_jobs, jobs_processed, jobs_skipped, status, run_id))
            conn.commit()

    def record_discovery_job(self, run_id: int, job_id: int, is_new: bool):
        """Records the relationship between a discovery run and a job."""
        with get_db_connection(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT OR IGNORE INTO discovery_run_jobs (discovery_run_id, job_id, is_new)
                VALUES (?, ?, ?)
            ''', (run_id, job_id, is_new))
            conn.commit()


    def get_discovery_run(self, run_id: int):
        from app.database.models import DiscoveryRun
        with get_db_connection(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM discovery_runs WHERE id = ?', (run_id,))
            row = cursor.fetchone()
            if row:
                return DiscoveryRun(**dict(row))
        return None

    def list_discovery_run_jobs(self, run_id: int, new_only: bool = True):
        from app.database.models import DiscoveryRunJob
        with get_db_connection(self.db_path) as conn:
            cursor = conn.cursor()
            query = 'SELECT * FROM discovery_run_jobs WHERE discovery_run_id = ?'
            params = [run_id]
            if new_only:
                query += ' AND is_new = 1'
            cursor.execute(query, tuple(params))
            results = []
            for row in cursor.fetchall():
                results.append(DiscoveryRunJob(**dict(row)))
            return results

    def get_jobs_by_ids(self, job_ids: List[int]) -> List[PersistedJob]:
        if not job_ids:
            return []
        
        with get_db_connection(self.db_path) as conn:
            cursor = conn.cursor()
            placeholders = ','.join('?' for _ in job_ids)
            query = f'SELECT * FROM jobs WHERE id IN ({placeholders})'
            cursor.execute(query, tuple(job_ids))
            
            results = []
            for row in cursor.fetchall():
                results.append(PersistedJob(**dict(row)))
            return results


    def create_application(self, job_id: int, session_id: str, status: str = "PREPARED", notes: Optional[str] = None, next_action: Optional[str] = None, follow_up_at: Optional[str] = None) -> int:
        with get_db_connection(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO applications (job_id, session_id, status, notes, next_action, follow_up_at)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (job_id, session_id, status, notes, next_action, follow_up_at))
            conn.commit()
            return cursor.lastrowid

    def get_application(self, application_id: int, session_id: Optional[str] = None):
        from app.database.models import JobApplication
        with get_db_connection(self.db_path) as conn:
            cursor = conn.cursor()
            query = 'SELECT * FROM applications WHERE id = ?'
            params = [application_id]
            if session_id:
                query += ' AND session_id = ?'
                params.append(session_id)
            cursor.execute(query, tuple(params))
            row = cursor.fetchone()
            if row:
                return JobApplication(**dict(row))
            return None

    def update_application_status(self, application_id: int, status: str, session_id: Optional[str] = None) -> bool:
        with get_db_connection(self.db_path) as conn:
            cursor = conn.cursor()
            query = 'UPDATE applications SET status = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?'
            params = [status, application_id]
            if session_id:
                query += ' AND session_id = ?'
                params.append(session_id)
            cursor.execute(query, tuple(params))
            conn.commit()
            return cursor.rowcount > 0

    def list_applications(self, session_id: Optional[str] = None, status: Optional[str] = None):
        from app.database.models import JobApplication
        with get_db_connection(self.db_path) as conn:
            cursor = conn.cursor()
            query = 'SELECT * FROM applications WHERE 1=1'
            params = []
            if session_id:
                query += ' AND session_id = ?'
                params.append(session_id)
            if status:
                query += ' AND status = ?'
                params.append(status)
            cursor.execute(query, tuple(params))
            results = []
            for row in cursor.fetchall():
                results.append(JobApplication(**dict(row)))
            return results

_repository_instance = None
from app.database.connection import DEFAULT_DB_PATH, init_db

def get_job_repository(db_path: str = DEFAULT_DB_PATH):
    global _repository_instance
    if _repository_instance is None:
        init_db(db_path)
        _repository_instance = JobRepository(db_path)
    return _repository_instance

# Default global accessor
def set_job_repository_for_testing(repo):
    global _repository_instance
    _repository_instance = repo
