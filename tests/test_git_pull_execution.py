import pytest
from unittest import mock
import subprocess
from app.integrations.models import ActionType, ActionStatus, ActionRequest, ActionResult
from app.integrations.local_system import LocalSystemIntegration
from app.tools.local_git_tools import execute_git_pull
from app.tools.registry import registry

@pytest.fixture
def temp_git_repo(tmp_path):
    subprocess.run(["git", "init"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.name", "Test User"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=tmp_path, check=True)
    return tmp_path

def test_tool_registration():
    assert "execute_git_pull" in registry._tools
    assert registry._requires_confirmation.get("execute_git_pull") is True

@mock.patch("app.integrations.local_system.LocalSystemIntegration._get_workspace_root")
@mock.patch("app.config.get_settings")
def test_execute_git_pull_tool_validation(mock_settings, mock_root, temp_git_repo):
    mock_root.return_value = temp_git_repo
    class MockSettings:
        workspace_root = temp_git_repo
    mock_settings.return_value = MockSettings()

    res = execute_git_pull("sess1", "-origin")
    assert res["status"] == "FAILED"
    assert res["message"] == "INVALID_REMOTE_NAME"

def test_no_network_calls_for_pull_execution(tmp_path):
    # Tests that no fetch/pull is actually called in the execution logic.
    original_popen = subprocess.run
    
    def run_wrapper(*args, **kwargs):
        cmd = args[0] if isinstance(args[0], list) else kwargs.get('args')
        if cmd and cmd[0] == "git":
            if cmd[1] in ("fetch", "pull", "push", "ls-remote", "remote update"):
                raise Exception(f"Network call detected: {cmd}")
        return original_popen(*args, **kwargs)

    source_repo = tmp_path / "source"
    source_repo.mkdir()
    subprocess.run(["git", "init"], cwd=source_repo, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=source_repo, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=source_repo, check=True)
    (source_repo / "f.txt").write_text("a")
    subprocess.run(["git", "add", "f.txt"], cwd=source_repo, check=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=source_repo, check=True)
    
    target_repo = tmp_path / "target"
    target_repo.mkdir()
    subprocess.run(["git", "init"], cwd=target_repo, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=target_repo, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=target_repo, check=True)
    subprocess.run(["git", "remote", "add", "origin", str(source_repo)], cwd=target_repo, check=True)
    subprocess.run(["git", "fetch", "origin"], cwd=target_repo, check=True)
    subprocess.run(["git", "checkout", "-b", "master", "origin/master"], cwd=target_repo, check=True)

    # Make source ahead
    (source_repo / "f.txt").write_text("b")
    subprocess.run(["git", "add", "f.txt"], cwd=source_repo, check=True)
    subprocess.run(["git", "commit", "-m", "source"], cwd=source_repo, check=True)
    
    subprocess.run(["git", "fetch", "origin"], cwd=target_repo, check=True)

    with mock.patch("subprocess.run", side_effect=run_wrapper):
        with mock.patch("app.integrations.local_system.LocalSystemIntegration._get_workspace_root", return_value=target_repo):
            class MockSettings:
                workspace_root = target_repo
                workspace_execution_timeout_seconds = 10
                workspace_execution_max_output_bytes = 1000
            with mock.patch("app.config.get_settings", return_value=MockSettings()):
                ls = LocalSystemIntegration()
                
                # Fetch target shas
                target_head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=target_repo, capture_output=True, text=True).stdout.strip()
                target_upstream = subprocess.run(["git", "rev-parse", "refs/remotes/origin/master"], cwd=target_repo, capture_output=True, text=True).stdout.strip()
                
                req = ActionRequest(
                    integration="local_system",
                    action_type=ActionType.WRITE,
                    session_id="sess1",
                    arguments={
                        "operation": "git_pull_fast_forward",
                        "remote_name": "origin",
                        "current_branch": "master",
                        "upstream_branch": "origin/master",
                        "upstream_ref": "refs/remotes/origin/master",
                        "expected_head_sha": target_head,
                        "expected_upstream_sha": target_upstream,
                        "behind": 1,
                    }
                )
                res = ls.execute(req)
                assert res.status == ActionStatus.SUCCESS
                assert res.data["new_head"] == target_upstream
                assert res.data["working_tree_clean"] is True
                assert res.data["network_used"] is False
                assert res.data["merge_commit_created"] is False
                
                # Check status
                status = subprocess.run(["git", "status", "--porcelain"], cwd=target_repo, capture_output=True, text=True).stdout.strip()
                assert status == ""

def test_stale_pull_proposal_toctou(tmp_path):
    source_repo = tmp_path / "source"
    source_repo.mkdir()
    subprocess.run(["git", "init"], cwd=source_repo, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=source_repo, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=source_repo, check=True)
    (source_repo / "f.txt").write_text("a")
    subprocess.run(["git", "add", "f.txt"], cwd=source_repo, check=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=source_repo, check=True)
    
    target_repo = tmp_path / "target"
    target_repo.mkdir()
    subprocess.run(["git", "init"], cwd=target_repo, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=target_repo, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=target_repo, check=True)
    subprocess.run(["git", "remote", "add", "origin", str(source_repo)], cwd=target_repo, check=True)
    subprocess.run(["git", "fetch", "origin"], cwd=target_repo, check=True)
    subprocess.run(["git", "checkout", "-b", "master", "origin/master"], cwd=target_repo, check=True)

    # Source ahead
    (source_repo / "f.txt").write_text("b")
    subprocess.run(["git", "add", "f.txt"], cwd=source_repo, check=True)
    subprocess.run(["git", "commit", "-m", "source"], cwd=source_repo, check=True)
    subprocess.run(["git", "fetch", "origin"], cwd=target_repo, check=True)
    
    with mock.patch("app.integrations.local_system.LocalSystemIntegration._get_workspace_root", return_value=target_repo):
        class MockSettings:
            workspace_root = target_repo
            workspace_execution_timeout_seconds = 10
            workspace_execution_max_output_bytes = 1000
        with mock.patch("app.config.get_settings", return_value=MockSettings()):
            ls = LocalSystemIntegration()
            
            target_head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=target_repo, capture_output=True, text=True).stdout.strip()
            target_upstream = subprocess.run(["git", "rev-parse", "refs/remotes/origin/master"], cwd=target_repo, capture_output=True, text=True).stdout.strip()
            
            req = ActionRequest(
                integration="local_system",
                action_type=ActionType.WRITE,
                session_id="sess1",
                arguments={
                    "operation": "git_pull_fast_forward",
                    "remote_name": "origin",
                    "current_branch": "master",
                    "upstream_branch": "origin/master",
                    "upstream_ref": "refs/remotes/origin/master",
                    "expected_head_sha": target_head,
                    "expected_upstream_sha": target_upstream,
                    "behind": 1,
                }
            )
            
            # TOCTOU: We make the worktree dirty BEFORE executing
            (target_repo / "f.txt").write_text("dirty")
            
            res = ls.execute(req)
            assert res.status == ActionStatus.FAILED
            assert "STALE_PULL_PROPOSAL: Dirty worktree" in res.message

