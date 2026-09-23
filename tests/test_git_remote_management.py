from app.tools.registry import registry
import pytest
import subprocess
from pathlib import Path
from unittest import mock
from app.integrations.models import ActionRequest, ActionType, ActionStatus
from app.integrations.local_system import LocalSystemIntegration
from app.tools.local_git_tools import add_git_remote, remove_git_remote, rename_git_remote, set_git_remote_url

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
def test_add_git_remote_basic(mock_settings, mock_root, temp_git_repo):
    mock_root.return_value = temp_git_repo
    class MockSettings:
        workspace_root = temp_git_repo
        workspace_execution_timeout_seconds = 10
        workspace_execution_max_output_bytes = 1000
    mock_settings.return_value = MockSettings()
    
    res = add_git_remote("sess1", "origin", "https://example.com/repo.git")
    assert res["status"] == "WAITING_FOR_CONFIRMATION"
    assert "https://example.com/repo.git" in res["message"]

@mock.patch("app.integrations.local_system.LocalSystemIntegration._get_workspace_root")
@mock.patch("app.config.get_settings")
def test_add_git_remote_sanitization(mock_settings, mock_root, temp_git_repo):
    mock_root.return_value = temp_git_repo
    class MockSettings:
        workspace_root = temp_git_repo
        workspace_execution_timeout_seconds = 10
        workspace_execution_max_output_bytes = 1000
    mock_settings.return_value = MockSettings()
    
    # Tool strips password
    res = add_git_remote("sess1", "origin", "https://user:password123@example.com/repo.git")
    assert res["status"] == "WAITING_FOR_CONFIRMATION"
    assert "password123" not in res["message"]
    assert "https://example.com/repo.git" in res["message"]

@mock.patch("app.integrations.local_system.LocalSystemIntegration._get_workspace_root")
@mock.patch("app.config.get_settings")
def test_add_git_remote_already_exists(mock_settings, mock_root, temp_git_repo):
    mock_root.return_value = temp_git_repo
    class MockSettings:
        workspace_root = temp_git_repo
        workspace_execution_timeout_seconds = 10
        workspace_execution_max_output_bytes = 1000
    mock_settings.return_value = MockSettings()
    
    subprocess.run(["git", "remote", "add", "origin", "https://example.com/old.git"], cwd=temp_git_repo, check=True)
    
    res = add_git_remote("sess1", "origin", "https://example.com/repo.git")
    assert res["status"] == "FAILED"
    assert res["message"] == "REMOTE_ALREADY_EXISTS"

@mock.patch("app.integrations.local_system.LocalSystemIntegration._get_workspace_root")
@mock.patch("app.config.get_settings")
def test_add_git_remote_execution(mock_settings, mock_root, temp_git_repo):
    mock_root.return_value = temp_git_repo
    class MockSettings:
        workspace_root = temp_git_repo
        workspace_execution_timeout_seconds = 10
        workspace_execution_max_output_bytes = 1000
    mock_settings.return_value = MockSettings()
    
    ls = LocalSystemIntegration()
    req = ActionRequest(
        integration="local_system",
        action_type=ActionType.WRITE,
        session_id="sess1",
        arguments={"operation": "git_remote_add", "name": "origin", "url": "https://example.com/repo.git"}
    )
    res = ls.execute(req)
    assert res.status == ActionStatus.SUCCESS
    assert res.data["success"] is True
    assert res.data["stdout"] == "[REDACTED BY INTEGRATION]"
    
    remotes_proc = subprocess.run(["git", "remote", "-v"], cwd=temp_git_repo, capture_output=True, text=True)
    assert "origin\thttps://example.com/repo.git (fetch)" in remotes_proc.stdout

@mock.patch("app.integrations.local_system.LocalSystemIntegration._get_workspace_root")
@mock.patch("app.config.get_settings")
def test_remove_git_remote(mock_settings, mock_root, temp_git_repo):
    mock_root.return_value = temp_git_repo
    class MockSettings:
        workspace_root = temp_git_repo
        workspace_execution_timeout_seconds = 10
        workspace_execution_max_output_bytes = 1000
    mock_settings.return_value = MockSettings()
    
    subprocess.run(["git", "remote", "add", "origin", "https://example.com/old.git"], cwd=temp_git_repo, check=True)
    
    ls = LocalSystemIntegration()
    req = ActionRequest(
        integration="local_system",
        action_type=ActionType.WRITE,
        session_id="sess1",
        arguments={"operation": "git_remote_remove", "name": "origin"}
    )
    res = ls.execute(req)
    assert res.status == ActionStatus.SUCCESS
    
    remotes_proc = subprocess.run(["git", "remote", "-v"], cwd=temp_git_repo, capture_output=True, text=True)
    assert "origin" not in remotes_proc.stdout

