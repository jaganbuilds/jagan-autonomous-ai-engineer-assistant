import pytest
import os
import subprocess
from unittest import mock
from app.integrations.local_system import LocalSystemIntegration
from app.integrations.models import ActionRequest, ActionType, ActionStatus
from app.tools.local_git_tools import get_git_branches, get_git_current_branch, create_git_branch
from app.tools.registry import registry
from app.integrations.gateway import action_gateway

@pytest.fixture
def local_system():
    return LocalSystemIntegration()

@pytest.fixture
def temp_git_repo(tmp_path):
    repo_dir = tmp_path / "repo"
    repo_dir.mkdir()
    subprocess.run(["git", "init"], cwd=repo_dir, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=repo_dir, check=True)
    subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=repo_dir, check=True)
    file1 = repo_dir / "file1.txt"
    file1.write_text("v1")
    subprocess.run(["git", "add", "file1.txt"], cwd=repo_dir, check=True)
    subprocess.run(["git", "commit", "-m", "initial"], cwd=repo_dir, check=True)
    return repo_dir

@pytest.fixture
def mock_settings():
    class MockSettings:
        workspace_root = "."
        workspace_execution_timeout_seconds = 2
        workspace_execution_max_output_bytes = 1000
    with mock.patch("app.integrations.local_system.get_settings", return_value=MockSettings()):
        yield

def test_inspection_requires_no_confirmation():
    assert registry.requires_confirmation("get_git_branches") is False
    assert registry.requires_confirmation("get_git_current_branch") is False

def test_creation_requires_confirmation():
    assert registry.requires_confirmation("create_git_branch") is True

def test_get_current_branch(local_system, temp_git_repo):
    with mock.patch("app.integrations.local_system.LocalSystemIntegration._get_workspace_root", return_value=str(temp_git_repo)):
        req = ActionRequest(
            integration="local_system",
            action_type=ActionType.READ,
            session_id="test",
            arguments={"operation": "git", "git_command": "branch", "args": ["--show-current"]}
        )
        res = local_system.execute(req)
        assert res.status == ActionStatus.SUCCESS
        # Note: in detached HEAD or some old git versions, it might be different, but for test it's likely 'master' or 'main'
        assert res.data["stdout"].strip() in ["main", "master"]

def test_get_git_branches_structured(local_system, temp_git_repo):
    # create another branch
    subprocess.run(["git", "branch", "feature"], cwd=temp_git_repo, check=True)
    
    with mock.patch("app.integrations.local_system.LocalSystemIntegration._get_workspace_root", return_value=str(temp_git_repo)):
        req = ActionRequest(
            integration="local_system",
            action_type=ActionType.READ,
            session_id="test",
            arguments={"operation": "git", "git_command": "branch", "args": ["--format=%(refname:short) %(HEAD)"]}
        )
        res = local_system.execute(req)
        assert res.status == ActionStatus.SUCCESS
        
        # We also need to test the wrapper tool logic to ensure structured output is populated
        pass

@mock.patch("app.integrations.local_system.LocalSystemIntegration._get_workspace_root")
def test_wrapper_tools_structured_output(mock_root, temp_git_repo):
    mock_root.return_value = str(temp_git_repo)
    subprocess.run(["git", "branch", "feature"], cwd=temp_git_repo, check=True)
    
    # Need to patch action_gateway so it uses the real LocalSystemIntegration pointing to our mock root
    # Actually, we can just call action_gateway.execute_action(req) directly if the registry is properly wired up.
    # The ActionGateway just dispatches to LocalSystemIntegration natively.
    # We only need to ensure LocalSystemIntegration._get_workspace_root points to temp_git_repo!
    
    res_str = get_git_branches("test_sess")
    import json
    res = json.loads(res_str) if isinstance(res_str, str) else res_str
    
    # result wrapper
    if "result" in res: res = res["result"]
    assert res["status"] == "SUCCESS"
    assert "structured" in res["data"]
    
    struct = res["data"]["structured"]
    assert "feature" in struct["branches"]
    assert struct["current_branch"] in ["main", "master"]

