from enum import Enum
from typing import List, Dict, Any, Optional
from datetime import datetime, timezone
from pydantic import BaseModel, Field
import uuid

class EventType(str, Enum):
    PLAN_CREATED = "plan_created"
    STEP_STARTED = "step_started"
    TOOL_EXECUTED = "tool_executed"
    STEP_VERIFIED = "step_verified"
    DECISION_MADE = "decision_made"
    REPLAN_OCCURRED = "replan_occurred"
    WAITING_FOR_CONFIRMATION = "waiting_for_confirmation"
    CONFIRMATION_RECEIVED = "confirmation_received"
    STEP_COMPLETED = "step_completed"
    STEP_FAILED = "step_failed"
    TASK_COMPLETED = "task_completed"
    TASK_FAILED = "task_failed"
    FAILURE_CLASSIFIED = "failure_classified"
    RETRY_DECIDED = "retry_decided"
    RETRY_STARTED = "retry_started"
    RETRY_COMPLETED = "retry_completed"
    RECOVERY_FAILED = "recovery_failed"
    CHECKPOINT_CREATED = "checkpoint_created"
    CHECKPOINT_RESTORED = "checkpoint_restored"
    RESTORE_VALIDATION_FAILED = "restore_validation_failed"
    RECOVERY_REQUIRES_REVIEW = "recovery_requires_review"
    RUN_STATUS_REQUESTED = "run_status_requested"
    RUN_RESUMED = "run_resumed"
    RUN_CANCELLED = "run_cancelled"
    RUN_CONTROL_REJECTED = "run_control_rejected"
    ACTION_GATEWAY_EXECUTED = "action_gateway_executed"

class TraceEvent(BaseModel):
    event_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    event_type: EventType
    step_id: Optional[int] = None
    tool_name: Optional[str] = None
    status: Optional[str] = None
    message: Optional[str] = None
    result_summary: Optional[Dict[str, Any]] = None
    error: Optional[str] = None

class ExecutionTrace(BaseModel):
    session_id: str
    goal: Optional[str] = None
    events: List[TraceEvent] = Field(default_factory=list)

class ExecutionTraceManager:
    """
    Manages the execution trace for orchestrated tasks.
    Ties into the existing state_manager by storing the trace in the session.
    """
    def __init__(self):
        # We will dynamically attach the trace to the SessionState object to avoid circular imports.
        # Python allows setting arbitrary attributes on Pydantic models if model_config has extra='allow',
        # but SessionState is a BaseModel. Let's just store it in a dict here tied to the session_id,
        # but cleanup when session is cleared, OR we can use the state_manager's session directly if we add a field.
        # Actually, let's just keep _traces dict here and clean it up if needed, or better, 
        # modify SessionState to have `trace: Optional[Any] = None`
        self._traces: Dict[str, ExecutionTrace] = {}

    def get_trace(self, session_id: str) -> ExecutionTrace:
        if session_id not in self._traces:
            self._traces[session_id] = ExecutionTrace(session_id=session_id)
        return self._traces[session_id]

    def clear_trace(self, session_id: str):
        if session_id in self._traces:
            del self._traces[session_id]

    def add_event(self, session_id: str, event_type: EventType, **kwargs):
        trace = self.get_trace(session_id)
        event = TraceEvent(event_type=event_type, **kwargs)
        trace.events.append(event)
        return event

    def generate_run_summary(self, session_id: str) -> Dict[str, Any]:
        trace = self.get_trace(session_id)
        
        events = trace.events
        total_steps = 0
        completed_steps = 0
        failed_steps = 0
        replans = 0
        confirmations = 0
        final_status = "unknown"
        
        # Calculate summary metrics based on events
        for e in events:
            if e.event_type == EventType.PLAN_CREATED:
                if e.result_summary and "total_steps" in e.result_summary:
                    total_steps = e.result_summary["total_steps"]
            elif e.event_type == EventType.STEP_COMPLETED:
                completed_steps += 1
            elif e.event_type == EventType.STEP_FAILED:
                failed_steps += 1
            elif e.event_type == EventType.REPLAN_OCCURRED:
                replans += 1
            elif e.event_type == EventType.WAITING_FOR_CONFIRMATION:
                confirmations += 1
            elif e.event_type == EventType.TASK_COMPLETED:
                final_status = "completed"
            elif e.event_type == EventType.TASK_FAILED:
                final_status = "failed"
                
        return {
            "goal": trace.goal,
            "status": final_status,
            "total_steps": total_steps,
            "completed_steps": completed_steps,
            "failed_steps": failed_steps,
            "replans": replans,
            "confirmations": confirmations,
            "events": [e.model_dump() for e in events]
        }

trace_manager = ExecutionTraceManager()
