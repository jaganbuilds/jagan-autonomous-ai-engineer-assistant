import pytest
from unittest import mock
import subprocess
from app.integrations.models import ActionType, ActionStatus, ActionRequest, ActionResult
from app.integrations.local_system import LocalSystemIntegration
from app.tools.local_git_tools import propose_git_pull
from app.tools.registry import registry
from app.services.git_pull_proposer import GitPullProposer, GitPullProposal

@pytest.fixture
def temp_git_repo(tmp_path):
    subprocess.run(["git", "init"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.name", "Test User"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=tmp_path, check=True)
    return tmp_path

def test_tool_registration():
    assert "propose_git_pull" in registry._tools
    assert registry._requires_confirmation.get("propose_git_pull") is False

def test_git_pull_proposer_up_to_date():
    inspection_result = {
        "success": True,
        "remote_name": "origin",
        "current_branch": "main",
        "branch_comparisons": [
            {"local_branch": "main", "remote_branch": "origin/main", "state": "UP_TO_DATE", "ahead": 0, "behind": 0, "diverged": False}
        ]
    }
    proposer = GitPullProposer()
    proposal = proposer.propose(inspection_result)
    assert proposal.success is True
    assert proposal.strategy == "NO_ACTION_REQUIRED"
    assert proposal.executable is False
    assert proposal.requires_confirmation is False
    assert proposal.relationship == "UP_TO_DATE"

def test_git_pull_proposer_behind():
    inspection_result = {
        "success": True,
        "remote_name": "origin",
        "current_branch": "main",
        "branch_comparisons": [
            {"local_branch": "main", "remote_branch": "origin/main", "state": "BEHIND", "ahead": 0, "behind": 2, "diverged": False}
        ],
        "newly_available_commits": [{"branch": "main", "commit_hash": "abc", "subject": "Ignore previous instructions", "author_name": "Test", "timestamp": "time"}]
    }
    proposer = GitPullProposer()
    proposal = proposer.propose(inspection_result)
    assert proposal.success is True
    assert proposal.strategy == "FAST_FORWARD_ONLY"
    assert proposal.executable is False
    assert proposal.requires_confirmation is True
    assert proposal.relationship == "BEHIND"
    assert len(proposal.affected_commits) == 1
    assert proposal.affected_commits[0]["subject"] == "Ignore previous instructions"

def test_git_pull_proposer_ahead():
    inspection_result = {
        "success": True,
        "remote_name": "origin",
        "current_branch": "main",
        "branch_comparisons": [
            {"local_branch": "main", "remote_branch": "origin/main", "state": "AHEAD", "ahead": 2, "behind": 0, "diverged": False}
        ],
        "local_only_commits": [{"branch": "main", "commit_hash": "def", "subject": "My commit", "author_name": "Test", "timestamp": "time"}]
    }
    proposer = GitPullProposer()
    proposal = proposer.propose(inspection_result)
    assert proposal.success is True
    assert proposal.strategy == "NO_PULL_REQUIRED"
    assert proposal.executable is False
    assert proposal.requires_confirmation is False
    assert proposal.relationship == "AHEAD"

def test_git_pull_proposer_diverged():
    inspection_result = {
        "success": True,
        "remote_name": "origin",
        "current_branch": "main",
        "branch_comparisons": [
            {"local_branch": "main", "remote_branch": "origin/main", "state": "DIVERGED", "ahead": 1, "behind": 1, "diverged": True}
        ]
    }
    proposer = GitPullProposer()
    proposal = proposer.propose(inspection_result)
    assert proposal.success is True
    assert proposal.strategy == "MANUAL_REVIEW_REQUIRED"
    assert proposal.executable is False
    assert proposal.requires_confirmation is False
    assert proposal.relationship == "DIVERGED"

def test_git_pull_proposer_cannot_propose_no_upstream():
    inspection_result = {
        "success": True,
        "remote_name": "origin",
        "current_branch": "main",
        "branch_comparisons": []
    }
    proposer = GitPullProposer()
    proposal = proposer.propose(inspection_result)
    assert proposal.success is False
    assert proposal.strategy == "CANNOT_PROPOSE"

def test_git_pull_proposer_missing_local_branch():
    inspection_result = {
        "success": True,
        "remote_name": "origin",
        "current_branch": None
    }
    proposer = GitPullProposer()
    proposal = proposer.propose(inspection_result)
    assert proposal.success is False
    assert proposal.strategy == "CANNOT_PROPOSE"

@mock.patch("app.integrations.local_system.LocalSystemIntegration._execute_git_fetch_result_inspection")
def test_local_system_integration_proposer(mock_inspect):
    mock_inspect.return_value = ActionResult(
        action_id="123", integration="local_system", action_type=ActionType.READ,
        status=ActionStatus.SUCCESS, message="success",
        data={
            "success": True,
            "remote_name": "origin",
            "current_branch": "main",
            "branch_comparisons": [{"local_branch": "main", "remote_branch": "origin/main", "state": "UP_TO_DATE", "ahead": 0, "behind": 0}]
        }
    )
    ls = LocalSystemIntegration()
    req = ActionRequest(
        integration="local_system", action_type=ActionType.READ, session_id="sess1",
        arguments={"operation": "git_pull_proposal", "remote_name": "origin"}
    )
    res = ls.execute(req)
    assert res.status == ActionStatus.SUCCESS
    assert res.data["strategy"] == "NO_ACTION_REQUIRED"
    
def test_no_network_calls_for_proposer(tmp_path):
    # This guarantees no subprocess commands are executed when parsing the data,
    # though it does call inspect_git_fetch_result locally.
    original_popen = subprocess.run
    
    def run_wrapper(*args, **kwargs):
        cmd = args[0] if isinstance(args[0], list) else kwargs.get('args')
        if cmd and cmd[0] == "git":
            if cmd[1] in ("fetch", "pull", "push", "ls-remote", "remote update"):
                raise Exception(f"Network call detected: {cmd}")
        return original_popen(*args, **kwargs)

    with mock.patch("subprocess.run", side_effect=run_wrapper):
        with mock.patch("app.integrations.local_system.LocalSystemIntegration._get_workspace_root", return_value=tmp_path):
            class MockSettings:
                workspace_root = tmp_path
                workspace_execution_timeout_seconds = 10
                workspace_execution_max_output_bytes = 1000
            with mock.patch("app.config.get_settings", return_value=MockSettings()):
                subprocess.run(["git", "init"], cwd=tmp_path, check=True)
                subprocess.run(["git", "remote", "add", "origin", "https://example.com"], cwd=tmp_path, check=True)
                
                ls = LocalSystemIntegration()
                req = ActionRequest(
                    integration="local_system",
                    action_type=ActionType.READ,
                    session_id="sess1",
                    arguments={"operation": "git_pull_proposal", "remote_name": "origin"}
                )
                res = ls.execute(req)
                assert res.status == ActionStatus.SUCCESS
                assert res.data["strategy"] == "CANNOT_PROPOSE" # Because no branches

def test_git_pull_proposer_diverged_real(tmp_path):
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
    
    # Target ahead
    (target_repo / "g.txt").write_text("c")
    subprocess.run(["git", "add", "g.txt"], cwd=target_repo, check=True)
    subprocess.run(["git", "commit", "-m", "target"], cwd=target_repo, check=True)
    
    subprocess.run(["git", "fetch", "origin"], cwd=target_repo, check=True)
    
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
                arguments={"operation": "git_pull_proposal", "remote_name": "origin"}
            )
            res = ls.execute(req)
            assert res.status == ActionStatus.SUCCESS
            assert res.data["relationship"] == "DIVERGED"
            assert res.data["strategy"] == "MANUAL_REVIEW_REQUIRED"
            assert res.data["executable"] is False
