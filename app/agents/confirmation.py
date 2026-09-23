from typing import Dict, Any, Optional
from app.agents.state import state_manager, SessionStatus

class ConfirmationManager:
    """Handles explicit human-in-the-loop confirmations for sensitive actions like sending emails."""
    
    def create_pending_email(self, session_id: str, job_id: str, subject: str, body: str, recipient: Optional[str]) -> dict:
        """Creates a pending email action via the ActionGateway."""
        from app.integrations.gateway import action_gateway
        from app.integrations.models import ActionRequest, ActionType
        
        request = ActionRequest(
            integration="gmail",
            action_type=ActionType.SEND,
            session_id=session_id,
            arguments={
                "to": recipient,
                "subject": subject,
                "body": body,
                "job_id": job_id
            }
        )
        
        result = action_gateway.execute_action(request)
        
        if result.status.value != "WAITING_FOR_CONFIRMATION":
            return {
                "status": "error",
                "message": f"Could not create draft: {result.message}"
            }
            
        return {
            "status": "waiting_for_confirmation",
            "action": "send_email",
            "job_id": job_id,
            "message": "The email draft is ready. Do you want to send it?"
        }

    def has_pending_email(self, session_id: str) -> bool:
        session = state_manager.get_session(session_id)
        pending = getattr(session, "pending_gateway_action", None)
        return pending is not None and pending.get("status") == "pending" and pending["request"].integration == "gmail"
        
    def confirm_email(self, session_id: str) -> dict:
        """Processes the confirmation of a pending email and actually sends it via Gmail."""
        from app.integrations.gateway import action_gateway
        
        if not self.has_pending_email(session_id):
            return {
                "status": "error",
                "message": "No pending email to send."
            }
            
        result = action_gateway.confirm_pending_action(session_id)
        
        # Format backward compatible result
        if result.status.value == "SUCCESS":
            return {
                "status": "sent",
                "action": "send_email",
                "message_id": result.data.get("message_id") if result.data else None,
                "message": "Email sent successfully."
            }
        else:
            return {
                "status": "send_failed",
                "action": "send_email",
                "error": result.data.get("error_code") if result.data else None,
                "message": f"Email could not be sent: {result.message}"
            }
        
    def reject_email(self, session_id: str) -> dict:
        """Processes the rejection of a pending email. No email is sent."""
        from app.integrations.gateway import action_gateway
        
        if self.has_pending_email(session_id):
            action_gateway.reject_pending_action(session_id)
            
        return {
            "status": "rejected",
            "action": "send_email",
            "message": "Email sending cancelled."
        }
        
    def create_pending_consolidation(self, session_id: str, proposal: Any) -> dict:
        """Creates a pending consolidation action."""
        session = state_manager.get_session(session_id)
        session.pending_consolidation_action = {
            "action": "consolidate_memories",
            "proposal": proposal
        }
        state_manager.update_status(session_id, SessionStatus.WAITING_FOR_CONFIRMATION)
        
        return {
            "status": "waiting_for_confirmation",
            "action": "consolidate_memories",
            "proposal_id": proposal.proposal_id,
            "message": "The memory consolidation proposal is ready. Do you want to apply it?"
        }

    def has_pending_consolidation(self, session_id: str) -> bool:
        session = state_manager.get_session(session_id)
        return session.pending_consolidation_action is not None
        
    def confirm_consolidation(self, session_id: str) -> dict:
        session = state_manager.get_session(session_id)
        action = session.pending_consolidation_action
        
        if not action or action.get("action") != "consolidate_memories":
            return {
                "status": "error",
                "message": "No pending consolidation to apply."
            }
            
        proposal = action.get("proposal")
        from app.memory.consolidation import consolidation_engine
        
        result = consolidation_engine.apply_proposal(proposal)
        
        if result["status"] == "success":
            session.pending_consolidation_action = None
            state_manager.update_status(session_id, SessionStatus.COMPLETED)
            return {
                "status": "success",
                "action": "consolidate_memories",
                "groups_processed": result["groups_processed"],
                "message": f"Consolidation applied successfully. {result['groups_processed']} groups processed."
            }
        else:
            # Stale proposal or error
            session.pending_consolidation_action = None
            state_manager.update_status(session_id, SessionStatus.COMPLETED)
            return {
                "status": "error",
                "action": "consolidate_memories",
                "message": f"Consolidation failed: {', '.join(result.get('errors', []))}. Please generate a new proposal."
            }

    def reject_consolidation(self, session_id: str) -> dict:
        session = state_manager.get_session(session_id)
        session.pending_consolidation_action = None
        state_manager.update_status(session_id, SessionStatus.COMPLETED)
        
        return {
            "status": "rejected",
            "action": "consolidate_memories",
            "message": "Memory consolidation cancelled."
        }

    def create_pending_maintenance(self, session_id: str, proposal: Any) -> dict:
        """Creates a pending maintenance action."""
        session = state_manager.get_session(session_id)
        session.pending_maintenance_action = {
            "action": "perform_memory_maintenance",
            "proposal": proposal
        }
        state_manager.update_status(session_id, SessionStatus.WAITING_FOR_CONFIRMATION)
        
        return {
            "status": "waiting_for_confirmation",
            "action": "perform_memory_maintenance",
            "proposal_id": proposal.proposal_id,
            "message": "The memory maintenance proposal is ready. Do you want to apply the recommended destructive actions?"
        }

    def has_pending_maintenance(self, session_id: str) -> bool:
        session = state_manager.get_session(session_id)
        return getattr(session, "pending_maintenance_action", None) is not None
        
    def confirm_maintenance(self, session_id: str) -> dict:
        session = state_manager.get_session(session_id)
        action = getattr(session, "pending_maintenance_action", None)
        
        if not action or action.get("action") != "perform_memory_maintenance":
            return {
                "status": "error",
                "message": "No pending memory maintenance to apply."
            }
            
        proposal = action.get("proposal")
        from app.memory.maintenance import maintenance_engine
        
        result = maintenance_engine.apply_proposal(proposal)
        
        if result["status"] == "success":
            session.pending_maintenance_action = None
            state_manager.update_status(session_id, SessionStatus.COMPLETED)
            return {
                "status": "success",
                "action": "perform_memory_maintenance",
                "processed": result.get("processed", 0),
                "message": f"Maintenance applied successfully. {result.get('processed', 0)} memories forgotten."
            }
        else:
            # Stale proposal or error
            session.pending_maintenance_action = None
            state_manager.update_status(session_id, SessionStatus.COMPLETED)
            return {
                "status": "error",
                "action": "perform_memory_maintenance",
                "message": f"Maintenance failed: {', '.join(result.get('errors', []))}. Please generate a new proposal."
            }

    def reject_maintenance(self, session_id: str) -> dict:
        session = state_manager.get_session(session_id)
        session.pending_maintenance_action = None
        state_manager.update_status(session_id, SessionStatus.COMPLETED)
        
        return {
            "status": "rejected",
            "action": "perform_memory_maintenance",
            "message": "Memory maintenance cancelled."
        }
        
    def confirm_gateway_action(self, session_id: str) -> dict:
        from app.integrations.gateway import action_gateway
        result = action_gateway.confirm_pending_action(session_id)
        return {
            "status": result.status.value,
            "action": result.action_type.value,
            "message": result.message
        }
        
    def reject_gateway_action(self, session_id: str) -> dict:
        from app.integrations.gateway import action_gateway
        result = action_gateway.reject_pending_action(session_id)
        return {
            "status": result.status.value,
            "action": result.action_type.value,
            "message": result.message
        }

confirmation_manager = ConfirmationManager()
