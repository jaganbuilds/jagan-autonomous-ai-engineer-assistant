import os
import pytest
from pathlib import Path
from app.integrations.models import ActionRequest, ActionType, ActionStatus
from app.integrations.gateway import action_gateway
from app.database.action_repository import action_repository
from app.config import get_settings

@pytest.fixture
def workspace(tmp_path):
    settings = get_settings()
    original_root = settings.workspace_root
    original_max = settings.workspace_max_read_bytes
    
    settings.workspace_root = str(tmp_path)
    settings.workspace_max_read_bytes = 10000 
    
    yield tmp_path
    
    settings.workspace_root = original_root
    settings.workspace_max_read_bytes = original_max
    action_repository.clear()

def test_edit_successful_exact_replacement(workspace):
    test_file = workspace / "edit.txt"
    test_file.write_text("def hello():\n    return 'old'\n")
    
    req = ActionRequest(
        action_id="e1",
        integration="local_system",
        action_type=ActionType.WRITE,
        session_id="s1",
        arguments={"operation": "edit", "filepath": "edit.txt", "expected_content": "return 'old'", "replacement": "return 'new'"},
        requires_confirmation=True
    )
    action_gateway.execute_action(req)
    result = action_gateway.confirm_pending_action("s1")
    assert result.status == ActionStatus.SUCCESS
    assert test_file.read_text() == "def hello():\n    return 'new'\n"

def test_edit_source_text_not_found(workspace):
    test_file = workspace / "edit2.txt"
    test_file.write_text("def hello():\n    return 'old'\n")
    
    req = ActionRequest(
        action_id="e2",
        integration="local_system",
        action_type=ActionType.WRITE,
        session_id="s1",
        arguments={"operation": "edit", "filepath": "edit2.txt", "expected_content": "return 'missing'", "replacement": "return 'new'"},
        requires_confirmation=True
    )
    action_gateway.execute_action(req)
    result = action_gateway.confirm_pending_action("s1")
    assert result.status == ActionStatus.FAILED
    assert "Expected content not found" in result.message
    assert test_file.read_text() == "def hello():\n    return 'old'\n"

def test_edit_multiple_matches_rejected(workspace):
    test_file = workspace / "edit3.txt"
    test_file.write_text("return 'old'\nreturn 'old'\n")
    
    req = ActionRequest(
        action_id="e3",
        integration="local_system",
        action_type=ActionType.WRITE,
        session_id="s1",
        arguments={"operation": "edit", "filepath": "edit3.txt", "expected_content": "return 'old'", "replacement": "return 'new'"},
        requires_confirmation=True
    )
    action_gateway.execute_action(req)
    result = action_gateway.confirm_pending_action("s1")
    assert result.status == ActionStatus.FAILED
    assert "Multiple matches found" in result.message
    assert test_file.read_text() == "return 'old'\nreturn 'old'\n"

def test_patch_valid(workspace):
    test_file = workspace / "patch.txt"
    test_file.write_text("line1\nline2\nline3\n")
    
    patch_content = """--- patch.txt
+++ patch.txt
@@ -1,3 +1,3 @@
 line1
-line2
+line2_patched
 line3
"""
    req = ActionRequest(
        action_id="p1",
        integration="local_system",
        action_type=ActionType.WRITE,
        session_id="s1",
        arguments={"operation": "patch", "filepath": "patch.txt", "patch_content": patch_content},
        requires_confirmation=True
    )
    action_gateway.execute_action(req)
    result = action_gateway.confirm_pending_action("s1")
    assert result.status == ActionStatus.SUCCESS
    assert test_file.read_text() == "line1\nline2_patched\nline3\n"

def test_patch_malformed(workspace):
    test_file = workspace / "patch2.txt"
    test_file.write_text("line1\n")
    
    patch_content = "This is not a patch"
    req = ActionRequest(
        action_id="p2",
        integration="local_system",
        action_type=ActionType.WRITE,
        session_id="s1",
        arguments={"operation": "patch", "filepath": "patch2.txt", "patch_content": patch_content},
        requires_confirmation=True
    )
    action_gateway.execute_action(req)
    result = action_gateway.confirm_pending_action("s1")
    assert result.status == ActionStatus.FAILED
    assert "malformed" in result.message

def test_patch_cannot_apply(workspace):
    test_file = workspace / "patch3.txt"
    test_file.write_text("lineA\n")
    
    patch_content = """--- patch3.txt
+++ patch3.txt
@@ -1,3 +1,3 @@
-line1
+line2
"""
    req = ActionRequest(
        action_id="p3",
        integration="local_system",
        action_type=ActionType.WRITE,
        session_id="s1",
        arguments={"operation": "patch", "filepath": "patch3.txt", "patch_content": patch_content},
        requires_confirmation=True
    )
    action_gateway.execute_action(req)
    result = action_gateway.confirm_pending_action("s1")
    assert result.status == ActionStatus.FAILED
    assert "cannot apply" in result.message
    assert test_file.read_text() == "lineA\n"

def test_patch_target_outside_workspace(workspace):
    patch_content = """--- ../outside.txt
+++ ../outside.txt
@@ -1 +1 @@
-a
+b
"""
    req = ActionRequest(
        action_id="p4",
        integration="local_system",
        action_type=ActionType.WRITE,
        session_id="s1",
        arguments={"operation": "patch", "filepath": "../outside.txt", "patch_content": patch_content},
        requires_confirmation=True
    )
    result = action_gateway.execute_action(req)
    assert result.status == ActionStatus.VALIDATION_ERROR
    assert "escape" in result.message

def test_tool_registry_discovery():
    from app.tools.registry import registry
    tools = registry.get_all_tools()
    
    tool_names = [t.__name__ for t in tools]
    assert "read_workspace_file" in tool_names
    assert "write_workspace_file" in tool_names
    assert "edit_workspace_file" in tool_names
    assert "apply_workspace_patch" in tool_names

def test_edit_concurrency_stale_content(workspace):
    test_file = workspace / "concurrent.txt"
    test_file.write_text("old version")
    
    req = ActionRequest(
        action_id="e4",
        integration="local_system",
        action_type=ActionType.WRITE,
        session_id="s1",
        arguments={"operation": "edit", "filepath": "concurrent.txt", "expected_content": "old version", "replacement": "new version"},
        requires_confirmation=True
    )
    # Prepare
    action_gateway.execute_action(req)
    
    # Another process changes the file
    test_file.write_text("newer version")
    
    # Confirm
    result = action_gateway.confirm_pending_action("s1")
    assert result.status == ActionStatus.FAILED
    assert "Expected content not found" in result.message
    
    # Ensure it wasn't overwritten
    assert test_file.read_text() == "newer version"

def test_rejected_confirmation_no_modification(workspace):
    test_file = workspace / "reject.txt"
    test_file.write_text("start")
    
    req = ActionRequest(
        action_id="e5",
        integration="local_system",
        action_type=ActionType.WRITE,
        session_id="s1",
        arguments={"operation": "edit", "filepath": "reject.txt", "expected_content": "start", "replacement": "end"},
        requires_confirmation=True
    )
    action_gateway.execute_action(req)
    
    # Reject
    result = action_gateway.reject_pending_action("s1")
    assert result.status == ActionStatus.REJECTED
    
    # File unchanged
    assert test_file.read_text() == "start"
