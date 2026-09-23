import pytest
from app.agents.decision import decision_engine, DecisionType, AgentDecision
from app.agents.orchestration import AgentPlan, PlanStep, TaskState

def test_decision_continue():
    step = PlanStep(id=1, description="test", tool_name="dummy_tool")
    plan = AgentPlan(goal="Test", steps=[step, PlanStep(id=2, description="next")])
    
    decision = decision_engine.make_decision(plan, step, True, False)
    assert decision.decision_type == DecisionType.CONTINUE

def test_decision_complete():
    step = PlanStep(id=2, description="test", tool_name="dummy_tool")
    plan = AgentPlan(goal="Test", steps=[PlanStep(id=1, description="prev"), step], current_step_index=1)
    
    decision = decision_engine.make_decision(plan, step, True, False)
    assert decision.decision_type == DecisionType.COMPLETE

def test_decision_fail_on_tool_failure():
    step = PlanStep(id=1, description="test", tool_name="dummy_tool", status=TaskState.FAILED, error="Some error")
    plan = AgentPlan(goal="Test", steps=[step])
    
    decision = decision_engine.make_decision(plan, step, True, False)
    assert decision.decision_type == DecisionType.FAIL

def test_decision_replan_on_verification_failure():
    step = PlanStep(id=1, description="test", tool_name="dummy_tool")
    plan = AgentPlan(goal="Test", steps=[step])
    
    decision = decision_engine.make_decision(plan, step, False, False)
    assert decision.decision_type == DecisionType.REPLAN

def test_decision_wait_for_confirmation():
    step = PlanStep(id=1, description="test", tool_name="send_email")
    plan = AgentPlan(goal="Test", steps=[step])
    
    decision = decision_engine.make_decision(plan, step, None, True)
    assert decision.decision_type == DecisionType.WAIT_FOR_CONFIRMATION

def test_decision_replan_deterministic_rule():
    step = PlanStep(id=1, description="test", tool_name="discover_new_jobs", result={"new_jobs": 0})
    plan = AgentPlan(goal="Test", steps=[step, PlanStep(id=2, description="next")])
    
    decision = decision_engine.make_decision(plan, step, True, False)
    assert decision.decision_type == DecisionType.REPLAN

def test_agent_replanner_truncates_plan():
    from app.agents.decision import AgentReplanner
    replanner = AgentReplanner()
    
    step = PlanStep(id=1, description="test", tool_name="discover_new_jobs")
    plan = AgentPlan(goal="Test", steps=[step, PlanStep(id=2, description="next")])
    
    updated_plan = replanner.replan(plan, step, {"new_jobs": 0})
    assert len(updated_plan.steps) == 1
    assert updated_plan.steps[0].id == 1

def test_dynamic_arg_chaining(monkeypatch):
    from app.agents.orchestration import orchestrator
    from unittest.mock import MagicMock
    
    session_id = "test_chaining"
    step1 = PlanStep(id=1, description="s1", tool_name="dummy1", result={"output_id": 42})
    step2 = PlanStep(id=2, description="s2", tool_name="dummy2", tool_args={"input_id": "$step_1.output_id"})
    plan = AgentPlan(goal="Test", steps=[step1, step2], current_step_index=1)
    
    orchestrator._plans[session_id] = plan
    
    mock_tool = MagicMock(return_value={"status": "success"})
    mock_tool.__signature__ = __import__('inspect').signature(lambda input_id, session_id: None)
    
    monkeypatch.setattr("app.agents.orchestration.registry.get_tool", lambda name: mock_tool)
    monkeypatch.setattr("app.agents.orchestration.registry.requires_confirmation", lambda name: False)
    
    orchestrator.execute_next_step(session_id)
    
    mock_tool.assert_called_once_with(input_id=42, session_id=session_id)

def test_session_isolation_in_orchestrator():
    from app.agents.orchestration import orchestrator
    
    plan1 = AgentPlan(goal="Test1")
    plan2 = AgentPlan(goal="Test2")
    
    orchestrator._plans["s1"] = plan1
    orchestrator._plans["s2"] = plan2
    
    assert orchestrator.get_plan("s1").goal == "Test1"
    assert orchestrator.get_plan("s2").goal == "Test2"
