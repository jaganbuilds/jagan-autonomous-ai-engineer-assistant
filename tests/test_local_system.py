import os
import pytest
from pathlib import Path
from app.integrations.models import ActionRequest, ActionType, ActionStatus, ActionResult
from app.integrations.gateway import action_gateway
from app.integrations.local_system import LocalSystemIntegration
from app.database.action_repository import action_repository
from app.config import get_settings

@pytest.fixture
def workspace(tmp_path):
    settings = get_settings()
    original_root = settings.workspace_root
    original_max = settings.workspace_max_read_bytes
    
    # Configure test workspace
    settings.workspace_root = str(tmp_path)
    settings.workspace_max_read_bytes = 1000 # Small limit for testing
    
    yield tmp_path
    
    # Restore
    settings.workspace_root = original_root
    settings.workspace_max_read_bytes = original_max
    action_repository.clear()

def test_valid_workspace_read(workspace):
    # Setup file
    test_file = workspace / "test.txt"
    test_file.write_text("hello world")
    
    req = ActionRequest(
        integration="local_system",
        action_type=ActionType.READ,
        session_id="s1",
        arguments={"filepath": "test.txt"}
    )
    result = action_gateway.execute_action(req)
    
    assert result.status == ActionStatus.SUCCESS
    assert result.data["content"] == "hello world"

def test_missing_file(workspace):
    req = ActionRequest(
        integration="local_system",
        action_type=ActionType.READ,
        session_id="s1",
        arguments={"filepath": "missing.txt"}
    )
    result = action_gateway.execute_action(req)
    
    assert result.status == ActionStatus.FAILED
    assert "File not found" in result.message

def test_directory_rejection(workspace):
    req = ActionRequest(
        integration="local_system",
        action_type=ActionType.READ,
        session_id="s1",
        arguments={"filepath": "."}
    )
    result = action_gateway.execute_action(req)
    
    assert result.status == ActionStatus.FAILED
    assert "Path is not a file" in result.message

def test_valid_write_after_confirmation(workspace):
    # Create request
    req = ActionRequest(
        action_id="w1",
        integration="local_system",
        action_type=ActionType.WRITE,
        session_id="s1",
        arguments={"filepath": "new.txt", "content": "writing data"},
        requires_confirmation=True
    )
    
    # First attempt -> Waiting for confirmation
    result1 = action_gateway.execute_action(req)
    assert result1.status == ActionStatus.WAITING_FOR_CONFIRMATION
    
    # Confirm
    result2 = action_gateway.confirm_pending_action("s1")
    assert result2.status == ActionStatus.SUCCESS
    
    # Verify file exists
    assert (workspace / "new.txt").read_text() == "writing data"

def test_write_rejection_without_confirmation(workspace):
    # Attempt to bypass requires_confirmation=True by setting it to False
    req = ActionRequest(
        action_id="w2",
        integration="local_system",
        action_type=ActionType.WRITE,
        session_id="s1",
        arguments={"filepath": "danger.txt", "content": "hacked"},
        requires_confirmation=False
    )
    
    # Preflight should override and force confirmation
    result = action_gateway.execute_action(req)
    assert result.status == ActionStatus.WAITING_FOR_CONFIRMATION
    assert not (workspace / "danger.txt").exists()

def test_rejected_confirmation(workspace):
    req = ActionRequest(
        action_id="w3",
        integration="local_system",
        action_type=ActionType.WRITE,
        session_id="s1",
        arguments={"filepath": "never.txt", "content": "data"},
        requires_confirmation=True
    )
    
    result1 = action_gateway.execute_action(req)
    assert result1.status == ActionStatus.WAITING_FOR_CONFIRMATION
    
    result2 = action_gateway.reject_pending_action("s1")
    assert result2.status == ActionStatus.REJECTED
    assert not (workspace / "never.txt").exists()

def test_path_traversal_dot_dot(workspace):
    req = ActionRequest(
        integration="local_system",
        action_type=ActionType.READ,
        session_id="s1",
        arguments={"filepath": "../outside.txt"}
    )
    result = action_gateway.execute_action(req)
    assert result.status == ActionStatus.VALIDATION_ERROR
    assert "escape the configured workspace" in result.message

