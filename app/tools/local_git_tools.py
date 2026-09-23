

def _validate_remote_name(name: str) -> bool:
    import re
    if not isinstance(name, str) or not name.strip() or len(name) > 200: return False
    if '\0' in name or '\n' in name or '\r' in name or ' ' in name or '\t' in name: return False
    if '/' in name or '\\' in name or '..' in name: return False
    if name.startswith('-'): return False
    if re.search(r'[;&|\$`<>()]', name): return False
    return True

def _validate_remote_url(url: str) -> bool:
    if not isinstance(url, str) or not url.strip() or len(url) > 1000: return False
    if url.startswith('-'): return False
    if '\0' in url or '\n' in url or '\r' in url or '\t' in url: return False
    return True

def _sanitize_remote_url(url: str) -> str:
    import urllib.parse
    try:
        if '://' in url:
            parsed = urllib.parse.urlparse(url)
            host = parsed.hostname or ''
            if parsed.port: host = f"{host}:{parsed.port}"
            query = parsed.query
            if query:
                from urllib.parse import parse_qsl, urlencode
                params = parse_qsl(query, keep_blank_values=True)
                safe_params = []
                for k, v in params:
                    kl = k.lower()
                    if any(s in kl for s in ['token', 'auth', 'password', 'passwd', 'secret', 'api_key', 'apikey', 'key']):
                        safe_params.append((k, 'REDACTED'))
                    else:
                        safe_params.append((k, v))
                query = urlencode(safe_params)
            return urllib.parse.urlunparse((parsed.scheme, host, parsed.path, parsed.params, query, parsed.fragment))
        else:
            if '@' in url and ':' in url:
                return url.split('@', 1)[1]
            return url
    except Exception:
        return 'REDACTED_URL_PARSE_ERROR'

from typing import Dict, Any, List, Optional
from app.tools.registry import registry
from app.integrations.gateway import action_gateway
from app.integrations.models import ActionRequest, ActionType, ActionStatus

@registry.register(requires_confirmation=False)
def get_git_status(session_id: str) -> Dict[str, Any]:
    """
    Gets the current Git repository status (equivalent to 'git status --short --branch').
    This is a safe, read-only operation.
    
    Args:
        session_id: The current session ID.
        
    Returns:
        Dict containing the git output and execution status.
    """
    request = ActionRequest(
        integration="local_system",
        action_type=ActionType.READ,
        session_id=session_id,
        arguments={"operation": "git", "git_command": "status", "args": ["--short", "--branch"]},
        requires_confirmation=False
    )
    result = action_gateway.execute_action(request)
    return result.model_dump()

@registry.register(requires_confirmation=False)
def get_git_branch(session_id: str) -> Dict[str, Any]:
    """
    Gets the current Git branch name (equivalent to 'git branch --show-current').
    This is a safe, read-only operation.
    
    Args:
        session_id: The current session ID.
        
    Returns:
        Dict containing the git output and execution status.
    """
    request = ActionRequest(
        integration="local_system",
        action_type=ActionType.READ,
        session_id=session_id,
        arguments={"operation": "git", "git_command": "branch", "args": ["--show-current"]},
        requires_confirmation=False
    )
    result = action_gateway.execute_action(request)
    return result.model_dump()

@registry.register(requires_confirmation=False)
def get_git_commits(session_id: str, count: int = 5) -> Dict[str, Any]:
    """
    Gets recent Git commits (equivalent to 'git log -n <count>').
    This is a safe, read-only operation.
    
    Args:
        session_id: The current session ID.
        count: The number of commits to retrieve (default 5, max 20).
        
    Returns:
        Dict containing the git output and execution status.
    """
    count = min(max(1, count), 20)
    request = ActionRequest(
        integration="local_system",
        action_type=ActionType.READ,
        session_id=session_id,
        arguments={"operation": "git", "git_command": "log", "args": ["-n", str(count)]},
        requires_confirmation=False
    )
    result = action_gateway.execute_action(request)
    return result.model_dump()

@registry.register(requires_confirmation=False)
def is_git_repository(session_id: str) -> Dict[str, Any]:
    """
    Checks if the workspace is a Git repository (equivalent to 'git rev-parse --is-inside-work-tree').
    This is a safe, read-only operation.
    
    Args:
        session_id: The current session ID.
        
    Returns:
        Dict containing the git output and execution status.
    """
    request = ActionRequest(
        integration="local_system",
        action_type=ActionType.READ,
        session_id=session_id,
        arguments={"operation": "git", "git_command": "rev-parse", "args": ["--is-inside-work-tree"]},
        requires_confirmation=False
    )
    result = action_gateway.execute_action(request)
    return result.model_dump()

@registry.register(requires_confirmation=False)
def get_git_diff_unstaged(session_id: str) -> Dict[str, Any]:
    """
    Gets the unstaged Git diff (equivalent to 'git diff').
    This is a safe, read-only operation.
    
    Args:
        session_id: The current session ID.
        
    Returns:
        Dict containing the git output and execution status.
    """
    request = ActionRequest(
        integration="local_system",
        action_type=ActionType.READ,
        session_id=session_id,
        arguments={"operation": "git", "git_command": "diff", "args": []},
        requires_confirmation=False
    )
    result = action_gateway.execute_action(request)
    return result.model_dump()

@registry.register(requires_confirmation=False)
def get_git_diff_staged(session_id: str) -> Dict[str, Any]:
    """
    Gets the staged Git diff (equivalent to 'git diff --cached').
    This is a safe, read-only operation.
    
    Args:
        session_id: The current session ID.
        
    Returns:
        Dict containing the git output and execution status.
    """
    request = ActionRequest(
        integration="local_system",
        action_type=ActionType.READ,
        session_id=session_id,
        arguments={"operation": "git", "git_command": "diff", "args": ["--cached"]},
        requires_confirmation=False
    )
    result = action_gateway.execute_action(request)
    return result.model_dump()