@mock.patch("app.integrations.local_system.LocalSystemIntegration._get_workspace_root")
@mock.patch("app.config.get_settings")
def test_remove_git_remote_not_found(mock_settings, mock_root, temp_git_repo):
    mock_root.return_value = temp_git_repo
    class MockSettings:
        workspace_root = temp_git_repo
        workspace_execution_timeout_seconds = 10
        workspace_execution_max_output_bytes = 1000
    mock_settings.return_value = MockSettings()
    
    res = remove_git_remote("sess1", "origin")
    assert res["status"] == "FAILED"
    assert res["message"] == "REMOTE_NOT_FOUND"

@mock.patch("app.integrations.local_system.LocalSystemIntegration._get_workspace_root")
@mock.patch("app.config.get_settings")
def test_rename_git_remote(mock_settings, mock_root, temp_git_repo):
    mock_root.return_value = temp_git_repo
    class MockSettings:
        workspace_root = temp_git_repo
        workspace_execution_timeout_seconds = 10
        workspace_execution_max_output_bytes = 1000
    mock_settings.return_value = MockSettings()
    
    subprocess.run(["git", "remote", "add", "origin", "https://example.com/repo.git"], cwd=temp_git_repo, check=True)
    
    ls = LocalSystemIntegration()
    req = ActionRequest(
        integration="local_system",
        action_type=ActionType.WRITE,
        session_id="sess1",
        arguments={"operation": "git_remote_rename", "old_name": "origin", "new_name": "upstream"}
    )
    res = ls.execute(req)
    assert res.status == ActionStatus.SUCCESS
    
    remotes_proc = subprocess.run(["git", "remote", "-v"], cwd=temp_git_repo, capture_output=True, text=True)
    assert "origin" not in remotes_proc.stdout
    assert "upstream\thttps://example.com/repo.git (fetch)" in remotes_proc.stdout

@mock.patch("app.integrations.local_system.LocalSystemIntegration._get_workspace_root")
@mock.patch("app.config.get_settings")
def test_set_git_remote_url(mock_settings, mock_root, temp_git_repo):
    mock_root.return_value = temp_git_repo
    class MockSettings:
        workspace_root = temp_git_repo
        workspace_execution_timeout_seconds = 10
        workspace_execution_max_output_bytes = 1000
    mock_settings.return_value = MockSettings()
    
    subprocess.run(["git", "remote", "add", "origin", "https://example.com/repo.git"], cwd=temp_git_repo, check=True)
    
    ls = LocalSystemIntegration()
    req = ActionRequest(
        integration="local_system",
        action_type=ActionType.WRITE,
        session_id="sess1",
        arguments={"operation": "git_remote_set_url", "name": "origin", "url": "https://example.com/new.git"}
    )
    res = ls.execute(req)
    assert res.status == ActionStatus.SUCCESS
    
    remotes_proc = subprocess.run(["git", "remote", "-v"], cwd=temp_git_repo, capture_output=True, text=True)
    assert "origin\thttps://example.com/new.git (fetch)" in remotes_proc.stdout

def test_git_remote_validation_logic():
    ls = LocalSystemIntegration()
    
    # Valid
    valid, err = ls.validate_arguments(ActionType.WRITE, {"operation": "git_remote_add", "name": "origin", "url": "https://example.com"})
    assert valid is True
    
    # Invalid name
    valid, err = ls.validate_arguments(ActionType.WRITE, {"operation": "git_remote_add", "name": "-origin", "url": "https://example.com"})
    assert valid is False
    
    valid, err = ls.validate_arguments(ActionType.WRITE, {"operation": "git_remote_add", "name": "ori gin", "url": "https://example.com"})
    assert valid is False
    
    valid, err = ls.validate_arguments(ActionType.WRITE, {"operation": "git_remote_add", "name": "origin;", "url": "https://example.com"})
    assert valid is False
    
    # Invalid URL
    valid, err = ls.validate_arguments(ActionType.WRITE, {"operation": "git_remote_add", "name": "origin", "url": "-https://example.com"})
    assert valid is False


# ====== ADDITIONAL TESTS ======

