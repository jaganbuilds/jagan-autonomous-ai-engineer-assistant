import sqlite3
import os
import contextlib
from typing import Generator

DEFAULT_DB_PATH = os.path.join(os.getcwd(), 'data', 'jagan_ai.db')

def init_db(db_path: str = DEFAULT_DB_PATH):
    """Initializes the database and creates the jobs table if it doesn't exist."""
    db_dir = os.path.dirname(db_path)
    if db_dir and not os.path.exists(db_dir):
        os.makedirs(db_dir, exist_ok=True)

    with sqlite3.connect(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS jobs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                job_key TEXT UNIQUE NOT NULL,
                external_id TEXT,
                source TEXT NOT NULL,
                title TEXT NOT NULL,
                company TEXT NOT NULL,
                location TEXT,
                experience TEXT,
                description TEXT,
                url TEXT,
                discovered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Create indexes for efficient querying
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_job_key ON jobs(job_key)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_source ON jobs(source)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_location ON jobs(location)')
        
        # Discovery run tables
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS discovery_runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                role TEXT,
                location TEXT,
                experience TEXT,
                started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                completed_at TIMESTAMP,
                total_found INTEGER DEFAULT 0,
                new_jobs INTEGER DEFAULT 0,
                existing_jobs INTEGER DEFAULT 0,
                jobs_processed INTEGER DEFAULT 0,
                jobs_skipped INTEGER DEFAULT 0,
                status TEXT NOT NULL
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS discovery_run_jobs (
                discovery_run_id INTEGER NOT NULL,
                job_id INTEGER NOT NULL,
                is_new BOOLEAN NOT NULL,
                FOREIGN KEY (discovery_run_id) REFERENCES discovery_runs(id),
                FOREIGN KEY (job_id) REFERENCES jobs(id),
                PRIMARY KEY (discovery_run_id, job_id)
            )
        ''')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS applications (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                job_id INTEGER NOT NULL,
                session_id TEXT NOT NULL,
                status TEXT NOT NULL,
                applied_at TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                notes TEXT,
                next_action TEXT,
                follow_up_at TIMESTAMP,
                FOREIGN KEY (job_id) REFERENCES jobs(id)
            )
        ''')

        cursor.execute('CREATE INDEX IF NOT EXISTS idx_application_session ON applications(session_id)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_application_job ON applications(job_id)')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS orchestration_checkpoints (
                run_id TEXT PRIMARY KEY,
                session_id TEXT NOT NULL,
                owner_id TEXT NOT NULL DEFAULT 'default_owner',
                goal TEXT NOT NULL,
                serialized_plan TEXT NOT NULL,
                status TEXT NOT NULL,
                schema_version TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        try:
            cursor.execute("ALTER TABLE orchestration_checkpoints ADD COLUMN owner_id TEXT NOT NULL DEFAULT 'default_owner'")
        except sqlite3.OperationalError:
            pass # Column already exists
            
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_orch_session ON orchestration_checkpoints(session_id)')

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS memories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                memory_type TEXT NOT NULL,
                content TEXT NOT NULL,
                source TEXT NOT NULL,
                confidence REAL,
                owner_id TEXT NOT NULL DEFAULT 'default_owner',
                scope TEXT NOT NULL DEFAULT 'session',
                importance TEXT NOT NULL DEFAULT 'normal',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        # Migration for existing memories table
        cursor.execute("PRAGMA table_info(memories)")
        columns = [col[1] for col in cursor.fetchall()]
        if 'owner_id' not in columns:
            cursor.execute("ALTER TABLE memories ADD COLUMN owner_id TEXT NOT NULL DEFAULT 'default_owner'")
        if 'scope' not in columns:
            cursor.execute("ALTER TABLE memories ADD COLUMN scope TEXT NOT NULL DEFAULT 'session'")
        if 'importance' not in columns:
            cursor.execute("ALTER TABLE memories ADD COLUMN importance TEXT NOT NULL DEFAULT 'normal'")

        cursor.execute('CREATE INDEX IF NOT EXISTS idx_memories_session ON memories(session_id)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_memories_type ON memories(memory_type)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_memories_owner_scope ON memories(owner_id, scope)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_memories_importance ON memories(importance)')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS actions (
                action_id TEXT PRIMARY KEY,
                session_id TEXT NOT NULL,
                owner_id TEXT NOT NULL,
                integration_name TEXT NOT NULL,
                action_type TEXT NOT NULL,
                risk_level TEXT NOT NULL,
                status TEXT NOT NULL,
                request_payload TEXT,
                result_payload TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                confirmed_at TIMESTAMP,
                completed_at TIMESTAMP
            )
        ''')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_actions_session_owner ON actions(session_id, owner_id)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_actions_status ON actions(status)')
        
        conn.commit()

@contextlib.contextmanager
def get_db_connection(db_path: str = DEFAULT_DB_PATH) -> Generator[sqlite3.Connection, None, None]:
    """Context manager for obtaining a database connection."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row # Allows accessing columns by name
    try:
        yield conn
    finally:
        conn.close()