@registry.register(requires_confirmation=False)
def get_git_changed_files(session_id: str) -> Dict[str, Any]:
    """
    Gets the names of changed files (equivalent to 'git diff --name-only').
    This is a safe, read-only operation.
    
    Args:
        session_id: The current session ID.
        
    Returns:
        Dict containing the git output and execution status.
    """
    request = ActionRequest(
        integration="local_system",
        action_type=ActionType.READ,
        session_id=session_id,
        arguments={"operation": "git", "git_command": "diff", "args": ["--name-only"]},
        requires_confirmation=False
    )
    result = action_gateway.execute_action(request)
    return result.model_dump()

@registry.register(requires_confirmation=False)
def get_git_diff_stats(session_id: str) -> Dict[str, Any]:
    """
    Gets the diff statistics (equivalent to 'git diff --stat').
    This is a safe, read-only operation.
    
    Args:
        session_id: The current session ID.
        
    Returns:
        Dict containing the git output and execution status.
    """
    request = ActionRequest(
        integration="local_system",
        action_type=ActionType.READ,
        session_id=session_id,
        arguments={"operation": "git", "git_command": "diff", "args": ["--stat"]},
        requires_confirmation=False
    )
    result = action_gateway.execute_action(request)
    return result.model_dump()

@registry.register(requires_confirmation=False)
def propose_git_commit(session_id: str) -> Dict[str, Any]:
    """
    Inspects the current repository and generates a structured Git commit proposal.
    This is a READ-ONLY tool. It does NOT execute git commit or modify files.
    
    Args:
        session_id: The current session ID.
        
    Returns:
        Dict containing the proposal status and the proposal data.
    """
    from app.services.git_commit_proposer import GitCommitProposer
    proposer = GitCommitProposer()
    return proposer.propose_commit(session_id)

@registry.register(requires_confirmation=True)
def execute_git_commit(session_id: str, message: str) -> Dict[str, Any]:
    """
    Executes a git commit with the given message.
    This is a WRITE operation and requires human confirmation.
    It will only commit files that are already staged. It will NOT automatically stage any files.
    
    Args:
        session_id: The current session ID.
        message: The commit message.
        
    Returns:
        Dict containing the commit result.
    """
    request = ActionRequest(
        integration="local_system",
        action_type=ActionType.WRITE,
        session_id=session_id,
        arguments={"operation": "git_commit", "message": message},
        requires_confirmation=True
    )
    result = action_gateway.execute_action(request)
    return result.model_dump()

@registry.register(requires_confirmation=False)
def get_git_branches(session_id: str) -> Dict[str, Any]:
    """
    Returns a list of all branches in the local Git repository and the current active branch.
    This is a READ operation.
    
    Args:
        session_id: The current session ID.
        
    Returns:
        Dict containing structured branch information.
    """
    # Use ActionType.READ with git_command = "branch", args = ["--format=%(refname:short) %(HEAD)"]
    request = ActionRequest(
        integration="local_system",
        action_type=ActionType.READ,
        session_id=session_id,
        arguments={"operation": "git", "git_command": "branch", "args": ["--format=%(refname:short) %(HEAD)"]},
        requires_confirmation=False
    )
    result = action_gateway.execute_action(request)
    
    if result.status != ActionStatus.SUCCESS:
        return result.model_dump()
        
    stdout = result.data.get("stdout", "")
    branches = []
    current_branch = None
    
    for line in stdout.splitlines():
        if not line.strip():
            continue
        parts = line.strip().split(" ", 1)
        b_name = parts[0]
        branches.append(b_name)
        if len(parts) > 1 and parts[1] == "*":
            current_branch = b_name
            
    # Modify data payload to include structured format
    result.data["structured"] = {
        "current_branch": current_branch,
        "branches": branches
    }
    
    return result.model_dump()

@registry.register(requires_confirmation=False)
def get_git_current_branch(session_id: str) -> Dict[str, Any]:
    """
    Returns the name of the current active branch.
    This is a READ operation.
    
    Args:
        session_id: The current session ID.
        
    Returns:
        Dict containing the current branch name.
    """
    request = ActionRequest(
        integration="local_system",
        action_type=ActionType.READ,
        session_id=session_id,
        arguments={"operation": "git", "git_command": "branch", "args": ["--show-current"]},
        requires_confirmation=False
    )
    result = action_gateway.execute_action(request)
    if result.status == ActionStatus.SUCCESS:
        result.data["structured"] = {
            "current_branch": result.data.get("stdout", "").strip()
        }
    return result.model_dump()

@registry.register(requires_confirmation=True)
def create_git_branch(session_id: str, branch_name: str) -> Dict[str, Any]:
    """
    Creates a new Git branch. 
    This is a WRITE operation and requires human confirmation.
    This operation does NOT switch or checkout the new branch.
    
    Args:
        session_id: The current session ID.
        branch_name: The name of the new branch to create.
        
    Returns:
        Dict containing the creation result.
    """
    request = ActionRequest(
        integration="local_system",
        action_type=ActionType.WRITE,
        session_id=session_id,
        arguments={"operation": "git_create_branch", "branch_name": branch_name},
        requires_confirmation=True
    )
    result = action_gateway.execute_action(request)
    return result.model_dump()

