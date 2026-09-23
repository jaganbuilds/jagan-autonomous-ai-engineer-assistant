from typing import List, Optional
from pydantic import BaseModel

class OrchestrationStepResult(BaseModel):
    step_id: int
    description: str
    tool_name: Optional[str]
    status: str
    attempts: int
    retry_count: int
    success: bool
    error: Optional[str] = None
    result_summary: Optional[dict] = None

class OrchestrationResult(BaseModel):
    run_id: str
    session_id: str
    goal: str
    status: str
    success: bool
    terminal: bool
    resumable: bool
    waiting_for_confirmation: bool
    current_step: int
    total_steps: int
    completed_steps: int
    failed_steps: int
    skipped_steps: int
    retry_count: int
    replan_count: int
    confirmation_required: bool
    next_action: Optional[str] = None
    message: Optional[str] = None
    error: Optional[str] = None
    steps: List[OrchestrationStepResult] = []
    summary: dict = {}

class OrchestrationResultBuilder:
    @staticmethod
    def build(plan, session_id: str) -> OrchestrationResult:
        from app.agents.orchestration import TaskState
        from app.agents.execution_trace import trace_manager
        
        terminal = plan.status in (TaskState.COMPLETED, TaskState.FAILED, TaskState.CANCELLED)
        resumable = plan.status in (TaskState.WAITING_FOR_CONFIRMATION, TaskState.PLANNING, TaskState.VERIFYING)
        waiting_for_confirmation = plan.status == TaskState.WAITING_FOR_CONFIRMATION
        
        success = plan.status == TaskState.COMPLETED
        
        steps = []
        completed_steps = 0
        failed_steps = 0
        skipped_steps = 0
        total_retries = 0
        
        for step in plan.steps:
            step_success = step.status == TaskState.COMPLETED
            if step_success:
                completed_steps += 1
            elif step.status == TaskState.FAILED:
                failed_steps += 1
                
            total_retries += step.retry_count
            
            steps.append(OrchestrationStepResult(
                step_id=step.id,
                description=step.description,
                tool_name=step.tool_name,
                status=step.status.value,
                attempts=step.retry_count + (1 if step.status != TaskState.PLANNING else 0),
                retry_count=step.retry_count,
                success=step_success,
                error=step.error,
                result_summary=None # keep it safe, don't dump raw tool results
            ))
            
        next_action = None
        message = None
        
        if plan.status == TaskState.COMPLETED:
            message = "Orchestration completed successfully."
        elif plan.status == TaskState.WAITING_FOR_CONFIRMATION:
            next_action = "human_confirmation"
            message = "Waiting for human confirmation."
        elif plan.status == TaskState.FAILED:
            message = f"Orchestration failed: {plan.error}"
        elif plan.status == TaskState.CANCELLED:
            message = "Orchestration cancelled."
            
        trace_summary = trace_manager.generate_run_summary(session_id)
        replan_count = trace_summary.get("replans", 0) if isinstance(trace_summary, dict) else 0
        
        return OrchestrationResult(
            run_id=plan.run_id,
            session_id=session_id,
            goal=plan.goal,
            status=plan.status.value,
            success=success,
            terminal=terminal,
            resumable=resumable,
            waiting_for_confirmation=waiting_for_confirmation,
            current_step=plan.current_step_index,
            total_steps=len(plan.steps),
            completed_steps=completed_steps,
            failed_steps=failed_steps,
            skipped_steps=skipped_steps,
            retry_count=total_retries,
            replan_count=replan_count,
            confirmation_required=waiting_for_confirmation,
            next_action=next_action,
            message=message,
            error=plan.error,
            steps=steps,
            summary=trace_summary if isinstance(trace_summary, dict) else {}
        )

    @staticmethod
    def build_error(run_id: str, session_id: str, error_message: str) -> OrchestrationResult:
        return OrchestrationResult(
            run_id=run_id,
            session_id=session_id,
            goal="",
            status="failed",
            success=False,
            terminal=True,
            resumable=False,
            waiting_for_confirmation=False,
            current_step=0,
            total_steps=0,
            completed_steps=0,
            failed_steps=0,
            skipped_steps=0,
            retry_count=0,
            replan_count=0,
            confirmation_required=False,
            next_action=None,
            message=error_message,
            error=error_message,
            steps=[],
            summary={}
        )
