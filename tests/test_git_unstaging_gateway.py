import pytest
import subprocess
from pathlib import Path
from unittest import mock
from app.integrations.models import ActionRequest, ActionType, ActionStatus
from app.integrations.local_system import LocalSystemIntegration
from app.integrations.gateway import action_gateway
from app.tools.local_git_tools import unstage_git_files

@pytest.fixture
def temp_git_repo(tmp_path):
    repo_dir = tmp_path / "repo"
    repo_dir.mkdir()
    
    subprocess.run(["git", "init"], cwd=repo_dir, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=repo_dir, check=True)
    subprocess.run(["git", "config", "user.name", "Test User"], cwd=repo_dir, check=True)
    
    file1 = repo_dir / "file1.txt"
    file1.write_text("initial")
    subprocess.run(["git", "add", "file1.txt"], cwd=repo_dir, check=True)
    subprocess.run(["git", "commit", "-m", "initial"], cwd=repo_dir, check=True)
    
    file2 = repo_dir / "file2.txt"
    file2.write_text("v1")
    subprocess.run(["git", "add", "file2.txt"], cwd=repo_dir, check=True)
    subprocess.run(["git", "commit", "-m", "file2", "file2.txt"], cwd=repo_dir, check=True)
    file2.write_text("v2")
    subprocess.run(["git", "add", "file2.txt"], cwd=repo_dir, check=True)
    return repo_dir

@mock.patch("app.integrations.local_system.LocalSystemIntegration._get_workspace_root")
@mock.patch("app.config.get_settings")
def test_unstage_gateway_flow(mock_settings, mock_root, temp_git_repo):
    mock_root.return_value = temp_git_repo
    class MockSettings:
        workspace_root = temp_git_repo
        workspace_execution_timeout_seconds = 10
        workspace_execution_max_output_bytes = 1000
    mock_settings.return_value = MockSettings()
    
    req = ActionRequest(
        integration="local_system",
        action_type=ActionType.WRITE,
        session_id="test",
        arguments={"operation": "git_unstage_files", "paths": ["file2.txt"]},
        requires_confirmation=True
    )
    
    res1 = action_gateway.execute_action(req)
    assert res1.status == ActionStatus.WAITING_FOR_CONFIRMATION

def test_unstage_validation(temp_git_repo):
    ls = LocalSystemIntegration()
    # Mocking get_workspace_root on instance to avoid filesystem permission issues if running globally
    with mock.patch.object(ls, '_get_workspace_root', return_value=temp_git_repo):
        # 1. Invalid wildcards
        valid, _ = ls.validate_arguments(ActionType.WRITE, {"operation": "git_unstage_files", "paths": ["*.txt"]})
        assert valid is False
        
        # 2. Empty list
        valid, _ = ls.validate_arguments(ActionType.WRITE, {"operation": "git_unstage_files", "paths": []})
        assert valid is False
        
        # 3. Valid file
        valid, _ = ls.validate_arguments(ActionType.WRITE, {"operation": "git_unstage_files", "paths": ["file2.txt"]})
        assert valid is True