@registry.register(requires_confirmation=True)
def switch_git_branch(session_id: str, branch_name: str) -> Dict[str, Any]:
    """
    Switches the current Git working tree to an existing local branch.
    This is a WRITE operation and requires human confirmation.
    
    Args:
        session_id: The current session ID.
        branch_name: The target branch to switch to.
        
    Returns:
        Dict containing the switch result.
    """
    # Pre-condition checks to avoid unnecessary confirmation
    
    # 1. Check current branch
    curr_req = ActionRequest(
        integration="local_system",
        action_type=ActionType.READ,
        session_id=session_id,
        arguments={"operation": "git", "git_command": "branch", "args": ["--show-current"]},
        requires_confirmation=False
    )
    curr_res = action_gateway.execute_action(curr_req)
    if curr_res.status == ActionStatus.SUCCESS and curr_res.data.get("stdout", "").strip() == branch_name:
        return {"status": "ALREADY_ON_BRANCH", "message": "The repository is already on this branch."}
        
    # 2. Check if branch exists
    exist_req = ActionRequest(
        integration="local_system",
        action_type=ActionType.READ,
        session_id=session_id,
        arguments={"operation": "git", "git_command": "branch", "args": ["--list", branch_name]},
        requires_confirmation=False
    )
    exist_res = action_gateway.execute_action(exist_req)
    if exist_res.status == ActionStatus.SUCCESS and not exist_res.data.get("stdout", "").strip():
        return {"status": "BRANCH_NOT_FOUND", "message": "The target branch does not exist locally."}
        
    # 3. Check for dirty working tree
    dirty_req = ActionRequest(
        integration="local_system",
        action_type=ActionType.READ,
        session_id=session_id,
        arguments={"operation": "git", "git_command": "status", "args": ["--porcelain"]},
        requires_confirmation=False
    )
    dirty_res = action_gateway.execute_action(dirty_req)
    if dirty_res.status == ActionStatus.SUCCESS and dirty_res.data.get("stdout", "").strip():
        return {"status": "DIRTY_WORKTREE_REQUIRES_REVIEW", "message": "The working tree is dirty. Stash or commit changes first."}
        
    # If pre-conditions pass, dispatch the WRITE request to ActionGateway
    request = ActionRequest(
        integration="local_system",
        action_type=ActionType.WRITE,
        session_id=session_id,
        arguments={"operation": "git_switch_branch", "branch_name": branch_name},
        requires_confirmation=True
    )
    result = action_gateway.execute_action(request)
    return result.model_dump()

@registry.register(requires_confirmation=True)
def delete_git_branch(session_id: str, branch_name: str) -> Dict[str, Any]:
    """
    Deletes an existing local Git branch safely.
    This is a DELETE operation and requires human confirmation.
    
    Args:
        session_id: The current session ID.
        branch_name: The target branch to delete.
        
    Returns:
        Dict containing the deletion result.
    """
    # Pre-condition checks to avoid unnecessary confirmation
    
    # 1. Check current branch
    curr_req = ActionRequest(
        integration="local_system",
        action_type=ActionType.READ,
        session_id=session_id,
        arguments={"operation": "git", "git_command": "branch", "args": ["--show-current"]},
        requires_confirmation=False
    )
    curr_res = action_gateway.execute_action(curr_req)
    if curr_res.status == ActionStatus.SUCCESS and curr_res.data.get("stdout", "").strip() == branch_name:
        return {"status": "CANNOT_DELETE_CURRENT_BRANCH", "message": "Cannot delete the currently active branch."}
        
    # 2. Check if branch exists
    exist_req = ActionRequest(
        integration="local_system",
        action_type=ActionType.READ,
        session_id=session_id,
        arguments={"operation": "git", "git_command": "branch", "args": ["--list", branch_name]},
        requires_confirmation=False
    )
    exist_res = action_gateway.execute_action(exist_req)
    if exist_res.status == ActionStatus.SUCCESS and not exist_res.data.get("stdout", "").strip():
        return {"status": "BRANCH_NOT_FOUND", "message": "The target branch does not exist locally."}
        
    # If pre-conditions pass, dispatch the DELETE request to ActionGateway
    request = ActionRequest(
        integration="local_system",
        action_type=ActionType.DELETE,
        session_id=session_id,
        arguments={"operation": "git_delete_branch", "branch_name": branch_name},
        requires_confirmation=True
    )
    result = action_gateway.execute_action(request)
    return result.model_dump()

