import pytest
from unittest.mock import MagicMock
from app.agents.recovery import recovery_manager, FailureCategory
from app.agents.decision import DecisionType
from app.tools.registry import registry
from app.agents.orchestration import orchestrator, TaskState, AgentPlan, PlanStep
from app.agents.state import state_manager
from app.agents.execution_trace import trace_manager, EventType
import json

def setup_function():
    state_manager.clear_session("test_recovery")

def test_classification():
    assert recovery_manager.classify_failure("Rate limit exceeded 429").category == FailureCategory.RATE_LIMITED
    assert recovery_manager.classify_failure("Network timeout transient").category == FailureCategory.TRANSIENT
    assert recovery_manager.classify_failure("Missing schema validation").category == FailureCategory.VALIDATION
    assert recovery_manager.classify_failure("Unauthorized 401 token").category == FailureCategory.AUTHENTICATION
    assert recovery_manager.classify_failure("Forbidden 403").category == FailureCategory.AUTHORIZATION
    assert recovery_manager.classify_failure("Job not found 404").category == FailureCategory.NOT_FOUND
    assert recovery_manager.classify_failure("External service 503 error").category == FailureCategory.EXTERNAL_SERVICE
    assert recovery_manager.classify_failure("Tool error happened").category == FailureCategory.TOOL_ERROR
    assert recovery_manager.classify_failure("Random bizarre exception").category == FailureCategory.UNKNOWN

def test_retry_policy():
    # non-retryable tool blocks retry even if transient error
    registry._retry_policies["non_retryable_tool"] = {"retryable": False, "max_retries": 0}
    decision = recovery_manager.evaluate_recovery("non_retryable_tool", "network timeout", 0)
    assert decision.decision_type == DecisionType.FAIL
    
    # default tool policy is safe
    registry._retry_policies.pop("unknown_tool", None)
    decision2 = recovery_manager.evaluate_recovery("unknown_tool", "network timeout", 0)
    assert decision2.decision_type == DecisionType.FAIL
    
    # retryable tool allows retry
    registry._retry_policies["retryable_tool"] = {"retryable": True, "max_retries": 2}
    decision3 = recovery_manager.evaluate_recovery("retryable_tool", "network timeout", 0)
    assert decision3.decision_type == DecisionType.RETRY

def test_retry_limits():
    registry._retry_policies["retryable_tool"] = {"retryable": True, "max_retries": 2}
    
    # first retry
    assert recovery_manager.evaluate_recovery("retryable_tool", "timeout", 0).decision_type == DecisionType.RETRY
    # second retry
    assert recovery_manager.evaluate_recovery("retryable_tool", "timeout", 1).decision_type == DecisionType.RETRY
    # maximum reached
    assert recovery_manager.evaluate_recovery("retryable_tool", "timeout", 2).decision_type == DecisionType.FAIL
    
def test_side_effect_tool_is_not_retried():
    registry._retry_policies["send_email"] = {"retryable": False, "max_retries": 0}
    decision = recovery_manager.evaluate_recovery("send_email", "timeout", 0)
    assert decision.decision_type == DecisionType.FAIL

def test_orchestration_successful_retry(monkeypatch):
    session_id = "test_recovery"
    
    steps = [PlanStep(id=1, description="Step 1", tool_name="retryable_tool")]
    plan = orchestrator.create_plan(session_id, "Test Goal", steps)
    
    # Tool that fails on first try, succeeds on second
    call_count = [0]
    def mock_tool_func(*args, **kwargs):
        call_count[0] += 1
        if call_count[0] == 1:
            raise Exception("network timeout")
        return {"status": "success"}
        
    mock_tool = MagicMock(side_effect=mock_tool_func)
    mock_tool.__signature__ = __import__('inspect').signature(lambda session_id: None)
    
    monkeypatch.setattr(registry, "get_tool", MagicMock(return_value=mock_tool))
    monkeypatch.setattr(registry, "requires_confirmation", MagicMock(return_value=False))
    
    # Set retry policy
    registry._retry_policies["retryable_tool"] = {"retryable": True, "max_retries": 1}
    
    orchestrator.execute_next_step(session_id)
    
    assert plan.status == TaskState.COMPLETED
    assert call_count[0] == 2
    
    trace = trace_manager.get_trace(session_id)
    event_types = [e.event_type for e in trace.events]
    assert EventType.FAILURE_CLASSIFIED in event_types
    assert EventType.RETRY_DECIDED in event_types
    assert EventType.RETRY_STARTED in event_types
    assert EventType.TASK_COMPLETED in event_types

def test_orchestration_repeated_failure_eventually_fails(monkeypatch):
    session_id = "test_recovery"
    
    steps = [PlanStep(id=1, description="Step 1", tool_name="retryable_tool")]
    plan = orchestrator.create_plan(session_id, "Test Goal", steps)
    
    # Tool that always fails
    def mock_tool_func(*args, **kwargs):
        return {"status": "error", "error": "network timeout"}
        
    mock_tool = MagicMock(side_effect=mock_tool_func)
    mock_tool.__signature__ = __import__('inspect').signature(lambda session_id: None)
    
    monkeypatch.setattr(registry, "get_tool", MagicMock(return_value=mock_tool))
    monkeypatch.setattr(registry, "requires_confirmation", MagicMock(return_value=False))
    
    # Set retry policy
    registry._retry_policies["retryable_tool"] = {"retryable": True, "max_retries": 1}
    
    orchestrator.execute_next_step(session_id)
    
    assert plan.status == TaskState.FAILED
    assert plan.steps[0].retry_count == 1
    
    trace = trace_manager.get_trace(session_id)
    event_types = [e.event_type for e in trace.events]
    assert EventType.RECOVERY_FAILED in event_types
    assert EventType.TASK_FAILED in event_types

