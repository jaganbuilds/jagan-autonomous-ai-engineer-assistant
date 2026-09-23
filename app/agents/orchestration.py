import logging
from enum import Enum
from typing import List, Dict, Any, Optional
import uuid
from pydantic import BaseModel, Field

from app.tools.registry import registry
from app.agents.state import state_manager, SessionStatus
from app.agents.confirmation import confirmation_manager

logger = logging.getLogger(__name__)

class TaskState(str, Enum):
    PLANNING = "planning"
    EXECUTING = "executing"
    VERIFYING = "verifying"
    WAITING_FOR_CONFIRMATION = "waiting_for_confirmation"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"

class PlanStep(BaseModel):
    id: int
    description: str
    tool_name: Optional[str] = None
    tool_args: Dict[str, Any] = Field(default_factory=dict)
    dependencies: List[int] = Field(default_factory=list)
    status: TaskState = TaskState.PLANNING
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    retry_count: int = 0

class AgentPlan(BaseModel):
    run_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    goal: str
    workflow_type: str = "general"
    steps: List[PlanStep] = Field(default_factory=list)
    current_step_index: int = 0
    status: TaskState = TaskState.PLANNING
    error: Optional[str] = None

class AgentOrchestrator:
    """
    A minimal, deterministic orchestration layer representing:
    Goal -> Plan -> Execution -> Verification -> Next Decision -> Completion
    """
    def __init__(self):
        # We store plans in memory, keyed by session_id, mapping to AgentPlan.
        # This keeps it separate from the generic SessionState for now, 
        # though it uses session_id as the linkage.
        self._plans: Dict[str, AgentPlan] = {}

    def create_plan(self, session_id: str, goal: str, steps: List[PlanStep]) -> AgentPlan:
        """Creates a new orchestrated plan."""
        plan = AgentPlan(goal=goal, steps=steps)
        self._plans[session_id] = plan
        state_manager.update_status(session_id, SessionStatus.PROCESSING)
        
        from app.agents.execution_trace import trace_manager, EventType
        # Clear any previous trace for the session when starting a new plan
        trace_manager.clear_trace(session_id)
        trace = trace_manager.get_trace(session_id)
        trace.goal = goal
        trace_manager.add_event(session_id, EventType.PLAN_CREATED, result_summary={"total_steps": len(steps)})
        
        self._checkpoint(session_id, plan)
        
        return plan

    def get_plan(self, session_id: str) -> Optional[AgentPlan]:
        """Gets the active plan for a session."""
        return self._plans.get(session_id)

    def _checkpoint(self, session_id: str, plan: AgentPlan):
        """Persists the current orchestration state safely."""
        from app.agents.checkpoint import OrchestrationCheckpoint, checkpoint_repository
        
        checkpoint = OrchestrationCheckpoint(
            run_id=plan.run_id,
            session_id=session_id,
            goal=plan.goal,
            plan=plan,
            status=plan.status
        )
        checkpoint_repository.create_or_update_checkpoint(checkpoint)
        
        from app.agents.execution_trace import trace_manager, EventType
        # Add trace if tracking is enabled. We don't want to clutter normal trace with continuous checkpoints,
        # but the spec asks for "CHECKPOINT_CREATED" in execution trace.
        # Let's add it carefully.
        trace_manager.add_event(session_id, EventType.CHECKPOINT_CREATED)

    def restore_orchestration(self, run_id: str, session_id: str, owner_id: str = "default_owner") -> Optional[AgentPlan]:
        """Restores a paused or interrupted orchestration session."""
        from app.agents.checkpoint import checkpoint_repository, CURRENT_SCHEMA_VERSION
        from app.agents.execution_trace import trace_manager, EventType
        
        checkpoint = checkpoint_repository.get_checkpoint(run_id)
        if not checkpoint:
            trace_manager.add_event(session_id, EventType.RESTORE_VALIDATION_FAILED, error="Checkpoint not found.")
            return None
            
        if checkpoint.session_id != session_id:
            trace_manager.add_event(session_id, EventType.RESTORE_VALIDATION_FAILED, error="Session ID mismatch.")
            return None
            
        if checkpoint.owner_id != owner_id:
            trace_manager.add_event(session_id, EventType.RESTORE_VALIDATION_FAILED, error="Owner ID mismatch.")
            return None
            
        if checkpoint.schema_version != CURRENT_SCHEMA_VERSION:
            trace_manager.add_event(session_id, EventType.RESTORE_VALIDATION_FAILED, error="Unsupported schema version.")
            return None
            
        # Crash safety: If it was executing when the process crashed, we don't automatically retry
        if checkpoint.status == TaskState.EXECUTING:
            # We don't know if the side-effect completed.
            # Convert status to failed or requires review.
            trace_manager.add_event(session_id, EventType.RECOVERY_REQUIRES_REVIEW, error="System crashed during execution. Manual review required.")
            checkpoint.plan.status = TaskState.FAILED
            checkpoint.status = TaskState.FAILED
            if checkpoint.plan.current_step_index < len(checkpoint.plan.steps):
                checkpoint.plan.steps[checkpoint.plan.current_step_index].status = TaskState.FAILED
                checkpoint.plan.steps[checkpoint.plan.current_step_index].error = "System crashed during execution. Automatic retry disabled for side-effect safety."
            
        # Restore into memory
        self._plans[session_id] = checkpoint.plan
        
        # Restore pending tool if waiting for confirmation
        if checkpoint.status == TaskState.WAITING_FOR_CONFIRMATION:
            if checkpoint.plan.current_step_index < len(checkpoint.plan.steps):
                step = checkpoint.plan.steps[checkpoint.plan.current_step_index]
                state_manager.set_pending_tool(session_id, step.tool_name, step.tool_args)
        else:
            if checkpoint.status == TaskState.FAILED:
                session_status = SessionStatus.ERROR
            elif checkpoint.status == TaskState.CANCELLED:
                session_status = SessionStatus.CANCELLED
            elif checkpoint.status == TaskState.COMPLETED:
                session_status = SessionStatus.COMPLETED
            elif checkpoint.status in (TaskState.PLANNING, TaskState.EXECUTING, TaskState.VERIFYING):
                session_status = SessionStatus.PROCESSING
            else:
                session_status = SessionStatus.IDLE
                
            state_manager.update_status(session_id, session_status)
        
        trace_manager.add_event(session_id, EventType.CHECKPOINT_RESTORED, result_summary={"run_id": run_id})
        
        return checkpoint.plan

    def resume_latest_workflow(self, session_id: str, owner_id: str = "default_owner") -> Optional['OrchestrationResult']:
        """
        Loads the latest valid checkpoint for the session/owner and resumes execution safely.
        """
        if session_id in self._plans and self._plans[session_id].status in (TaskState.PLANNING, TaskState.EXECUTING, TaskState.VERIFYING):
            from app.agents.execution_trace import trace_manager, EventType
            trace_manager.add_event(session_id, EventType.RESTORE_VALIDATION_FAILED, error="Concurrent resume protection: Plan is already actively running in memory.")
            return None
            
        from app.agents.checkpoint import checkpoint_repository
        
        checkpoint = checkpoint_repository.get_latest_checkpoint_for_session(session_id)
        if not checkpoint:
            return None
            
        plan = self.restore_orchestration(checkpoint.run_id, session_id, owner_id)
        if not plan:
            return None
            
        # If it was restored successfully and is ready to run, run it!
        # But wait, if it was restored into WAITING_FOR_CONFIRMATION, run_orchestration will just return the state.
        # If it was restored into PLANNING (e.g. ready for next step), run_orchestration will continue executing!
        if plan.status in (TaskState.PLANNING, TaskState.WAITING_FOR_CONFIRMATION, TaskState.FAILED, TaskState.CANCELLED, TaskState.COMPLETED):
            return self.run_orchestration(session_id)
            
        return None

    def run_orchestration(self, session_id: str) -> 'OrchestrationResult':
        """
        Runs the orchestration loop for the active plan until it hits a terminal or paused state.
        Returns the structured OrchestrationResult.
        """
        plan = self.get_plan(session_id)
        if not plan:
            raise ValueError(f"No active plan found for session {session_id}")
            
        while plan.status == TaskState.PLANNING:
            plan = self.execute_next_step(session_id)
            
        from app.agents.orchestration_result import OrchestrationResultBuilder
        return OrchestrationResultBuilder.build(plan, session_id)

    def execute_next_step(self, session_id: str) -> AgentPlan:
        """
        Executes the current step in the plan.
        Moves state through EXECUTING -> VERIFYING -> COMPLETED/FAILED.
        """
        plan = self.get_plan(session_id)
        if not plan:
            raise ValueError(f"No active plan found for session {session_id}")

        if plan.status in (TaskState.COMPLETED, TaskState.FAILED, TaskState.WAITING_FOR_CONFIRMATION):
            return plan

        if plan.current_step_index >= len(plan.steps):
            plan.status = TaskState.COMPLETED
            state_manager.update_status(session_id, SessionStatus.COMPLETED)
            return plan

        step = plan.steps[plan.current_step_index]
        
        # Verify the step has not already completed
        if step.status == TaskState.COMPLETED:
            self._advance_step(session_id, plan)
            return plan
            
        # Verify dependencies are completed
        for dep_id in step.dependencies:
            dep_step = next((s for s in plan.steps if s.id == dep_id), None)
            if not dep_step or dep_step.status != TaskState.COMPLETED:
                self._fail_step(plan, step, f"Dependency {dep_id} is not completed.")
                return plan
        
        # Move to executing
        plan.status = TaskState.EXECUTING
        step.status = TaskState.EXECUTING
        
        # Resolve tool
        if not step.tool_name:
            # A step without a tool is just a logical/manual step; skip it as completed
            step.status = TaskState.COMPLETED
            self._advance_step(session_id, plan)
            return plan

        tool_func = registry.get_tool(step.tool_name)
        if not tool_func:
            self._fail_step(plan, step, f"Tool {step.tool_name} not found in registry.")
            return plan

        # Check confirmation boundary
        from app.agents.decision import decision_engine, DecisionType
        if registry.requires_confirmation(step.tool_name):
            decision = decision_engine.make_decision(
                plan=plan,
                step=step,
                verification_passed=None,
                requires_confirmation=True
            )
            if decision.decision_type == DecisionType.WAIT_FOR_CONFIRMATION:
                plan.status = TaskState.WAITING_FOR_CONFIRMATION
                step.status = TaskState.WAITING_FOR_CONFIRMATION
                
                from app.agents.execution_trace import trace_manager, EventType
                trace_manager.add_event(session_id, EventType.WAITING_FOR_CONFIRMATION, step_id=step.id, tool_name=step.tool_name)
                
                # Delegate to existing confirmation system
                state_manager.set_pending_tool(session_id, step.tool_name, step.tool_args)
                self._checkpoint(session_id, plan)
                return plan

        return self._execute_and_advance(session_id, plan, step, tool_func)

    def resume_after_confirmation(self, session_id: str, approved: bool, native_result: Optional[Dict[str, Any]] = None) -> AgentPlan:
        """
        Resumes an orchestration plan that was paused for human confirmation.
        """
        plan = self.get_plan(session_id)
        if not plan:
            raise ValueError(f"No active plan found for session {session_id}")

        if plan.status != TaskState.WAITING_FOR_CONFIRMATION:
            raise ValueError(f"Plan is not waiting for confirmation. Status: {plan.status}")

        step = plan.steps[plan.current_step_index]
        
        from app.agents.execution_trace import trace_manager, EventType
        
        if not approved:
            trace_manager.add_event(session_id, EventType.CONFIRMATION_RECEIVED, step_id=step.id, tool_name=step.tool_name, result_summary={"approved": False})
            self._fail_step(plan, step, "Action rejected by human.")
            state_manager.update_status(session_id, SessionStatus.IDLE)
            return plan

        # The confirmation is approved.
        trace_manager.add_event(session_id, EventType.CONFIRMATION_RECEIVED, step_id=step.id, tool_name=step.tool_name, result_summary={"approved": True})
        self._checkpoint(session_id, plan)
        
        if native_result is not None:
            # The tool was already executed natively by the confirmation manager
            step.result = native_result
            return self._verify_and_decide(session_id, plan, step, native_result)
        else:
            state_manager.clear_pending_tool(session_id)
            
        tool_func = registry.get_tool(step.tool_name)
        if not tool_func:
            self._fail_step(plan, step, f"Tool {step.tool_name} not found in registry during resume.")
            return plan

        # Safely execute the exact authorized tool
        return self._execute_and_advance(session_id, plan, step, tool_func)

    def _execute_and_advance(self, session_id: str, plan: AgentPlan, step: PlanStep, tool_func) -> AgentPlan:
        """Executes the tool, runs verification, and evaluates decisions safely."""
        from app.agents.execution_trace import trace_manager, EventType
        
        try:
            trace_manager.add_event(session_id, EventType.STEP_STARTED, step_id=step.id, tool_name=step.tool_name)
            
            # We inject session_id implicitly if the tool accepts it, mirroring ManagerAgent
            args = dict(step.tool_args)
            
            # Simple variable chaining: "$step_N.key"
            for k, v in args.items():
                if isinstance(v, str) and v.startswith("$step_"):
                    # e.g. "$step_1.run_id"
                    parts = v.replace("$step_", "").split(".", 1)
                    if len(parts) == 2:
                        ref_id = int(parts[0])
                        ref_key = parts[1]
                        for prev_step in plan.steps:
                            if prev_step.id == ref_id and prev_step.result and isinstance(prev_step.result, dict):
                                args[k] = prev_step.result.get(ref_key, v)
                                break
            
            import inspect
            sig = inspect.signature(tool_func)
            if "session_id" in sig.parameters and "session_id" not in args:
                args["session_id"] = session_id
                
            result = tool_func(**args)
            if isinstance(result, str):
                import json
                try:
                    step.result = json.loads(result)
                except Exception:
                    step.result = {"raw": result}
            else:
                step.result = result
            
            summary = {"status": step.result.get("status")} if isinstance(step.result, dict) else None
            trace_manager.add_event(session_id, EventType.TOOL_EXECUTED, step_id=step.id, tool_name=step.tool_name, result_summary=summary)
            
            # Move to verification
            plan.status = TaskState.VERIFYING
            step.status = TaskState.VERIFYING
            
            return self._verify_and_decide(session_id, plan, step, step.result)
            
        except Exception as e:
            logger.exception("Error during orchestrator execution")
            
            from app.agents.execution_trace import trace_manager, EventType
            trace_manager.add_event(session_id, EventType.STEP_FAILED, step_id=step.id, error=str(e))
            
            from app.agents.recovery import recovery_manager
            from app.agents.decision import DecisionType
            recovery_decision = recovery_manager.evaluate_recovery(step.tool_name, str(e), step.retry_count)
            
            trace_manager.add_event(session_id, EventType.FAILURE_CLASSIFIED, step_id=step.id, result_summary={"decision": recovery_decision.decision_type.value, "reason": recovery_decision.reason})
            
            if recovery_decision.decision_type == DecisionType.RETRY:
                if plan.workflow_type != "coding":
                    step.retry_count += 1
                    trace_manager.add_event(session_id, EventType.RETRY_DECIDED, step_id=step.id)
                    trace_manager.add_event(session_id, EventType.RETRY_STARTED, step_id=step.id)
                    self._checkpoint(session_id, plan)
                    return self._execute_and_advance(session_id, plan, step, tool_func)
                else:
                    trace_manager.add_event(session_id, EventType.RECOVERY_FAILED, step_id=step.id, error="Retry disabled for coding tasks.")
                
            self._fail_step(plan, step, str(e))
            
        return plan

    def _verify_and_decide(self, session_id: str, plan: AgentPlan, step: PlanStep, result: Any) -> AgentPlan:
        """Runs verification and evaluates decisions safely based on a tool execution result."""
        from app.agents.execution_trace import trace_manager, EventType
        
        # Verify
        verification_passed = self.verify_step_result(step, result)
        trace_manager.add_event(session_id, EventType.STEP_VERIFIED, step_id=step.id, result_summary={"passed": verification_passed})
        
        # Make decision
        from app.agents.decision import decision_engine, DecisionType
        decision = decision_engine.make_decision(
            plan=plan,
            step=step,
            verification_passed=verification_passed,
            requires_confirmation=False # It was evaluated before execute
        )
        
        trace_manager.add_event(session_id, EventType.DECISION_MADE, step_id=step.id, message=decision.decision_type.value)
        
        # Intercept FAIL or REPLAN for recovery, but only if there is an error
        if decision.decision_type in (DecisionType.FAIL, DecisionType.REPLAN):
            error_msg = None
            if isinstance(step.result, dict):
                error_msg = step.result.get("error")
            if not error_msg:
                error_msg = decision.error
                
            if error_msg:
                from app.agents.recovery import recovery_manager
                recovery_decision = recovery_manager.evaluate_recovery(step.tool_name, error_msg, step.retry_count)
                
                trace_manager.add_event(session_id, EventType.FAILURE_CLASSIFIED, step_id=step.id, result_summary={"decision": recovery_decision.decision_type.value, "reason": recovery_decision.reason})
                
                if recovery_decision.decision_type == DecisionType.RETRY:
                    if plan.workflow_type != "coding":
                        step.retry_count += 1
                        trace_manager.add_event(session_id, EventType.RETRY_DECIDED, step_id=step.id)
                        trace_manager.add_event(session_id, EventType.RETRY_STARTED, step_id=step.id)
                        self._checkpoint(session_id, plan)
                        
                        tool_func = registry.get_tool(step.tool_name)
                        return self._execute_and_advance(session_id, plan, step, tool_func)
                    else:
                        decision.decision_type = DecisionType.FAIL
                        trace_manager.add_event(session_id, EventType.RECOVERY_FAILED, step_id=step.id, error="Retry disabled for coding tasks.")
                else:
                    decision.decision_type = recovery_decision.decision_type
                    if recovery_decision.decision_type == DecisionType.FAIL:
                        trace_manager.add_event(session_id, EventType.RECOVERY_FAILED, step_id=step.id)
        
        # Apply decision
        if decision.decision_type == DecisionType.CONTINUE:
            step.status = TaskState.COMPLETED
            plan.current_step_index += 1
            trace_manager.add_event(session_id, EventType.STEP_COMPLETED, step_id=step.id)
            self._checkpoint(session_id, plan)
            return self.execute_next_step(session_id)
        elif decision.decision_type == DecisionType.COMPLETE:
            step.status = TaskState.COMPLETED
            plan.status = TaskState.COMPLETED
            trace_manager.add_event(session_id, EventType.STEP_COMPLETED, step_id=step.id)
            trace_manager.add_event(session_id, EventType.TASK_COMPLETED)
            state_manager.update_status(session_id, SessionStatus.COMPLETED)
            self._checkpoint(session_id, plan)
        elif decision.decision_type == DecisionType.WAIT_FOR_CONFIRMATION:
            step.status = TaskState.WAITING_FOR_CONFIRMATION
            plan.status = TaskState.WAITING_FOR_CONFIRMATION
            trace_manager.add_event(session_id, EventType.WAITING_FOR_CONFIRMATION, step_id=step.id, tool_name=step.tool_name)
            state_manager.update_status(session_id, SessionStatus.WAITING_FOR_CONFIRMATION)
            self._checkpoint(session_id, plan)
        elif decision.decision_type == DecisionType.REPLAN:
            if plan.workflow_type == "coding":
                trace_manager.add_event(session_id, EventType.RECOVERY_FAILED, step_id=step.id, error="Replan disabled for coding tasks.")
                self._fail_step(plan, step, f"Execution failed. {decision.error}")
                self._checkpoint(session_id, plan)
                return plan
                
            trace_manager.add_event(session_id, EventType.REPLAN_OCCURRED, step_id=step.id)
            from app.agents.decision import AgentReplanner
            replanner = AgentReplanner()
            old_len = len(plan.steps)
            plan = replanner.replan(plan, step, result)
            if len(plan.steps) < old_len:
                if plan.current_step_index >= len(plan.steps) - 1:
                    step.status = TaskState.COMPLETED
                    plan.status = TaskState.COMPLETED
                    trace_manager.add_event(session_id, EventType.STEP_COMPLETED, step_id=step.id)
                    trace_manager.add_event(session_id, EventType.TASK_COMPLETED)
                    state_manager.update_status(session_id, SessionStatus.COMPLETED)
            else:
                self._fail_step(plan, step, f"Replan failed to recover. Original error: {decision.error}")
            self._checkpoint(session_id, plan)
        elif decision.decision_type == DecisionType.FAIL:
            self._fail_step(plan, step, f"Execution or verification failed. {decision.error}")
            self._checkpoint(session_id, plan)
            
        return plan

    def verify_step_result(self, step: PlanStep, result: Any) -> bool:
        """
        Minimal deterministic verification boundary.
        Checks if the tool returned a structured dictionary indicating success.
        """
        if isinstance(result, dict):
            status = result.get("status")
            if status in ("error", "failed", "job_not_found", "email_draft_unavailable"):
                return False
            # If no status field is present, assume success if no exception was raised.
            return True
        # If it returns a non-dict (like a list or string), we assume success if no exception was raised
        return True

    def _advance_step(self, session_id: str, plan: AgentPlan):
        """Advances the plan to the next step, completing the plan if finished."""
        plan.current_step_index += 1
        if plan.current_step_index >= len(plan.steps):
            plan.status = TaskState.COMPLETED
            state_manager.update_status(session_id, SessionStatus.COMPLETED)
        else:
            plan.status = TaskState.PLANNING

    def _fail_step(self, plan: AgentPlan, step: PlanStep, error_msg: str):
        """Marks the step and the plan as failed."""
        from app.agents.execution_trace import trace_manager, EventType
        
        session_id = next((sid for sid, p in self._plans.items() if p is plan), "default")
        
        step.status = TaskState.FAILED
        step.error = error_msg
        trace_manager.add_event(session_id, EventType.STEP_FAILED, step_id=step.id, error=error_msg)
        
        plan.status = TaskState.FAILED
        plan.error = error_msg
        trace_manager.add_event(session_id, EventType.TASK_FAILED, error=error_msg)
        
        state_manager.update_status(session_id, SessionStatus.ERROR)
        self._checkpoint(session_id, plan)

# Singleton instance
orchestrator = AgentOrchestrator()