def test_git_pull_execution_rejections(tmp_path):
    source_repo = tmp_path / "source"
    source_repo.mkdir()
    subprocess.run(["git", "init"], cwd=source_repo, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=source_repo, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=source_repo, check=True)
    (source_repo / "f.txt").write_text("a")
    subprocess.run(["git", "add", "f.txt"], cwd=source_repo, check=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=source_repo, check=True)
    
    target_repo = tmp_path / "target"
    target_repo.mkdir()
    subprocess.run(["git", "init"], cwd=target_repo, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=target_repo, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=target_repo, check=True)
    subprocess.run(["git", "remote", "add", "origin", str(source_repo)], cwd=target_repo, check=True)
    subprocess.run(["git", "fetch", "origin"], cwd=target_repo, check=True)
    subprocess.run(["git", "checkout", "-b", "master", "origin/master"], cwd=target_repo, check=True)
    
    with mock.patch("app.config.get_settings") as mock_settings:
        class MockSettings:
            workspace_root = target_repo
        mock_settings.return_value = MockSettings()
        
        # UP_TO_DATE
        res = execute_git_pull("sess1", "origin")
        assert res["status"] == "FAILED"
        assert res["message"] == "UP_TO_DATE"
        
        # AHEAD
        (target_repo / "g.txt").write_text("c")
        subprocess.run(["git", "add", "g.txt"], cwd=target_repo, check=True)
        subprocess.run(["git", "commit", "-m", "target"], cwd=target_repo, check=True)
        res = execute_git_pull("sess1", "origin")
        assert res["status"] == "FAILED"
        assert res["message"] == "AHEAD"
        
        # DIVERGED
        (source_repo / "f.txt").write_text("b")
        subprocess.run(["git", "add", "f.txt"], cwd=source_repo, check=True)
        subprocess.run(["git", "commit", "-m", "source"], cwd=source_repo, check=True)
        subprocess.run(["git", "fetch", "origin"], cwd=target_repo, check=True)
        res = execute_git_pull("sess1", "origin")
        assert res["status"] == "FAILED"
        assert res["message"] == "DIVERGED"
        
        # Reset to BEHIND but add untracked file
        subprocess.run(["git", "reset", "--hard", "HEAD~1"], cwd=target_repo, check=True)
        (target_repo / "untracked.txt").write_text("u")
        res = execute_git_pull("sess1", "origin")
        assert res["status"] == "FAILED"
        assert res["message"] == "DIRTY_WORKTREE_REQUIRES_REVIEW"
        
        # Staged change
        subprocess.run(["git", "add", "untracked.txt"], cwd=target_repo, check=True)
        res = execute_git_pull("sess1", "origin")
        assert res["status"] == "FAILED"
        assert res["message"] == "DIRTY_WORKTREE_REQUIRES_REVIEW"
        
        # Clean up
        subprocess.run(["git", "reset", "--hard"], cwd=target_repo, check=True)
        subprocess.run(["git", "clean", "-fd"], cwd=target_repo, check=True)
        
        # Valid execution returns success (confirmation required)
        res = execute_git_pull("sess1", "origin")
        assert res["status"] == "WAITING_FOR_CONFIRMATION"