@mock.patch("app.integrations.local_system.LocalSystemIntegration._get_workspace_root")
@mock.patch("app.config.get_settings")
def test_add_git_remote_invalid_name(mock_settings, mock_root, temp_git_repo):
    mock_root.return_value = temp_git_repo
    class MockSettings:
        workspace_root = temp_git_repo
        workspace_execution_timeout_seconds = 10
        workspace_execution_max_output_bytes = 1000
    mock_settings.return_value = MockSettings()
    
    res = add_git_remote("sess1", "-origin", "https://example.com/repo.git")
    assert res["status"] == "FAILED"
    assert res["message"] == "INVALID_REMOTE_NAME"

@mock.patch("app.integrations.local_system.LocalSystemIntegration._get_workspace_root")
@mock.patch("app.config.get_settings")
def test_add_git_remote_invalid_url(mock_settings, mock_root, temp_git_repo):
    mock_root.return_value = temp_git_repo
    class MockSettings:
        workspace_root = temp_git_repo
        workspace_execution_timeout_seconds = 10
        workspace_execution_max_output_bytes = 1000
    mock_settings.return_value = MockSettings()
    
    res = add_git_remote("sess1", "origin", "-https://example.com/repo.git")
    assert res["status"] == "FAILED"
    assert res["message"] == "INVALID_REMOTE_URL"
    
@mock.patch("app.integrations.local_system.LocalSystemIntegration._get_workspace_root")
@mock.patch("app.config.get_settings")
def test_add_git_remote_shell_injection(mock_settings, mock_root, temp_git_repo):
    mock_root.return_value = temp_git_repo
    class MockSettings:
        workspace_root = temp_git_repo
        workspace_execution_timeout_seconds = 10
        workspace_execution_max_output_bytes = 1000
    mock_settings.return_value = MockSettings()
    
    res = add_git_remote("sess1", "origin;git push", "https://example.com/repo.git")
    assert res["status"] == "FAILED"
    assert res["message"] == "INVALID_REMOTE_NAME"

@mock.patch("app.integrations.local_system.LocalSystemIntegration._get_workspace_root")
@mock.patch("app.config.get_settings")
def test_remove_git_remote_invalid_name(mock_settings, mock_root, temp_git_repo):
    mock_root.return_value = temp_git_repo
    class MockSettings:
        workspace_root = temp_git_repo
        workspace_execution_timeout_seconds = 10
        workspace_execution_max_output_bytes = 1000
    mock_settings.return_value = MockSettings()
    
    res = remove_git_remote("sess1", "-origin")
    assert res["status"] == "FAILED"
    assert res["message"] == "INVALID_REMOTE_NAME"

@mock.patch("app.integrations.local_system.LocalSystemIntegration._get_workspace_root")
@mock.patch("app.config.get_settings")
def test_rename_git_remote_same_name(mock_settings, mock_root, temp_git_repo):
    mock_root.return_value = temp_git_repo
    class MockSettings:
        workspace_root = temp_git_repo
        workspace_execution_timeout_seconds = 10
        workspace_execution_max_output_bytes = 1000
    mock_settings.return_value = MockSettings()
    
    res = rename_git_remote("sess1", "origin", "origin")
    assert res["status"] == "FAILED"
    assert res["message"] == "INVALID_REMOTE_NAME"
    
@mock.patch("app.integrations.local_system.LocalSystemIntegration._get_workspace_root")
@mock.patch("app.config.get_settings")
def test_rename_git_remote_already_exists(mock_settings, mock_root, temp_git_repo):
    mock_root.return_value = temp_git_repo
    class MockSettings:
        workspace_root = temp_git_repo
        workspace_execution_timeout_seconds = 10
        workspace_execution_max_output_bytes = 1000
    mock_settings.return_value = MockSettings()
    
    subprocess.run(["git", "remote", "add", "origin", "https://example.com/repo.git"], cwd=temp_git_repo, check=True)
    subprocess.run(["git", "remote", "add", "upstream", "https://example.com/repo2.git"], cwd=temp_git_repo, check=True)
    
    res = rename_git_remote("sess1", "origin", "upstream")
    assert res["status"] == "FAILED"
    assert res["message"] == "REMOTE_ALREADY_EXISTS"