@mock.patch("app.integrations.local_system.LocalSystemIntegration._get_workspace_root")
def test_create_branch_success(mock_root, temp_git_repo):
    mock_root.return_value = str(temp_git_repo)
    
    req = ActionRequest(
        integration="local_system",
        action_type=ActionType.WRITE,
        session_id="test",
        arguments={"operation": "git_create_branch", "branch_name": "new_branch"}
    )
    
    res = LocalSystemIntegration().execute(req)
    assert res.status == ActionStatus.SUCCESS
    
    # verify branch created
    branches = subprocess.run(["git", "branch"], cwd=temp_git_repo, capture_output=True, text=True).stdout
    assert "new_branch" in branches
    
    # verify HEAD didn't change (no checkout)
    current = subprocess.run(["git", "branch", "--show-current"], cwd=temp_git_repo, capture_output=True, text=True).stdout.strip()
    assert current != "new_branch"

@mock.patch("app.integrations.local_system.LocalSystemIntegration._get_workspace_root")
def test_create_branch_already_exists(mock_root, temp_git_repo):
    mock_root.return_value = str(temp_git_repo)
    subprocess.run(["git", "branch", "existing"], cwd=temp_git_repo, check=True)
    
    req = ActionRequest(
        integration="local_system",
        action_type=ActionType.WRITE,
        session_id="test",
        arguments={"operation": "git_create_branch", "branch_name": "existing"}
    )
    
    res = LocalSystemIntegration().execute(req)
    assert res.status == ActionStatus.FAILED
    assert res.message == "BRANCH_ALREADY_EXISTS"

def test_branch_validation(local_system):
    def check(name):
        req = ActionRequest(
            integration="local_system",
            action_type=ActionType.WRITE,
            session_id="test",
            arguments={"operation": "git_create_branch", "branch_name": name}
        )
        return local_system.validate_arguments(req.action_type, req.arguments)

    valid, _ = check("good-branch")
    assert valid is True
    
    valid, err = check("")
    assert valid is False
    assert "missing" in err.lower()
    
    valid, err = check("-flag")
    assert valid is False
    assert "start with '-'" in err
    
    valid, err = check("branch; rm -rf /")
    assert valid is False
    assert "dangerous" in err
    
    valid, err = check("HEAD")
    assert valid is False
    assert "reserved" in err

@mock.patch("app.integrations.local_system.LocalSystemIntegration._get_workspace_root")
def test_git_invalid_ref_rejected(mock_root, temp_git_repo):
    mock_root.return_value = str(temp_git_repo)
    
    req = ActionRequest(
        integration="local_system",
        action_type=ActionType.WRITE,
        session_id="test",
        arguments={"operation": "git_create_branch", "branch_name": "invalid..name"} # git doesn't allow ..
    )
    
    res = LocalSystemIntegration().execute(req)
    assert res.status == ActionStatus.VALIDATION_ERROR
    assert "Invalid Git branch name" in res.message

def test_gateway_requires_confirmation_flow_branch():
    req = ActionRequest(
        integration="local_system",
        action_type=ActionType.WRITE,
        session_id="test",
        arguments={"operation": "git_create_branch", "branch_name": "branch"},
        requires_confirmation=True
    )
    
    res1 = action_gateway.execute_action(req)
    assert res1.status == ActionStatus.WAITING_FOR_CONFIRMATION
    
    res2 = action_gateway.execute_action(req)
    assert res2.status == ActionStatus.WAITING_FOR_CONFIRMATION

@mock.patch("subprocess.Popen")
def test_git_create_timeout(mock_popen, mock_settings):
    # Mock validation pass
    mock_check = mock.Mock()
    mock_check.returncode = 0
    mock_exist = mock.Mock()
    mock_exist.returncode = 1
    
    with mock.patch("subprocess.run", side_effect=[mock_check, mock_exist]):
        mock_proc = mock.Mock()
        import subprocess as sp
        mock_proc.communicate.side_effect = sp.TimeoutExpired(cmd=["git"], timeout=2, output=b"", stderr=b"")
        mock_proc.returncode = None
        mock_popen.return_value = mock_proc
        
        req = ActionRequest(
            integration="local_system",
            action_type=ActionType.WRITE,
            session_id="test",
            arguments={"operation": "git_create_branch", "branch_name": "timeout"}
        )
        res = LocalSystemIntegration().execute(req)
        assert res.status == ActionStatus.FAILED
        assert res.data["timed_out"] is True
