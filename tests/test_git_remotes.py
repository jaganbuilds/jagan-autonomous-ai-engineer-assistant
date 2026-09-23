import pytest
import subprocess
from pathlib import Path
from unittest import mock
from app.integrations.models import ActionRequest, ActionType, ActionStatus
from app.integrations.local_system import LocalSystemIntegration
from app.tools.local_git_tools import get_git_remotes

@pytest.fixture
def temp_git_repo(tmp_path):
    repo_dir = tmp_path / "repo"
    repo_dir.mkdir()
    
    subprocess.run(["git", "init"], cwd=repo_dir, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=repo_dir, check=True)
    subprocess.run(["git", "config", "user.name", "Test User"], cwd=repo_dir, check=True)
    return repo_dir

@mock.patch("app.integrations.local_system.LocalSystemIntegration._get_workspace_root")
@mock.patch("app.config.get_settings")
@mock.patch("subprocess.run")
def test_git_remotes_not_repo(mock_run, mock_settings, mock_root, tmp_path):
    mock_root.return_value = tmp_path
    class MockSettings:
        workspace_root = tmp_path
        workspace_execution_timeout_seconds = 10
        workspace_execution_max_output_bytes = 1000
    mock_settings.return_value = MockSettings()
    
    # Mock rev-parse to fail
    mock_proc = mock.Mock()
    mock_proc.returncode = 128
    mock_run.return_value = mock_proc
    
    res = get_git_remotes("test_sess")
    assert res.get("success") is False
    assert res.get("status") == "NOT_A_GIT_REPOSITORY"

@mock.patch("app.integrations.local_system.LocalSystemIntegration._get_workspace_root")
@mock.patch("app.config.get_settings")
def test_git_remotes_empty(mock_settings, mock_root, temp_git_repo):
    mock_root.return_value = temp_git_repo
    class MockSettings:
        workspace_root = temp_git_repo
        workspace_execution_timeout_seconds = 10
        workspace_execution_max_output_bytes = 1000
    mock_settings.return_value = MockSettings()
    
    res = get_git_remotes("test_sess")
    assert res.get("success") is True
    assert res.get("remotes") == []

@mock.patch("app.integrations.local_system.LocalSystemIntegration._get_workspace_root")
@mock.patch("app.config.get_settings")
def test_git_remotes_sanitization(mock_settings, mock_root, temp_git_repo):
    mock_root.return_value = temp_git_repo
    class MockSettings:
        workspace_root = temp_git_repo
        workspace_execution_timeout_seconds = 10
        workspace_execution_max_output_bytes = 1000
    mock_settings.return_value = MockSettings()
    
    subprocess.run(["git", "remote", "add", "origin", "https://user:password123@example.com/repo.git"], cwd=temp_git_repo, check=True)
    subprocess.run(["git", "remote", "add", "upstream", "https://ghp_SECRET_TOKEN@github.com/org/repo.git"], cwd=temp_git_repo, check=True)
    subprocess.run(["git", "remote", "add", "ssh_remote", "git@github.com:owner/repo.git"], cwd=temp_git_repo, check=True)
    subprocess.run(["git", "remote", "add", "query_remote", "https://example.com/repo.git?token=SECRET_VALUE"], cwd=temp_git_repo, check=True)
    
    res = get_git_remotes("test_sess")
    assert res.get("success") is True
    
    remotes = {r["name"]: r for r in res["remotes"]}
    assert len(remotes) == 4
    assert remotes["origin"]["fetch_url"] == "https://example.com/repo.git"
    assert remotes["upstream"]["fetch_url"] == "https://github.com/org/repo.git"
    assert remotes["ssh_remote"]["fetch_url"] == "github.com:owner/repo.git"
    assert remotes["query_remote"]["fetch_url"] == "https://example.com/repo.git?token=REDACTED"
    assert res.get("stdout") == "[REDACTED BY INTEGRATION]"
    assert res.get("stderr") == "[REDACTED BY INTEGRATION]"

@mock.patch("app.integrations.local_system.LocalSystemIntegration._get_workspace_root")
@mock.patch("app.config.get_settings")
def test_git_remotes_push_fetch_split(mock_settings, mock_root, temp_git_repo):
    mock_root.return_value = temp_git_repo
    class MockSettings:
        workspace_root = temp_git_repo
        workspace_execution_timeout_seconds = 10
        workspace_execution_max_output_bytes = 1000
    mock_settings.return_value = MockSettings()
    
    subprocess.run(["git", "remote", "add", "origin", "https://example.com/fetch.git"], cwd=temp_git_repo, check=True)
    subprocess.run(["git", "remote", "set-url", "--push", "origin", "https://example.com/push.git"], cwd=temp_git_repo, check=True)
    
    res = get_git_remotes("test_sess")
    assert res.get("success") is True
    
    remotes = res["remotes"]
    assert len(remotes) == 1
    
    origin = remotes[0]
    assert origin["name"] == "origin"
    assert origin["fetch_url"] == "https://example.com/fetch.git"
    assert origin["push_url"] == "https://example.com/push.git"

def test_git_remotes_validation():
    ls = LocalSystemIntegration()
    valid, err = ls.validate_arguments(ActionType.READ, {"operation": "git_remotes"})
    assert valid is True
    assert err == ""
