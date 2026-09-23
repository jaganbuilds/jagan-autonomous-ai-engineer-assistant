from typing import Dict, Any, Optional
from app.tools import registry
from app.integrations.gateway import action_gateway
from app.integrations.models import ActionRequest, ActionType

@registry.register(requires_confirmation=False)
def list_github_repositories(session_id: str) -> Dict[str, Any]:
    """
    Lists the authenticated user's GitHub repositories.
    
    This is a safe, read-only operation.
    """
    request = ActionRequest(
        integration="github",
        action_type=ActionType.READ,
        session_id=session_id,
        arguments={
            "action": "LIST_REPOSITORIES"
        }
    )
    result = action_gateway.execute_action(request)
    return {
        "status": result.status.value,
        "data": result.data if result.status.value == "SUCCESS" else None,
        "message": result.message
    }

@registry.register(requires_confirmation=False)
def get_github_repository(session_id: str, owner: str, repo: str) -> Dict[str, Any]:
    """
    Gets metadata for a specific GitHub repository.
    
    Args:
        owner: The owner or organization of the repository (e.g. "jaganbuilds").
        repo: The repository name.
        
    This is a safe, read-only operation.
    """
    request = ActionRequest(
        integration="github",
        action_type=ActionType.READ,
        session_id=session_id,
        arguments={
            "action": "GET_REPOSITORY",
            "owner": owner,
            "repo": repo
        }
    )
    result = action_gateway.execute_action(request)
    return {
        "status": result.status.value,
        "data": result.data if result.status.value == "SUCCESS" else None,
        "message": result.message
    }

@registry.register(requires_confirmation=False)
def get_github_repository_files(session_id: str, owner: str, repo: str, path: str = "") -> Dict[str, Any]:
    """
    Gets the list of files in a GitHub repository at a specific path.
    
    Args:
        owner: The owner or organization of the repository.
        repo: The repository name.
        path: The path to the directory (leave empty for root).
        
    This is a safe, read-only, bounded operation.
    """
    request = ActionRequest(
        integration="github",
        action_type=ActionType.READ,
        session_id=session_id,
        arguments={
            "action": "GET_REPOSITORY_FILES",
            "owner": owner,
            "repo": repo,
            "path": path
        }
    )
    result = action_gateway.execute_action(request)
    return {
        "status": result.status.value,
        "data": result.data if result.status.value == "SUCCESS" else None,
        "message": result.message
    }

@registry.register(requires_confirmation=False)
def get_github_recent_commits(session_id: str, owner: str, repo: str, limit: int = 10) -> Dict[str, Any]:
    """
    Gets recent commits for a GitHub repository.
    
    Args:
        owner: The owner or organization of the repository.
        repo: The repository name.
        limit: Number of commits to fetch (max 50, default 10).
        
    This is a safe, read-only, bounded operation.
    """
    request = ActionRequest(
        integration="github",
        action_type=ActionType.READ,
        session_id=session_id,
        arguments={
            "action": "GET_RECENT_COMMITS",
            "owner": owner,
            "repo": repo,
            "limit": limit
        }
    )
    result = action_gateway.execute_action(request)
    return {
        "status": result.status.value,
        "data": result.data if result.status.value == "SUCCESS" else None,
        "message": result.message
    }

@registry.register(requires_confirmation=False)
def inspect_github_repository(session_id: str, owner: str, repo: str) -> Dict[str, Any]:
    """
    Gets a deterministic repository overview including metadata, recent activity, and structure.
    
    Args:
        owner: The owner or organization of the repository.
        repo: The repository name.
    """
    request = ActionRequest(
        integration="github",
        action_type=ActionType.READ,
        session_id=session_id,
        arguments={
            "action": "INSPECT_REPOSITORY",
            "owner": owner,
            "repo": repo
        }
    )
    result = action_gateway.execute_action(request)
    return {
        "status": result.status.value,
        "data": result.data if result.status.value == "SUCCESS" else None,
        "message": result.message
    }

@registry.register(requires_confirmation=False)
def get_github_readme(session_id: str, owner: str, repo: str) -> Dict[str, Any]:
    """
    Retrieves the README file for a GitHub repository.
    """
    request = ActionRequest(
        integration="github",
        action_type=ActionType.READ,
        session_id=session_id,
        arguments={
            "action": "GET_README",
            "owner": owner,
            "repo": repo
        }
    )
    result = action_gateway.execute_action(request)
    return {
        "status": result.status.value,
        "data": result.data if result.status.value == "SUCCESS" else None,
        "message": result.message
    }

@registry.register(requires_confirmation=False)
def get_github_file(session_id: str, owner: str, repo: str, path: str) -> Dict[str, Any]:
    """
    Retrieves the content of a specific source file from a GitHub repository.
    
    Args:
        owner: The owner or organization of the repository.
        repo: The repository name.
        path: The path to the file.
    """
    request = ActionRequest(
        integration="github",
        action_type=ActionType.READ,
        session_id=session_id,
        arguments={
            "action": "GET_FILE",
            "owner": owner,
            "repo": repo,
            "path": path
        }
    )
    result = action_gateway.execute_action(request)
    return {
        "status": result.status.value,
        "data": result.data if result.status.value == "SUCCESS" else None,
        "message": result.message
    }

