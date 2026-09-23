from enum import Enum
from typing import Dict, Any, List
from pydantic import BaseModel, Field
from app.workflows.models import JobMatchPair

class SessionStatus(str, Enum):
    IDLE = "idle"
    PROCESSING = "processing"
    WAITING_FOR_CONFIRMATION = "waiting_for_confirmation"
    COMPLETED = "completed"
    ERROR = "error"
    CANCELLED = "cancelled"

class SessionState(BaseModel):
    session_id: str
    status: SessionStatus = SessionStatus.IDLE
    pending_tool_call: Dict[str, Any] | None = None
    pending_email_action: Dict[str, Any] | None = None
    pending_consolidation_action: Dict[str, Any] | None = None
    pending_maintenance_action: Dict[str, Any] | None = None
    pending_gateway_action: Dict[str, Any] | None = None
    history: List[Dict[str, Any]] = Field(default_factory=list)
    job_results: Dict[str, JobMatchPair] = Field(default_factory=dict)

class StateManager:
    """
    In-memory state management for sessions and tasks.
    In a production system, this could be backed by Redis or a database.
    """
    def __init__(self):
        self._sessions: Dict[str, SessionState] = {}

    def get_session(self, session_id: str) -> SessionState:
        """Retrieves a session or creates a new one if it doesn't exist."""
        if session_id not in self._sessions:
            self._sessions[session_id] = SessionState(session_id=session_id)
        return self._sessions[session_id]

    def update_status(self, session_id: str, status: SessionStatus):
        """Updates the status of a specific session."""
        session = self.get_session(session_id)
        session.status = status

    def set_pending_tool(self, session_id: str, tool_name: str, tool_args: Dict[str, Any]):
        """Sets a tool call that is waiting for user confirmation."""
        session = self.get_session(session_id)
        session.pending_tool_call = {
            "name": tool_name,
            "args": tool_args
        }
        session.status = SessionStatus.WAITING_FOR_CONFIRMATION

    def clear_pending_tool(self, session_id: str):
        """Clears the pending tool call after execution or cancellation."""
        session = self.get_session(session_id)
        session.pending_tool_call = None
        session.status = SessionStatus.IDLE

    def add_to_history(self, session_id: str, role: str, content: str):
        """Adds a message to the session history."""
        session = self.get_session(session_id)
        session.history.append({"role": role, "content": content})
        
    def store_job_results(self, session_id: str, results: List[JobMatchPair]) -> List[str]:
        """Stores jobs in the session and assigns them stable IDs (job_1, job_2, etc.)."""
        session = self.get_session(session_id)
        session.job_results.clear()
        
        job_ids = []
        for i, pair in enumerate(results, start=1):
            job_id = f"job_{i}"
            session.job_results[job_id] = pair
            job_ids.append(job_id)
        return job_ids

    def get_job_result(self, session_id: str, job_reference: str) -> JobMatchPair | None:
        """Retrieves a stored job by reference (e.g., 'job_1', '1', 'job 1')."""
        session = self.get_session(session_id)
        if job_reference in session.job_results:
            return session.job_results[job_reference]
            
        norm = job_reference.lower().strip().replace(" ", "_")
        if norm in session.job_results:
            return session.job_results[norm]
            
        if norm.isdigit():
            norm_id = f"job_{norm}"
            if norm_id in session.job_results:
                return session.job_results[norm_id]
                
        return None
        
    def clear_session(self, session_id: str):
        """Removes a session completely."""
        if session_id in self._sessions:
            del self._sessions[session_id]
        
        # Clear trace if exists
        try:
            from app.agents.execution_trace import trace_manager
            trace_manager.clear_trace(session_id)
        except ImportError:
            pass

# Global state manager instance
state_manager = StateManager()