@registry.register(requires_confirmation=True)
def stage_git_files(session_id: str, paths: list[str]) -> Dict[str, Any]:
    """
    Stages explicitly specified workspace-relative files.
    This is a WRITE operation and requires human confirmation.
    
    Args:
        session_id: The current session ID.
        paths: A list of workspace-relative file paths to stage.
        
    Returns:
        Dict containing the staging result and status.
    """
    if not paths:
        return {"status": "FAILED", "message": "EXPLICIT_PATHS_REQUIRED"}
        
    # Check git repo
    repo_req = ActionRequest(
        integration="local_system",
        action_type=ActionType.READ,
        session_id=session_id,
        arguments={"operation": "git", "git_command": "status", "args": ["--porcelain"]},
        requires_confirmation=False
    )
    repo_res = action_gateway.execute_action(repo_req)
    if repo_res.status != ActionStatus.SUCCESS:
        return {"status": "NOT_A_GIT_REPOSITORY", "message": "The workspace is not a valid Git repository."}
        
    # We need to perform the pre-checks here to return FILE_NOT_FOUND, DIRECTORY_NOT_ALLOWED, etc.
    # We can use the read_file tool to verify path safety but we need a better way.
    # Actually, we can just do a git status on the specific files, but if a file doesn't exist, git status might just return nothing.
    # Let's rely on the gateway executing the _execute_git_stage_files which has the preconditions!
    # Wait, the prompt says "Before confirmation, inspect the requested paths. Return deterministic results...".
    # If the gateway handles it, it happens AFTER confirmation.
    # BUT I can do the os.path checks here!
    
    import os
    from app.config import get_settings
    root = get_settings().workspace_root
    
    for p in paths:
        if any(wc in p for wc in ["*", "?", "[", "]"]):
            return {"status": "FAILED", "message": "Wildcards are not allowed in paths."}
            
        full_path = root / p
        
        # Prevent traversal
        try:
            full_path = full_path.resolve()
            if not str(full_path).startswith(str(root.resolve())):
                return {"status": "FAILED", "message": f"Path outside workspace: {p}"}
        except Exception:
            return {"status": "FAILED", "message": f"Invalid path: {p}"}
            
        if not full_path.exists():
            return {"status": "FILE_NOT_FOUND", "message": f"File does not exist: {p}"}
        if full_path.is_dir():
            return {"status": "DIRECTORY_NOT_ALLOWED", "message": f"Cannot stage directories: {p}"}
            
        # Check ignore
        ign_req = ActionRequest(
            integration="local_system",
            action_type=ActionType.READ,
            session_id=session_id,
            arguments={"operation": "git", "git_command": "check-ignore", "args": ["--quiet", p]},
            requires_confirmation=False
        )
        ign_res = action_gateway.execute_action(ign_req)
        # returncode 0 means ignored. In our action_gateway, exit_code 0 means SUCCESS.
        if ign_res.status == ActionStatus.SUCCESS and ign_res.data.get("exit_code") == 0:
            return {"status": "IGNORED_FILE", "message": f"File is ignored by Git: {p}"}
            
    # Check already staged
    # We will get status for each file
    file_statuses = {}
    for p in paths:
        st_req = ActionRequest(
            integration="local_system",
            action_type=ActionType.READ,
            session_id=session_id,
            arguments={"operation": "git", "git_command": "status", "args": ["--porcelain", "--", p]},
            requires_confirmation=False
        )
        st_res = action_gateway.execute_action(st_req)
        out = st_res.data.get("stdout", "") if st_res.status == ActionStatus.SUCCESS else ""
        print('OUT IS:', repr(out))
        if out:
            # First 2 chars
            xy = out[:2]
            if xy in ("M ", "A ", "D ", "R ", "C "):
                file_statuses[p] = "ALREADY_STAGED"
            else:
                file_statuses[p] = "NEEDS_STAGING"
        else:
            file_statuses[p] = "ALREADY_STAGED"
            
    # If ALL are ALREADY_STAGED or clean
    print('FILE_STATUSES:', file_statuses)
    if all(s == "ALREADY_STAGED" for s in file_statuses.values()):
        return {"status": "ALREADY_STAGED", "message": "All requested files are already staged."}
        
    request = ActionRequest(
        integration="local_system",
        action_type=ActionType.WRITE,
        session_id=session_id,
        arguments={"operation": "git_stage_files", "paths": paths},
        requires_confirmation=True
    )
    result = action_gateway.execute_action(request)
    return result.model_dump()


@registry.register(requires_confirmation=True)
def unstage_git_files(session_id: str, paths: list[str]) -> dict[str, Any]:
    """
    Unstages the specified workspace-relative paths from the Git index.
    
    This operates strictly on the Git index using `git restore --staged -- <paths>`.
    It does not modify the working tree contents.
    
    Returns:
        A dictionary with the action result.
    """
    if not isinstance(paths, list) or not paths:
        return {"status": "VALIDATION_ERROR", "message": "Paths must be a non-empty list of strings."}
        
    for p in paths:
        if not isinstance(p, str) or not p.strip():
            return {"status": "VALIDATION_ERROR", "message": "Paths must be non-empty strings."}
        if any(wc in p for wc in ["*", "?", "[", "]"]):
            return {"status": "WILDCARD_NOT_ALLOWED", "message": "Wildcards are not allowed in paths."}
            
    from app.integrations.local_system import LocalSystemIntegration
    from app.integrations.gateway import action_gateway
    from app.integrations.models import ActionRequest, ActionType, ActionStatus
    
    # Path resolution safety check
    ls = LocalSystemIntegration()
    is_safe, resolved_path, err = ls._safe_resolve(paths[0]) # Cheap check on first path to block absolute escapes early
    if not is_safe:
        if "outside" in err.lower():
            return {"status": "PATH_OUTSIDE_WORKSPACE", "message": err}
        return {"status": "VALIDATION_ERROR", "message": err}
        
    
    
    # Check if repo exists
    repo_req = ActionRequest(
        integration="local_system",
        action_type=ActionType.READ,
        session_id=session_id,
        arguments={"operation": "git", "git_command": "rev-parse", "args": ["--is-inside-work-tree"]},
        requires_confirmation=False
    )
    repo_res = action_gateway.execute_action(repo_req)
    if repo_res.status != ActionStatus.SUCCESS or repo_res.data.get("exit_code") != 0:
        return {"status": "NOT_A_GIT_REPOSITORY", "message": "The current workspace is not a Git repository."}
        
    file_statuses = {}
    for p in paths:
        is_safe, resolved, _ = ls._safe_resolve(p)
        if not is_safe:
            return {"status": "VALIDATION_ERROR", "message": "Invalid path"}
            
        if resolved.exists() and resolved.is_dir():
            return {"status": "DIRECTORY_NOT_ALLOWED", "message": f"Path is a directory: {p}"}
            
        st_req = ActionRequest(
            integration="local_system",
            action_type=ActionType.READ,
            session_id=session_id,
            arguments={"operation": "git", "git_command": "status", "args": ["--porcelain", "--", p]},
            requires_confirmation=False
        )
        st_res = action_gateway.execute_action(st_req)
        out = st_res.data.get("stdout", "") if st_res.status == ActionStatus.SUCCESS else ""
        if out:
            xy = out[:2]
            if xy[0] in ("M", "A", "D", "R", "C"):
                file_statuses[p] = "STAGED"
            else:
                file_statuses[p] = "NOT_STAGED"
        else:
            if not resolved.exists():
                return {"status": "FILE_NOT_FOUND", "message": f"File does not exist and is not tracked: {p}"}
            file_statuses[p] = "NOT_STAGED"
            
    if all(s == "NOT_STAGED" for s in file_statuses.values()):
        return {"status": "NOT_STAGED", "message": "All requested files are already unstaged or unchanged."}
        
    request = ActionRequest(
        integration="local_system",
        action_type=ActionType.WRITE,
        session_id=session_id,
        arguments={"operation": "git_unstage_files", "paths": paths},
        requires_confirmation=True
    )
    result = action_gateway.execute_action(request)
    return result.model_dump()

