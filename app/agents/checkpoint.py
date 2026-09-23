import json
from typing import Optional, List, Dict, Any
from datetime import datetime, timezone
import uuid
from pydantic import BaseModel, Field

from app.agents.orchestration import AgentPlan, TaskState
from app.database.connection import get_db_connection

CURRENT_SCHEMA_VERSION = "1.0"

class OrchestrationCheckpoint(BaseModel):
    run_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    session_id: str
    owner_id: str = "default_owner"
    goal: str
    plan: AgentPlan
    status: TaskState
    schema_version: str = CURRENT_SCHEMA_VERSION
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

class OrchestrationRepository:
    def create_or_update_checkpoint(self, checkpoint: OrchestrationCheckpoint) -> OrchestrationCheckpoint:
        checkpoint.updated_at = datetime.now(timezone.utc).isoformat()
        
        with get_db_connection() as conn:
            cursor = conn.cursor()
            
            # Serialize the plan to JSON safely
            serialized_plan = checkpoint.plan.model_dump_json()
            
            cursor.execute('''
                INSERT INTO orchestration_checkpoints (
                    run_id, session_id, owner_id, goal, serialized_plan, status, schema_version, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(run_id) DO UPDATE SET
                    serialized_plan=excluded.serialized_plan,
                    status=excluded.status,
                    updated_at=excluded.updated_at
            ''', (
                checkpoint.run_id,
                checkpoint.session_id,
                checkpoint.owner_id,
                checkpoint.goal,
                serialized_plan,
                checkpoint.status.value,
                checkpoint.schema_version,
                checkpoint.created_at,
                checkpoint.updated_at
            ))
            conn.commit()
            return checkpoint

    def get_checkpoint(self, run_id: str) -> Optional[OrchestrationCheckpoint]:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM orchestration_checkpoints WHERE run_id = ?", (run_id,))
            row = cursor.fetchone()
            
            if not row:
                return None
                
            return self._row_to_checkpoint(row)
            
    def get_latest_checkpoint_for_session(self, session_id: str) -> Optional[OrchestrationCheckpoint]:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM orchestration_checkpoints WHERE session_id = ? ORDER BY updated_at DESC LIMIT 1", (session_id,))
            row = cursor.fetchone()
            
            if not row:
                return None
                
            return self._row_to_checkpoint(row)

    def list_checkpoints_for_session(self, session_id: str) -> List[OrchestrationCheckpoint]:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM orchestration_checkpoints WHERE session_id = ? ORDER BY updated_at DESC", (session_id,))
            rows = cursor.fetchall()
            return [self._row_to_checkpoint(row) for row in rows]

    def _row_to_checkpoint(self, row) -> OrchestrationCheckpoint:
        # Load serialized plan
        plan_dict = json.loads(row["serialized_plan"])
        plan = AgentPlan(**plan_dict)
        
        return OrchestrationCheckpoint(
            run_id=row["run_id"],
            session_id=row["session_id"],
            owner_id=row["owner_id"],
            goal=row["goal"],
            plan=plan,
            status=TaskState(row["status"]),
            schema_version=row["schema_version"],
            created_at=row["created_at"],
            updated_at=row["updated_at"]
        )
        
    def delete_checkpoint(self, run_id: str):
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM orchestration_checkpoints WHERE run_id = ?", (run_id,))
            conn.commit()

# Singleton instance
checkpoint_repository = OrchestrationRepository()
