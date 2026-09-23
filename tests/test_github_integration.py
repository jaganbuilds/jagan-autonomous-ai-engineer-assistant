import pytest
from unittest.mock import patch, MagicMock
from app.integrations.models import ActionRequest, ActionType, ActionStatus
from app.integrations.github import GitHubIntegration
from app.integrations.gateway import action_gateway as gw
from app.integrations.github_client import GitHubError

@pytest.fixture
def gateway():
    gw.register_integration(GitHubIntegration())
    return gw

def test_github_validation_list_repos(gateway):
    req = ActionRequest(
        integration="github",
        action_type=ActionType.READ,
        session_id="s1",
        arguments={"action": "LIST_REPOSITORIES"}
    )
    # The integration executes it directly since it is READ (LOW risk)
    # But since we aren't mocking the client yet, we just want to ensure it tries to execute and fails with AUTHENTICATION_REQUIRED
    res = gateway.execute_action(req)
    # With no token in config, it raises AUTHENTICATION_REQUIRED
    assert res.status == ActionStatus.FAILED
    assert "AUTHENTICATION_REQUIRED" in res.message

def test_github_validation_missing_owner(gateway):
    req = ActionRequest(
        integration="github",
        action_type=ActionType.READ,
        session_id="s1",
        arguments={"action": "GET_REPOSITORY", "repo": "test"}
    )
    res = gateway.execute_action(req)
    assert res.status == ActionStatus.VALIDATION_ERROR
    assert "Missing 'owner'" in res.message

def test_github_validation_missing_repo(gateway):
    req = ActionRequest(
        integration="github",
        action_type=ActionType.READ,
        session_id="s1",
        arguments={"action": "GET_REPOSITORY", "owner": "test"}
    )
    res = gateway.execute_action(req)
    assert res.status == ActionStatus.VALIDATION_ERROR
    assert "Missing 'repo'" in res.message

@patch("app.integrations.github_client.GitHubClient._request")
def test_github_list_repositories(mock_request, gateway):
    mock_request.return_value = [
        {"name": "repo1", "full_name": "owner/repo1", "private": False, "html_url": "url1"},
        {"name": "repo2", "full_name": "owner/repo2", "private": True, "html_url": "url2"}
    ]
    
    with patch("app.integrations.github_client.get_settings") as mock_settings:
        mock_settings.return_value.github_token = "fake_token"
        mock_settings.return_value.github_repository_limit = 30
        
        req = ActionRequest(
            integration="github",
            action_type=ActionType.READ,
            session_id="s1",
            arguments={"action": "LIST_REPOSITORIES"}
        )
        res = gateway.execute_action(req)
        
        print("LIST_REPOSITORIES ERROR MESSAGE:", res.message)
        assert res.status == ActionStatus.SUCCESS
        assert len(res.data) == 2
        assert res.data[0]["name"] == "repo1"

@patch("app.integrations.github_client.GitHubClient._request")
def test_github_get_repository(mock_request, gateway):
    mock_request.return_value = {
        "name": "repo1", "full_name": "owner/repo1", "stargazers_count": 10, "visibility": "public"
    }
    
    req = ActionRequest(
        integration="github",
        action_type=ActionType.READ,
        session_id="s1",
        arguments={"action": "GET_REPOSITORY", "owner": "owner", "repo": "repo1"}
    )
    res = gateway.execute_action(req)
    
    assert res.status == ActionStatus.SUCCESS
    assert res.data["name"] == "repo1"
    assert res.data["stars"] == 10
    
@patch("app.integrations.github_client.GitHubClient._request")
def test_github_get_files(mock_request, gateway):
    mock_request.return_value = [
        {"name": "README.md", "type": "file", "size": 100},
        {"name": "src", "type": "dir", "size": 0}
    ]
    
    with patch("app.integrations.github_client.get_settings") as mock_settings:
        mock_settings.return_value.github_file_limit = 50
        
        req = ActionRequest(
            integration="github",
            action_type=ActionType.READ,
            session_id="s1",
            arguments={"action": "GET_REPOSITORY_FILES", "owner": "owner", "repo": "repo1"}
        )
        res = gateway.execute_action(req)
        
        print("GET_FILES ERROR MESSAGE:", res.message)
        assert res.status == ActionStatus.SUCCESS
        assert len(res.data) == 2
        assert res.data[0]["name"] == "README.md"
        assert res.data[1]["type"] == "dir"

