import pytest
from app.integrations.models import ActionType, ActionStatus, ActionRequest
from app.integrations.local_system import LocalSystemIntegration
from app.tools.local_git_tools import fetch_git_remote
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
    assert "fetch_git_remote" in registry._tools
    assert registry._requires_confirmation["fetch_git_remote"] is True

@mock.patch("app.integrations.local_system.LocalSystemIntegration._get_workspace_root")
@mock.patch("app.config.get_settings")
def test_fetch_git_remote_tool_validation(mock_settings, mock_root, temp_git_repo):
    mock_root.return_value = temp_git_repo
    class MockSettings:
        workspace_root = temp_git_repo
        workspace_execution_timeout_seconds = 10
        workspace_execution_max_output_bytes = 1000
    mock_settings.return_value = MockSettings()

    subprocess.run(["git", "remote", "add", "origin", "https://example.com/repo.git"], cwd=temp_git_repo, check=True)
    
    with mock.patch("app.tools.local_git_tools.action_gateway.execute_action") as mock_exec:
        mock_res = mock.MagicMock()
        mock_res.status = ActionStatus.WAITING_FOR_CONFIRMATION
        mock_res.model_dump.return_value = {"status": "WAITING_FOR_CONFIRMATION"}
        mock_exec.return_value = mock_res
        
        res = fetch_git_remote("sess1", "origin")
        
        req = mock_exec.call_args[0][0]
        assert req.action_type == ActionType.EXECUTE
        assert req.arguments["operation"] == "git_fetch"
        assert req.arguments["remote_name"] == "origin"
        assert req.arguments["pinned_url"] == "https://example.com/repo.git"
        assert "https://example.com/repo.git" in req.arguments["confirmation_message"]

@mock.patch("app.integrations.local_system.LocalSystemIntegration._get_workspace_root")
@mock.patch("app.config.get_settings")
def test_fetch_git_remote_not_found(mock_settings, mock_root, temp_git_repo):
    mock_root.return_value = temp_git_repo
    class MockSettings:
        workspace_root = temp_git_repo
        workspace_execution_timeout_seconds = 10
        workspace_execution_max_output_bytes = 1000
    mock_settings.return_value = MockSettings()

    res = fetch_git_remote("sess1", "nonexistent")
    assert res["status"] == "FAILED"
    assert res["message"] == "REMOTE_NOT_FOUND"

@mock.patch("app.integrations.local_system.LocalSystemIntegration._get_workspace_root")
@mock.patch("app.config.get_settings")
def test_fetch_git_remote_invalid_name(mock_settings, mock_root, temp_git_repo):
    mock_root.return_value = temp_git_repo
    class MockSettings:
        workspace_root = temp_git_repo
        workspace_execution_timeout_seconds = 10
        workspace_execution_max_output_bytes = 1000
    mock_settings.return_value = MockSettings()

    res = fetch_git_remote("sess1", "-origin")
    assert res["status"] == "FAILED"
    assert res["message"] == "INVALID_REMOTE_NAME"

@mock.patch("app.integrations.local_system.LocalSystemIntegration._get_workspace_root")
@mock.patch("app.config.get_settings")
def test_fetch_git_remote_shell_injection(mock_settings, mock_root, temp_git_repo):
    mock_root.return_value = temp_git_repo
    class MockSettings:
        workspace_root = temp_git_repo
        workspace_execution_timeout_seconds = 10
        workspace_execution_max_output_bytes = 1000
    mock_settings.return_value = MockSettings()

    res = fetch_git_remote("sess1", "origin;git push")
    assert res["status"] == "FAILED"
    assert res["message"] == "INVALID_REMOTE_NAME"

