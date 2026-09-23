from enum import Enum
from typing import Optional, Any
from pydantic import BaseModel
from app.agents.orchestration import AgentPlan, PlanStep, TaskState

class DecisionType(str, Enum):
    CONTINUE = "continue"
    COMPLETE = "complete"
    WAIT_FOR_CONFIRMATION = "wait_for_confirmation"
    FAIL = "fail"
    REPLAN = "replan"
    RETRY = "retry"

class AgentDecision(BaseModel):
    decision_type: DecisionType
    reason: str
    current_step_id: int
    next_step_id: Optional[int] = None
    error: Optional[str] = None

class AgentReplanner:
    """
    A minimal, deterministic replanner.
    Handles explicitly defined recoverable errors.
    """
    def replan(self, plan: AgentPlan, step: PlanStep, verification_result: Any) -> AgentPlan:
        # Example condition for replanning
        # If discovery tool found 0 jobs, we could normally FAIL or REPLAN.
        # For this step, we just return the plan as-is if no recovery is found, or we can truncate the plan.
        
        # We handle the 'no jobs found' scenario deterministically here.
        if step.tool_name == "discover_new_jobs" and isinstance(verification_result, dict):
            new_jobs = verification_result.get("new_jobs", 0)
            if new_jobs == 0:
                # Truncate the plan and mark it COMPLETE early since there's nothing to process
                plan.steps = plan.steps[:plan.current_step_index + 1]
                return plan
                
        # If no specific rule matched, we just return the plan, and it will FAIL because it wasn't recovered
        return plan

class AgentDecisionEngine:
    """
    Determines what to do after a step finishes executing and verifying.
    """
    def __init__(self):
        self.replanner = AgentReplanner()

    def make_decision(
        self, 
        plan: AgentPlan, 
        step: PlanStep, 
        verification_passed: bool, 
        requires_confirmation: bool
    ) -> AgentDecision:
        
        if requires_confirmation:
            return AgentDecision(
                decision_type=DecisionType.WAIT_FOR_CONFIRMATION,
                reason="The tool requires explicit human confirmation.",
                current_step_id=step.id
            )
            
        if isinstance(step.result, dict) and step.result.get("status") == "waiting_for_confirmation":
            return AgentDecision(
                decision_type=DecisionType.WAIT_FOR_CONFIRMATION,
                reason="The tool paused natively for human confirmation.",
                current_step_id=step.id
            )
            
        if step.status == TaskState.FAILED:
            return AgentDecision(
                decision_type=DecisionType.FAIL,
                reason="The tool execution encountered an unhandled exception.",
                current_step_id=step.id,
                error=step.error
            )
            
        if not verification_passed:
            # Here we introduce the structural boundary for REPLAN
            # If verification failed, we could ask the replanner to fix it.
            # We trigger a REPLAN decision.
            return AgentDecision(
                decision_type=DecisionType.REPLAN,
                reason="Verification failed, attempting to replan.",
                current_step_id=step.id,
                error="Verification failure."
            )
            
        # Specific business rule checks that might override standard flow (e.g. 0 jobs found)
        # Even if verification 'passed', we can choose to REPLAN to truncate the plan
        if step.tool_name == "discover_new_jobs" and isinstance(step.result, dict):
            if step.result.get("new_jobs", 0) == 0:
                return AgentDecision(
                    decision_type=DecisionType.REPLAN,
                    reason="No new jobs found, replanning to truncate workflow.",
                    current_step_id=step.id
                )

        if plan.current_step_index == len(plan.steps) - 1:
            return AgentDecision(
                decision_type=DecisionType.COMPLETE,
                reason="All steps in the plan have been executed successfully.",
                current_step_id=step.id
            )
            
        return AgentDecision(
            decision_type=DecisionType.CONTINUE,
            reason="Step completed successfully, continuing to next step.",
            current_step_id=step.id,
            next_step_id=plan.steps[plan.current_step_index + 1].id
        )

decision_engine = AgentDecisionEngine()