@patch("app.integrations.github_client.GitHubClient._request")
def test_github_404_error(mock_request, gateway):
    mock_request.side_effect = GitHubError("NOT_FOUND", 404)
    
    req = ActionRequest(
        integration="github",
        action_type=ActionType.READ,
        session_id="s1",
        arguments={"action": "GET_REPOSITORY", "owner": "owner", "repo": "missing"}
    )
    res = gateway.execute_action(req)
    
    assert res.status == ActionStatus.FAILED
    assert "NOT_FOUND" in res.message

@patch("app.integrations.github_client.GitHubClient._request")
def test_github_403_rate_limit(mock_request, gateway):
    mock_request.side_effect = GitHubError("RATE_LIMITED", 403)
    
    req = ActionRequest(
        integration="github",
        action_type=ActionType.READ,
        session_id="s1",
        arguments={"action": "GET_REPOSITORY", "owner": "owner", "repo": "repo1"}
    )
    res = gateway.execute_action(req)
    
    assert res.status == ActionStatus.FAILED
    assert "RATE_LIMITED" in res.message

def test_github_tools():
    # Test that tools route through action_gateway
    from app.tools.github_tools import list_github_repositories, get_github_repository
    from app.integrations.models import ActionResult
    
    with patch("app.tools.github_tools.action_gateway.execute_action") as mock_execute:
        mock_result = ActionResult(action_id="1", integration="github", action_type=ActionType.READ, status=ActionStatus.SUCCESS, message="OK", data=[{"name": "test"}])
        mock_execute.return_value = mock_result
        
        res = list_github_repositories("s1")
        assert res["status"] == "SUCCESS"
        assert res["data"][0]["name"] == "test"
        
        res2 = get_github_repository("s1", "owner", "repo")
        assert res2["status"] == "SUCCESS"
        assert mock_execute.call_count == 2

@patch("app.integrations.github_client.GitHubClient._request")
def test_github_get_readme(mock_request, gateway):
    import base64
    mock_request.return_value = {
        "name": "README.md",
        "path": "README.md",
        "content": base64.b64encode(b"Hello World").decode("utf-8"),
        "encoding": "base64",
        "size": 11
    }
    
    req = ActionRequest(
        integration="github",
        action_type=ActionType.READ,
        session_id="s1",
        arguments={"action": "GET_README", "owner": "owner", "repo": "repo"}
    )
    res = gateway.execute_action(req)
    assert res.status == ActionStatus.SUCCESS
    assert res.data["readme_found"] is True
    assert res.data["readme_content"] == "Hello World"

@patch("app.integrations.github_client.GitHubClient._request")
def test_github_get_readme_missing(mock_request, gateway):
    mock_request.side_effect = GitHubError("NOT_FOUND", 404)
    
    req = ActionRequest(
        integration="github",
        action_type=ActionType.READ,
        session_id="s1",
        arguments={"action": "GET_README", "owner": "owner", "repo": "repo"}
    )
    res = gateway.execute_action(req)
    assert res.status == ActionStatus.SUCCESS
    assert res.data["readme_found"] is False

@patch("app.integrations.github_client.GitHubClient._request")
def test_github_get_file_content(mock_request, gateway):
    import base64
    mock_request.return_value = {
        "name": "app.py",
        "path": "src/app.py",
        "content": base64.b64encode(b"print('test')").decode("utf-8"),
        "encoding": "base64",
        "size": 13,
        "type": "file"
    }
    
    req = ActionRequest(
        integration="github",
        action_type=ActionType.READ,
        session_id="s1",
        arguments={"action": "GET_FILE", "owner": "owner", "repo": "repo", "path": "src/app.py"}
    )
    res = gateway.execute_action(req)
    assert res.status == ActionStatus.SUCCESS
    assert res.data["content"] == "print('test')"