@registry.register(requires_confirmation=False)
def get_git_remotes(session_id: str) -> dict[str, Any]:
    """
    Retrieves the configured Git remotes for the current workspace.
    Remote URLs are safely sanitized to remove any credentials.
    
    Returns:
        A dictionary containing the success status and a list of remotes,
        each with a name, fetch_url, and push_url.
    """
    from app.integrations.local_system import LocalSystemIntegration
    from app.integrations.models import ActionRequest, ActionType, ActionStatus
    
    ls = LocalSystemIntegration()
    
    req = ActionRequest(
        integration="local_system",
        action_type=ActionType.READ,
        session_id=session_id,
        arguments={"operation": "git_remotes"},
        requires_confirmation=False
    )
    
    res = ls.execute(req)
    if res.status == ActionStatus.SUCCESS:
        return res.data
    else:
        return {"success": False, "status": res.message, "message": "Failed to retrieve remotes."}


@registry.register(requires_confirmation=True)
def add_git_remote(session_id: str, name: str, url: str) -> dict[str, Any]:
    """
    Adds a new Git remote to the local repository.
    This modifies local configuration only and does not contact the remote.
    """
    from app.integrations.gateway import action_gateway
    from app.integrations.models import ActionRequest, ActionType, ActionStatus
    from app.integrations.local_system import LocalSystemIntegration
    
    # Pre-flight check
    ls = LocalSystemIntegration()
    root = ls._get_workspace_root()
    import subprocess, os
    env = os.environ.copy()
    try:
        repo_proc = subprocess.run(["git", "rev-parse", "--is-inside-work-tree"], cwd=root, env=env, shell=False, capture_output=True, text=True)
        if repo_proc.returncode != 0:
            return {"status": "FAILED", "message": "NOT_A_GIT_REPOSITORY"}
    except Exception:
        return {"status": "FAILED", "message": "NOT_A_GIT_REPOSITORY"}
        
    remotes_proc = subprocess.run(["git", "remote"], cwd=root, env=env, shell=False, capture_output=True, text=True)
    if name in remotes_proc.stdout.splitlines():
        return {"status": "FAILED", "message": "REMOTE_ALREADY_EXISTS"}
        
    if not _validate_remote_name(name):
        return {"status": "FAILED", "message": "INVALID_REMOTE_NAME"}
    if not _validate_remote_url(url):
        return {"status": "FAILED", "message": "INVALID_REMOTE_URL"}
    safe_url = _sanitize_remote_url(url)
    msg = f"Add Git remote '{name}' pointing to:\n{safe_url}\n\nThis changes local Git configuration only.\nIt does not push, pull, fetch, or contact the remote."
    
    req = ActionRequest(
        integration="local_system",
        action_type=ActionType.WRITE,
        session_id=session_id,
        arguments={"operation": "git_remote_add", "name": name, "url": safe_url, "confirmation_message": msg},
        requires_confirmation=True
    )
    res = action_gateway.execute_action(req)
    res_dict = res.model_dump()
    if res.status == ActionStatus.WAITING_FOR_CONFIRMATION:
        res_dict["message"] = msg
    return res_dict

@registry.register(requires_confirmation=True)
def remove_git_remote(session_id: str, name: str) -> dict[str, Any]:
    """
    Removes a Git remote from the local repository.
    This modifies local configuration only and does not contact the remote.
    """
    from app.integrations.gateway import action_gateway
    from app.integrations.models import ActionRequest, ActionType, ActionStatus
    from app.integrations.local_system import LocalSystemIntegration
    
    ls = LocalSystemIntegration()
    root = ls._get_workspace_root()
    import subprocess, os
    env = os.environ.copy()
    try:
        repo_proc = subprocess.run(["git", "rev-parse", "--is-inside-work-tree"], cwd=root, env=env, shell=False, capture_output=True, text=True)
        if repo_proc.returncode != 0:
            return {"status": "FAILED", "message": "NOT_A_GIT_REPOSITORY"}
    except Exception:
        return {"status": "FAILED", "message": "NOT_A_GIT_REPOSITORY"}
        
    remotes_proc = subprocess.run(["git", "remote"], cwd=root, env=env, shell=False, capture_output=True, text=True)
    if not _validate_remote_name(name):
        return {"status": "FAILED", "message": "INVALID_REMOTE_NAME"}
    if name not in remotes_proc.stdout.splitlines():
        return {"status": "FAILED", "message": "REMOTE_NOT_FOUND"}
        
    msg = f"Remove Git remote '{name}'?\nThis changes the local repository configuration only.\nIt does not push, pull, fetch, or contact the remote."
    
    req = ActionRequest(
        integration="local_system",
        action_type=ActionType.WRITE,
        session_id=session_id,
        arguments={"operation": "git_remote_remove", "name": name, "confirmation_message": msg},
        requires_confirmation=True
    )
    res = action_gateway.execute_action(req)
    res_dict = res.model_dump()
    if res.status == ActionStatus.WAITING_FOR_CONFIRMATION:
        res_dict["message"] = msg
    return res_dict

