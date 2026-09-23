import pytest
from app.agents.orchestration import orchestrator, AgentPlan, PlanStep, TaskState
from app.agents.checkpoint import checkpoint_repository, OrchestrationCheckpoint
from app.agents.state import state_manager, SessionStatus
import uuid

@pytest.fixture(autouse=True)
def setup_teardown():
    # Setup database
    from app.database.connection import init_db
    init_db()
    
    # Cleanup memory
    orchestrator._plans.clear()
    state_manager._sessions.clear()
    yield

def test_checkpoint_creation_and_retrieval():
    plan = AgentPlan(goal="Test", steps=[PlanStep(id=1, description="Step 1")])
    checkpoint = OrchestrationCheckpoint(session_id="session1", owner_id="owner1", goal="Test", plan=plan, status=TaskState.PLANNING)
    
    checkpoint_repository.create_or_update_checkpoint(checkpoint)
    
    retrieved = checkpoint_repository.get_latest_checkpoint_for_session("session1")
    assert retrieved is not None
    assert retrieved.session_id == "session1"
    assert retrieved.owner_id == "owner1"
    assert len(retrieved.plan.steps) == 1

def test_checkpoint_update():
    plan = AgentPlan(goal="Test", steps=[PlanStep(id=1, description="Step 1")])
    checkpoint = OrchestrationCheckpoint(run_id="run1", session_id="session1", owner_id="owner1", goal="Test", plan=plan, status=TaskState.PLANNING)
    checkpoint_repository.create_or_update_checkpoint(checkpoint)
    
    checkpoint.status = TaskState.WAITING_FOR_CONFIRMATION
    checkpoint_repository.create_or_update_checkpoint(checkpoint)
    
    retrieved = checkpoint_repository.get_checkpoint("run1")
    assert retrieved.status == TaskState.WAITING_FOR_CONFIRMATION

def test_owner_isolation():
    plan = AgentPlan(goal="Test", steps=[])
    checkpoint = OrchestrationCheckpoint(session_id="session1", owner_id="ownerA", goal="Test", plan=plan, status=TaskState.PLANNING)
    checkpoint_repository.create_or_update_checkpoint(checkpoint)
    
    # Try to resume with ownerB
    result = orchestrator.resume_latest_workflow("session1", owner_id="ownerB")
    assert result is None
    
def test_session_isolation():
    plan = AgentPlan(goal="Test", steps=[])
    checkpoint = OrchestrationCheckpoint(session_id="session1", owner_id="ownerA", goal="Test", plan=plan, status=TaskState.PLANNING)
    checkpoint_repository.create_or_update_checkpoint(checkpoint)
    
    # Try to resume with session2
    result = orchestrator.resume_latest_workflow("session2", owner_id="ownerA")
    assert result is None

def test_concurrent_resume_protection():
    plan = AgentPlan(goal="Test", steps=[])
    checkpoint = OrchestrationCheckpoint(session_id="session1", owner_id="ownerA", goal="Test", plan=plan, status=TaskState.PLANNING)
    checkpoint_repository.create_or_update_checkpoint(checkpoint)
    
    # Inject active plan into memory
    active_plan = AgentPlan(goal="Test", status=TaskState.EXECUTING)
    orchestrator._plans["session1"] = active_plan
    
    # Try to resume while actively executing
    result = orchestrator.resume_latest_workflow("session1", owner_id="ownerA")
    assert result is None