@patch("app.integrations.github_client.GitHubClient._request")
def test_github_get_project_structure(mock_request, gateway):
    def side_effect(method, endpoint, **kwargs):
        if "git/trees" in endpoint:
            return {
                "tree": [
                    {"path": "README.md", "type": "blob", "size": 100},
                    {"path": "src", "type": "tree"},
                    {"path": "src/app.py", "type": "blob", "size": 200},
                    {"path": "data.bin", "type": "blob", "size": 500}
                ]
            }
        elif "/repos/" in endpoint and "git/trees" not in endpoint:
            return {"default_branch": "main"}
            
    mock_request.side_effect = side_effect
    
    req = ActionRequest(
        integration="github",
        action_type=ActionType.READ,
        session_id="s1",
        arguments={"action": "GET_PROJECT_STRUCTURE", "owner": "owner", "repo": "repo"}
    )
    res = gateway.execute_action(req)
    assert res.status == ActionStatus.SUCCESS
    
    important_files = res.data["important_files"]
    paths = [f["path"] for f in important_files]
    assert "README.md" in paths
    assert "src/app.py" in paths
    assert "data.bin" not in paths

@patch("app.integrations.github_client.GitHubClient._request")
def test_github_inspect_repository(mock_request, gateway):
    def side_effect(method, endpoint, **kwargs):
        if endpoint.endswith("/readme"):
            import base64
            return {
                "name": "README.md", "path": "README.md",
                "content": base64.b64encode(b"Hello").decode("utf-8"),
                "encoding": "base64", "size": 5
            }
        elif endpoint.endswith("/commits"):
            return [{"sha": "123", "commit": {"message": "fix"}, "author": {"name": "user"}}]
        elif "git/trees" in endpoint:
            return {"tree": [{"path": "README.md", "type": "blob", "size": 100}]}
        elif "/repos/" in endpoint:
            return {"name": "repo", "full_name": "owner/repo", "description": "desc", "default_branch": "main"}
            
    mock_request.side_effect = side_effect
    
    req = ActionRequest(
        integration="github",
        action_type=ActionType.READ,
        session_id="s1",
        arguments={"action": "INSPECT_REPOSITORY", "owner": "owner", "repo": "repo"}
    )
    res = gateway.execute_action(req)
    assert res.status == ActionStatus.SUCCESS
    assert res.data["repository"] == "owner/repo"
    assert res.data["readme_available"] is True
    assert res.data["recent_commits_count"] == 1
    assert len(res.data["important_files_preview"]) == 1