@registry.register(requires_confirmation=True)
def rename_git_remote(session_id: str, old_name: str, new_name: str) -> dict[str, Any]:
    """
    Renames a Git remote in the local repository.
    This modifies local configuration only and does not contact the remote.
    """
    from app.integrations.gateway import action_gateway
    from app.integrations.models import ActionRequest, ActionType, ActionStatus
    from app.integrations.local_system import LocalSystemIntegration
    
    ls = LocalSystemIntegration()
    root = ls._get_workspace_root()
    import subprocess, os
    env = os.environ.copy()
    try:
        repo_proc = subprocess.run(["git", "rev-parse", "--is-inside-work-tree"], cwd=root, env=env, shell=False, capture_output=True, text=True)
        if repo_proc.returncode != 0:
            return {"status": "FAILED", "message": "NOT_A_GIT_REPOSITORY"}
    except Exception:
        return {"status": "FAILED", "message": "NOT_A_GIT_REPOSITORY"}
        
    remotes_proc = subprocess.run(["git", "remote"], cwd=root, env=env, shell=False, capture_output=True, text=True)
    remotes = remotes_proc.stdout.splitlines()
    if not _validate_remote_name(old_name) or not _validate_remote_name(new_name):
        return {"status": "FAILED", "message": "INVALID_REMOTE_NAME"}
    if old_name == new_name:
        return {"status": "FAILED", "message": "INVALID_REMOTE_NAME"}
    if old_name not in remotes:
        return {"status": "FAILED", "message": "REMOTE_NOT_FOUND"}
    if new_name in remotes:
        return {"status": "FAILED", "message": "REMOTE_ALREADY_EXISTS"}
        
    msg = f"Rename Git remote '{old_name}' to '{new_name}'?\nThis changes the local repository configuration only.\nIt does not push, pull, fetch, or contact the remote."
    
    req = ActionRequest(
        integration="local_system",
        action_type=ActionType.WRITE,
        session_id=session_id,
        arguments={"operation": "git_remote_rename", "old_name": old_name, "new_name": new_name, "confirmation_message": msg},
        requires_confirmation=True
    )
    res = action_gateway.execute_action(req)
    res_dict = res.model_dump()
    if res.status == ActionStatus.WAITING_FOR_CONFIRMATION:
        res_dict["message"] = msg
    return res_dict

@registry.register(requires_confirmation=True)
def set_git_remote_url(session_id: str, name: str, url: str) -> dict[str, Any]:
    """
    Sets the URL for a Git remote in the local repository.
    This modifies local configuration only and does not contact the remote.
    """
    from app.integrations.gateway import action_gateway
    from app.integrations.models import ActionRequest, ActionType, ActionStatus
    from app.integrations.local_system import LocalSystemIntegration
    
    ls = LocalSystemIntegration()
    root = ls._get_workspace_root()
    import subprocess, os
    env = os.environ.copy()
    try:
        repo_proc = subprocess.run(["git", "rev-parse", "--is-inside-work-tree"], cwd=root, env=env, shell=False, capture_output=True, text=True)
        if repo_proc.returncode != 0:
            return {"status": "FAILED", "message": "NOT_A_GIT_REPOSITORY"}
    except Exception:
        return {"status": "FAILED", "message": "NOT_A_GIT_REPOSITORY"}
        
    remotes_proc = subprocess.run(["git", "remote"], cwd=root, env=env, shell=False, capture_output=True, text=True)
    if not _validate_remote_name(name):
        return {"status": "FAILED", "message": "INVALID_REMOTE_NAME"}
    if name not in remotes_proc.stdout.splitlines():
        return {"status": "FAILED", "message": "REMOTE_NOT_FOUND"}
        
    if not _validate_remote_name(name):
        return {"status": "FAILED", "message": "INVALID_REMOTE_NAME"}
    if not _validate_remote_url(url):
        return {"status": "FAILED", "message": "INVALID_REMOTE_URL"}
    safe_url = _sanitize_remote_url(url)
    msg = f"Change Git remote '{name}' URL to:\n{safe_url}\n\nThis changes local Git configuration only.\nIt does not push, pull, fetch, or contact the remote."
    
    req = ActionRequest(
        integration="local_system",
        action_type=ActionType.WRITE,
        session_id=session_id,
        arguments={"operation": "git_remote_set_url", "name": name, "url": safe_url, "confirmation_message": msg},
        requires_confirmation=True
    )
    res = action_gateway.execute_action(req)
    res_dict = res.model_dump()
    if res.status == ActionStatus.WAITING_FOR_CONFIRMATION:
        res_dict["message"] = msg
    return res_dict