def test_full_successful_fast_forward(tmp_path):
    source_repo = tmp_path / "source"
    source_repo.mkdir()
    subprocess.run(["git", "init"], cwd=source_repo, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=source_repo, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=source_repo, check=True)
    (source_repo / "f.txt").write_text("a")
    subprocess.run(["git", "add", "f.txt"], cwd=source_repo, check=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=source_repo, check=True)
    
    target_repo = tmp_path / "target"
    target_repo.mkdir()
    subprocess.run(["git", "init"], cwd=target_repo, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=target_repo, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=target_repo, check=True)
    subprocess.run(["git", "remote", "add", "origin", str(source_repo)], cwd=target_repo, check=True)
    subprocess.run(["git", "fetch", "origin"], cwd=target_repo, check=True)
    subprocess.run(["git", "checkout", "-b", "master", "origin/master"], cwd=target_repo, check=True)

    # Make source ahead
    (source_repo / "f.txt").write_text("b")
    subprocess.run(["git", "add", "f.txt"], cwd=source_repo, check=True)
    subprocess.run(["git", "commit", "-m", "source"], cwd=source_repo, check=True)
    subprocess.run(["git", "fetch", "origin"], cwd=target_repo, check=True)
    
    with mock.patch("app.integrations.local_system.LocalSystemIntegration._get_workspace_root", return_value=target_repo):
        class MockSettings:
            workspace_root = target_repo
            workspace_execution_timeout_seconds = 10
            workspace_execution_max_output_bytes = 1000
        with mock.patch("app.config.get_settings", return_value=MockSettings()):
            ls = LocalSystemIntegration()
            
            target_head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=target_repo, capture_output=True, text=True).stdout.strip()
            target_upstream = subprocess.run(["git", "rev-parse", "refs/remotes/origin/master"], cwd=target_repo, capture_output=True, text=True).stdout.strip()
            
            req = ActionRequest(
                integration="local_system",
                action_type=ActionType.WRITE,
                session_id="sess1",
                arguments={
                    "operation": "git_pull_fast_forward",
                    "remote_name": "origin",
                    "current_branch": "master",
                    "upstream_branch": "origin/master",
                    "upstream_ref": "refs/remotes/origin/master",
                    "expected_head_sha": target_head,
                    "expected_upstream_sha": target_upstream,
                    "behind": 1,
                }
            )
            
            res = ls.execute(req)
            assert res.status == ActionStatus.SUCCESS
            assert res.data["new_head"] == target_upstream
            assert res.data["working_tree_clean"] is True
            assert res.data["relationship_after"] == "UP_TO_DATE"