def test_application_restart_simulation_and_resume_from_correct_step(monkeypatch):
    # Step 1: completed, Step 2: pending
    step1 = PlanStep(id=1, description="Step 1", tool_name="mock_tool_1", status=TaskState.COMPLETED)
    step2 = PlanStep(id=2, description="Step 2", tool_name="mock_tool_2", status=TaskState.PLANNING)
    plan = AgentPlan(goal="Test", steps=[step1, step2], current_step_index=1, status=TaskState.PLANNING)
    
    checkpoint = OrchestrationCheckpoint(session_id="session_restart", owner_id="owner1", goal="Test", plan=plan, status=TaskState.PLANNING)
    checkpoint_repository.create_or_update_checkpoint(checkpoint)
    
    # Mock registry so step 2 can execute
    from app.tools.registry import registry
    monkeypatch.setattr(registry, "get_tool", lambda name: (lambda **kwargs: "Success"))
    
    # Simulate restart by clearing memory
    orchestrator._plans.clear()
    state_manager._sessions.clear()
    
    # Resume
    result = orchestrator.resume_latest_workflow("session_restart", owner_id="owner1")
    assert result is not None
    assert result.status == "completed"
    
    # Verify Step 2 executed, and Step 1 was NOT re-executed
    restored_plan = orchestrator.get_plan("session_restart")
    assert restored_plan.current_step_index == 1
    assert restored_plan.steps[0].status == TaskState.COMPLETED
    assert restored_plan.steps[1].status == TaskState.COMPLETED

def test_waiting_for_confirmation_recovery():
    step1 = PlanStep(id=1, description="Step 1", tool_name="mock_tool", status=TaskState.WAITING_FOR_CONFIRMATION)
    plan = AgentPlan(goal="Test", steps=[step1], current_step_index=0, status=TaskState.WAITING_FOR_CONFIRMATION)
    
    checkpoint = OrchestrationCheckpoint(session_id="session_conf", owner_id="owner1", goal="Test", plan=plan, status=TaskState.WAITING_FOR_CONFIRMATION)
    checkpoint_repository.create_or_update_checkpoint(checkpoint)
    
    orchestrator._plans.clear()
    state_manager._sessions.clear()
    
    result = orchestrator.resume_latest_workflow("session_conf", owner_id="owner1")
    assert result is not None
    assert result.status == "waiting_for_confirmation"
    assert orchestrator.get_plan("session_conf").status == TaskState.WAITING_FOR_CONFIRMATION

def test_failed_workflow_recovery():
    step1 = PlanStep(id=1, description="Step 1", tool_name="mock_tool", status=TaskState.FAILED)
    plan = AgentPlan(goal="Test", steps=[step1], current_step_index=0, status=TaskState.FAILED)
    
    checkpoint = OrchestrationCheckpoint(session_id="session_fail", owner_id="owner1", goal="Test", plan=plan, status=TaskState.FAILED)
    checkpoint_repository.create_or_update_checkpoint(checkpoint)
    
    orchestrator._plans.clear()
    
    result = orchestrator.resume_latest_workflow("session_fail", owner_id="owner1")
    assert result is not None
    assert result.status == "failed"

def test_corrupted_missing_checkpoint_handling():
    result = orchestrator.resume_latest_workflow("session_missing", owner_id="owner1")
    assert result is None

def test_action_idempotency_crash_during_executing():
    # If it was executing when the app crashed, it should mark it as failed on recovery
    # to prevent blind retries of side-effect actions.
    step1 = PlanStep(id=1, description="Step 1", tool_name="mock_tool", status=TaskState.EXECUTING)
    plan = AgentPlan(goal="Test", steps=[step1], current_step_index=0, status=TaskState.EXECUTING)
    
    checkpoint = OrchestrationCheckpoint(session_id="session_exec", owner_id="owner1", goal="Test", plan=plan, status=TaskState.EXECUTING)
    checkpoint_repository.create_or_update_checkpoint(checkpoint)
    
    orchestrator._plans.clear()
    
    result = orchestrator.resume_latest_workflow("session_exec", owner_id="owner1")
    
    assert result is not None
    assert result.status == "failed"
    restored_plan = orchestrator.get_plan("session_exec")
    assert restored_plan.status == TaskState.FAILED
    assert restored_plan.steps[0].status == TaskState.FAILED
    assert "System crashed during execution" in restored_plan.steps[0].error