@registry.register(requires_confirmation=False)
def get_github_project_structure(session_id: str, owner: str, repo: str) -> Dict[str, Any]:
    """
    Discovers important files and the structure of a GitHub repository.
    """
    request = ActionRequest(
        integration="github",
        action_type=ActionType.READ,
        session_id=session_id,
        arguments={
            "action": "GET_PROJECT_STRUCTURE",
            "owner": owner,
            "repo": repo
        }
    )
    result = action_gateway.execute_action(request)
    return {
        "status": result.status.value,
        "data": result.data if result.status.value == "SUCCESS" else None,
        "message": result.message
    }

@registry.register(requires_confirmation=True)
def create_github_branch(session_id: str, owner: str, repo: str, branch_name: str, source_branch: str) -> Dict[str, Any]:
    """
    Creates a new branch in a GitHub repository.
    
    Args:
        owner: The owner or organization of the repository.
        repo: The repository name.
        branch_name: The name of the new branch to create.
        source_branch: The name of the existing branch to branch from.
    """
    request = ActionRequest(
        integration="github",
        action_type=ActionType.WRITE,
        session_id=session_id,
        arguments={
            "action": "CREATE_BRANCH",
            "owner": owner,
            "repo": repo,
            "branch_name": branch_name,
            "source_branch": source_branch
        },
        requires_confirmation=True
    )
    result = action_gateway.execute_action(request)
    if result.status.value == "WAITING_FOR_CONFIRMATION":
        return {
            "status": "waiting_for_confirmation",
            "action": "create_github_branch",
            "message": f"This will create a new branch in {owner}/{repo}.\n\nRepository: {owner}/{repo}\nNew Branch: {branch_name}\nSource: {source_branch}\n\nDo you want me to continue?"
        }
    return {
        "status": result.status.value,
        "data": result.data if result.status.value == "SUCCESS" else None,
        "message": result.message
    }

@registry.register(requires_confirmation=True)
def create_github_commit(session_id: str, owner: str, repo: str, branch: str, file_path: str, content: str, commit_message: str) -> Dict[str, Any]:
    """
    Creates a commit that creates or updates a file in a GitHub repository.
    
    Args:
        owner: The owner or organization of the repository.
        repo: The repository name.
        branch: The branch to commit to.
        file_path: The path of the file to create or update.
        content: The text content of the file.
        commit_message: The commit message.
    """
    request = ActionRequest(
        integration="github",
        action_type=ActionType.WRITE,
        session_id=session_id,
        arguments={
            "action": "CREATE_COMMIT",
            "owner": owner,
            "repo": repo,
            "branch": branch,
            "file_path": file_path,
            "content": content,
            "commit_message": commit_message
        },
        requires_confirmation=True
    )
    result = action_gateway.execute_action(request)
    if result.status.value == "WAITING_FOR_CONFIRMATION":
        return {
            "status": "waiting_for_confirmation",
            "action": "create_github_commit",
            "message": f"This will create a commit in {owner}/{repo}.\n\nRepository: {owner}/{repo}\nBranch: {branch}\nFile: {file_path}\nMessage: {commit_message}\n\nDo you want me to continue?"
        }
    return {
        "status": result.status.value,
        "data": result.data if result.status.value == "SUCCESS" else None,
        "message": result.message
    }

@registry.register(requires_confirmation=True)
def create_github_pull_request(session_id: str, owner: str, repo: str, title: str, head: str, base: str, body: str = "") -> Dict[str, Any]:
    """
    Creates a pull request in a GitHub repository.
    
    Args:
        owner: The owner or organization of the repository.
        repo: The repository name.
        title: The title of the pull request.
        head: The name of the branch where your changes are implemented.
        base: The name of the branch you want the changes pulled into.
        body: The contents of the pull request description.
    """
    request = ActionRequest(
        integration="github",
        action_type=ActionType.WRITE,
        session_id=session_id,
        arguments={
            "action": "CREATE_PULL_REQUEST",
            "owner": owner,
            "repo": repo,
            "title": title,
            "head": head,
            "base": base,
            "body": body
        },
        requires_confirmation=True
    )
    result = action_gateway.execute_action(request)
    if result.status.value == "WAITING_FOR_CONFIRMATION":
        return {
            "status": "waiting_for_confirmation",
            "action": "create_github_pull_request",
            "message": f"This will create a pull request in {owner}/{repo}.\n\nRepository: {owner}/{repo}\nHead: {head}\nBase: {base}\nTitle: {title}\n\nDo you want me to continue?"
        }
    return {
        "status": result.status.value,
        "data": result.data if result.status.value == "SUCCESS" else None,
        "message": result.message
    }
