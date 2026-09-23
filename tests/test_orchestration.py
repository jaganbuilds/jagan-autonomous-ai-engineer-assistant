import pytest
from unittest.mock import MagicMock
from app.agents.orchestration import orchestrator, TaskState, PlanStep
from app.agents.state import state_manager, SessionStatus
from app.tools.registry import registry
from app.agents.confirmation import confirmation_manager

@pytest.fixture
def clean_orchestrator():
    orchestrator._plans.clear()
    yield orchestrator
    orchestrator._plans.clear()

def test_plan_creation(clean_orchestrator):
    session_id = "test_orch_1"
    steps = [
        PlanStep(id=1, description="Step 1", tool_name="dummy_tool"),
        PlanStep(id=2, description="Step 2", tool_name="dummy_tool_2")
    ]
    plan = clean_orchestrator.create_plan(session_id, "Test Goal", steps)
    
    assert plan.goal == "Test Goal"
    assert len(plan.steps) == 2
    assert plan.status == TaskState.PLANNING
    assert state_manager.get_session(session_id).status == SessionStatus.PROCESSING

def test_successful_execution_and_verification(clean_orchestrator, monkeypatch):
    session_id = "test_orch_2"
    
    # Mock tool
    def dummy_func(arg1, session_id):
        return {"status": "success", "data": 123}
    
    mock_tool = MagicMock(side_effect=dummy_func)
    mock_tool.__signature__ = __import__('inspect').signature(dummy_func)
    
    monkeypatch.setattr(registry, "get_tool", MagicMock(return_value=mock_tool))
    monkeypatch.setattr(registry, "requires_confirmation", MagicMock(return_value=False))
    
    steps = [PlanStep(id=1, description="Step 1", tool_name="dummy_tool", tool_args={"arg1": "val1"})]
    plan = clean_orchestrator.create_plan(session_id, "Goal", steps)
    
    updated_plan = clean_orchestrator.execute_next_step(session_id)
    
    assert updated_plan.status == TaskState.COMPLETED
    assert updated_plan.steps[0].status == TaskState.COMPLETED
    assert updated_plan.steps[0].result == {"status": "success", "data": 123}
    assert updated_plan.current_step_index == 0
    mock_tool.assert_called_once_with(arg1="val1", session_id=session_id)
    assert state_manager.get_session(session_id).status == SessionStatus.COMPLETED

def test_failed_tool_verification(clean_orchestrator, monkeypatch):
    session_id = "test_orch_3"
    
    def dummy_func_fail(session_id):
        return {"status": "error", "message": "Failed"}
    mock_tool = MagicMock(side_effect=dummy_func_fail)
    mock_tool.__signature__ = __import__('inspect').signature(dummy_func_fail)
    
    monkeypatch.setattr(registry, "get_tool", MagicMock(return_value=mock_tool))
    monkeypatch.setattr(registry, "requires_confirmation", MagicMock(return_value=False))
    
    steps = [PlanStep(id=1, description="Step 1", tool_name="dummy_tool")]
    plan = clean_orchestrator.create_plan(session_id, "Goal", steps)
    
    updated_plan = clean_orchestrator.execute_next_step(session_id)
    
    assert updated_plan.status == TaskState.FAILED
    assert updated_plan.steps[0].status == TaskState.FAILED
    assert "Execution or verification failed" in updated_plan.error
    assert state_manager.get_session(session_id).status != SessionStatus.COMPLETED

def test_confirmation_boundary(clean_orchestrator, monkeypatch):
    session_id = "test_orch_4"
    
    # Tool exists and requires confirmation
    monkeypatch.setattr(registry, "get_tool", MagicMock(return_value=MagicMock()))
    monkeypatch.setattr(registry, "requires_confirmation", MagicMock(return_value=True))
    
    # Mock confirmation manager and state manager
    monkeypatch.setattr(confirmation_manager, "create_pending_email", MagicMock())
    monkeypatch.setattr(state_manager, "set_pending_tool", MagicMock())
    
    steps = [PlanStep(id=1, description="Send", tool_name="send_email", tool_args={"job_id": 1})]
    plan = clean_orchestrator.create_plan(session_id, "Goal", steps)
    
    updated_plan = clean_orchestrator.execute_next_step(session_id)
    
    assert updated_plan.status == TaskState.WAITING_FOR_CONFIRMATION
    assert updated_plan.steps[0].status == TaskState.WAITING_FOR_CONFIRMATION
    state_manager.set_pending_tool.assert_called_once()
