from typing import Dict, Any
from app.integrations.gateway import action_gateway
from app.integrations.models import ActionRequest, ActionType, ActionStatus
from app.services.verification_analyzer import analyze_verification_result

class FixVerificationFlow:
    def __init__(self, session_id: str):
        self.session_id = session_id

    def trigger_verification(self) -> Dict[str, Any]:
        """
        Triggers a controlled pytest execution to verify an applied fix.
        This explicitly routes through the ActionGateway and requires human confirmation.
        """
        req = ActionRequest(
            integration="local_system",
            action_type=ActionType.EXECUTE,
            session_id=self.session_id,
            arguments={"operation": "pytest", "args": []},
            requires_confirmation=True
        )
        res = action_gateway.execute_action(req)
        
        return {
            "status": res.status.value,
            "action_id": req.action_id,
            "message": "Verification requested. Awaiting human confirmation." if res.status == ActionStatus.WAITING_FOR_CONFIRMATION else res.message
        }

    def aggregate_final_result(self, execution_result: Dict[str, Any]) -> Dict[str, Any]:
        """
        Takes the raw execution result (post-confirmation) and aggregates it into 
        the final structured verification result.
        """
        if execution_result.get("status") != ActionStatus.SUCCESS.value:
            return {
                "fix_applied": True,
                "verification_started": False,
                "verification_success": False,
                "exit_code": None,
                "failed_tests": [],
                "error_categories": [],
                "summary": f"Verification did not execute: {execution_result.get('message', 'Rejected or Failed')}",
                "timed_out": False,
                "output_truncated": False
            }
            
        analysis = analyze_verification_result(execution_result)
        
        return {
            "fix_applied": True,
            "verification_started": True,
            "verification_success": analysis.get("success"),
            "exit_code": analysis.get("exit_code"),
            "failed_tests": [t.get("test_name", t) if isinstance(t, dict) else t for t in analysis.get("failed_tests", [])],
            "error_categories": analysis.get("error_categories", []),
            "summary": analysis.get("summary"),
            "timed_out": analysis.get("timed_out"),
            "output_truncated": analysis.get("output_truncated")
        }
