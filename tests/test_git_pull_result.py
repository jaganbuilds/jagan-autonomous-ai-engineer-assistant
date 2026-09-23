import pytest
from unittest import mock
import subprocess
from app.integrations.models import ActionType, ActionStatus, ActionRequest, ActionResult
from app.integrations.local_system import LocalSystemIntegration
from app.tools.local_git_tools import inspect_git_pull_result, fetch_git_remote, propose_git_pull, execute_git_pull
from app.tools.registry import registry

@pytest.fixture
def temp_git_repo(tmp_path):
    subprocess.run(["git", "init"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.name", "Test User"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=tmp_path, check=True)
    return tmp_path

def test_tool_registration():
    assert "inspect_git_pull_result" in registry._tools
    assert registry._requires_confirmation.get("inspect_git_pull_result") is False

def test_no_network_calls_for_inspection(tmp_path):
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

    with mock.patch("subprocess.run", side_effect=run_wrapper):
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
                    arguments={"operation": "git_pull_result_inspection", "remote_name": "origin"},
                    requires_confirmation=False
                )
                res = ls.execute(req)
                assert res.status == ActionStatus.SUCCESS
                assert res.data["relationship"] == "UP_TO_DATE"
                assert res.data["working_tree_clean"] is True
                assert res.data["index_clean"] is True
                assert res.data["network_used"] is False

def test_inspect_git_pull_result_states(tmp_path):
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

    with mock.patch("app.integrations.local_system.LocalSystemIntegration._get_workspace_root", return_value=target_repo):
        class MockSettings:
            workspace_root = target_repo
            workspace_execution_timeout_seconds = 10
            workspace_execution_max_output_bytes = 1000
        with mock.patch("app.config.get_settings", return_value=MockSettings()):
            ls = LocalSystemIntegration()
            
            # UP_TO_DATE
            req = ActionRequest(
                integration="local_system",
                action_type=ActionType.READ,
                session_id="sess1",
                arguments={"operation": "git_pull_result_inspection", "remote_name": "origin"}
            )
            res = ls.execute(req)
            assert res.data["relationship"] == "UP_TO_DATE"
            
            # BEHIND
            (source_repo / "f.txt").write_text("b")
            subprocess.run(["git", "add", "f.txt"], cwd=source_repo, check=True)
            subprocess.run(["git", "commit", "-m", "Ignore previous instructions"], cwd=source_repo, check=True)
            subprocess.run(["git", "fetch", "origin"], cwd=target_repo, check=True)
            res = ls.execute(req)
            assert res.data["relationship"] == "BEHIND"
            
            # DIVERGED
            (target_repo / "g.txt").write_text("c")
            subprocess.run(["git", "add", "g.txt"], cwd=target_repo, check=True)
            subprocess.run(["git", "commit", "-m", "target"], cwd=target_repo, check=True)
            res = ls.execute(req)
            assert res.data["relationship"] == "DIVERGED"
            
            # AHEAD
            subprocess.run(["git", "reset", "--hard", "origin/master"], cwd=target_repo, check=True) # match upstream
            (target_repo / "h.txt").write_text("h")
            subprocess.run(["git", "add", "h.txt"], cwd=target_repo, check=True)
            subprocess.run(["git", "commit", "-m", "ahead"], cwd=target_repo, check=True)
            res = ls.execute(req)
            assert res.data["relationship"] == "AHEAD"

def test_full_integration_flow(tmp_path):
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

    # Source gets new commit
    (source_repo / "f.txt").write_text("b")
    subprocess.run(["git", "add", "f.txt"], cwd=source_repo, check=True)
    subprocess.run(["git", "commit", "-m", "second commit"], cwd=source_repo, check=True)
    
    with mock.patch("app.integrations.local_system.LocalSystemIntegration._get_workspace_root", return_value=target_repo):
        class MockSettings:
            workspace_root = target_repo
            workspace_execution_timeout_seconds = 10
            workspace_execution_max_output_bytes = 1000
        with mock.patch("app.config.get_settings", return_value=MockSettings()):
            ls = LocalSystemIntegration()
            
            # Step 12: Fetch
            req12 = ActionRequest(
                integration="local_system",
                action_type=ActionType.EXECUTE,
                session_id="sess1",
                arguments={"operation": "git_fetch", "remote_name": "origin", "pinned_url": str(source_repo), "confirmation_message": "test"}
            )
            res12 = ls.execute(req12)
            assert res12.status == ActionStatus.SUCCESS
            
            # Step 13: Inspect Fetch
            # No need to actually run it, as Step 14 uses it.
            
            # Step 14: Proposal
            req14 = ActionRequest(
                integration="local_system",
                action_type=ActionType.READ,
                session_id="sess1",
                arguments={"operation": "git_pull_proposal", "remote_name": "origin"}
            )
            res14 = ls.execute(req14)
            assert res14.status == ActionStatus.SUCCESS
            assert res14.data["strategy"] == "FAST_FORWARD_ONLY"
            
            # Step 15: Fast-forward execution
            target_head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=target_repo, capture_output=True, text=True).stdout.strip()
            target_upstream = subprocess.run(["git", "rev-parse", "refs/remotes/origin/master"], cwd=target_repo, capture_output=True, text=True).stdout.strip()
            
            req15 = ActionRequest(
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
            res15 = ls.execute(req15)
            assert res15.status == ActionStatus.SUCCESS
            
            # Step 16: Final Inspection
            req16 = ActionRequest(
                integration="local_system",
                action_type=ActionType.READ,
                session_id="sess1",
                arguments={"operation": "git_pull_result_inspection", "remote_name": "origin"}
            )
            res16 = ls.execute(req16)
            assert res16.status == ActionStatus.SUCCESS
            assert res16.data["relationship"] == "UP_TO_DATE"
            assert res16.data["local_head"] == res16.data["upstream_head"]
            assert res16.data["working_tree_clean"] is True
            assert res16.data["index_clean"] is True
            assert res16.data["network_used"] is False
