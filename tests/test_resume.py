import pytest
from unittest.mock import MagicMock
from app.agents.orchestration import orchestrator, TaskState, AgentPlan, PlanStep
from app.agents.state import state_manager, SessionStatus
from app.agents.confirmation import confirmation_manager
from app.tools.registry import registry
from app.agents.manager import ManagerAgent

def test_pause_and_resume_approval(monkeypatch):
    session_id = "test_resume_approve"
    state_manager.clear_session(session_id)
    
    # 1. Setup a plan with a tool that requires confirmation
    step = PlanStep(id=1, description="Email step", tool_name="send_email", tool_args={"job_id": 123, "recipient": "hr@example.com"})
    plan = orchestrator.create_plan(session_id, "Send an email", [step])
    
    # Mock registry and confirmation manager
    def dummy_send(job_id, recipient, session_id):
        return confirmation_manager.create_pending_email(session_id, job_id, "sub", "body", recipient)
    
    mock_tool = MagicMock(side_effect=dummy_send)
    mock_tool.__signature__ = __import__('inspect').signature(lambda job_id, recipient, session_id: None)
    
    monkeypatch.setattr(registry, "get_tool", MagicMock(return_value=mock_tool))
    monkeypatch.setattr(registry, "requires_confirmation", MagicMock(return_value=False))
    
    mock_confirm = MagicMock(return_value={"status": "sent", "action": "send_email"})
    monkeypatch.setattr(confirmation_manager, "confirm_email", mock_confirm)
    
    # 2. Execute - it should pause
    updated_plan = orchestrator.execute_next_step(session_id)
    assert updated_plan.status == TaskState.WAITING_FOR_CONFIRMATION
    assert step.status == TaskState.WAITING_FOR_CONFIRMATION
    assert getattr(state_manager.get_session(session_id), "pending_gateway_action", None) is not None
    
    # 3. ManagerAgent processes 'yes'
    agent = ManagerAgent()
    reply = agent.process_message("yes", session_id)
    
    # 4. Verification
    assert reply == "Orchestration completed successfully."
    assert plan.status == TaskState.COMPLETED
    assert step.status == TaskState.COMPLETED
    mock_tool.assert_called_once_with(job_id=123, recipient="hr@example.com", session_id=session_id)
    assert state_manager.get_session(session_id).status == SessionStatus.IDLE

def test_pause_and_resume_rejection(monkeypatch):
    session_id = "test_resume_reject"
    state_manager.clear_session(session_id)
    
    step = PlanStep(id=1, description="Email step", tool_name="send_email", tool_args={"job_id": 123})
    plan = orchestrator.create_plan(session_id, "Send an email", [step])
    
    monkeypatch.setattr(registry, "requires_confirmation", MagicMock(return_value=True))
    
    orchestrator.execute_next_step(session_id)
    
    agent = ManagerAgent()
    reply = agent.process_message("no", session_id)
    
    assert "Orchestration cancelled" in reply
    assert plan.status == TaskState.FAILED
    assert "Action rejected by human" in plan.error
    assert state_manager.get_session(session_id).status == SessionStatus.IDLE
    assert getattr(state_manager.get_session(session_id), "pending_gateway_action", None) is None

def test_dynamic_args_survive_resume(monkeypatch):
    session_id = "test_resume_args"
    state_manager.clear_session(session_id)
    
    step1 = PlanStep(id=1, description="Step 1", tool_name="dummy1", result={"output_id": 42})
    step2 = PlanStep(id=2, description="Step 2", tool_name="send_email", tool_args={"job_id": "$step_1.output_id"})
    plan = orchestrator.create_plan(session_id, "Test", [step1, step2])
    plan.current_step_index = 1
    
    mock_tool = MagicMock(return_value={"status": "success"})
    mock_tool.__signature__ = __import__('inspect').signature(lambda job_id, session_id: None)
    
    monkeypatch.setattr(registry, "get_tool", MagicMock(return_value=mock_tool))
    monkeypatch.setattr(registry, "requires_confirmation", MagicMock(return_value=True))
    
    # Execute step 2 - pauses
    orchestrator.execute_next_step(session_id)
    
    # Resume
    updated_plan = orchestrator.resume_after_confirmation(session_id, approved=True)
    
    mock_tool.assert_called_once_with(job_id=42, session_id=session_id)
    assert updated_plan.status == TaskState.COMPLETED

def test_session_isolation_on_resume():
    session_1 = "test_iso_1"
    session_2 = "test_iso_2"
    
    plan = orchestrator.create_plan(session_1, "Test", [PlanStep(id=1, description="test")])
    plan.status = TaskState.WAITING_FOR_CONFIRMATION
    
    # Trying to resume session 2 should fail because it has no plan waiting
    with pytest.raises(ValueError, match="No active plan found for session test_iso_2"):
        orchestrator.resume_after_confirmation(session_2, approved=True)
