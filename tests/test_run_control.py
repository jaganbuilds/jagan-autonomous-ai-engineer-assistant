import pytest
from unittest.mock import MagicMock
from app.agents.run_control import run_controller
from app.agents.orchestration import orchestrator, TaskState, AgentPlan, PlanStep
from app.agents.state import state_manager, SessionStatus
from app.agents.checkpoint import checkpoint_repository, OrchestrationCheckpoint, CURRENT_SCHEMA_VERSION
from app.agents.execution_trace import trace_manager, EventType
from app.tools.registry import registry
from app.database.connection import init_db

def setup_module():
    init_db()

def setup_function():
    pass

def test_status_inspection():
    session_id = "test_status"
    run_id = "run_status"
    
    plan = AgentPlan(run_id=run_id, goal="Test Goal", steps=[
        PlanStep(id=1, description="Step 1", tool_name="dummy_tool")
    ])
    cp = OrchestrationCheckpoint(run_id=run_id, session_id=session_id, goal="Test Goal", plan=plan, status=TaskState.PLANNING)
    checkpoint_repository.create_or_update_checkpoint(cp)
    
    # 1. get active run status
    status = run_controller.get_status(run_id, session_id)
    assert status.status == TaskState.PLANNING
    assert status.cancellation_allowed is True
    assert status.resumable is True
    
    # 2. get waiting-for-confirmation status
    cp.status = TaskState.WAITING_FOR_CONFIRMATION
    checkpoint_repository.create_or_update_checkpoint(cp)
    status2 = run_controller.get_status(run_id, session_id)
    assert status2.status == TaskState.WAITING_FOR_CONFIRMATION
    assert status2.waiting_for_confirmation is True
    
    # 3. get completed status
    cp.status = TaskState.COMPLETED
    checkpoint_repository.create_or_update_checkpoint(cp)
    status3 = run_controller.get_status(run_id, session_id)
    assert status3.terminal is True
    assert status3.cancellation_allowed is False
    assert status3.resumable is False
    
    # 4. get failed status
    cp.status = TaskState.FAILED
    checkpoint_repository.create_or_update_checkpoint(cp)
    status4 = run_controller.get_status(run_id, session_id)
    assert status4.terminal is True
    assert status4.cancellation_allowed is False
    
    # 5. get cancelled status
    cp.status = TaskState.CANCELLED
    checkpoint_repository.create_or_update_checkpoint(cp)
    status5 = run_controller.get_status(run_id, session_id)
    assert status5.status == TaskState.CANCELLED
    assert status5.terminal is True
    
    # 6. unknown run
    assert run_controller.get_status("unknown", session_id) is None
    
    # 7. wrong session
    assert run_controller.get_status(run_id, "wrong_session") is None

def test_cancellation():
    session_id = "test_cancel"
    run_id = "run_cancel"
    
    plan = AgentPlan(run_id=run_id, goal="Cancel Goal", steps=[
        PlanStep(id=1, description="Step 1", tool_name="dummy_tool")
    ])
    orchestrator._plans[session_id] = plan # simulate in-memory active
    cp = OrchestrationCheckpoint(run_id=run_id, session_id=session_id, goal="Cancel Goal", plan=plan, status=TaskState.PLANNING)
    checkpoint_repository.create_or_update_checkpoint(cp)
    
    # 1. cancel active run
    result = run_controller.cancel(run_id, session_id)
    assert result.status == "cancelled"
    
    status = run_controller.get_status(run_id, session_id)
    assert status.status == TaskState.CANCELLED
    assert orchestrator.get_plan(session_id).status == TaskState.CANCELLED
    
    # 2. cancel already-cancelled run rejected
    result2 = run_controller.cancel(run_id, session_id)
    assert result2.status == "failed"
    
    # 3. cross-session cancellation rejected
    result3 = run_controller.cancel(run_id, "wrong")
    assert result3.status == "failed"
    
    # 4. checkpoint remains after cancellation
    assert checkpoint_repository.get_checkpoint(run_id) is not None

def test_cancellation_trace():
    session_id = "test_cancel_trace"
    run_id = "run_cancel_trace"
    
    plan = AgentPlan(run_id=run_id, goal="Cancel Goal", steps=[])
    cp = OrchestrationCheckpoint(run_id=run_id, session_id=session_id, goal="Cancel Goal", plan=plan, status=TaskState.PLANNING)
    checkpoint_repository.create_or_update_checkpoint(cp)
    
    run_controller.cancel(run_id, session_id)
    
    trace = trace_manager.get_trace(session_id)
    event_types = [e.event_type for e in trace.events]
    assert EventType.RUN_CANCELLED in event_types
    assert EventType.TASK_FAILED in event_types

def test_resume_behavior(monkeypatch):
    session_id = "test_resume"
    run_id = "run_resume"
    
    plan = AgentPlan(run_id=run_id, goal="Resume Goal", status=TaskState.WAITING_FOR_CONFIRMATION, steps=[
        PlanStep(id=1, description="Step 1", tool_name="dummy_tool", tool_args={"x": 1}, status=TaskState.WAITING_FOR_CONFIRMATION)
    ], current_step_index=0)
    
    cp = OrchestrationCheckpoint(run_id=run_id, session_id=session_id, goal="Resume Goal", plan=plan, status=TaskState.WAITING_FOR_CONFIRMATION)
    checkpoint_repository.create_or_update_checkpoint(cp)
    
    # 1. resume confirmation-waiting run
    result = run_controller.resume(run_id, session_id)
    assert result.status == "waiting_for_confirmation"
    assert "waiting for human confirmation" in result.message.lower()
    
    # 2. resume preserves confirmation boundary (state manager has the pending tool)
    session = state_manager.get_session(session_id)
    assert session.status == SessionStatus.WAITING_FOR_CONFIRMATION
    assert session.pending_tool_call["name"] == "dummy_tool"
    
    # 3. resume restores context
    assert orchestrator.get_plan(session_id).steps[0].tool_args["x"] == 1
    
    # 4. resume unknown external execution state (crash)
    plan.status = TaskState.EXECUTING
    cp.status = TaskState.EXECUTING
    checkpoint_repository.create_or_update_checkpoint(cp)
    
    result2 = run_controller.resume(run_id, session_id)
    assert result2.status == "failed"
    
    # 5. resume completed run rejected
    cp.status = TaskState.COMPLETED
    checkpoint_repository.create_or_update_checkpoint(cp)
    result3 = run_controller.resume(run_id, session_id)
    assert result3.status == "failed"

def test_tools_integration():
    from app.tools.orchestration_status_tool import get_orchestration_status
    from app.tools.orchestration_control_tool import control_orchestration
    
    session_id = "test_tools"
    run_id = "run_tools"
    plan = AgentPlan(run_id=run_id, goal="Tool Goal")
    cp = OrchestrationCheckpoint(run_id=run_id, session_id=session_id, goal="Tool Goal", plan=plan, status=TaskState.PLANNING)
    checkpoint_repository.create_or_update_checkpoint(cp)
    
    status = get_orchestration_status(session_id, run_id)
    assert status["status"] == "planning"
    
    cancel_res = control_orchestration(session_id, run_id, "cancel")
    assert cancel_res["status"] == "cancelled"
    
    status2 = get_orchestration_status(session_id, run_id)
    assert status2["status"] == "cancelled"
    
    resume_res = control_orchestration(session_id, run_id, "resume")
    assert resume_res["status"] == "failed" # because it's cancelled