@patch("app.integrations.github_client.GitHubClient._request")
def test_github_get_file_binary(mock_request, gateway):
    import base64
    # Create invalid utf-8 string by encoding random bytes
    mock_request.return_value = {
        "name": "image.png",
        "path": "image.png",
        "content": base64.b64encode(b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR").decode("utf-8"),
        "encoding": "base64",
        "size": 16,
        "type": "file"
    }
    
    req = ActionRequest(
        integration="github",
        action_type=ActionType.READ,
        session_id="s1",
        arguments={"action": "GET_FILE", "owner": "owner", "repo": "repo", "path": "image.png"}
    )
    res = gateway.execute_action(req)
    # the client raises GitHubError("BINARY_FILE", 400) which gateway wraps into FAILED
    assert res.status == ActionStatus.FAILED
    assert "BINARY_FILE" in res.message

def test_github_write_action_requires_confirmation(gateway):
    req = ActionRequest(
        integration="github",
        action_type=ActionType.WRITE,
        session_id="s1",
        arguments={
            "action": "CREATE_BRANCH",
            "owner": "owner",
            "repo": "repo",
            "branch_name": "feature",
            "source_branch": "main"
        }
    )
    res = gateway.execute_action(req)
    # It must pause for confirmation because ActionRiskLevel is HIGH
    assert res.status == ActionStatus.WAITING_FOR_CONFIRMATION

@patch("app.integrations.github_client.GitHubClient._request")
def test_github_create_branch_confirmed(mock_request, gateway):
    # Mocking getting source branch SHA
    mock_request.side_effect = [
        {"object": {"sha": "abc1234"}},  # GET ref
        {}                                # POST create ref
    ]
    
    req = ActionRequest(
        action_id="123",
        integration="github",
        action_type=ActionType.WRITE,
        session_id="s1",
        arguments={
            "action": "CREATE_BRANCH",
            "owner": "owner",
            "repo": "repo",
            "branch_name": "feature",
            "source_branch": "main"
        }
    )
    # 1. First execution should pause
    res1 = gateway.execute_action(req)
    assert res1.status == ActionStatus.WAITING_FOR_CONFIRMATION
    
    # 2. Confirm execution
    res2 = gateway.confirm_pending_action("s1")
    assert res2.status == ActionStatus.SUCCESS
    assert res2.data["branch_name"] == "feature"
    assert res2.data["created"] is True
    
    # ensure mock was called twice (GET and POST)
    assert mock_request.call_count == 2
    args, kwargs = mock_request.call_args_list[1]
    assert args[0] == "POST"
    assert "refs/heads/feature" in kwargs["json"]["ref"]

@patch("app.integrations.github_client.GitHubClient._request")
def test_github_create_commit_confirmed(mock_request, gateway):
    # Mocking getting file (doesn't exist)
    mock_request.side_effect = [
        GitHubError("NOT_FOUND", 404), # GET file
        {"commit": {"sha": "commit123", "html_url": "url"}} # PUT file
    ]
    
    req = ActionRequest(
        action_id="456",
        integration="github",
        action_type=ActionType.WRITE,
        session_id="s1",
        arguments={
            "action": "CREATE_COMMIT",
            "owner": "owner",
            "repo": "repo",
            "branch": "main",
            "file_path": "README.md",
            "content": "Hello",
            "commit_message": "Add readme"
        }
    )
    res1 = gateway.execute_action(req)
    assert res1.status == ActionStatus.WAITING_FOR_CONFIRMATION
    
    res2 = gateway.confirm_pending_action("s1")
    assert res2.status == ActionStatus.SUCCESS
    assert res2.data["commit_sha"] == "commit123"

@patch("app.integrations.github_client.GitHubClient._request")
def test_github_create_pr_confirmed(mock_request, gateway):
    mock_request.return_value = {"number": 1, "title": "My PR", "html_url": "pr_url"}
    
    req = ActionRequest(
        action_id="789",
        integration="github",
        action_type=ActionType.WRITE,
        session_id="s1",
        arguments={
            "action": "CREATE_PULL_REQUEST",
            "owner": "owner",
            "repo": "repo",
            "title": "My PR",
            "head": "feature",
            "base": "main"
        }
    )
    res1 = gateway.execute_action(req)
    assert res1.status == ActionStatus.WAITING_FOR_CONFIRMATION
    
    res2 = gateway.confirm_pending_action("s1")
    assert res2.status == ActionStatus.SUCCESS
    assert res2.data["pull_request_number"] == 1

def test_github_write_validation_failures(gateway):
    # Missing head
    req = ActionRequest(
        integration="github",
        action_type=ActionType.WRITE,
        session_id="s1",
        arguments={
            "action": "CREATE_PULL_REQUEST",
            "owner": "owner",
            "repo": "repo",
            "title": "My PR",
            "base": "main"
        }
    )
    res = gateway.execute_action(req)
    assert res.status == ActionStatus.VALIDATION_ERROR
    assert "Missing 'head' branch" in res.message
    
    # Missing owner
    req2 = ActionRequest(
        integration="github",
        action_type=ActionType.WRITE,
        session_id="s1",
        arguments={"action": "CREATE_BRANCH", "branch_name": "x", "source_branch": "y"}
    )
    res2 = gateway.execute_action(req2)
    assert res2.status == ActionStatus.VALIDATION_ERROR