@registry.register(requires_confirmation=True)
def fetch_git_remote(session_id: str, remote_name: str) -> dict:
    '''
    Fetches remote-tracking references and metadata from a specific remote.
    '''
    from app.config import get_settings
    from app.integrations.models import ActionRequest, ActionType, ActionStatus
    from app.integrations.gateway import action_gateway
    import subprocess, os
    
    settings = get_settings()
    root = settings.workspace_root
    env = os.environ.copy()
    
    try:
        repo_proc = subprocess.run(["git", "rev-parse", "--is-inside-work-tree"], cwd=root, env=env, shell=False, capture_output=True, text=True)
        if repo_proc.returncode != 0:
            return {"status": "FAILED", "message": "NOT_A_GIT_REPOSITORY"}
    except Exception:
        return {"status": "FAILED", "message": "NOT_A_GIT_REPOSITORY"}
        
    if not _validate_remote_name(remote_name):
        return {"status": "FAILED", "message": "INVALID_REMOTE_NAME"}
        
    remotes_proc = subprocess.run(["git", "remote"], cwd=root, env=env, shell=False, capture_output=True, text=True)
    if remote_name not in remotes_proc.stdout.splitlines():
        return {"status": "FAILED", "message": "REMOTE_NOT_FOUND"}
        
    url_proc = subprocess.run(["git", "remote", "get-url", remote_name], cwd=root, env=env, shell=False, capture_output=True, text=True)
    if url_proc.returncode != 0:
        return {"status": "FAILED", "message": "REMOTE_NOT_FOUND"}
        
    url = url_proc.stdout.strip()
    safe_url = _sanitize_remote_url(url)
    
    msg = f"Fetch from Git remote '{remote_name}'?\n\nRemote:\n{safe_url}\n\nThis will contact the remote and update local\nremote-tracking references.\n\nIt will NOT merge, rebase, checkout, or modify\nworking-tree files."
    
    req = ActionRequest(
        integration="local_system",
        action_type=ActionType.EXECUTE,
        session_id=session_id,
        arguments={"operation": "git_fetch", "remote_name": remote_name, "pinned_url": url, "confirmation_message": msg},
        requires_confirmation=True
    )
    res = action_gateway.execute_action(req)
    res_dict = res.model_dump()
    if res.status == ActionStatus.WAITING_FOR_CONFIRMATION:
        res_dict["message"] = msg
    return res_dict

@registry.register(requires_confirmation=False)
def inspect_git_fetch_result(session_id: str, remote_name: str) -> dict:
    '''
    Inspects the local repository state AFTER a successful controlled fetch.
    '''
    from app.integrations.models import ActionRequest, ActionType, ActionStatus
    from app.integrations.gateway import action_gateway
    
    if not _validate_remote_name(remote_name):
        return {"status": "FAILED", "message": "INVALID_REMOTE_NAME"}
        
    req = ActionRequest(
        integration="local_system",
        action_type=ActionType.READ,
        session_id=session_id,
        arguments={"operation": "git_fetch_result_inspection", "remote_name": remote_name},
        requires_confirmation=False
    )
    res = action_gateway.execute_action(req)
    return res.model_dump()

@registry.register(requires_confirmation=False)
def propose_git_pull(session_id: str, remote_name: str) -> dict:
    '''
    Proposes a controlled Git pull operation based on local repository state.
    '''
    from app.integrations.models import ActionRequest, ActionType
    from app.integrations.gateway import action_gateway
    
    if not _validate_remote_name(remote_name):
        return {"status": "FAILED", "message": "INVALID_REMOTE_NAME"}
        
    req = ActionRequest(
        integration="local_system",
        action_type=ActionType.READ,
        session_id=session_id,
        arguments={"operation": "git_pull_proposal", "remote_name": remote_name},
        requires_confirmation=False
    )
    res = action_gateway.execute_action(req)
    return res.model_dump()



@registry.register(requires_confirmation=True)
def execute_git_pull(session_id: str, remote_name: str) -> dict:
    '''
    Executes a controlled Git pull (fast-forward only) using an already-fetched remote.
    '''
    from app.config import get_settings
    from app.integrations.models import ActionRequest, ActionType, ActionStatus
    from app.integrations.gateway import action_gateway
    import subprocess, os
    
    settings = get_settings()
    root = settings.workspace_root
    env = os.environ.copy()
    
    if not _validate_remote_name(remote_name):
        return {"status": "FAILED", "message": "INVALID_REMOTE_NAME"}
        
    try:
        repo_proc = subprocess.run(["git", "rev-parse", "--is-inside-work-tree"], cwd=root, env=env, shell=False, capture_output=True, text=True)
        if repo_proc.returncode != 0:
            return {"status": "FAILED", "message": "NOT_A_GIT_REPOSITORY"}
    except Exception:
        return {"status": "FAILED", "message": "NOT_A_GIT_REPOSITORY"}
        
    curr_branch_proc = subprocess.run(["git", "branch", "--show-current"], cwd=root, env=env, shell=False, capture_output=True, text=True)
    current_branch = curr_branch_proc.stdout.strip()
    if not current_branch or curr_branch_proc.returncode != 0:
        return {"status": "FAILED", "message": "DETACHED_HEAD_OR_NO_BRANCH"}
        
    local_branches_proc = subprocess.run(["git", "for-each-ref", "--format=%(refname:short) %(upstream:short)", "refs/heads/"], cwd=root, env=env, shell=False, capture_output=True, text=True)
    upstream = None
    for line in local_branches_proc.stdout.splitlines():
        parts = line.strip().split()
        if len(parts) == 2 and parts[0] == current_branch:
            upstream = parts[1]
            break
            
    if not upstream or not upstream.startswith(f"{remote_name}/"):
        return {"status": "FAILED", "message": "NO_UPSTREAM_CONFIGURATION"}
        
    upstream_ref = f"refs/remotes/{upstream}"
    up_check = subprocess.run(["git", "rev-parse", "--verify", upstream_ref], cwd=root, env=env, shell=False, capture_output=True, text=True)
    if up_check.returncode != 0:
        return {"status": "FAILED", "message": "MISSING_REMOTE_TRACKING_REF"}
    expected_upstream_sha = up_check.stdout.strip()
    
    head_check = subprocess.run(["git", "rev-parse", "HEAD"], cwd=root, env=env, shell=False, capture_output=True, text=True)
    expected_head_sha = head_check.stdout.strip()
    
    status_proc = subprocess.run(["git", "status", "--porcelain", "--untracked-files=all"], cwd=root, env=env, shell=False, capture_output=True, text=True)
    if status_proc.stdout.strip() != "":
        return {"status": "FAILED", "message": "DIRTY_WORKTREE_REQUIRES_REVIEW"}
        
    rev_list_proc = subprocess.run(["git", "rev-list", "--left-right", "--count", f"{current_branch}...{upstream}"], cwd=root, env=env, shell=False, capture_output=True, text=True)
    ahead = 0
    behind = 0
    if rev_list_proc.returncode == 0:
        counts = rev_list_proc.stdout.strip().split()
        if len(counts) == 2:
            ahead = int(counts[0])
            behind = int(counts[1])
            
    if ahead == 0 and behind == 0:
        return {"status": "FAILED", "message": "UP_TO_DATE"}
    if ahead > 0 and behind == 0:
        return {"status": "FAILED", "message": "AHEAD"}
    if ahead > 0 and behind > 0:
        return {"status": "FAILED", "message": "DIVERGED"}
        
    msg = f"Fast-forward local branch `{current_branch}` to `{upstream}`.\n\nCurrent commit: {expected_head_sha[:7]}\nTarget commit:  {expected_upstream_sha[:7]}\nBehind by:     {behind} commits\nAhead by:      {ahead} commits\n\nWorking tree: clean\n\nThis operation:\n- uses the already-fetched remote-tracking branch\n- performs fast-forward only\n- does not fetch from the network\n- does not create a merge commit\n- does not rebase\n- does not stash/reset/clean changes\n\nApprove to continue."
    
    req = ActionRequest(
        integration="local_system",
        action_type=ActionType.WRITE,
        session_id=session_id,
        arguments={
            "operation": "git_pull_fast_forward",
            "remote_name": remote_name,
            "current_branch": current_branch,
            "upstream_branch": upstream,
            "upstream_ref": upstream_ref,
            "expected_head_sha": expected_head_sha,
            "expected_upstream_sha": expected_upstream_sha,
            "behind": behind,
            "confirmation_message": msg
        },
        requires_confirmation=True
    )
    res = action_gateway.execute_action(req)
    return res.model_dump()

