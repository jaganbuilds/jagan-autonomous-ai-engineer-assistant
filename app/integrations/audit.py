import re
from typing import Dict, Any, Optional, List
from datetime import datetime, timezone
from app.database.action_repository import action_repository

class AuditService:
    def _calculate_duration(self, created_at: Optional[str], completed_at: Optional[str]) -> Optional[int]:
        if not created_at or not completed_at:
            return None
        try:
            # Parse ISO 8601 strings
            created = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
            completed = datetime.fromisoformat(completed_at.replace("Z", "+00:00"))
            duration = (completed - created).total_seconds() * 1000
            return int(duration)
        except Exception:
            return None

    def _sanitize_dict(self, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
            
        sanitized = {}
        sensitive_keys = {
            "token", "access_token", "refresh_token", "api_key", "secret",
            "password", "authorization", "credentials", "client_secret"
        }
        
        for k, v in data.items():
            k_lower = k.lower()
            is_sensitive = any(sk in k_lower for sk in sensitive_keys)
            
            if is_sensitive:
                sanitized[k] = "***"
            elif isinstance(v, dict):
                sanitized[k] = self._sanitize_dict(v)
            elif isinstance(v, list):
                sanitized[k] = [self._sanitize_dict(item) if isinstance(item, dict) else item for item in v]
            else:
                sanitized[k] = v
        return sanitized

    def _format_audit_record(self, action: Dict[str, Any]) -> Dict[str, Any]:
        """Formats a DB action record into a safe audit representation."""
        req_payload = self._sanitize_dict(action.get("request_payload", {}))
        res_payload = self._sanitize_dict(action.get("result_payload", {}))
        
        # Convert massive payloads to metadata summaries
        if action.get("action_type") == "READ" and isinstance(res_payload, dict):
            if not res_payload.get("_meta"):
                res_payload = {"_meta": f"{action.get('integration_name')} action completed successfully."}
                
        return {
            "action_id": action["action_id"],
            "session_id": action["session_id"],
            "owner_id": action["owner_id"],
            "integration_name": action["integration_name"],
            "action_type": action["action_type"],
            "risk_level": action["risk_level"],
            "status": action["status"],
            "created_at": action["created_at"],
            "confirmed_at": action["confirmed_at"],
            "completed_at": action["completed_at"],
            "duration_ms": self._calculate_duration(action["created_at"], action["completed_at"]),
            "request_payload": req_payload,
            "result_payload": res_payload
        }

    def get_action_audit(self, session_id: str, owner_id: str, action_id: str) -> Optional[Dict[str, Any]]:
        action = action_repository.get_action(action_id, session_id, owner_id)
        if not action:
            return None
        return self._format_audit_record(action)
        
    def list_actions(self, session_id: str, owner_id: str, integration_name: Optional[str] = None, 
                     action_type: Optional[str] = None, status: Optional[str] = None, 
                     limit: int = 50, offset: int = 0) -> List[Dict[str, Any]]:
        actions = action_repository.list_actions(
            session_id=session_id, owner_id=owner_id, 
            integration_name=integration_name, action_type=action_type, 
            status=status, limit=limit, offset=offset
        )
        return [self._format_audit_record(act) for act in actions]

    def get_action_statistics(self, session_id: str, owner_id: str) -> Dict[str, Any]:
        return action_repository.get_action_statistics(session_id, owner_id)

audit_service = AuditService()
