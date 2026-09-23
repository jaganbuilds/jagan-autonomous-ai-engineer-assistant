import pytest
import os
from unittest.mock import MagicMock
from app.agents.checkpoint import checkpoint_repository, OrchestrationCheckpoint, CURRENT_SCHEMA_VERSION
from app.agents.orchestration import orchestrator, TaskState, AgentPlan, PlanStep
from app.agents.state import state_manager, SessionStatus
from app.agents.execution_trace import trace_manager, EventType
from app.tools.registry import registry
from app.database.connection import init_db

# Use an in-memory DB or temporary test DB if possible
# For these tests, we will just use the default DB but clean it up or isolate IDs
# Jagan AI test suite doesn't have an isolated pytest fixture for db natively, but we can ensure unique IDs.

def setup_module():
    init_db()

def setup_function():
    pass

def test_checkpoint_persistence():
    session_id = "test_cp_persistence"
    run_id = "run_123"
    
    plan = AgentPlan(run_id=run_id, goal="Test Goal")
    cp = OrchestrationCheckpoint(
        run_id=run_id,
        session_id=session_id,
        goal="Test Goal",
        plan=plan,
        status=TaskState.PLANNING
    )
    
    # 1. creation
    checkpoint_repository.create_or_update_checkpoint(cp)
    
    # 2. retrieval
    retrieved = checkpoint_repository.get_checkpoint(run_id)
    assert retrieved is not None
    assert retrieved.goal == "Test Goal"
    assert retrieved.plan.run_id == run_id
    
    # 3. update
    cp.status = TaskState.COMPLETED
    checkpoint_repository.create_or_update_checkpoint(cp)
    retrieved2 = checkpoint_repository.get_checkpoint(run_id)
    assert retrieved2.status == TaskState.COMPLETED
    
    # 5. list
    lst = checkpoint_repository.list_checkpoints_for_session(session_id)
    assert len(lst) == 1
    
    # 4. delete
    checkpoint_repository.delete_checkpoint(run_id)
    assert checkpoint_repository.get_checkpoint(run_id) is None

def test_checkpoint_serialization():
    run_id = "run_serial"
    plan = AgentPlan(run_id=run_id, goal="Serial Goal", steps=[
        PlanStep(id=1, description="Step 1", tool_name="dummy_tool", retry_count=2, tool_args={"job_id": 42})
    ])
    
    cp = OrchestrationCheckpoint(
        run_id=run_id,
        session_id="session_serial",
        goal="Serial Goal",
        plan=plan,
        status=TaskState.EXECUTING
    )
    checkpoint_repository.create_or_update_checkpoint(cp)
    
    restored = checkpoint_repository.get_checkpoint(run_id)
    assert restored.schema_version == CURRENT_SCHEMA_VERSION
    assert restored.plan.steps[0].retry_count == 2
    assert restored.plan.steps[0].tool_args["job_id"] == 42
    
    checkpoint_repository.delete_checkpoint(run_id)

def test_orchestrator_checkpoint_lifecycle(monkeypatch):
    session_id = "test_lifecycle"
    
    def dummy_func_fail(session_id):
        raise Exception("timeout")
        
    mock_tool = MagicMock(side_effect=dummy_func_fail)
    mock_tool.__signature__ = __import__('inspect').signature(lambda session_id: None)
    monkeypatch.setattr(registry, "get_tool", MagicMock(return_value=mock_tool))
    monkeypatch.setattr(registry, "requires_confirmation", MagicMock(return_value=False))
    registry._retry_policies["dummy_tool"] = {"retryable": True, "max_retries": 1}
    
    # 1. creation
    plan = orchestrator.create_plan(session_id, "Goal", [PlanStep(id=1, description="Step 1", tool_name="dummy_tool")])
    run_id = plan.run_id
    
    cp1 = checkpoint_repository.get_checkpoint(run_id)
    assert cp1.status == TaskState.PLANNING
    
    # Execute - fails and retries (which changes state)
    orchestrator.execute_next_step(session_id)
    
    cp2 = checkpoint_repository.get_checkpoint(run_id)
    assert cp2.status == TaskState.FAILED
    assert cp2.plan.steps[0].retry_count == 1
    
    checkpoint_repository.delete_checkpoint(run_id)

def test_orchestrator_restore_crash_safety():
    session_id = "test_restore_crash"
    run_id = "run_crash"
    
    plan = AgentPlan(run_id=run_id, goal="Crash Goal", status=TaskState.EXECUTING, steps=[
        PlanStep(id=1, description="Step 1", tool_name="dummy_tool", status=TaskState.EXECUTING)
    ], current_step_index=0)
    
    # Manually create a checkpoint stuck in EXECUTING
    cp = OrchestrationCheckpoint(
        run_id=run_id,
        session_id=session_id,
        goal="Crash Goal",
        plan=plan,
        status=TaskState.EXECUTING
    )
    checkpoint_repository.create_or_update_checkpoint(cp)
    
    # Restore
    restored_plan = orchestrator.restore_orchestration(run_id, session_id)
    assert restored_plan.status == TaskState.FAILED
    assert restored_plan.steps[0].status == TaskState.FAILED
    assert "crashed during execution" in restored_plan.steps[0].error
    
    checkpoint_repository.delete_checkpoint(run_id)

def test_orchestrator_restore_waiting_for_confirmation():
    session_id = "test_restore_wait"
    run_id = "run_wait"
    
    plan = AgentPlan(run_id=run_id, goal="Wait Goal", status=TaskState.WAITING_FOR_CONFIRMATION, steps=[
        PlanStep(id=1, description="Step 1", tool_name="dummy_tool", tool_args={"job_id": 1}, status=TaskState.WAITING_FOR_CONFIRMATION)
    ], current_step_index=0)
    
    cp = OrchestrationCheckpoint(
        run_id=run_id,
        session_id=session_id,
        goal="Wait Goal",
        plan=plan,
        status=TaskState.WAITING_FOR_CONFIRMATION
    )
    checkpoint_repository.create_or_update_checkpoint(cp)
    
    restored_plan = orchestrator.restore_orchestration(run_id, session_id)
    assert restored_plan.status == TaskState.WAITING_FOR_CONFIRMATION
    
    assert state_manager.get_session(session_id).status == SessionStatus.WAITING_FOR_CONFIRMATION
    assert state_manager.get_session(session_id).pending_tool_call["name"] == "dummy_tool"
    
    checkpoint_repository.delete_checkpoint(run_id)

def test_orchestrator_restore_safety_checks():
    session_id = "test_restore_safety"
    run_id = "run_safety"
    
    plan = AgentPlan(run_id=run_id, goal="Goal")
    cp = OrchestrationCheckpoint(
        run_id=run_id,
        session_id=session_id,
        goal="Goal",
        plan=plan,
        status=TaskState.PLANNING,
        schema_version="99.9" # unsupported
    )
    checkpoint_repository.create_or_update_checkpoint(cp)
    
    # Unsupported version
    assert orchestrator.restore_orchestration(run_id, session_id) is None
    
    cp.schema_version = CURRENT_SCHEMA_VERSION
    checkpoint_repository.create_or_update_checkpoint(cp)
    
    # Mismatched session
    assert orchestrator.restore_orchestration(run_id, "wrong_session") is None
    
    checkpoint_repository.delete_checkpoint(run_id)
