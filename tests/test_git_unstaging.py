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
    
    # file2: Staged modification
    file2 = repo_dir / "file2.txt"
    file2.write_text("v1")
    subprocess.run(["git", "add", "file2.txt"], cwd=repo_dir, check=True)
    subprocess.run(["git", "commit", "-m", "file2"], cwd=repo_dir, check=True)
    file2.write_text("v2")
    subprocess.run(["git", "add", "file2.txt"], cwd=repo_dir, check=True)
    
    # file3: Staged modification AND unstaged modification (MM)
    file3 = repo_dir / "file3.txt"
    file3.write_text("v1")
    subprocess.run(["git", "add", "file3.txt"], cwd=repo_dir, check=True)
    subprocess.run(["git", "commit", "-m", "file3", "file3.txt"], cwd=repo_dir, check=True)
    file3.write_text("v2")
    subprocess.run(["git", "add", "file3.txt"], cwd=repo_dir, check=True) # Staged v2
    file3.write_text("v3") # Unstaged v3
    
    # file4: New file staged (A)
    file4 = repo_dir / "file4.txt"
    file4.write_text("new")
    subprocess.run(["git", "add", "file4.txt"], cwd=repo_dir, check=True)
    
    # file5: Staged deletion (D)
    file5 = repo_dir / "file5.txt"
    file5.write_text("v1")
    subprocess.run(["git", "add", "file5.txt"], cwd=repo_dir, check=True)
    subprocess.run(["git", "commit", "-m", "file5", "file5.txt"], cwd=repo_dir, check=True)
    subprocess.run(["git", "rm", "file5.txt"], cwd=repo_dir, check=True)
    
    return repo_dir

@mock.patch("app.integrations.local_system.LocalSystemIntegration._get_workspace_root")
@mock.patch("app.config.get_settings")
def test_unstage_prechecks(mock_settings, mock_root, temp_git_repo):
    mock_root.return_value = temp_git_repo
    class MockSettings:
        workspace_root = temp_git_repo
        workspace_execution_timeout_seconds = 10
        workspace_execution_max_output_bytes = 1000
    mock_settings.return_value = MockSettings()
    
    # 1. Missing file
    res1 = unstage_git_files("sess", ["nonexistent.txt"])
    assert res1.get("status") == "FILE_NOT_FOUND"
    
    # 2. Directory
    dir1 = temp_git_repo / "dir1"
    dir1.mkdir()
    res2 = unstage_git_files("sess", ["dir1"])
    assert res2.get("status") == "DIRECTORY_NOT_ALLOWED"
    
    # 3. Not staged
    res3 = unstage_git_files("sess", ["file1.txt"])
    assert res3.get("status") == "NOT_STAGED"

@mock.patch("app.integrations.local_system.LocalSystemIntegration._get_workspace_root")
@mock.patch("app.config.get_settings")
def test_unstage_success(mock_settings, mock_root, temp_git_repo):
    mock_root.return_value = temp_git_repo
    class MockSettings:
        workspace_root = temp_git_repo
        workspace_execution_timeout_seconds = 10
        workspace_execution_max_output_bytes = 1000
    mock_settings.return_value = MockSettings()
    
    # Unstage file2 (normal staged) and file3 (mixed) and file4 (new) and file5 (deleted)
    req = ActionRequest(
        integration="local_system",
        action_type=ActionType.WRITE,
        session_id="test",
        arguments={"operation": "git_unstage_files", "paths": ["file2.txt", "file3.txt", "file4.txt", "file5.txt"]},
        requires_confirmation=False # Bypass confirmation for testing execution
    )
    
    st = subprocess.run(['git', 'status', '--porcelain', '--', 'file2.txt'], cwd=temp_git_repo, capture_output=True, text=True)
    print('ST OUT:', repr(st.stdout))
    res = LocalSystemIntegration().execute(req)
    assert res.status == ActionStatus.SUCCESS
    assert res.data.get("success") is True
    
    # Verify file2 unstaged and content preserved
    st2 = subprocess.run(["git", "status", "--porcelain", "--", "file2.txt"], cwd=temp_git_repo, capture_output=True, text=True).stdout
    assert st2.strip() == "M file2.txt"
    assert (temp_git_repo / "file2.txt").read_text() == "v2"
    
    # Verify file3 unstaged and content preserved (working tree should STILL be v3)
    st3 = subprocess.run(["git", "status", "--porcelain", "--", "file3.txt"], cwd=temp_git_repo, capture_output=True, text=True).stdout
    assert st3.strip() == "M file3.txt"
    assert (temp_git_repo / "file3.txt").read_text() == "v3"
    
    # Verify file4 is untracked now
    st4 = subprocess.run(["git", "status", "--porcelain", "--", "file4.txt"], cwd=temp_git_repo, capture_output=True, text=True).stdout
    assert st4.strip() == "?? file4.txt"
    assert (temp_git_repo / "file4.txt").read_text() == "new"
    
    # Verify file5 is unstaged deleted (working tree should remain deleted)
    st5 = subprocess.run(["git", "status", "--porcelain", "--", "file5.txt"], cwd=temp_git_repo, capture_output=True, text=True).stdout
    assert st5.strip() == "D file5.txt"
    assert not (temp_git_repo / "file5.txt").exists()

@mock.patch("app.integrations.local_system.LocalSystemIntegration._get_workspace_root")
@mock.patch("app.config.get_settings")
def test_unstage_toctou(mock_settings, mock_root, temp_git_repo):
    mock_root.return_value = temp_git_repo
    class MockSettings:
        workspace_root = temp_git_repo
        workspace_execution_timeout_seconds = 10
        workspace_execution_max_output_bytes = 1000
    mock_settings.return_value = MockSettings()
    
    ls = LocalSystemIntegration()
    
    # We mutate it before execution
    (temp_git_repo / "file2.txt").unlink()
    
    req = ActionRequest(
        integration="local_system",
        action_type=ActionType.WRITE,
        session_id="test",
        arguments={"operation": "git_unstage_files", "paths": ["file2.txt"]},
        requires_confirmation=False
    )
    
    res = ls.execute(req)
    # Actually wait, if we delete file2, it becomes a DELETED file in the working tree.
    # Its index status is still staged M, and working tree is deleted.
    # So `git status` says `MD file2.txt`.
    # And our TOCTOU check checks if out is empty. It's not.
    # It checks xy[0] in ("M", "A", "D", "R", "C"). `MD` starts with `M`.
    # So it should SUCCEED in unstaging! Let's check!
    assert res.status == ActionStatus.SUCCESS
    
    # Let's test a real TOCTOU failure: we completely unstage it behind its back!
    subprocess.run(["git", "restore", "--staged", "--", "file4.txt"], cwd=temp_git_repo, check=True)
    
    req2 = ActionRequest(
        integration="local_system",
        action_type=ActionType.WRITE,
        session_id="test",
        arguments={"operation": "git_unstage_files", "paths": ["file4.txt"]},
        requires_confirmation=False
    )
    res2 = ls.execute(req2)
    assert res2.status == ActionStatus.FAILED
    assert res2.message == "NOT_STAGED"