@registry.register(requires_confirmation=False)
def inspect_git_pull_result(session_id: str, remote_name: str) -> dict:
    '''
    Inspects the result of a controlled Git pull operation (or the current synchronization state).
    Returns a deterministic structured observation including branch relationships, worktree state, and commits.
    This is a safe, read-only operation.
    
    Args:
        session_id: The current session ID.
        remote_name: The remote name (e.g. 'origin').
        
    Returns:
        Dict containing the inspection status.
    '''
    from app.integrations.models import ActionRequest, ActionType
    from app.integrations.gateway import action_gateway
    
    if not _validate_remote_name(remote_name):
        return {"status": "FAILED", "message": "INVALID_REMOTE_NAME"}
        
    req = ActionRequest(
        integration="local_system",
        action_type=ActionType.READ,
        session_id=session_id,
        arguments={"operation": "git_pull_result_inspection", "remote_name": remote_name},
        requires_confirmation=False
    )
    res = action_gateway.execute_action(req)
    return res.model_dump()

@registry.register(requires_confirmation=True)
def push_git_remote(session_id: str, remote_name: str, branch_name: str) -> dict:
    if not _validate_remote_name(remote_name):
        return {"status": "INVALID_REMOTE", "message": "Invalid remote name."}
        
    if not branch_name or not branch_name.strip() or branch_name.startswith('-'):
        return {"status": "INVALID_BRANCH", "message": "Invalid branch name."}
        
    if ':' in branch_name or '*' in branch_name or '?' in branch_name or ' ' in branch_name or '+' in branch_name or '\\' in branch_name:
        return {"status": "INVALID_BRANCH", "message": "Refspecs, colons, and wildcards are explicitly blocked."}
        
    status_dict = get_git_status(session_id)
    if "error" in status_dict:
        return status_dict
        
    if not status_dict.get("clean"):
        return {"status": "DIRTY_WORKING_TREE", "message": "Working tree must be clean before pushing."}
        
    current_branch = status_dict.get("current_branch")
    if current_branch != branch_name:
        return {"status": "BRANCH_MISMATCH", "message": f"Must push current branch '{current_branch}', but requested '{branch_name}'"}
        
    commits_dict = get_git_commits(session_id, count=1)
    if "error" in commits_dict or not commits_dict.get("commits"):
        return {"status": "NO_COMMITS", "message": "No commits exist to push."}
        
    head_sha = commits_dict["commits"][0]["hash"]
    
    remotes_dict = get_git_remotes(session_id)
    if "error" in remotes_dict:
        return remotes_dict
        
    if remote_name not in remotes_dict.get("remotes", {}):
        return {"status": "MISSING_REMOTE", "message": f"Remote '{remote_name}' does not exist."}
        
    remote_url = remotes_dict["remotes"][remote_name].get("push_url")
    if not remote_url:
        return {"status": "MISSING_REMOTE_URL", "message": f"Remote '{remote_name}' has no push URL configured."}
        
    request = ActionRequest(
        integration="local_system",
        action_type=ActionType.WRITE,
        session_id=session_id,
        arguments={
            "operation": "git_push",
            "remote_name": remote_name,
            "branch_name": branch_name,
            "expected_head_sha": head_sha,
            "expected_remote_url": remote_url
        },
        requires_confirmation=True
    )
    
    result = action_gateway.execute_action(request)
    
    if result.status == ActionStatus.WAITING_FOR_CONFIRMATION:
        return {
            "status": "waiting_for_confirmation",
            "action": "git_push",
            "message": f"Push local branch '{branch_name}' to remote '{remote_name}'?\n\nCommit: {head_sha}\nDestination URL: {remote_url}\n\nWARNING: The operation will only proceed if the current local state is clean and the remote URL remains unchanged."
        }
        
    return {
        "status": result.status.value,
        "data": result.data if result.status.value == "SUCCESS" else None,
        "message": result.message
    }