def test_dynamic_args_survive_retry(monkeypatch):
    session_id = "test_recovery"
    
    # First step succeeds
    step1 = PlanStep(id=1, description="Step 1", tool_name="success_tool")
    step1.result = {"run_id": 42}
    
    # Second step uses dynamic arg and retries
    step2 = PlanStep(id=2, description="Step 2", tool_name="retryable_tool", tool_args={"job_id": "$step_1.run_id"})
    
    plan = orchestrator.create_plan(session_id, "Test Goal", [step1, step2])
    plan.current_step_index = 1 # skip first step
    
    call_count = [0]
    called_args = []
    def mock_tool_func(*args, **kwargs):
        call_count[0] += 1
        called_args.append(kwargs)
        if call_count[0] == 1:
            raise Exception("timeout")
        return {"status": "success"}
        
    mock_tool = MagicMock(side_effect=mock_tool_func)
    mock_tool.__signature__ = __import__('inspect').signature(lambda job_id, session_id: None)
    
    monkeypatch.setattr(registry, "get_tool", MagicMock(return_value=mock_tool))
    monkeypatch.setattr(registry, "requires_confirmation", MagicMock(return_value=False))
    
    registry._retry_policies["retryable_tool"] = {"retryable": True, "max_retries": 2}
    
    orchestrator.execute_next_step(session_id)
    
    assert call_count[0] == 2
    assert called_args[0].get("job_id") == 42
    assert called_args[1].get("job_id") == 42
    assert plan.status == TaskState.COMPLETED

def test_unsafe_recovery_can_pause(monkeypatch):
    session_id = "test_recovery_pause"
    state_manager.clear_session(session_id)
    
    step = PlanStep(id=1, description="Step 1", tool_name="unsafe_tool")
    plan = orchestrator.create_plan(session_id, "Test Goal", [step])
    
    call_count = [0]
    def mock_tool_func(*args, **kwargs):
        call_count[0] += 1
        return {"status": "error", "error": "validation failed"}
        
    mock_tool = MagicMock(side_effect=mock_tool_func)
    mock_tool.__signature__ = __import__('inspect').signature(lambda session_id: None)
    
    monkeypatch.setattr(registry, "get_tool", MagicMock(return_value=mock_tool))
    monkeypatch.setattr(registry, "requires_confirmation", MagicMock(return_value=True))
    
    # 1. Execute -> Pauses because of requires_confirmation
    orchestrator.execute_next_step(session_id)
    assert plan.status == TaskState.WAITING_FOR_CONFIRMATION
    assert call_count[0] == 0
    
    # 2. Resume -> Rejects
    orchestrator.resume_after_confirmation(session_id, approved=False)
    assert plan.status == TaskState.FAILED
    assert call_count[0] == 0
    assert plan.steps[0].retry_count == 0

def test_resume_continues_and_fails_safely(monkeypatch):
    session_id = "test_recovery_resume"
    state_manager.clear_session(session_id)
    
    step = PlanStep(id=1, description="Step 1", tool_name="unsafe_tool")
    plan = orchestrator.create_plan(session_id, "Test Goal", [step])
    
    call_count = [0]
    def mock_tool_func(*args, **kwargs):
        call_count[0] += 1
        return {"status": "error", "error": "validation failed"}
        
    mock_tool = MagicMock(side_effect=mock_tool_func)
    mock_tool.__signature__ = __import__('inspect').signature(lambda session_id: None)
    
    monkeypatch.setattr(registry, "get_tool", MagicMock(return_value=mock_tool))
    monkeypatch.setattr(registry, "requires_confirmation", MagicMock(return_value=True))
    
    # 1. Execute -> Pauses
    orchestrator.execute_next_step(session_id)
    assert plan.status == TaskState.WAITING_FOR_CONFIRMATION
    
    # 2. Resume -> Approves -> Executes -> Fails verification -> Fails recovery
    orchestrator.resume_after_confirmation(session_id, approved=True)
    assert plan.status == TaskState.FAILED
    assert call_count[0] == 1
    assert plan.steps[0].retry_count == 0

def test_retry_counters_isolated_between_sessions(monkeypatch):
    session_id1 = "test_recovery_iso_1"
    session_id2 = "test_recovery_iso_2"
    
    plan1 = orchestrator.create_plan(session_id1, "Test Goal 1", [PlanStep(id=1, description="Step 1", tool_name="retryable_tool")])
    plan2 = orchestrator.create_plan(session_id2, "Test Goal 2", [PlanStep(id=1, description="Step 1", tool_name="retryable_tool")])
    
    # Tool that always fails
    def mock_tool_func(*args, **kwargs):
        return {"status": "error", "error": "timeout"}
        
    mock_tool = MagicMock(side_effect=mock_tool_func)
    mock_tool.__signature__ = __import__('inspect').signature(lambda session_id: None)
    
    monkeypatch.setattr(registry, "get_tool", MagicMock(return_value=mock_tool))
    monkeypatch.setattr(registry, "requires_confirmation", MagicMock(return_value=False))
    registry._retry_policies["retryable_tool"] = {"retryable": True, "max_retries": 1}
    
    orchestrator.execute_next_step(session_id1)
    # Reaches max retries, fails
    assert plan1.steps[0].retry_count == 1
    assert plan1.status == TaskState.FAILED
    
    orchestrator.execute_next_step(session_id2)
    # Session 2 gets its own retry count
    assert plan2.steps[0].retry_count == 1
    assert plan2.status == TaskState.FAILED
