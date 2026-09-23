from typing import Dict, Any, Optional
from app.tools.registry import registry
from app.integrations.gateway import action_gateway
from app.integrations.models import ActionRequest, ActionType

@registry.register(requires_confirmation=False)
def read_workspace_file(session_id: str, filepath: str) -> Dict[str, Any]:
    """
    Reads the content of a file from the local project workspace.
    This operation is safe and read-only.
    
    Args:
        session_id: The current session ID.
        filepath: The relative path to the file inside the workspace.
        
    Returns:
        Dict containing status and file content.
    """
    request = ActionRequest(
        integration="local_system",
        action_type=ActionType.READ,
        session_id=session_id,
        arguments={"filepath": filepath},
        requires_confirmation=False
    )
    result = action_gateway.execute_action(request)
    return result.model_dump()

@registry.register(requires_confirmation=True)
def write_workspace_file(session_id: str, filepath: str, content: str) -> Dict[str, Any]:
    """
    Writes content to a file inside the local project workspace.
    Creates parent directories if necessary.
    Requires explicit human confirmation.
    
    Args:
        session_id: The current session ID.
        filepath: The relative path to the file inside the workspace.
        content: The text content to write to the file.
        
    Returns:
        Dict containing the status of the write operation.
    """
    request = ActionRequest(
        integration="local_system",
        action_type=ActionType.WRITE,
        session_id=session_id,
        arguments={"filepath": filepath, "content": content},
        requires_confirmation=True
    )
    result = action_gateway.execute_action(request)
    return result.model_dump()

@registry.register(requires_confirmation=True)
def edit_workspace_file(session_id: str, filepath: str, expected_content: str, replacement: str) -> Dict[str, Any]:
    """
    Edits an existing file in the local project workspace.
    The edit must be deterministic: expected_content must exactly match one unique section of the file.
    Requires explicit human confirmation.
    
    Args:
        session_id: The current session ID.
        filepath: The relative path to the file inside the workspace.
        expected_content: The exact text to replace.
        replacement: The text to replace it with.
        
    Returns:
        Dict containing the status of the edit operation.
    """
    request = ActionRequest(
        integration="local_system",
        action_type=ActionType.WRITE,
        session_id=session_id,
        arguments={"operation": "edit", "filepath": filepath, "expected_content": expected_content, "replacement": replacement},
        requires_confirmation=True
    )
    result = action_gateway.execute_action(request)
    return result.model_dump()

@registry.register(requires_confirmation=True)
def apply_workspace_patch(session_id: str, filepath: str, patch_content: str) -> Dict[str, Any]:
    """
    Applies a unified diff patch to a file in the local project workspace.
    The patch must be deterministic and validate cleanly.
    Requires explicit human confirmation.
    
    Args:
        session_id: The current session ID.
        filepath: The relative path to the file inside the workspace.
        patch_content: The unified diff patch string to apply to the file.
        
    Returns:
        Dict containing the status of the patch operation.
    """
    request = ActionRequest(
        integration="local_system",
        action_type=ActionType.WRITE,
        session_id=session_id,
        arguments={"operation": "patch", "filepath": filepath, "patch_content": patch_content},
        requires_confirmation=True
    )
    result = action_gateway.execute_action(request)
    return result.model_dump()

@registry.register(requires_confirmation=True)
def execute_workspace_verification(session_id: str, operation: str, args: list[str] = None) -> Dict[str, Any]:
    """
    Executes a controlled verification operation (e.g., pytest) on the local workspace.
    Requires explicit human confirmation.
    
    Args:
        session_id: The current session ID.
        operation: The verification operation to run. Only 'pytest' is currently supported.
        args: List of arguments to pass to the operation.
        
    Returns:
        Dict containing the structured result of the execution.
    """
    if args is None:
        args = []
    request = ActionRequest(
        integration="local_system",
        action_type=ActionType.EXECUTE,
        session_id=session_id,
        arguments={"operation": operation, "args": args},
        requires_confirmation=True
    )
    result = action_gateway.execute_action(request)
    return result.model_dump()

@registry.register(requires_confirmation=False)
def analyze_verification_result(result: Dict[str, Any]) -> Dict[str, Any]:
    """
    Analyzes the structured execution result of a verification step (like pytest)
    to extract meaningful failures, errors, and files.
    
    This is a pure analysis layer. It does not mutate the filesystem or execute code.
    
    Args:
        result: The structured verification result dictionary returned by execute_workspace_verification.
        
    Returns:
        Dict containing the structured analysis (success, error categories, failed tests, affected files).
    """
    from app.services.verification_analyzer import analyze_verification_result as _analyze
    return _analyze(result)

@registry.register(requires_confirmation=True)
def propose_code_fix(session_id: str, analysis: Dict[str, Any]) -> Dict[str, Any]:
    """
    Generates a code fix proposal based on a verification analysis result and requests
    human confirmation to apply it via the safe patching system.
    
    Args:
        session_id: The current session ID.
        analysis: The structured analysis dictionary returned by analyze_verification_result.
        
    Returns:
        Dict containing the proposal details and the gateway action status (WAITING_FOR_CONFIRMATION).
    """
    from app.services.code_fix_proposer import CodeFixProposer
    proposer = CodeFixProposer()
    proposal = proposer.generate_proposal(session_id, analysis)
    
    if not proposal:
        return {
            "status": "failed",
            "message": "No reliable fix information could be generated for the given analysis."
        }
        
    if not proposal.patch_content:
        return {
            "status": "failed",
            "message": "A proposal was generated, but it did not contain a valid patch."
        }
        
    # We formulate an ActionRequest to apply the patch. This natively triggers ActionGateway's
    # HIGH-RISK WRITE confirmation flow before any file is actually mutated.
    request = ActionRequest(
        integration="local_system",
        action_type=ActionType.WRITE,
        session_id=session_id,
        arguments={
            "filepath": proposal.affected_file,
            "operation": "patch",
            "patch_content": proposal.patch_content,
            "proposal_reason": proposal.reason,
            "proposed_change": proposal.proposed_change
        },
        requires_confirmation=True
    )
    
    result = action_gateway.execute_action(request)
    
    return {
        "status": result.status.value,
        "proposal": proposal.model_dump(),
        "action_result": result.model_dump()
    }

@registry.register(requires_confirmation=True)
def verify_applied_fix(session_id: str) -> Dict[str, Any]:
    """
    Triggers a controlled pytest verification after a code fix has been applied.
    Requires human confirmation.
    
    Args:
        session_id: The current session ID.
        
    Returns:
        Dict indicating WAITING_FOR_CONFIRMATION status.
    """
    from app.services.fix_verifier import FixVerificationFlow
    flow = FixVerificationFlow(session_id)
    return flow.trigger_verification()

@registry.register()
def analyze_fix_verification(session_id: str, execution_result: Dict[str, Any]) -> Dict[str, Any]:
    """
    Analyzes the raw verification execution result and returns a structured final result.
    
    Args:
        session_id: The current session ID.
        execution_result: The raw ActionResult from the execute_workspace_verification run.
        
    Returns:
        A structured dict with fix_applied, verification_success, and summary.
    """
    from app.services.fix_verifier import FixVerificationFlow
    flow = FixVerificationFlow(session_id)
    return flow.aggregate_final_result(execution_result)