def test_path_traversal_windows(workspace):
    req = ActionRequest(
        integration="local_system",
        action_type=ActionType.READ,
        session_id="s1",
        arguments={"filepath": "..\\outside.txt"}
    )
    result = action_gateway.execute_action(req)
    assert result.status == ActionStatus.VALIDATION_ERROR
    assert "escape the configured workspace" in result.message

def test_absolute_path_escape(workspace):
    req = ActionRequest(
        integration="local_system",
        action_type=ActionType.READ,
        session_id="s1",
        arguments={"filepath": "/etc/passwd"}
    )
    result = action_gateway.execute_action(req)
    assert result.status == ActionStatus.VALIDATION_ERROR
    assert "escape the configured workspace" in result.message

def test_symlink_escape(workspace, tmp_path_factory):
    # Create an outside directory and file
    outside_dir = tmp_path_factory.mktemp("outside")
    outside_file = outside_dir / "secret.txt"
    outside_file.write_text("secrets")
    
    # Create a symlink inside the workspace pointing outside
    symlink_path = workspace / "link_out"
    try:
        os.symlink(str(outside_dir), str(symlink_path))
    except OSError:
        pytest.skip("Symlinks not supported on this OS without elevated privileges.")
        
    req = ActionRequest(
        integration="local_system",
        action_type=ActionType.READ,
        session_id="s1",
        arguments={"filepath": "link_out/secret.txt"}
    )
    result = action_gateway.execute_action(req)
    
    assert result.status == ActionStatus.VALIDATION_ERROR
    assert "escape the configured workspace" in result.message

def test_workspace_isolation_write(workspace):
    req = ActionRequest(
        integration="local_system",
        action_type=ActionType.WRITE,
        session_id="s1",
        arguments={"filepath": "../evil.txt", "content": "evil"},
        requires_confirmation=True
    )
    # The validation happens before it even enters PENDING_CONFIRMATION
    result = action_gateway.execute_action(req)
    assert result.status == ActionStatus.VALIDATION_ERROR

def test_session_isolation(workspace):
    req = ActionRequest(
        action_id="w4",
        integration="local_system",
        action_type=ActionType.WRITE,
        session_id="s1",
        arguments={"filepath": "test.txt", "content": "1"}
    )
    action_gateway.execute_action(req)
    
    # Try confirming from a different session
    result = action_gateway.confirm_pending_action("s2")
    assert result.status == ActionStatus.FAILED
    assert "No pending action" in result.message

def test_duplicate_idempotent_write(workspace):
    req = ActionRequest(
        action_id="w6",
        integration="local_system",
        action_type=ActionType.WRITE,
        session_id="s1",
        arguments={"filepath": "idem.txt", "content": "first"},
        requires_confirmation=True
    )
    action_gateway.execute_action(req)
    action_gateway.confirm_pending_action("s1")
    
    # Alter the file externally
    (workspace / "idem.txt").write_text("altered")
    
    # Submit the exact same action ID again
    result = action_gateway.execute_action(req)
    
    # Should return SUCCESS but not actually write
    assert result.status == ActionStatus.SUCCESS
    assert (workspace / "idem.txt").read_text() == "altered" # Remains altered

def test_bounded_read_behavior(workspace):
    large_file = workspace / "large.txt"
    # Write 1500 bytes (limit is 1000 in test config)
    large_file.write_text("x" * 1500)
    
    req = ActionRequest(
        integration="local_system",
        action_type=ActionType.READ,
        session_id="s1",
        arguments={"filepath": "large.txt"}
    )
    result = action_gateway.execute_action(req)
    
    assert result.status == ActionStatus.FAILED
    assert "too large to read" in result.message

def test_capability_discovery():
    from app.integrations.capability_service import capability_service
    
    caps = capability_service.get_integration_capabilities("local_system")
    assert caps.healthy
    assert any(a.action_type.value == "READ" for a in caps.supported_actions)
    assert any(a.action_type.value == "WRITE" for a in caps.supported_actions)

def test_tool_registry_discovery():
    from app.tools.registry import registry
    tools = registry.get_all_tools()
    
    tool_names = [t.__name__ for t in tools]
    assert "read_workspace_file" in tool_names
    assert "write_workspace_file" in tool_names
