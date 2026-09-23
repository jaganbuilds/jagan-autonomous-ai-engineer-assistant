import pytest
from pathlib import Path
import time
from app.integrations.models import ActionRequest, ActionType, ActionStatus
from app.integrations.gateway import action_gateway
from app.database.action_repository import action_repository
from app.config import get_settings

@pytest.fixture
def workspace(tmp_path):
    settings = get_settings()
    original_root = settings.workspace_root
    original_max = settings.workspace_execution_max_output_bytes
    original_timeout = settings.workspace_execution_timeout_seconds
    
    settings.workspace_root = str(tmp_path)
    settings.workspace_execution_max_output_bytes = 1000
    settings.workspace_execution_timeout_seconds = 2
    
    yield tmp_path
    
    settings.workspace_root = original_root
    settings.workspace_execution_max_output_bytes = original_max
    settings.workspace_execution_timeout_seconds = original_timeout
    action_repository.clear()

def test_execute_successful_pytest(workspace):
    # Create a dummy passing test
    test_file = workspace / "test_dummy.py"
    test_file.write_text("def test_ok(): pass\n")
    
    req = ActionRequest(
        action_id="ex1",
        integration="local_system",
        action_type=ActionType.EXECUTE,
        session_id="s1",
        arguments={"operation": "pytest", "args": ["test_dummy.py"]},
        requires_confirmation=True
    )
    action_gateway.execute_action(req)
    result = action_gateway.confirm_pending_action("s1")
    
    assert result.status == ActionStatus.SUCCESS
    assert result.data["success"] is True
    assert result.data["exit_code"] == 0
    assert "test_ok" in result.data["stdout"] or "1 passed" in result.data["stdout"]

def test_execute_unsupported_operation(workspace):
    req = ActionRequest(
        action_id="ex2",
        integration="local_system",
        action_type=ActionType.EXECUTE,
        session_id="s1",
        arguments={"operation": "python", "args": ["--version"]},
        requires_confirmation=True
    )
    result = action_gateway.execute_action(req)
    assert result.status == ActionStatus.VALIDATION_ERROR
    assert "Unsupported operation" in result.message

def test_execute_shell_syntax_rejected(workspace):
    req = ActionRequest(
        action_id="ex3",
        integration="local_system",
        action_type=ActionType.EXECUTE,
        session_id="s1",
        arguments={"operation": "pytest", "args": ["test.py", "&&", "rm", "-rf", "/"]},
        requires_confirmation=True
    )
    result = action_gateway.execute_action(req)
    assert result.status == ActionStatus.VALIDATION_ERROR
    assert "dangerous shell characters" in result.message

def test_execute_path_traversal_rejected(workspace):
    req = ActionRequest(
        action_id="ex4",
        integration="local_system",
        action_type=ActionType.EXECUTE,
        session_id="s1",
        arguments={"operation": "pytest", "args": ["../outside.py"]},
        requires_confirmation=True
    )
    result = action_gateway.execute_action(req)
    assert result.status == ActionStatus.VALIDATION_ERROR
    assert "Unsafe argument" in result.message

def test_execute_rejected_confirmation(workspace):
    req = ActionRequest(
        action_id="ex5",
        integration="local_system",
        action_type=ActionType.EXECUTE,
        session_id="s1",
        arguments={"operation": "pytest", "args": []},
        requires_confirmation=True
    )
    action_gateway.execute_action(req)
    result = action_gateway.reject_pending_action("s1")
    assert result.status == ActionStatus.REJECTED

def test_execute_idempotency_duplicate_confirmation(workspace):
    test_file = workspace / "test_dup.py"
    test_file.write_text("def test_ok(): pass\n")
    
    req = ActionRequest(
        action_id="ex6",
        integration="local_system",
        action_type=ActionType.EXECUTE,
        session_id="s1",
        arguments={"operation": "pytest", "args": ["test_dup.py"]},
        requires_confirmation=True
    )
    action_gateway.execute_action(req)
    result1 = action_gateway.confirm_pending_action("s1")
    assert result1.status == ActionStatus.SUCCESS
    
    # Confirming again should fail due to no pending action
    result2 = action_gateway.confirm_pending_action("s1")
    assert result2.status == ActionStatus.FAILED
    assert "No pending action" in result2.message

def test_execute_timeout(workspace):
    test_file = workspace / "test_timeout.py"
    test_file.write_text("import time\ndef test_slow(): time.sleep(5)\n")
    
    req = ActionRequest(
        action_id="ex7",
        integration="local_system",
        action_type=ActionType.EXECUTE,
        session_id="s1",
        arguments={"operation": "pytest", "args": ["test_timeout.py"]},
        requires_confirmation=True
    )
    action_gateway.execute_action(req)
    result = action_gateway.confirm_pending_action("s1")
    
    assert result.status == ActionStatus.SUCCESS
    assert result.data["timed_out"] is True
    assert result.data["success"] is False
    assert result.data["exit_code"] == -1

def test_tool_registry_discovery():
    from app.tools.registry import registry
    tools = registry.get_all_tools()
    tool_names = [t.__name__ for t in tools]
    assert "execute_workspace_verification" in tool_names
