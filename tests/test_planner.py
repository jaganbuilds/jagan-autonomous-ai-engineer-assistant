import pytest
from unittest.mock import MagicMock
from app.agents.planner import planner
from app.agents.orchestration import orchestrator, TaskState
from app.agents.manager import ManagerAgent
from app.agents.state import state_manager, SessionStatus
from app.agents.router import Intent

def test_goal_to_plan():
    session_id = "test_planner_1"
    plan = planner.create_plan_for_goal(session_id, "Find AI Engineer fresher jobs in Chennai")
    
    assert plan.goal == "Find AI Engineer fresher jobs in Chennai"
    assert len(plan.steps) == 3
    assert plan.steps[0].tool_name == "discover_new_jobs"
    assert plan.steps[1].tool_name == "unknown_tool"  # Because it's unregistered in this basic test env
    assert plan.steps[2].tool_name == "unknown_tool"
    assert plan.status == TaskState.PLANNING

def test_unsupported_goal(monkeypatch):
    from app.config import get_settings
    settings = get_settings()
    monkeypatch.setattr(settings, "openrouter_api_key", "mock")
    
    session_id = "test_planner_2"
    plan = planner.create_plan_for_goal(session_id, "Do something unknown")
    
    assert plan.steps[0].tool_name == "read_workspace_file"

def test_manager_orchestration_trigger(monkeypatch):
    agent = ManagerAgent()
    session_id = "test_trigger_1"
    
    # We want to mock orchestrator so we don't actually run real tools
    mock_orchestrator = MagicMock()
    mock_plan = MagicMock()
    mock_plan.steps = [MagicMock(tool_name="dummy_tool")]
    mock_plan.status = TaskState.COMPLETED
    mock_orchestrator.execute_next_step.return_value = mock_plan
    
    monkeypatch.setattr("app.agents.orchestration.orchestrator", mock_orchestrator)
    monkeypatch.setattr("app.agents.planner.planner.create_plan_for_goal", MagicMock(return_value=mock_plan))
    
    # Trigger orchestration
    response = agent.process_message("Find some jobs", session_id)
    assert "completed successfully" in response
    assert state_manager.get_session(session_id).status == SessionStatus.IDLE

def test_manager_skips_orchestration_for_simple_request(monkeypatch):
    agent = ManagerAgent()
    session_id = "test_trigger_2"
    
    # Mock LLM gateway
    from app.llm.models import LLMResponse
    mock_gateway = MagicMock()
    mock_response = LLMResponse(text="Here is the calculation: 200", tool_calls=[])
    mock_gateway.chat.return_value = mock_response
    monkeypatch.setattr("app.agents.manager.gateway", mock_gateway)
    
    response = agent.process_message("Calculate 25 * 8", session_id)
    assert response == "Here is the calculation: 200"

def test_session_isolation_in_planner():
    session_1 = "s1"
    session_2 = "s2"
    
    plan1 = planner.create_plan_for_goal(session_1, "Find jobs")
    plan2 = planner.create_plan_for_goal(session_2, "Find jobs")
    
    assert orchestrator.get_plan(session_1) is plan1
    assert orchestrator.get_plan(session_2) is plan2
    assert plan1 is not plan2
