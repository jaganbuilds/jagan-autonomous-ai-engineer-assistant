from typing import Optional
from pydantic import BaseModel
from app.agents.checkpoint import checkpoint_repository
from app.agents.orchestration import orchestrator, TaskState
from app.agents.execution_trace import trace_manager, EventType
from app.agents.state import state_manager

class OrchestrationRunStatus(BaseModel):
    run_id: str
    session_id: str
    goal: str
    status: TaskState
    current_step_index: int
    total_steps: int
    current_step_id: Optional[int] = None
    current_step_description: Optional[str] = None
    waiting_for_confirmation: bool
    created_at: str
    updated_at: str
    terminal: bool
    resumable: bool
    cancellation_allowed: bool

class OrchestrationRunController:
    """Provides safe lifecycle operations for an orchestration run."""
    
    def get_status(self, run_id: str, session_id: str) -> Optional[OrchestrationRunStatus]:
        checkpoint = checkpoint_repository.get_checkpoint(run_id)
        if not checkpoint:
            return None
            
        if checkpoint.session_id != session_id:
            return None
            
        trace_manager.add_event(session_id, EventType.RUN_STATUS_REQUESTED, result_summary={"run_id": run_id})
            
        plan = checkpoint.plan
        current_step = None
        if plan.current_step_index < len(plan.steps):
            current_step = plan.steps[plan.current_step_index]
            
        terminal = checkpoint.status in (TaskState.COMPLETED, TaskState.FAILED, TaskState.CANCELLED)
        cancellation_allowed = not terminal
        
        # Resumable if it's waiting, paused, or stuck in executing (which restore_orchestration will turn into FAILED safely, but we can allow the attempt)
        # But wait, if it's FAILED due to crash, it becomes FAILED. So it's not resumable.
        # It's resumable if it's WAITING_FOR_CONFIRMATION or PLANNING or VERIFYING (paused states).
        # We'll let restore_orchestration handle the strict logic, but we hint it here.
        resumable = not terminal
        
        return OrchestrationRunStatus(
            run_id=checkpoint.run_id,
            session_id=checkpoint.session_id,
            goal=checkpoint.goal,
            status=checkpoint.status,
            current_step_index=plan.current_step_index,
            total_steps=len(plan.steps),
            current_step_id=current_step.id if current_step else None,
            current_step_description=current_step.description if current_step else None,
            waiting_for_confirmation=checkpoint.status == TaskState.WAITING_FOR_CONFIRMATION,
            created_at=checkpoint.created_at,
            updated_at=checkpoint.updated_at,
            terminal=terminal,
            resumable=resumable,
            cancellation_allowed=cancellation_allowed
        )

    def resume(self, run_id: str, session_id: str) -> 'OrchestrationResult':
        """
        Resumes a paused or waiting orchestration.
        """
        from app.agents.orchestration_result import OrchestrationResultBuilder
        checkpoint = checkpoint_repository.get_checkpoint(run_id)
        if not checkpoint:
            return OrchestrationResultBuilder.build_error(run_id, session_id, "Checkpoint not found.")
            
        if checkpoint.session_id != session_id:
            return OrchestrationResultBuilder.build_error(run_id, session_id, "Session ID mismatch.")
            
        terminal = checkpoint.status in (TaskState.COMPLETED, TaskState.FAILED, TaskState.CANCELLED)
        if terminal:
            return OrchestrationResultBuilder.build_error(run_id, session_id, f"Run is already {checkpoint.status.value}.")
            
        plan = orchestrator.restore_orchestration(run_id, session_id)
        if not plan:
            trace_manager.add_event(session_id, EventType.RUN_CONTROL_REJECTED, error="Restore failed.")
            return OrchestrationResultBuilder.build_error(run_id, session_id, "Restore validation failed. Check traces.")
            
        trace_manager.add_event(session_id, EventType.RUN_RESUMED, result_summary={"run_id": run_id})
        
        # If the restored plan is FAILED (e.g. crash safety), we don't continue execution
        if plan.status == TaskState.FAILED:
            return OrchestrationResultBuilder.build(plan, session_id)
            
        # If waiting for confirmation, let the confirmation manager handle it when the user replies.
        if plan.status == TaskState.WAITING_FOR_CONFIRMATION:
            return OrchestrationResultBuilder.build(plan, session_id)
            
        # Continue execution
        return orchestrator.run_orchestration(session_id)

    def cancel(self, run_id: str, session_id: str) -> 'OrchestrationResult':
        """
        Cancels an orchestration run safely.
        """
        from app.agents.orchestration_result import OrchestrationResultBuilder
        checkpoint = checkpoint_repository.get_checkpoint(run_id)
        if not checkpoint:
            return OrchestrationResultBuilder.build_error(run_id, session_id, "Checkpoint not found.")
            
        if checkpoint.session_id != session_id:
            return OrchestrationResultBuilder.build_error(run_id, session_id, "Session ID mismatch.")
            
        terminal = checkpoint.status in (TaskState.COMPLETED, TaskState.FAILED, TaskState.CANCELLED)
        if terminal:
            return OrchestrationResultBuilder.build_error(run_id, session_id, f"Run is already {checkpoint.status.value}.")
            
        # Mark as cancelled
        checkpoint.status = TaskState.CANCELLED
        checkpoint.plan.status = TaskState.CANCELLED
        
        if checkpoint.plan.current_step_index < len(checkpoint.plan.steps):
            checkpoint.plan.steps[checkpoint.plan.current_step_index].status = TaskState.CANCELLED
            
        checkpoint_repository.create_or_update_checkpoint(checkpoint)
        
        # Also cancel active plan in memory if it matches
        active_plan = orchestrator.get_plan(session_id)
        if active_plan and active_plan.run_id == run_id:
            active_plan.status = TaskState.CANCELLED
            if active_plan.current_step_index < len(active_plan.steps):
                active_plan.steps[active_plan.current_step_index].status = TaskState.CANCELLED
            
            # Clear pending tool if any
            state_manager.clear_pending_tool(session_id)
            
        trace_manager.add_event(session_id, EventType.RUN_CANCELLED, result_summary={"run_id": run_id})
        trace_manager.add_event(session_id, EventType.TASK_FAILED, error="Run was explicitly cancelled.")
        
        return OrchestrationResultBuilder.build(checkpoint.plan, session_id)

run_controller = OrchestrationRunController()
