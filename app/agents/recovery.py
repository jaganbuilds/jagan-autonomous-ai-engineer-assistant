from enum import Enum
from typing import Dict, Any, Optional
from pydantic import BaseModel

from app.tools.registry import registry
from app.agents.decision import DecisionType

class FailureCategory(str, Enum):
    TRANSIENT = "transient"
    VALIDATION = "validation"
    AUTHENTICATION = "authentication"
    AUTHORIZATION = "authorization"
    NOT_FOUND = "not_found"
    RATE_LIMITED = "rate_limited"
    EXTERNAL_SERVICE = "external_service"
    TOOL_ERROR = "tool_error"
    UNKNOWN = "unknown"

class FailureClassification(BaseModel):
    category: FailureCategory
    retryable: bool
    reason: str

class RecoveryDecision(BaseModel):
    decision_type: DecisionType
    reason: str
    delay_seconds: int = 0

class RecoveryManager:
    """
    Evaluates execution failures deterministically and decides if a retry is safe.
    """
    def classify_failure(self, error_msg: str) -> FailureClassification:
        error_lower = str(error_msg).lower()
        
        # Deterministic rules based on error text
        if "rate limit" in error_lower or "429" in error_lower or "too many requests" in error_lower:
            return FailureClassification(category=FailureCategory.RATE_LIMITED, retryable=True, reason="Rate limit hit")
            
        if "timeout" in error_lower or "connection reset" in error_lower or "transient" in error_lower or "network" in error_lower:
            return FailureClassification(category=FailureCategory.TRANSIENT, retryable=True, reason="Transient network error")
            
        if "auth" in error_lower or "credentials" in error_lower or "token" in error_lower or "401" in error_lower or "403" in error_lower:
            # If it's authorization/authentication, it's NOT safe to retry blindly
            category = FailureCategory.AUTHORIZATION if "403" in error_lower else FailureCategory.AUTHENTICATION
            return FailureClassification(category=category, retryable=False, reason="Auth failure is not retryable")
            
        if "not found" in error_lower or "404" in error_lower:
            return FailureClassification(category=FailureCategory.NOT_FOUND, retryable=False, reason="Resource not found")
            
        if "validation" in error_lower or "invalid" in error_lower or "missing" in error_lower or "schema" in error_lower:
            return FailureClassification(category=FailureCategory.VALIDATION, retryable=False, reason="Validation error")
            
        if "500" in error_lower or "502" in error_lower or "503" in error_lower or "external" in error_lower:
            return FailureClassification(category=FailureCategory.EXTERNAL_SERVICE, retryable=True, reason="External service error")
            
        if "tool" in error_lower:
            return FailureClassification(category=FailureCategory.TOOL_ERROR, retryable=False, reason="Tool execution error")
            
        return FailureClassification(category=FailureCategory.UNKNOWN, retryable=False, reason="Unknown error")

    def evaluate_recovery(self, tool_name: str, error_msg: str, current_retry_count: int) -> RecoveryDecision:
        classification = self.classify_failure(error_msg)
        
        if not classification.retryable:
            return RecoveryDecision(
                decision_type=DecisionType.FAIL, 
                reason=f"Failure classification {classification.category.value} is not safe to retry: {classification.reason}"
            )
            
        policy = registry.get_retry_policy(tool_name)
        if not policy["retryable"]:
            return RecoveryDecision(
                decision_type=DecisionType.FAIL,
                reason=f"Tool {tool_name} is not explicitly marked as safe for retry."
            )
            
        if current_retry_count >= policy["max_retries"]:
            return RecoveryDecision(
                decision_type=DecisionType.FAIL,
                reason=f"Max retries ({policy['max_retries']}) reached for tool {tool_name}."
            )
            
        # All conditions met: it's a retryable error, the tool is safe to retry, and we haven't hit the limit.
        # Note: If it's an action that is explicitly unsafe, it should have retryable=False in the registry.
        # By default registry sets retryable=False, max_retries=0.
        return RecoveryDecision(
            decision_type=DecisionType.RETRY,
            reason=f"Safe to retry. Attempt {current_retry_count + 1} of {policy['max_retries']}."
        )

# Singleton instance
recovery_manager = RecoveryManager()
