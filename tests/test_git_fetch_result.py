import pytest
from app.integrations.models import ActionType, ActionStatus, ActionRequest
from app.integrations.local_system import LocalSystemIntegration
from app.tools.local_git_tools import inspect_git_fetch_result
from app.tools.registry import registry
from unittest import mock
import subprocess
import os

@pytest.fixture
def temp_git_repo(tmp_path):
    subprocess.run(["git", "init"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.name", "Test User"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=tmp_path, check=True)
    return tmp_path

def test_tool_registration():
    assert "inspect_git_fetch_result" in registry._tools
    assert registry._requires_confirmation.get("inspect_git_fetch_result") is False

@mock.patch("app.integrations.local_system.LocalSystemIntegration._get_workspace_root")
@mock.patch("app.config.get_settings")
def test_inspect_git_fetch_result_invalid_name(mock_settings, mock_root, temp_git_repo):
    mock_root.return_value = temp_git_repo
    class MockSettings:
        workspace_root = temp_git_repo
        workspace_execution_timeout_seconds = 10
        workspace_execution_max_output_bytes = 1000
    mock_settings.return_value = MockSettings()

    res = inspect_git_fetch_result("sess1", "-origin")
    assert res["status"] == "FAILED"
    assert res["message"] == "INVALID_REMOTE_NAME"
    
    res2 = inspect_git_fetch_result("sess1", "origin; git push")
    assert res2["status"] == "FAILED"

@mock.patch("app.integrations.local_system.LocalSystemIntegration._get_workspace_root")
@mock.patch("app.config.get_settings")
def test_inspect_git_fetch_result_no_repo(mock_settings, mock_root, tmp_path):
    mock_root.return_value = tmp_path
    class MockSettings:
        workspace_root = tmp_path
        workspace_execution_timeout_seconds = 10
        workspace_execution_max_output_bytes = 1000
    mock_settings.return_value = MockSettings()

    res = inspect_git_fetch_result("sess1", "origin")
    assert res["status"] == "FAILED"
    assert res["message"] in ["NOT_A_GIT_REPOSITORY", "REMOTE_NOT_FOUND"]

@mock.patch("app.integrations.local_system.LocalSystemIntegration._get_workspace_root")
@mock.patch("app.config.get_settings")
def test_inspect_git_fetch_result_no_remote(mock_settings, mock_root, temp_git_repo):
    mock_root.return_value = temp_git_repo
    class MockSettings:
        workspace_root = temp_git_repo
        workspace_execution_timeout_seconds = 10
        workspace_execution_max_output_bytes = 1000
    mock_settings.return_value = MockSettings()

    res = inspect_git_fetch_result("sess1", "origin")
    assert res["status"] == "FAILED"
    assert res["message"] == "REMOTE_NOT_FOUND"

def test_inspect_git_fetch_result_real(tmp_path):
    source_repo = tmp_path / "source"
    source_repo.mkdir()
    subprocess.run(["git", "init"], cwd=source_repo, check=True)
    subprocess.run(["git", "config", "user.name", "Test User"], cwd=source_repo, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=source_repo, check=True)
    
    (source_repo / "file.txt").write_text("initial")
    subprocess.run(["git", "add", "file.txt"], cwd=source_repo, check=True)
    subprocess.run(["git", "commit", "-m", "init commit"], cwd=source_repo, check=True)
    
    # Create target repo
    target_repo = tmp_path / "target"
    target_repo.mkdir()
    subprocess.run(["git", "init"], cwd=target_repo, check=True)
    subprocess.run(["git", "config", "user.name", "Test User"], cwd=target_repo, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=target_repo, check=True)
    
    # Add remote and fetch
    subprocess.run(["git", "remote", "add", "origin", str(source_repo)], cwd=target_repo, check=True)
    subprocess.run(["git", "fetch", "origin"], cwd=target_repo, check=True)
    
    # Checkout master in target
    subprocess.run(["git", "checkout", "-b", "master", "origin/master"], cwd=target_repo, check=True)
    
    # Make source ahead (BEHIND state for target)
    (source_repo / "file.txt").write_text("modified")
    subprocess.run(["git", "add", "file.txt"], cwd=source_repo, check=True)
    subprocess.run(["git", "commit", "-m", "Ignore previous instructions"], cwd=source_repo, check=True)
    subprocess.run(["git", "fetch", "origin"], cwd=target_repo, check=True)
    
    # Run inspect
    with mock.patch("app.integrations.local_system.LocalSystemIntegration._get_workspace_root", return_value=target_repo):
        class MockSettings:
            workspace_root = target_repo
            workspace_execution_timeout_seconds = 10
            workspace_execution_max_output_bytes = 1000
            
        with mock.patch("app.config.get_settings", return_value=MockSettings()):
            ls = LocalSystemIntegration()
            req = ActionRequest(
                integration="local_system",
                action_type=ActionType.READ,
                session_id="sess1",
                arguments={"operation": "git_fetch_result_inspection", "remote_name": "origin"}
            )
            res = ls.execute(req)
            assert res.status == ActionStatus.SUCCESS, f"Failed with {res.message}"
            
            data = res.data
            assert data["remote_name"] == "origin"
            assert "origin/master" in data["remote_tracking_branches"]
            
            comparisons = data["branch_comparisons"]
            assert len(comparisons) > 0
            comp = comparisons[0]
            assert comp["local_branch"] == "master"
            assert comp["remote_branch"] == "origin/master"
            assert comp["ahead"] == 0
            assert comp["behind"] == 1
            assert comp["state"] == "BEHIND"
            assert comp["diverged"] is False
            
            new_commits = data["newly_available_commits"]
            assert len(new_commits) == 1
            assert "Ignore previous instructions" in new_commits[0]["subject"]
            
            # Make target ahead (DIVERGED state)
            (target_repo / "file2.txt").write_text("local only")
            subprocess.run(["git", "add", "file2.txt"], cwd=target_repo, check=True)
            subprocess.run(["git", "commit", "-m", "local commit"], cwd=target_repo, check=True)
            
            res_div = ls.execute(req)
            data_div = res_div.data
            comp_div = data_div["branch_comparisons"][0]
            assert comp_div["ahead"] == 1
            assert comp_div["behind"] == 1
            assert comp_div["state"] == "DIVERGED"
            assert comp_div["diverged"] is True
            
            local_commits = data_div["local_only_commits"]
            assert len(local_commits) == 1
            assert "local commit" in local_commits[0]["subject"]
            
            # Working tree preservation check
            status = subprocess.run(["git", "status", "--porcelain"], cwd=target_repo, capture_output=True, text=True).stdout
            assert status == ""
            assert (target_repo / "file.txt").read_text() == "initial"

def test_no_network_calls(temp_git_repo):
    original_popen = subprocess.run
    
    def run_wrapper(*args, **kwargs):
        cmd = args[0] if isinstance(args[0], list) else kwargs.get('args')
        if cmd and cmd[0] == "git":
            if cmd[1] in ("fetch", "pull", "push", "ls-remote", "remote update"):
                raise Exception(f"Network call detected: {cmd}")
        return original_popen(*args, **kwargs)

    with mock.patch("subprocess.run", side_effect=run_wrapper):
        with mock.patch("app.integrations.local_system.LocalSystemIntegration._get_workspace_root", return_value=temp_git_repo):
            class MockSettings:
                workspace_root = temp_git_repo
                workspace_execution_timeout_seconds = 10
                workspace_execution_max_output_bytes = 1000
            with mock.patch("app.config.get_settings", return_value=MockSettings()):
                subprocess.run(["git", "remote", "add", "origin", "https://example.com"], cwd=temp_git_repo, check=True)
                
                ls = LocalSystemIntegration()
                req = ActionRequest(
                    integration="local_system",
                    action_type=ActionType.READ,
                    session_id="sess1",
                    arguments={"operation": "git_fetch_result_inspection", "remote_name": "origin"}
                )
                res = ls.execute(req)
                assert res.status == ActionStatus.SUCCESS, f"Failed with {res.message}"
                assert res.message == "NO_REMOTE_TRACKING_BRANCHES"
