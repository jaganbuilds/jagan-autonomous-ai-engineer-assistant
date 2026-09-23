from typing import Dict, Any, Type, Optional
from app.integrations.models import (
    ActionRequest, ActionResult, ActionStatus, ActionType,
    get_action_risk_level, ActionRiskLevel
)
from app.agents.state import state_manager, SessionStatus
from app.database.action_repository import action_repository

class BaseIntegration:
    @property
    def integration_name(self) -> str:
        raise NotImplementedError
        
    @property
    def supported_actions(self) -> list[ActionType]:
        raise NotImplementedError
        
    def validate_arguments(self, action_type: ActionType, arguments: Dict[str, Any]) -> tuple[bool, str]:
        raise NotImplementedError
        
    def execute(self, request: ActionRequest) -> ActionResult:
        raise NotImplementedError
        
    def check_health(self) -> 'IntegrationCapability':
        """
        Determines if the integration is available, authenticated, and healthy.
        Returns an IntegrationCapability object.
        """
        raise NotImplementedError


class ActionGateway:
    def __init__(self):
        self._integrations: Dict[str, BaseIntegration] = {}
        
    def register_integration(self, integration: BaseIntegration):
        self._integrations[integration.integration_name] = integration
        
    def _sanitize_payload(self, action_type: ActionType, payload: Dict[str, Any], is_result: bool = False) -> Dict[str, Any]:
        if not payload:
            return {}
        safe_payload = dict(payload)
        # Remove anything looking like secrets
        for k in list(safe_payload.keys()):
            k_lower = k.lower()
            if 'token' in k_lower or 'secret' in k_lower or 'auth' in k_lower or 'password' in k_lower:
                safe_payload[k] = "***"
        
        # Don't store massive READ payloads
        if is_result and action_type == ActionType.READ:
            return {"_meta": "Large READ payload omitted from persistence."}
            
        return safe_payload

    def execute_action(self, request: ActionRequest) -> ActionResult:
        # Load from DB for Idempotency
        existing = action_repository.get_action(request.action_id, request.session_id, request.owner_id)
        if existing:
            status_str = existing["status"]
            if status_str in ("SUCCESS", "COMPLETED", "FAILED", "REJECTED", "VALIDATION_ERROR", "NOT_SUPPORTED", "UNAUTHORIZED", "FAILED_RECOVERY"):
                return self._build_result_from_dict(existing)
            elif status_str == "PENDING_CONFIRMATION":
                state_manager.update_status(request.session_id, SessionStatus.WAITING_FOR_CONFIRMATION)
                return self._build_result(request, ActionStatus.WAITING_FOR_CONFIRMATION, "Action requires explicit user confirmation before executing.")
            elif status_str == "EXECUTING":
                # Crash recovery during execution
                action_repository.update_status(request.action_id, "FAILED_RECOVERY")
                return self._build_result(request, ActionStatus.FAILED, "Action was EXECUTING during a crash. Marked as FAILED_RECOVERY to prevent duplicate side effects.")

        # Run Preflight
        from app.integrations.preflight import validate_preflight
        preflight_result = validate_preflight(request)
        
        if not preflight_result.allowed:
            # Map preflight failure reasons to action status
            status = ActionStatus.FAILED
            if preflight_result.reason == "VALIDATION_ERROR" or preflight_result.reason == "INVALID_REQUEST":
                status = ActionStatus.VALIDATION_ERROR
            elif preflight_result.reason == "UNSUPPORTED_ACTION" or preflight_result.reason == "UNKNOWN_INTEGRATION":
                status = ActionStatus.NOT_SUPPORTED
            elif preflight_result.reason == "AUTHENTICATION_REQUIRED":
                status = ActionStatus.UNAUTHORIZED
                
            res = self._build_result(request, status, preflight_result.safe_message)
            self._persist_new_action(request, res, ActionRiskLevel(preflight_result.risk_level))
            return res
            
        integration = self._integrations.get(request.integration)
        
        # Risk & Confirmation Check
        # Uses preflight's computed confirmation requirement
        if preflight_result.requires_confirmation:
            request.requires_confirmation = True
            
        if request.requires_confirmation:
            # We don't have it in DB yet, create it as PENDING_CONFIRMATION
            action_repository.create_action(
                action_id=request.action_id,
                session_id=request.session_id,
                owner_id=request.owner_id,
                integration_name=request.integration,
                action_type=request.action_type.value,
                risk_level=preflight_result.risk_level,
                status="PENDING_CONFIRMATION",
                request_payload=self._sanitize_payload(request.action_type, request.arguments)
            )
            # Update state manager for legacy compatibility if needed
            state_manager.update_status(request.session_id, SessionStatus.WAITING_FOR_CONFIRMATION)
            session = state_manager.get_session(request.session_id)
            session.pending_gateway_action = {
                "status": "pending",
                "action_id": request.action_id,
                "request": request
            }
            return self._build_result(request, ActionStatus.WAITING_FOR_CONFIRMATION, "Action requires explicit user confirmation before executing.")
                
        # LOW risk execution
        # Create as EXECUTING
        action_repository.create_action(
            action_id=request.action_id,
            session_id=request.session_id,
            owner_id=request.owner_id,
            integration_name=request.integration,
            action_type=request.action_type.value,
            risk_level=preflight_result.risk_level,
            status="EXECUTING",
            request_payload=self._sanitize_payload(request.action_type, request.arguments)
        )
        
        return self._do_execute(request, integration)

    def _persist_new_action(self, request: ActionRequest, result: ActionResult, risk: ActionRiskLevel):
        action_repository.create_action(
            action_id=request.action_id,
            session_id=request.session_id,
            owner_id=request.owner_id,
            integration_name=request.integration,
            action_type=request.action_type.value,
            risk_level=risk.value,
            status=result.status.value,
            request_payload=self._sanitize_payload(request.action_type, request.arguments)
        )
        action_repository.save_result(
            request.action_id,
            result.status.value,
            self._sanitize_payload(request.action_type, result.data if hasattr(result, "data") and isinstance(result.data, dict) else {}, is_result=True)
        )

    def _do_execute(self, request: ActionRequest, integration: BaseIntegration) -> ActionResult:
        try:
            result = integration.execute(request)
            self._log_trace(request, result.status)
            
            # Save result to DB
            res_dict = result.data if isinstance(result.data, dict) else ({"data": result.data} if result.data else {})
            action_repository.save_result(
                request.action_id,
                result.status.value,
                self._sanitize_payload(request.action_type, res_dict, is_result=True)
            )
            return result
        except Exception as e:
            import traceback
            traceback.print_exc()
            self._log_trace(request, ActionStatus.FAILED)
            err_result = self._build_result(request, ActionStatus.FAILED, "Integration execution failed due to an internal provider error.")
            action_repository.save_result(
                request.action_id,
                ActionStatus.FAILED.value,
                {"error": "Internal provider error"}
            )
            return err_result
            
    def _build_result(self, request: ActionRequest, status: ActionStatus, message: str, data: Optional[Dict[str, Any]] = None) -> ActionResult:
        return ActionResult(
            action_id=request.action_id,
            integration=request.integration,
            action_type=request.action_type,
            status=status,
            message=message,
            data=data
        )

    def _build_result_from_dict(self, db_record: dict) -> ActionResult:
        # Fallback to SUCCESS if it's COMPLETED in DB but we map to ActionStatus
        status_val = db_record["status"]
        if status_val == "COMPLETED":
            status_val = "SUCCESS"
        elif status_val == "FAILED_RECOVERY":
            status_val = "FAILED"
            
        return ActionResult(
            action_id=db_record["action_id"],
            integration=db_record["integration_name"],
            action_type=ActionType(db_record["action_type"]),
            status=ActionStatus(status_val),
            message=f"Loaded from persistent cache (status: {db_record['status']}).",
            data=db_record["result_payload"]
        )
        
    def confirm_pending_action(self, session_id: str) -> ActionResult:
        # Load from DB to support restart
        db_action = action_repository.get_pending_action_for_session(session_id)
        
        if not db_action:
            return ActionResult(
                action_id="unknown",
                integration="gateway",
                action_type=ActionType.EXECUTE,
                status=ActionStatus.FAILED,
                message="No pending action to confirm."
            )
            
        request = ActionRequest(
            action_id=db_action["action_id"],
            integration=db_action["integration_name"],
            action_type=ActionType(db_action["action_type"]),
            session_id=db_action["session_id"],
            owner_id=db_action["owner_id"],
            arguments=db_action["request_payload"],
            requires_confirmation=True
        )
        
        # Try atomic transition
        success = action_repository.try_transition_to_executing(request.action_id, request.session_id, request.owner_id)
        if not success:
            # Already confirmed, rejected, or doesn't exist
            state_manager.update_status(session_id, SessionStatus.COMPLETED)
            existing = action_repository.get_action(request.action_id, request.session_id, request.owner_id)
            if existing:
                return self._build_result_from_dict(existing)
            return self._build_result(request, ActionStatus.FAILED, "Action could not be confirmed.")
            
        # Clean up legacy state
        session = state_manager.get_session(session_id)
        session.pending_gateway_action = None
        state_manager.update_status(session_id, SessionStatus.COMPLETED)
        
        integration = self._integrations.get(request.integration)
        if not integration:
            action_repository.save_result(request.action_id, "FAILED", {"error": "Integration missing"})
            return self._build_result(request, ActionStatus.FAILED, "Integration missing")
            
        return self._do_execute(request, integration)
        
    def reject_pending_action(self, session_id: str) -> ActionResult:
        db_action = action_repository.get_pending_action_for_session(session_id)
        
        if not db_action:
            return ActionResult(
                action_id="unknown",
                integration="gateway",
                action_type=ActionType.EXECUTE,
                status=ActionStatus.FAILED,
                message="No pending action to reject."
            )
            
        request = ActionRequest(
            action_id=db_action["action_id"],
            integration=db_action["integration_name"],
            action_type=ActionType(db_action["action_type"]),
            session_id=db_action["session_id"],
            owner_id=db_action["owner_id"],
            arguments=db_action["request_payload"]
        )
        
        # Mark in DB
        action_repository.update_status(request.action_id, "REJECTED")
        
        session = state_manager.get_session(session_id)
        session.pending_gateway_action = None
        state_manager.update_status(session_id, SessionStatus.COMPLETED)
        self._log_trace(request, ActionStatus.REJECTED)
        
        return self._build_result(request, ActionStatus.REJECTED, "Action rejected by user. No external side effect occurred.")
        
    def _log_trace(self, request: ActionRequest, status: ActionStatus):
        try:
            from app.agents.execution_trace import trace_manager
            
            trace_manager.add_event(
                session_id=request.session_id,
                event_type="action_gateway_executed",
                tool_name=request.integration,
                status=status.value,
                message=f"Action {request.action_type.value}",
                result_summary={
                    "action_id": request.action_id
                }
            )
        except ImportError:
            pass

action_gateway = ActionGateway()