@mock.patch("app.integrations.local_system.LocalSystemIntegration._get_workspace_root")
@mock.patch("app.config.get_settings")
def test_set_git_remote_url_invalid(mock_settings, mock_root, temp_git_repo):
    mock_root.return_value = temp_git_repo
    class MockSettings:
        workspace_root = temp_git_repo
        workspace_execution_timeout_seconds = 10
        workspace_execution_max_output_bytes = 1000
    mock_settings.return_value = MockSettings()
    
    subprocess.run(["git", "remote", "add", "origin", "https://example.com/repo.git"], cwd=temp_git_repo, check=True)
    
    res = set_git_remote_url("sess1", "origin", "-https://example.com/repo.git")
    assert res["status"] == "FAILED"
    assert res["message"] == "INVALID_REMOTE_URL"

@mock.patch("app.integrations.local_system.LocalSystemIntegration._get_workspace_root")
@mock.patch("app.config.get_settings")
def test_set_git_remote_url_not_found(mock_settings, mock_root, temp_git_repo):
    mock_root.return_value = temp_git_repo
    class MockSettings:
        workspace_root = temp_git_repo
        workspace_execution_timeout_seconds = 10
        workspace_execution_max_output_bytes = 1000
    mock_settings.return_value = MockSettings()
    
    res = set_git_remote_url("sess1", "origin", "https://example.com/repo.git")
    assert res["status"] == "FAILED"
    assert res["message"] == "REMOTE_NOT_FOUND"

@mock.patch("app.integrations.local_system.LocalSystemIntegration._get_workspace_root")
@mock.patch("app.config.get_settings")
def test_add_git_remote_toctou(mock_settings, mock_root, temp_git_repo):
    mock_root.return_value = temp_git_repo
    class MockSettings:
        workspace_root = temp_git_repo
        workspace_execution_timeout_seconds = 10
        workspace_execution_max_output_bytes = 1000
    mock_settings.return_value = MockSettings()
    
    # Pre-flight is clean, but right before execution, another process adds it
    subprocess.run(["git", "remote", "add", "origin", "https://example.com/old.git"], cwd=temp_git_repo, check=True)
    
    ls = LocalSystemIntegration()
    req = ActionRequest(
        integration="local_system",
        action_type=ActionType.WRITE,
        session_id="sess1",
        arguments={"operation": "git_remote_add", "name": "origin", "url": "https://example.com/repo.git"}
    )
    res = ls.execute(req)
    assert res.status == ActionStatus.FAILED
    assert res.message == "REMOTE_ALREADY_EXISTS"

@mock.patch("app.integrations.local_system.LocalSystemIntegration._get_workspace_root")
@mock.patch("app.config.get_settings")
def test_no_network_calls(mock_settings, mock_root, temp_git_repo):
    mock_root.return_value = temp_git_repo
    class MockSettings:
        workspace_root = temp_git_repo
        workspace_execution_timeout_seconds = 10
        workspace_execution_max_output_bytes = 1000
    mock_settings.return_value = MockSettings()
    
    import subprocess
    original_popen = subprocess.Popen
    called_cmds = []
    
    def popen_wrapper(*args, **kwargs):
        cmd = args[0] if isinstance(args[0], list) else kwargs.get('args')
        if cmd:
            called_cmds.append(cmd)
            if cmd[0] == "git" and len(cmd) > 1 and cmd[1] in ("fetch", "push", "pull", "clone", "ls-remote"):
                raise Exception(f"Network call detected: {cmd}")
        return original_popen(*args, **kwargs)
        
    with mock.patch("subprocess.Popen", side_effect=popen_wrapper) as mock_popen:
        ls = LocalSystemIntegration()
        req = ActionRequest(
            integration="local_system",
            action_type=ActionType.WRITE,
            session_id="sess1",
            arguments={"operation": "git_remote_add", "name": "origin", "url": "https://example.com/repo.git"}
        )
        res = ls.execute(req)
        assert res.status == ActionStatus.SUCCESS, f"Failed: {res.message}"
        
        found_add = False
        for cmd in called_cmds:
            if cmd[:3] == ["git", "remote", "add"]:
                found_add = True
                assert cmd == ["git", "remote", "add", "origin", "https://example.com/repo.git"]
        assert found_add, "git remote add was not called"

def test_tool_registration():
    assert "add_git_remote" in registry._tools
    assert "remove_git_remote" in registry._tools
    assert "rename_git_remote" in registry._tools
    assert "set_git_remote_url" in registry._tools
    
    assert registry._requires_confirmation["add_git_remote"] is True
    assert registry._requires_confirmation["remove_git_remote"] is True
    assert registry._requires_confirmation["rename_git_remote"] is True
    assert registry._requires_confirmation["set_git_remote_url"] is True

