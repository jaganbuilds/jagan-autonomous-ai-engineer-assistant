import pytest
from unittest.mock import MagicMock
from app.agents.orchestration import orchestrator, TaskState, AgentPlan, PlanStep
from app.agents.state import state_manager
from app.agents.execution_trace import trace_manager, EventType
from app.agents.confirmation import confirmation_manager
from app.tools.registry import registry

def setup_function():
    # Clean up state before each test
    state_manager.clear_session("test_trace")
    # This also clears trace because of the hook in state_manager

def test_trace_creation():
    session_id = "test_trace"
    
    steps = [PlanStep(id=1, description="Step 1", tool_name="dummy_tool")]
    plan = orchestrator.create_plan(session_id, "Test Goal", steps)
    
    trace = trace_manager.get_trace(session_id)
    assert trace.goal == "Test Goal"
    events = [e for e in trace.events if e.event_type not in (EventType.CHECKPOINT_CREATED, EventType.CHECKPOINT_RESTORED)]
    assert len(events) == 1
    assert events[0].event_type == EventType.PLAN_CREATED
    assert events[0].result_summary["total_steps"] == 1

def test_full_execution_trace(monkeypatch):
    session_id = "test_trace"
    
    steps = [PlanStep(id=1, description="Step 1", tool_name="dummy_tool")]
    plan = orchestrator.create_plan(session_id, "Test Goal", steps)
    
    mock_tool = MagicMock(return_value={"status": "success"})
    mock_tool.__signature__ = __import__('inspect').signature(lambda session_id: None)
    
    monkeypatch.setattr(registry, "get_tool", MagicMock(return_value=mock_tool))
    monkeypatch.setattr(registry, "requires_confirmation", MagicMock(return_value=False))
    
    orchestrator.execute_next_step(session_id)
    
    trace = trace_manager.get_trace(session_id)
    event_types = [e.event_type for e in trace.events if e.event_type not in (EventType.CHECKPOINT_CREATED, EventType.CHECKPOINT_RESTORED)]
    
    assert event_types == [
        EventType.PLAN_CREATED,
        EventType.STEP_STARTED,
        EventType.TOOL_EXECUTED,
        EventType.STEP_VERIFIED,
        EventType.DECISION_MADE,
        EventType.STEP_COMPLETED,
        EventType.TASK_COMPLETED
    ]
    
    summary = trace_manager.generate_run_summary(session_id)
    assert summary["goal"] == "Test Goal"
    assert summary["status"] == "completed"
    assert summary["total_steps"] == 1
    assert summary["completed_steps"] == 1
    assert summary["failed_steps"] == 0
    assert summary["confirmations"] == 0
    assert summary["replans"] == 0

def test_replan_trace(monkeypatch):
    session_id = "test_trace"
    
    steps = [
        PlanStep(id=1, description="Step 1", tool_name="discover_new_jobs"),
        PlanStep(id=2, description="Step 2", tool_name="dummy_tool")
    ]
    plan = orchestrator.create_plan(session_id, "Test Goal", steps)
    
    mock_tool = MagicMock(return_value={"new_jobs": 0})
    mock_tool.__signature__ = __import__('inspect').signature(lambda session_id: None)
    
    monkeypatch.setattr(registry, "get_tool", MagicMock(return_value=mock_tool))
    monkeypatch.setattr(registry, "requires_confirmation", MagicMock(return_value=False))
    
    orchestrator.execute_next_step(session_id)
    
    summary = trace_manager.generate_run_summary(session_id)
    assert summary["status"] == "completed"
    assert summary["replans"] == 1
    assert summary["completed_steps"] == 1
    
    trace = trace_manager.get_trace(session_id)
    event_types = [e.event_type for e in trace.events if e.event_type not in (EventType.CHECKPOINT_CREATED, EventType.CHECKPOINT_RESTORED)]
    assert EventType.REPLAN_OCCURRED in event_types

def test_pause_and_resume_trace(monkeypatch):
    session_id = "test_trace"
    
    step = PlanStep(id=1, description="Email step", tool_name="send_email", tool_args={"job_id": 123})
    plan = orchestrator.create_plan(session_id, "Test Goal", [step])
    
    monkeypatch.setattr(registry, "requires_confirmation", MagicMock(return_value=True))
    
    # 1. Execute -> Pause
    orchestrator.execute_next_step(session_id)
    
    trace = trace_manager.get_trace(session_id)
    event_types = [e.event_type for e in trace.events if e.event_type not in (EventType.CHECKPOINT_CREATED, EventType.CHECKPOINT_RESTORED)]
    assert event_types[-1] == EventType.WAITING_FOR_CONFIRMATION
    
    summary_paused = trace_manager.generate_run_summary(session_id)
    assert summary_paused["confirmations"] == 1
    assert summary_paused["status"] == "unknown" # not yet completed
    
    # Mock tool so it doesn't really run
    mock_tool = MagicMock(return_value={"status": "success"})
    mock_tool.__signature__ = __import__('inspect').signature(lambda job_id, session_id: None)
    monkeypatch.setattr(registry, "get_tool", MagicMock(return_value=mock_tool))
    
    # 2. Resume -> Approve
    orchestrator.resume_after_confirmation(session_id, approved=True)
    
    summary_resumed = trace_manager.generate_run_summary(session_id)
    assert summary_resumed["status"] == "completed"
    
    event_types_final = [e.event_type for e in trace_manager.get_trace(session_id).events if e.event_type not in (EventType.CHECKPOINT_CREATED, EventType.CHECKPOINT_RESTORED)]
    assert EventType.CONFIRMATION_RECEIVED in event_types_final

def test_rejection_trace(monkeypatch):
    session_id = "test_trace"
    
    step = PlanStep(id=1, description="Email step", tool_name="send_email", tool_args={"job_id": 123})
    plan = orchestrator.create_plan(session_id, "Test Goal", [step])
    
    monkeypatch.setattr(registry, "requires_confirmation", MagicMock(return_value=True))
    
    orchestrator.execute_next_step(session_id)
    orchestrator.resume_after_confirmation(session_id, approved=False)
    
    summary = trace_manager.generate_run_summary(session_id)
    assert summary["status"] == "failed"
    assert summary["failed_steps"] == 1
    
    trace = trace_manager.get_trace(session_id)
    event_types = [e.event_type for e in trace.events if e.event_type not in (EventType.CHECKPOINT_CREATED, EventType.CHECKPOINT_RESTORED)]
    assert EventType.STEP_FAILED in event_types
    assert EventType.TASK_FAILED in event_types