@mock.patch("app.integrations.local_system.LocalSystemIntegration._get_workspace_root")
@mock.patch("app.config.get_settings")
def test_fetch_git_remote_execution(mock_settings, mock_root, temp_git_repo):
    mock_root.return_value = temp_git_repo
    class MockSettings:
        workspace_root = temp_git_repo
        workspace_execution_timeout_seconds = 10
        workspace_execution_max_output_bytes = 1000
    mock_settings.return_value = MockSettings()

    subprocess.run(["git", "remote", "add", "origin", "https://example.com/repo.git"], cwd=temp_git_repo, check=True)

    original_popen = subprocess.Popen
    called_cmds = []

    def popen_wrapper(*args, **kwargs):
        cmd = args[0] if isinstance(args[0], list) else kwargs.get('args')
        if cmd:
            called_cmds.append(cmd)
            # Prevent actual fetch by returning a dummy
            if cmd[:2] == ["git", "fetch"]:
                mock_proc = mock.MagicMock()
                mock_proc.communicate.return_value = ("fetch stdout", "fetch stderr")
                mock_proc.returncode = 0
                mock_proc.wait.return_value = 0
                return mock_proc
            if cmd[0] == "git" and len(cmd) > 1 and cmd[1] in ("push", "pull", "clone", "ls-remote"):
                raise Exception(f"Network call detected: {cmd}")
        return original_popen(*args, **kwargs)

    with mock.patch("subprocess.Popen", side_effect=popen_wrapper):
        ls = LocalSystemIntegration()
        req = ActionRequest(
            integration="local_system",
            action_type=ActionType.EXECUTE,
            session_id="sess1",
            arguments={"operation": "git_fetch", "remote_name": "origin", "pinned_url": "https://example.com/repo.git"}
        )
        res = ls.execute(req)
        assert res.status == ActionStatus.SUCCESS, f"Failed: {res.message}"
        assert res.data["network_operation"] is True
        
        found_fetch = False
        for cmd in called_cmds:
            if cmd[:3] == ["git", "fetch", "origin"]:
                found_fetch = True
                assert cmd == ["git", "fetch", "origin"]
        assert found_fetch, "git fetch origin was not called"

@mock.patch("app.integrations.local_system.LocalSystemIntegration._get_workspace_root")
@mock.patch("app.config.get_settings")
def test_fetch_git_remote_toctou(mock_settings, mock_root, temp_git_repo):
    mock_root.return_value = temp_git_repo
    class MockSettings:
        workspace_root = temp_git_repo
        workspace_execution_timeout_seconds = 10
        workspace_execution_max_output_bytes = 1000
    mock_settings.return_value = MockSettings()

    subprocess.run(["git", "remote", "add", "origin", "https://example.com/repo.git"], cwd=temp_git_repo, check=True)

    ls = LocalSystemIntegration()
    # pinned_url is different from the actual url in repo (simulating it changed after preflight)
    req = ActionRequest(
        integration="local_system",
        action_type=ActionType.EXECUTE,
        session_id="sess1",
        arguments={"operation": "git_fetch", "remote_name": "origin", "pinned_url": "https://example.com/old.git"}
    )
    res = ls.execute(req)
    assert res.status == ActionStatus.FAILED
    assert res.message == "REMOTE_CONFIGURATION_CHANGED"

def test_fetch_git_remote_real(tmp_path):
    import time
    source_repo = tmp_path / "source"
    source_repo.mkdir()
    subprocess.run(["git", "init"], cwd=source_repo, check=True)
    subprocess.run(["git", "config", "user.name", "Test User"], cwd=source_repo, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=source_repo, check=True)
    
    (source_repo / "file.txt").write_text("initial")
    subprocess.run(["git", "add", "file.txt"], cwd=source_repo, check=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=source_repo, check=True)
    
    target_repo = tmp_path / "target"
    target_repo.mkdir()
    subprocess.run(["git", "init"], cwd=target_repo, check=True)
    subprocess.run(["git", "config", "user.name", "Test User"], cwd=target_repo, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=target_repo, check=True)
    
    subprocess.run(["git", "remote", "add", "origin", str(source_repo)], cwd=target_repo, check=True)
    
    with mock.patch("app.integrations.local_system.LocalSystemIntegration._get_workspace_root", return_value=target_repo):
        class MockSettings:
            workspace_root = target_repo
            workspace_execution_timeout_seconds = 10
            workspace_execution_max_output_bytes = 1000
            
        with mock.patch("app.config.get_settings", return_value=MockSettings()):
            ls = LocalSystemIntegration()
            req = ActionRequest(
                integration="local_system",
                action_type=ActionType.EXECUTE,
                session_id="sess1",
                arguments={"operation": "git_fetch", "remote_name": "origin", "pinned_url": str(source_repo)}
            )
            res = ls.execute(req)
            assert res.status == ActionStatus.SUCCESS
            assert res.data["network_operation"] is True
            
            # Verify refs were updated
            refs = subprocess.run(["git", "branch", "-r"], cwd=target_repo, capture_output=True, text=True).stdout
            assert "origin/master" in refs or "origin/main" in refs
            
            # Verify working tree remains unchanged
            assert not (target_repo / "file.txt").exists()
