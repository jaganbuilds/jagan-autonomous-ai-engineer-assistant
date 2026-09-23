import pytest
from app.agents.orchestration_result import OrchestrationResultBuilder, OrchestrationResult, OrchestrationStepResult
from app.agents.orchestration import AgentPlan, PlanStep, TaskState
from app.agents.orchestration_response import OrchestrationResponseMapper

def test_completed_result():
    plan = AgentPlan(run_id="run1", goal="Goal 1", status=TaskState.COMPLETED, steps=[
        PlanStep(id=1, description="s1", status=TaskState.COMPLETED),
        PlanStep(id=2, description="s2", status=TaskState.COMPLETED, retry_count=1)
    ])
    result = OrchestrationResultBuilder.build(plan, "session1")
    
    assert result.status == "completed"
    assert result.success is True
    assert result.terminal is True
    assert result.resumable is False
    assert result.total_steps == 2
    assert result.completed_steps == 2
    assert result.retry_count == 1
    
    response = OrchestrationResponseMapper.map_to_natural_response(result)
    assert "completed successfully" in response.lower()

def test_waiting_confirmation_result():
    plan = AgentPlan(run_id="run2", goal="Goal 2", status=TaskState.WAITING_FOR_CONFIRMATION, steps=[
        PlanStep(id=1, description="s1", status=TaskState.WAITING_FOR_CONFIRMATION)
    ], current_step_index=0)
    result = OrchestrationResultBuilder.build(plan, "session2")
    
    assert result.status == "waiting_for_confirmation"
    assert result.success is False
    assert result.terminal is False
    assert result.resumable is True
    assert result.waiting_for_confirmation is True
    assert result.confirmation_required is True
    
    response = OrchestrationResponseMapper.map_to_natural_response(result)
    assert "paused" in response.lower()
    assert "step 1" in response.lower()

def test_failed_result():
    plan = AgentPlan(run_id="run3", goal="Goal 3", status=TaskState.FAILED, error="Some API failure", steps=[
        PlanStep(id=1, description="s1", status=TaskState.FAILED, error="Some API failure")
    ], current_step_index=0)
    result = OrchestrationResultBuilder.build(plan, "session3")
    
    assert result.status == "failed"
    assert result.success is False
    assert result.terminal is True
    assert result.resumable is False
    assert result.failed_steps == 1
    assert result.error == "Some API failure"
    assert "Some API failure" in result.message
    
    response = OrchestrationResponseMapper.map_to_natural_response(result)
    assert "failed" in response.lower()
    assert "some api failure" in response.lower()

def test_cancelled_result():
    plan = AgentPlan(run_id="run4", goal="Goal 4", status=TaskState.CANCELLED, steps=[
        PlanStep(id=1, description="s1", status=TaskState.CANCELLED)
    ], current_step_index=0)
    result = OrchestrationResultBuilder.build(plan, "session4")
    
    assert result.status == "cancelled"
    assert result.terminal is True
    assert result.resumable is False
    
    response = OrchestrationResponseMapper.map_to_natural_response(result)
    assert "cancelled" in response.lower()
    assert "step 1 rejected" in response.lower()

def test_build_error():
    result = OrchestrationResultBuilder.build_error("run5", "session5", "Restore failed")
    assert result.status == "failed"
    assert result.terminal is True
    assert result.resumable is False
    assert result.error == "Restore failed"
    
def test_secrets_sanitized():
    plan = AgentPlan(run_id="run6", goal="Goal", status=TaskState.COMPLETED, steps=[
        PlanStep(id=1, description="s1", status=TaskState.COMPLETED, tool_args={"api_key": "secret123"})
    ])
    result = OrchestrationResultBuilder.build(plan, "session6")
    dump = result.model_dump()
    
    # tool_args should NOT be present in the step result dump
    assert "tool_args" not in dump["steps"][0]
    
    # The step result shouldn't contain raw tool payload
    assert result.steps[0].result_summary is None

def test_json_serializable():
    plan = AgentPlan(run_id="run7", goal="Goal", status=TaskState.COMPLETED, steps=[])
    result = OrchestrationResultBuilder.build(plan, "session7")
    
    import json
    json_str = result.model_dump_json()
    assert "run7" in json_str
