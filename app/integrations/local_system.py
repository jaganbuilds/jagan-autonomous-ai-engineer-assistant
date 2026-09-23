import os
from pathlib import Path
from typing import Dict, Any, Tuple, Optional
from app.integrations.gateway import BaseIntegration
from app.integrations.models import ActionType, ActionRequest, ActionResult, ActionStatus, ActionRiskLevel
from app.integrations.capabilities import ActionCapability
from app.config import get_settings

class LocalSystemIntegration(BaseIntegration):
    """
    Provides safe, gateway-governed access to the local project workspace.
    Supports READ_FILE and WRITE_FILE bounded strictly to the configured workspace root.
    """
    
    @property
    def integration_name(self) -> str:
        return "local_system"
        
    @property
    def supported_actions(self) -> list[ActionType]:
        return [ActionType.READ, ActionType.WRITE, ActionType.EXECUTE, ActionType.DELETE]
        
    def _get_workspace_root(self) -> Path:
        settings = get_settings()
        root_path = Path(settings.workspace_root).resolve(strict=False)
        return root_path

    def _safe_resolve(self, filepath: str) -> Tuple[bool, Optional[Path], str]:
        """
        Resolves a path safely, preventing traversal outside the allowed workspace directory.
        Protects against symlink escaping by resolving to absolute paths.
        """
        if not filepath or not isinstance(filepath, str) or not filepath.strip():
            return False, None, "Filepath is missing or invalid."
            
        workspace_root = self._get_workspace_root()
        try:
            target_path = (workspace_root / filepath).resolve(strict=False)
            if not str(target_path).startswith(str(workspace_root)):
                return False, None, "Path attempts to escape the configured workspace"
            return True, target_path, ""
        except Exception as e:
            return False, None, f"Invalid path: {e}"

    def validate_arguments(self, action_type: ActionType, arguments: Dict[str, Any]) -> Tuple[bool, str]:
        if action_type not in self.supported_actions:
            return False, f"Action {action_type} is not supported by local_system."
            
        if action_type == ActionType.READ:
            operation = arguments.get("operation", "read_file")
            if operation in ("git_fetch_result_inspection", "git_pull_proposal", "git_pull_result_inspection"):
                remote_name = arguments.get("remote_name")
                if not isinstance(remote_name, str) or not remote_name.strip():
                    return False, "Invalid remote name"
                invalid_chars = ["/", "\\", ";", "|", "&", "$", "`", "\x00", ">", "<"]
                if any(c in remote_name for c in invalid_chars) or remote_name.startswith("-"):
                    return False, "Invalid remote name format"
                return True, ""
            if operation == "read_file":
                filepath = arguments.get("filepath")
                is_safe, _, error_msg = self._safe_resolve(filepath)
                if not is_safe:
                    return False, error_msg
                return True, ""
            elif operation == "git_remotes":
                return True, ""
            elif operation == "git":
                git_cmd = arguments.get("git_command")
                if git_cmd not in ("status", "branch", "log", "rev-parse", "diff", "check-ignore"):
                    return False, f"Unsupported git read command: {git_cmd}"
                args = arguments.get("args", [])
                if not isinstance(args, list):
                    return False, "Invalid 'args': must be a list of strings."
                for arg in args:
                    if not isinstance(arg, str):
                        return False, f"Invalid argument type: {type(arg)}"
                    invalid_chars = ["&&", ";", "|", ">", "<", "$", "`"]
                    if any(c in arg for c in invalid_chars):
                        return False, f"Argument contains dangerous shell characters: {arg}"
                    if arg.startswith("--exec") or arg.startswith("--system") or arg.startswith("!"):
                        return False, f"Unsafe argument: {arg}"
                return True, ""
            else:
                return False, f"Invalid READ operation: {operation}"
                
        if action_type == ActionType.EXECUTE:
            operation = arguments.get("operation")
            if operation == "git_fetch":
                remote_name = arguments.get("remote_name")
                if not isinstance(remote_name, str) or not remote_name.strip():
                    return False, "Invalid remote name"
                invalid_chars = ["/", "\\", ";", "|", "&", "$", "`", "\x00", ">", "<"]
                if any(c in remote_name for c in invalid_chars) or remote_name.startswith("-"):
                    return False, "Invalid remote name format"
                return True, ""
            if operation != "pytest":
                return False, f"Unsupported operation: {operation}"
            
            args = arguments.get("args", [])
            if not isinstance(args, list):
                return False, "Invalid 'args': must be a list of strings."
                
            for arg in args:
                if not isinstance(arg, str):
                    return False, f"Invalid argument type: {type(arg)}"
                
                # Reject shell syntax
                invalid_chars = ["&&", ";", "|", ">", "<", "$", "`"]
                if any(c in arg for c in invalid_chars):
                    return False, f"Argument contains dangerous shell characters: {arg}"
                    
                # If looks like path or traversal
                if "/" in arg or "\\" in arg or ".." in arg:
                    is_safe, _, error_msg = self._safe_resolve(arg)
                    if not is_safe:
                        return False, f"Unsafe argument '{arg}': {error_msg}"
            return True, ""
        
        if action_type == ActionType.WRITE:
            operation = arguments.get("operation", "write")
            if operation not in ("write", "edit", "patch", "git_commit", "git_create_branch", "git_switch_branch", "git_stage_files", "git_unstage_files", "git_remote_add", "git_remote_remove", "git_remote_rename", "git_remote_set_url", "git_pull_fast_forward", "git_push"):
                return False, f"Invalid WRITE operation: {operation}"
                
            if operation == "git_pull_fast_forward":
                return True, arguments.get("confirmation_message", "Fast-forward git pull")
            if operation in ("write", "edit", "patch"):
                filepath = arguments.get("filepath")
                is_safe, _, error_msg = self._safe_resolve(filepath)
                if not is_safe:
                    return False, error_msg
            elif operation == "git_commit":
                msg = arguments.get("message")
                if not isinstance(msg, str) or not msg.strip():
                    return False, "Invalid or missing 'message' for git_commit."
                if msg.startswith("-"):
                    return False, "Commit message cannot start with '-' to prevent flag injection."
            elif operation in ("git_create_branch", "git_switch_branch"):
                branch_name = arguments.get("branch_name")
                if not isinstance(branch_name, str) or not branch_name.strip():
                    return False, f"Invalid or missing 'branch_name' for {operation}."
                if branch_name.startswith("-"):
                    return False, "Branch name cannot start with '-' to prevent flag injection."
                # Basic string validation against traversal/shell chars, git check-ref-format handles the rest internally
                invalid_chars = ["&&", ";", "|", ">", "<", "$", "`", "..", " ", "\\\\"]
                if any(c in branch_name for c in invalid_chars):
                    return False, "Branch name contains dangerous or invalid characters."
                reserved = ["HEAD", "ORIG_HEAD", "FETCH_HEAD", "MERGE_HEAD"]
                if branch_name.upper() in reserved:
                    return False, f"Branch name '{branch_name}' is reserved."
            elif operation == "git_stage_files":
                paths = arguments.get("paths")
                if not isinstance(paths, list) or not paths:
                    return False, "Invalid or missing 'paths' list for git_stage_files."
                
                for p in paths:
                    if not isinstance(p, str) or not p.strip():
                        return False, "All paths must be non-empty strings."
                    if any(wc in p for wc in ["*", "?", "[", "]"]):
                        return False, "Wildcards are not allowed in paths."
                    is_safe, _, err = self._safe_resolve(p)
                    if not is_safe:
                        return False, f"Unsafe path '{p}': {err}"
            elif operation == "git_unstage_files":
                paths = arguments.get("paths")
                if not isinstance(paths, list) or not paths:
                    return False, "Invalid or missing 'paths' list for git_unstage_files."
                
                for p in paths:
                    if not isinstance(p, str) or not p.strip():
                        return False, "All paths must be non-empty strings."
                    if any(wc in p for wc in ["*", "?", "[", "]"]):
                        return False, "Wildcards are not allowed in paths."
                    is_safe, _, err = self._safe_resolve(p)
                    if not is_safe:
                        return False, f"Unsafe path '{p}': {err}"
            elif operation in ("git_remote_add", "git_remote_remove", "git_remote_rename", "git_remote_set_url"):
                name = arguments.get("name")
                if not isinstance(name, str) or not name.strip():
                    return False, "Invalid or missing 'name'."
                if name.startswith("-"):
                    return False, "Remote name cannot start with '-'."
                if any(c in name for c in ["/", "\\", ";", "|", "&", "$", "`", "\x00", ">", "<", " "]):
                    return False, "Invalid characters in remote name."
                if operation in ("git_remote_add", "git_remote_set_url"):
                    url = arguments.get("url")
                    if not isinstance(url, str) or not url.strip() or url.startswith("-"):
                        return False, "Invalid or missing 'url'."
            elif operation == "git_push":
                remote_name = arguments.get("remote_name")
                branch_name = arguments.get("branch_name")
                if not isinstance(remote_name, str) or not remote_name.strip() or remote_name.startswith("-"):
                    return False, "Invalid or missing 'remote_name'."
                if not isinstance(branch_name, str) or not branch_name.strip() or branch_name.startswith("-"):
                    return False, "Invalid or missing 'branch_name'."
                # Check expected state
                expected_head_sha = arguments.get("expected_head_sha")
                expected_remote_url = arguments.get("expected_remote_url")
                if not expected_head_sha or not expected_remote_url:
                    return False, "git_push requires expected_head_sha and expected_remote_url for TOCTOU protection."
            return True, ""
            return True, ""
            
        elif action_type == ActionType.DELETE:
            operation = arguments.get("operation")
            if operation == "git_delete_branch":
                branch_name = arguments.get("branch_name")
                if not isinstance(branch_name, str) or not branch_name.strip():
                    return False, "Invalid or missing branch name"
                if branch_name.startswith("-"):
                    return False, "Branch name cannot start with '-'"
                if any(c in branch_name for c in [";", "|", "&", "$", "`", "\x00", ">", "<"]):
                    return False, "Invalid characters in branch name"
                reserved = ["HEAD", "ORIG_HEAD", "FETCH_HEAD", "MERGE_HEAD"]
                if branch_name.upper() in reserved:
                    return False, f"Branch name '{branch_name}' is reserved."
                return True, ""
            return False, f"Unsupported DELETE operation: {operation}"
            
        return False, f"Unhandled action type: {action_type}"

    def execute(self, request: ActionRequest) -> ActionResult:
        action_type = request.action_type
        
        if action_type == ActionType.READ:
            operation = request.arguments.get("operation", "read_file")
            if operation == "git_pull_proposal":
                return self._execute_git_pull_proposal(request)
            if operation == "git_fetch_result_inspection":
                return self._execute_git_fetch_result_inspection(request)
            if operation == "git_pull_result_inspection":
                return self._execute_git_pull_result_inspection(request)
            if operation == "read_file":
                filepath = request.arguments.get("filepath")
                is_safe, target_path, error_msg = self._safe_resolve(filepath)
                if not is_safe: return ActionResult(action_id=request.action_id, integration=request.integration, action_type=action_type, status=ActionStatus.VALIDATION_ERROR, message=error_msg)
                return self._read_file(request, target_path)
            elif operation == "git_remotes":
                return self._execute_git_remotes(request)
            elif operation == "git":
                return self._execute_git_read(request, request.arguments.get("git_command"), request.arguments.get("args", []))
                
        elif action_type == ActionType.WRITE:
            operation = request.arguments.get("operation", "write")
            if operation in ("write", "edit", "patch"):
                filepath = request.arguments.get("filepath")
                is_safe, target_path, error_msg = self._safe_resolve(filepath)
                if not is_safe: return ActionResult(action_id=request.action_id, integration=request.integration, action_type=action_type, status=ActionStatus.VALIDATION_ERROR, message=error_msg)
                if operation == "write": return self._write_file(request, target_path, request.arguments.get("content"))
                if operation == "edit": return self._edit_file(request, target_path, request.arguments.get("expected_content"), request.arguments.get("replacement"))
                if operation == "patch": return self._patch_file(request, target_path, request.arguments.get("patch_content"))
                
            elif operation == "git_pull_fast_forward":
                return self._execute_git_pull_fast_forward(request)
            
            elif operation == "git_push":
                return self._execute_git_push(request)

            elif operation == "git_commit":
                return self._execute_git_commit(request, request.arguments.get("message"))
            elif operation == "git_create_branch":
                return self._execute_git_create_branch(request, request.arguments.get("branch_name"))
            elif operation == "git_switch_branch":
                return self._execute_git_switch_branch(request, request.arguments.get("branch_name"))
            elif operation == "git_stage_files":
                return self._execute_git_stage_files(request, request.arguments.get("paths"))
            elif operation == "git_unstage_files":
                return self._execute_git_unstage_files(request, request.arguments.get("paths"))
            elif operation in ("git_remote_add", "git_remote_remove", "git_remote_rename", "git_remote_set_url"):
                return self._execute_git_remote_write(request)
                
        elif action_type == ActionType.DELETE:
            operation = request.arguments.get("operation")
            if operation == "git_delete_branch":
                return self._execute_git_delete_branch(request, request.arguments.get("branch_name"))
                
        elif action_type == ActionType.EXECUTE:
            operation = request.arguments.get("operation")
            if operation == "git_fetch":
                return self._execute_git_fetch(request)
            if operation == "pytest":
                return self._execute_command(request, "pytest", request.arguments.get("args", []))
                
        return ActionResult(action_id=request.action_id, integration=request.integration, action_type=request.action_type, status=ActionStatus.FAILED, message="Operation not supported or failed.")


    def _execute_git_remotes(self, request: ActionRequest) -> ActionResult:
        import subprocess
        import sys
        import time
        import os
        import urllib.parse
        
        settings = get_settings()
        timeout = settings.workspace_execution_timeout_seconds
        max_bytes = settings.workspace_execution_max_output_bytes
        env = os.environ.copy()
        root = self._get_workspace_root()
        
        # Verify it's a Git repo
        try:
            repo_proc = subprocess.run(["git", "rev-parse", "--is-inside-work-tree"], cwd=root, env=env, shell=False, capture_output=True, text=True)
            if repo_proc.returncode != 0:
                return ActionResult(action_id=request.action_id, integration=request.integration, action_type=request.action_type, status=ActionStatus.FAILED, message="NOT_A_GIT_REPOSITORY")
        except Exception:
            return ActionResult(action_id=request.action_id, integration=request.integration, action_type=request.action_type, status=ActionStatus.FAILED, message="NOT_A_GIT_REPOSITORY")
            
        cmd = ["git", "remote", "-v"]
        start_time = time.time()
        timed_out = False
        output_truncated = False
        proc = None
        
        try:
            if sys.platform == "win32":
                proc = subprocess.Popen(cmd, cwd=root, stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=False, env=env, text=True, creationflags=subprocess.CREATE_NEW_PROCESS_GROUP)
            else:
                proc = subprocess.Popen(cmd, cwd=root, stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=False, env=env, text=True, preexec_fn=os.setsid)
            stdout, stderr = proc.communicate(timeout=timeout)
        except subprocess.TimeoutExpired as e:
            timed_out = True
            if proc:
                try:
                    if sys.platform == "win32": subprocess.run(['taskkill', '/F', '/T', '/PID', str(proc.pid)], capture_output=True)
                    else:
                        import signal; os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
                except Exception: proc.kill()
                stdout = e.stdout.decode() if isinstance(e.stdout, bytes) else (e.stdout or "")
                stderr = e.stderr.decode() if isinstance(e.stderr, bytes) else (e.stderr or "")
                proc.wait()
        except Exception as e:
            return ActionResult(action_id=request.action_id, integration=request.integration, action_type=request.action_type, status=ActionStatus.FAILED, message=f"Git remote failed: {str(e)}")
            
        duration = round(time.time() - start_time, 2)
        
        if stdout and len(stdout) > max_bytes:
            stdout = stdout[:max_bytes]
            output_truncated = True
            
        def sanitize_url(url: str) -> str:
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
                
        remotes = {}
        if stdout:
            for line in stdout.splitlines():
                parts = line.strip().split()
                if len(parts) >= 3:
                    name = parts[0]
                    url = parts[1]
                    rtype = parts[2].strip("()")
                    safe_url = sanitize_url(url)
                    
                    if name not in remotes:
                        remotes[name] = {"name": name}
                    if rtype == "fetch":
                        remotes[name]["fetch_url"] = safe_url
                    elif rtype == "push":
                        remotes[name]["push_url"] = safe_url
                        
        final_exit_code = proc.returncode if not timed_out and proc is not None else -1
        success = final_exit_code == 0
        
        return ActionResult(
            action_id=request.action_id,
            integration=request.integration,
            action_type=request.action_type,
            status=ActionStatus.SUCCESS if success else ActionStatus.FAILED,
            message="Git remotes fetched successfully" if success else "Git remote fetch failed",
            data={
                "operation": "git_remotes",
                "success": success,
                "exit_code": final_exit_code,
                "remotes": list(remotes.values()),
                "duration": duration,
                "timed_out": timed_out,
                "output_truncated": output_truncated,
                "stdout": "[REDACTED BY INTEGRATION]",
                "stderr": "[REDACTED BY INTEGRATION]"
            }
        )


    def _execute_git_remote_write(self, request: ActionRequest) -> ActionResult:
        import subprocess
        import sys
        import time
        import os
        
        operation = request.arguments.get("operation")
        settings = get_settings()
        timeout = settings.workspace_execution_timeout_seconds
        max_bytes = settings.workspace_execution_max_output_bytes
        env = os.environ.copy()
        root = self._get_workspace_root()
        
        try:
            repo_proc = subprocess.run(["git", "rev-parse", "--is-inside-work-tree"], cwd=root, env=env, shell=False, capture_output=True, text=True)
            if repo_proc.returncode != 0:
                return ActionResult(action_id=request.action_id, integration=request.integration, action_type=request.action_type, status=ActionStatus.FAILED, message="NOT_A_GIT_REPOSITORY")
        except Exception:
            return ActionResult(action_id=request.action_id, integration=request.integration, action_type=request.action_type, status=ActionStatus.FAILED, message="NOT_A_GIT_REPOSITORY")
            
        remotes_proc = subprocess.run(["git", "remote"], cwd=root, env=env, shell=False, capture_output=True, text=True)
        current_remotes = set(remotes_proc.stdout.splitlines())
        
        if operation == "git_remote_add":
            name = request.arguments.get("name")
            url = request.arguments.get("url")
            if name in current_remotes:
                return ActionResult(action_id=request.action_id, integration=request.integration, action_type=request.action_type, status=ActionStatus.FAILED, message="REMOTE_ALREADY_EXISTS")
            cmd = ["git", "remote", "add", name, url]
            
        elif operation == "git_remote_remove":
            name = request.arguments.get("name")
            if name not in current_remotes:
                return ActionResult(action_id=request.action_id, integration=request.integration, action_type=request.action_type, status=ActionStatus.FAILED, message="REMOTE_NOT_FOUND")
            cmd = ["git", "remote", "remove", name]
            
        elif operation == "git_remote_rename":
            old_name = request.arguments.get("old_name")
            new_name = request.arguments.get("new_name")
            if old_name not in current_remotes:
                return ActionResult(action_id=request.action_id, integration=request.integration, action_type=request.action_type, status=ActionStatus.FAILED, message="REMOTE_NOT_FOUND")
            if new_name in current_remotes:
                return ActionResult(action_id=request.action_id, integration=request.integration, action_type=request.action_type, status=ActionStatus.FAILED, message="REMOTE_ALREADY_EXISTS")
            cmd = ["git", "remote", "rename", old_name, new_name]
            
        elif operation == "git_remote_set_url":
            name = request.arguments.get("name")
            url = request.arguments.get("url")
            if name not in current_remotes:
                return ActionResult(action_id=request.action_id, integration=request.integration, action_type=request.action_type, status=ActionStatus.FAILED, message="REMOTE_NOT_FOUND")
            cmd = ["git", "remote", "set-url", name, url]
        
        start_time = time.time()
        timed_out = False
        output_truncated = False
        proc = None
        
        try:
            if sys.platform == "win32":
                proc = subprocess.Popen(cmd, cwd=root, stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=False, env=env, text=True, creationflags=subprocess.CREATE_NEW_PROCESS_GROUP)
            else:
                proc = subprocess.Popen(cmd, cwd=root, stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=False, env=env, text=True, preexec_fn=os.setsid)
            stdout, stderr = proc.communicate(timeout=timeout)
        except subprocess.TimeoutExpired as e:
            timed_out = True
            if proc:
                try:
                    if sys.platform == "win32": subprocess.run(['taskkill', '/F', '/T', '/PID', str(proc.pid)], capture_output=True)
                    else:
                        import signal; os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
                except Exception: proc.kill()
                stdout = e.stdout.decode() if isinstance(e.stdout, bytes) else (e.stdout or "")
                stderr = e.stderr.decode() if isinstance(e.stderr, bytes) else (e.stderr or "")
                proc.wait()
        except Exception as e:
            return ActionResult(action_id=request.action_id, integration=request.integration, action_type=request.action_type, status=ActionStatus.FAILED, message=f"Git remote operation failed: {str(e)}")
            
        duration = round(time.time() - start_time, 2)
        final_exit_code = proc.returncode if not timed_out and proc is not None else -1
        success = final_exit_code == 0
        
        scrubbed_stderr = "Git command failed. Error output sanitized." if not success else ""
        
        data = {
            "operation": operation,
            "success": success,
            "exit_code": final_exit_code,
            "duration": duration,
            "timed_out": timed_out,
            "output_truncated": output_truncated,
            "stdout": "[REDACTED BY INTEGRATION]",
            "stderr": scrubbed_stderr
        }
        
        if operation == "git_remote_add": data["remote_name"] = request.arguments.get("name")
        elif operation == "git_remote_remove": data["remote_name"] = request.arguments.get("name")
        elif operation == "git_remote_rename":
            data["old_name"] = request.arguments.get("old_name")
            data["new_name"] = request.arguments.get("new_name")
        elif operation == "git_remote_set_url": data["remote_name"] = request.arguments.get("name")
        
        return ActionResult(
            action_id=request.action_id,
            integration=request.integration,
            action_type=request.action_type,
            status=ActionStatus.SUCCESS if success else ActionStatus.FAILED,
            message=f"Git remote operation {'succeeded' if success else 'failed'}",
            data=data
        )


    def _read_file(self, request: ActionRequest, target_path: Path) -> ActionResult:
        settings = get_settings()
        if not target_path.exists():
            return ActionResult(action_id=request.action_id, integration=request.integration, action_type=request.action_type, status=ActionStatus.FAILED, message="File not found")
        if target_path.is_dir():
            return ActionResult(action_id=request.action_id, integration=request.integration, action_type=request.action_type, status=ActionStatus.FAILED, message="Path is not a file")
            
        content = target_path.read_text(encoding="utf-8")
        if len(content) > settings.workspace_max_read_bytes:
            return ActionResult(action_id=request.action_id, integration=request.integration, action_type=request.action_type, status=ActionStatus.FAILED, message="File is too large to read securely")
            
        return ActionResult(
            action_id=request.action_id,
            integration=request.integration,
            action_type=request.action_type,
            status=ActionStatus.SUCCESS,
            message="File read successfully",
            data={"content": content, "size": len(content), "operation": "read_file"}
        )

    def _write_file(self, request: ActionRequest, target_path: Path, content: str) -> ActionResult:
        target_path.parent.mkdir(parents=True, exist_ok=True)
        target_path.write_text(content, encoding="utf-8")
        return ActionResult(
            action_id=request.action_id,
            integration=request.integration,
            action_type=request.action_type,
            status=ActionStatus.SUCCESS,
            message="File written successfully",
            data={"operation": "write", "filepath": str(target_path)}
        )

    def _edit_file(self, request: ActionRequest, target_path: Path, expected_content: str, replacement: str) -> ActionResult:
        if not target_path.exists():
            return ActionResult(action_id=request.action_id, integration=request.integration, action_type=request.action_type, status=ActionStatus.FAILED, message="File not found")
        content = target_path.read_text(encoding="utf-8")
        
        if expected_content not in content:
            return ActionResult(action_id=request.action_id, integration=request.integration, action_type=request.action_type, status=ActionStatus.FAILED, message="Expected content not found in file")
            
        if content.count(expected_content) > 1:
            return ActionResult(action_id=request.action_id, integration=request.integration, action_type=request.action_type, status=ActionStatus.FAILED, message="Multiple matches found for expected content")
            
        new_content = content.replace(expected_content, replacement)
        target_path.write_text(new_content, encoding="utf-8")
        return ActionResult(
            action_id=request.action_id,
            integration=request.integration,
            action_type=request.action_type,
            status=ActionStatus.SUCCESS,
            message="File edited successfully",
            data={"operation": "edit", "filepath": str(target_path)}
        )

    def _patch_file(self, request: ActionRequest, target_path: Path, patch_content: str) -> ActionResult:
        import subprocess
        if not target_path.exists():
            return ActionResult(action_id=request.action_id, integration=request.integration, action_type=request.action_type, status=ActionStatus.FAILED, message="File not found")
            
        if not patch_content.strip().startswith("---"):
            return ActionResult(action_id=request.action_id, integration=request.integration, action_type=request.action_type, status=ActionStatus.FAILED, message="Patch is malformed")
        p = subprocess.run(["git", "apply"], input=patch_content, text=True, cwd=str(self._get_workspace_root()), capture_output=True)
        if p.returncode != 0:
            return ActionResult(action_id=request.action_id, integration=request.integration, action_type=request.action_type, status=ActionStatus.FAILED, message=f"Patch is malformed or cannot apply: {p.stderr}")
            
        return ActionResult(
            action_id=request.action_id,
            integration=request.integration,
            action_type=request.action_type,
            status=ActionStatus.SUCCESS,
            message="Patch applied successfully",
            data={"operation": "patch", "filepath": str(target_path)}
        )

    def _execute_command(self, request: ActionRequest, cmd: str, args: list[str]) -> ActionResult:
        import subprocess, time, sys
        settings = get_settings()
        start = time.time()
        
        try:
            if cmd == "pytest":
                cmd = sys.executable
                args = ["-m", "pytest"] + args
            p = subprocess.run([cmd] + args, cwd=str(self._get_workspace_root()), capture_output=True, text=True, timeout=settings.workspace_execution_timeout_seconds)
            out = p.stdout
            err = p.stderr
            truncated = False
            if len(out) > settings.workspace_execution_max_output_bytes:
                out = out[:settings.workspace_execution_max_output_bytes] + "\n...[TRUNCATED]"
                truncated = True
            if len(err) > settings.workspace_execution_max_output_bytes:
                err = err[:settings.workspace_execution_max_output_bytes] + "\n...[TRUNCATED]"
                truncated = True
                
            return ActionResult(
                action_id=request.action_id,
                integration=request.integration,
                action_type=request.action_type,
                status=ActionStatus.SUCCESS if p.returncode == 0 else ActionStatus.FAILED,
                message="Execution successful" if p.returncode == 0 else "Execution failed",
                data={
                    "operation": "execute",
                    "success": p.returncode == 0,
                    "exit_code": p.returncode,
                    "stdout": out,
                    "stderr": err,
                    "duration": round(time.time() - start, 2),
                    "timed_out": False,
                    "output_truncated": truncated
                }
            )
        except subprocess.TimeoutExpired as e:
            return ActionResult(
                action_id=request.action_id,
                integration=request.integration,
                action_type=request.action_type,
                status=ActionStatus.SUCCESS,
                message="Execution timed out",
                data={"operation": "execute", "success": False, "timed_out": True, "exit_code": -1, "stdout": "", "stderr": "", "output_truncated": False}
            )

    def _execute_git_read(self, request: ActionRequest, git_cmd: str, args: list[str]) -> ActionResult:
        import subprocess
        import sys
        import time
        import os
        
        settings = get_settings()
        timeout = settings.workspace_execution_timeout_seconds
        max_bytes = settings.workspace_execution_max_output_bytes
        
        allowed_cmds = {
            "status": ["status", "--short", "--branch"],
            "branch": ["branch", "--show-current"],
            "log": ["log", "-n"],
            "rev-parse": ["rev-parse", "--is-inside-work-tree"],
            "diff": ["diff"],
            "check-ignore": ["check-ignore", "--quiet"]
        }
        
        if git_cmd not in allowed_cmds:
            return ActionResult(
                action_id=request.action_id,
                integration=request.integration,
                action_type=request.action_type,
                status=ActionStatus.FAILED,
                message=f"Unsupported git command '{git_cmd}'"
            )
            
        cmd = ["git", git_cmd] + args
        env = os.environ.copy()
        
        start_time = time.time()
        timed_out = False
        output_truncated = False
        proc = None
        
        try:
            if sys.platform == "win32":
                proc = subprocess.Popen(
                    cmd,
                    cwd=self._get_workspace_root(),
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    shell=False,
                    env=env,
                    text=True,
                    creationflags=subprocess.CREATE_NEW_PROCESS_GROUP
                )
            else:
                proc = subprocess.Popen(
                    cmd,
                    cwd=self._get_workspace_root(),
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    shell=False,
                    env=env,
                    text=True,
                    preexec_fn=os.setsid
                )
                
            stdout, stderr = proc.communicate(timeout=timeout)
            
        except subprocess.TimeoutExpired as e:
            timed_out = True
            if proc:
                try:
                    if sys.platform == "win32":
                        subprocess.run(['taskkill', '/F', '/T', '/PID', str(proc.pid)], capture_output=True)
                    else:
                        import signal
                        os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
                except Exception:
                    proc.kill()
                    
                stdout = e.stdout.decode() if isinstance(e.stdout, bytes) else (e.stdout or "")
                stderr = e.stderr.decode() if isinstance(e.stderr, bytes) else (e.stderr or "")
                proc.wait()
        except FileNotFoundError:
            return ActionResult(
                action_id=request.action_id,
                integration=request.integration,
                action_type=request.action_type,
                status=ActionStatus.FAILED,
                message="Git executable not found."
            )
        except Exception as e:
            return ActionResult(
                action_id=request.action_id,
                integration=request.integration,
                action_type=request.action_type,
                status=ActionStatus.FAILED,
                message=f"Git execution failed: {str(e)}"
            )
            
        duration = round(time.time() - start_time, 2)
        
        if stdout and len(stdout) > max_bytes:
            stdout = stdout[:max_bytes] + "\\n...[TRUNCATED]"
            output_truncated = True
        if stderr and len(stderr) > max_bytes:
            stderr = stderr[:max_bytes] + "\\n...[TRUNCATED]"
            output_truncated = True
            
        final_exit_code = proc.returncode if not timed_out and proc is not None else -1
            
        return ActionResult(
            action_id=request.action_id,
            integration=request.integration,
            action_type=request.action_type,
            status=ActionStatus.SUCCESS,
            message="Git command completed",
            data={
                "git_command": git_cmd,
                "success": final_exit_code == 0,
                "exit_code": final_exit_code,
                "stdout": stdout or "",
                "stderr": stderr or "",
                "duration": duration,
                "timed_out": timed_out,
                "output_truncated": output_truncated
            }
        )


    def _execute_git_commit(self, request: ActionRequest, message: str) -> ActionResult:
        import subprocess
        import sys
        import time
        import os
        
        settings = get_settings()
        timeout = settings.workspace_execution_timeout_seconds
        max_bytes = settings.workspace_execution_max_output_bytes
        env = os.environ.copy()
        root = self._get_workspace_root()
        
        # 1. Check if there are staged changes
        try:
            check_proc = subprocess.run(
                ["git", "diff", "--cached", "--quiet"],
                cwd=root,
                env=env,
                shell=False
            )
            if check_proc.returncode == 0:
                # 0 means no differences (i.e., no staged changes)
                return ActionResult(
                    action_id=request.action_id,
                    integration=request.integration,
                    action_type=request.action_type,
                    status=ActionStatus.FAILED,
                    message="NO_STAGED_CHANGES"
                )
        except FileNotFoundError:
            return ActionResult(
                action_id=request.action_id,
                integration=request.integration,
                action_type=request.action_type,
                status=ActionStatus.FAILED,
                message="Git executable not found."
            )
            
        # 2. Execute commit
        cmd = ["git", "commit", "-m", message]
        
        start_time = time.time()
        timed_out = False
        output_truncated = False
        proc = None
        
        try:
            if sys.platform == "win32":
                proc = subprocess.Popen(
                    cmd,
                    cwd=root,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    shell=False,
                    env=env,
                    text=True,
                    creationflags=subprocess.CREATE_NEW_PROCESS_GROUP
                )
            else:
                proc = subprocess.Popen(
                    cmd,
                    cwd=root,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    shell=False,
                    env=env,
                    text=True,
                    preexec_fn=os.setsid
                )
                
            stdout, stderr = proc.communicate(timeout=timeout)
            
        except subprocess.TimeoutExpired as e:
            timed_out = True
            if proc:
                try:
                    if sys.platform == "win32":
                        subprocess.run(['taskkill', '/F', '/T', '/PID', str(proc.pid)], capture_output=True)
                    else:
                        import signal
                        os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
                except Exception:
                    proc.kill()
                    
                stdout = e.stdout.decode() if isinstance(e.stdout, bytes) else (e.stdout or "")
                stderr = e.stderr.decode() if isinstance(e.stderr, bytes) else (e.stderr or "")
                proc.wait()
        except Exception as e:
            return ActionResult(
                action_id=request.action_id,
                integration=request.integration,
                action_type=request.action_type,
                status=ActionStatus.FAILED,
                message=f"Git commit execution failed: {str(e)}"
            )
            
        duration = round(time.time() - start_time, 2)
        
        if stdout and len(stdout) > max_bytes:
            stdout = stdout[:max_bytes] + "\\n...[TRUNCATED]"
            output_truncated = True
        if stderr and len(stderr) > max_bytes:
            stderr = stderr[:max_bytes] + "\\n...[TRUNCATED]"
            output_truncated = True
            
        final_exit_code = proc.returncode if not timed_out and proc is not None else -1
        success = final_exit_code == 0
        
        return ActionResult(
            action_id=request.action_id,
            integration=request.integration,
            action_type=request.action_type,
            status=ActionStatus.SUCCESS if success else ActionStatus.FAILED,
            message="Git commit successful" if success else "Git commit failed",
            data={
                "operation": "git_commit",
                "success": success,
                "exit_code": final_exit_code,
                "stdout": stdout or "",
                "stderr": stderr or "",
                "duration": duration,
                "timed_out": timed_out,
                "output_truncated": output_truncated
            }
        )



    def _execute_git_create_branch(self, request: ActionRequest, branch_name: str) -> ActionResult:
        import subprocess
        import sys
        import time
        import os
        
        settings = get_settings()
        timeout = settings.workspace_execution_timeout_seconds
        max_bytes = settings.workspace_execution_max_output_bytes
        env = os.environ.copy()
        root = self._get_workspace_root()
        
        # 1. Validate branch name using Git's own ref formatting check
        try:
            check_proc = subprocess.run(
                ["git", "check-ref-format", "--branch", branch_name],
                cwd=root,
                env=env,
                shell=False,
                capture_output=True,
                text=True
            )
            if check_proc.returncode != 0:
                return ActionResult(
                    action_id=request.action_id,
                    integration=request.integration,
                    action_type=request.action_type,
                    status=ActionStatus.VALIDATION_ERROR,
                    message=f"Invalid Git branch name: {check_proc.stderr.strip()}"
                )
        except FileNotFoundError:
            return ActionResult(
                action_id=request.action_id,
                integration=request.integration,
                action_type=request.action_type,
                status=ActionStatus.FAILED,
                message="Git executable not found."
            )
            
        # 2. Check if branch already exists
        try:
            exist_proc = subprocess.run(
                ["git", "show-ref", "--verify", "--quiet", f"refs/heads/{branch_name}"],
                cwd=root,
                env=env,
                shell=False
            )
            if exist_proc.returncode == 0:
                return ActionResult(
                    action_id=request.action_id,
                    integration=request.integration,
                    action_type=request.action_type,
                    status=ActionStatus.FAILED,
                    message="BRANCH_ALREADY_EXISTS"
                )
        except Exception as e:
            return ActionResult(
                action_id=request.action_id,
                integration=request.integration,
                action_type=request.action_type,
                status=ActionStatus.FAILED,
                message=f"Failed to check branch existence: {str(e)}"
            )
            
        # 3. Create branch (DO NOT CHECKOUT)
        cmd = ["git", "branch", branch_name]
        
        start_time = time.time()
        timed_out = False
        output_truncated = False
        proc = None
        
        try:
            if sys.platform == "win32":
                proc = subprocess.Popen(
                    cmd,
                    cwd=root,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    shell=False,
                    env=env,
                    text=True,
                    creationflags=subprocess.CREATE_NEW_PROCESS_GROUP
                )
            else:
                proc = subprocess.Popen(
                    cmd,
                    cwd=root,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    shell=False,
                    env=env,
                    text=True,
                    preexec_fn=os.setsid
                )
                
            stdout, stderr = proc.communicate(timeout=timeout)
            
        except subprocess.TimeoutExpired as e:
            timed_out = True
            if proc:
                try:
                    if sys.platform == "win32":
                        subprocess.run(['taskkill', '/F', '/T', '/PID', str(proc.pid)], capture_output=True)
                    else:
                        import signal
                        os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
                except Exception:
                    proc.kill()
                    
                stdout = e.stdout.decode() if isinstance(e.stdout, bytes) else (e.stdout or "")
                stderr = e.stderr.decode() if isinstance(e.stderr, bytes) else (e.stderr or "")
                proc.wait()
        except Exception as e:
            return ActionResult(
                action_id=request.action_id,
                integration=request.integration,
                action_type=request.action_type,
                status=ActionStatus.FAILED,
                message=f"Git branch creation failed: {str(e)}"
            )
            
        duration = round(time.time() - start_time, 2)
        
        if stdout and len(stdout) > max_bytes:
            stdout = stdout[:max_bytes] + "\\n...[TRUNCATED]"
            output_truncated = True
        if stderr and len(stderr) > max_bytes:
            stderr = stderr[:max_bytes] + "\\n...[TRUNCATED]"
            output_truncated = True
            
        final_exit_code = proc.returncode if not timed_out and proc is not None else -1
        success = final_exit_code == 0
        
        return ActionResult(
            action_id=request.action_id,
            integration=request.integration,
            action_type=request.action_type,
            status=ActionStatus.SUCCESS if success else ActionStatus.FAILED,
            message=f"Created branch {branch_name}" if success else "Git branch creation failed",
            data={
                "operation": "git_create_branch",
                "success": success,
                "exit_code": final_exit_code,
                "stdout": stdout or "",
                "stderr": stderr or "",
                "duration": duration,
                "timed_out": timed_out,
                "output_truncated": output_truncated
            }
        )


    def _execute_git_delete_branch(self, request: ActionRequest, branch_name: str) -> ActionResult:
        import subprocess
        import sys
        import time
        import os
        
        settings = get_settings()
        timeout = settings.workspace_execution_timeout_seconds
        max_bytes = settings.workspace_execution_max_output_bytes
        env = os.environ.copy()
        root = self._get_workspace_root()
        
        # Preconditions
        # 1. Target exists locally?
        try:
            exist_proc = subprocess.run(["git", "show-ref", "--verify", "--quiet", f"refs/heads/{branch_name}"], cwd=root, env=env, shell=False)
            if exist_proc.returncode != 0:
                return ActionResult(action_id=request.action_id, integration=request.integration, action_type=request.action_type, status=ActionStatus.FAILED, message="BRANCH_NOT_FOUND")
        except Exception as e:
            return ActionResult(action_id=request.action_id, integration=request.integration, action_type=request.action_type, status=ActionStatus.FAILED, message=f"Failed to check branch existence: {str(e)}")
            
        # 2. Is current branch?
        try:
            curr_proc = subprocess.run(["git", "branch", "--show-current"], cwd=root, env=env, shell=False, capture_output=True, text=True)
            if curr_proc.stdout.strip() == branch_name:
                return ActionResult(action_id=request.action_id, integration=request.integration, action_type=request.action_type, status=ActionStatus.FAILED, message="CANNOT_DELETE_CURRENT_BRANCH")
        except Exception as e:
            pass
            
        cmd = ["git", "branch", "-d", branch_name]
        
        start_time = time.time()
        timed_out = False
        output_truncated = False
        proc = None
        
        try:
            if sys.platform == "win32":
                proc = subprocess.Popen(cmd, cwd=root, stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=False, env=env, text=True, creationflags=subprocess.CREATE_NEW_PROCESS_GROUP)
            else:
                proc = subprocess.Popen(cmd, cwd=root, stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=False, env=env, text=True, preexec_fn=os.setsid)
            stdout, stderr = proc.communicate(timeout=timeout)
        except subprocess.TimeoutExpired as e:
            timed_out = True
            if proc:
                try:
                    if sys.platform == "win32": subprocess.run(['taskkill', '/F', '/T', '/PID', str(proc.pid)], capture_output=True)
                    else:
                        import signal; os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
                except Exception: proc.kill()
                stdout = e.stdout.decode() if isinstance(e.stdout, bytes) else (e.stdout or "")
                stderr = e.stderr.decode() if isinstance(e.stderr, bytes) else (e.stderr or "")
                proc.wait()
        except Exception as e:
            return ActionResult(action_id=request.action_id, integration=request.integration, action_type=request.action_type, status=ActionStatus.FAILED, message=f"Git branch deletion failed: {str(e)}")
            
        duration = round(time.time() - start_time, 2)
        
        if stdout and len(stdout) > max_bytes:
            stdout = stdout[:max_bytes] + "\\n...[TRUNCATED]"
            output_truncated = True
        if stderr and len(stderr) > max_bytes:
            stderr = stderr[:max_bytes] + "\\n...[TRUNCATED]"
            output_truncated = True
            
        final_exit_code = proc.returncode if not timed_out and proc is not None else -1
        success = final_exit_code == 0
        
        # Check for unmerged error
        message = f"Deleted branch {branch_name}" if success else "Git branch deletion failed"
        if not success and "not fully merged" in stderr.lower():
            message = "BRANCH_NOT_FULLY_MERGED"
            
        return ActionResult(
            action_id=request.action_id,
            integration=request.integration,
            action_type=request.action_type,
            status=ActionStatus.SUCCESS if success else ActionStatus.FAILED,
            message=message,
            data={"operation": "git_delete_branch", "success": success, "exit_code": final_exit_code, "stdout": stdout or "", "stderr": stderr or "", "duration": duration, "timed_out": timed_out, "output_truncated": output_truncated}
        )


    def _execute_git_stage_files(self, request: ActionRequest, paths: list[str]) -> ActionResult:
        import subprocess
        import sys
        import time
        import os
        
        settings = get_settings()
        timeout = settings.workspace_execution_timeout_seconds
        max_bytes = settings.workspace_execution_max_output_bytes
        env = os.environ.copy()
        root = self._get_workspace_root()
        
        # Verify it's a Git repo
        try:
            repo_proc = subprocess.run(["git", "rev-parse", "--is-inside-work-tree"], cwd=root, env=env, shell=False, capture_output=True, text=True)
            if repo_proc.returncode != 0:
                return ActionResult(action_id=request.action_id, integration=request.integration, action_type=request.action_type, status=ActionStatus.FAILED, message="NOT_A_GIT_REPOSITORY")
        except Exception:
            return ActionResult(action_id=request.action_id, integration=request.integration, action_type=request.action_type, status=ActionStatus.FAILED, message="NOT_A_GIT_REPOSITORY")
            
        validated_paths = []
        for p in paths:
            is_safe, resolved_path, err = self._safe_resolve(p)
            if not is_safe:
                return ActionResult(action_id=request.action_id, integration=request.integration, action_type=request.action_type, status=ActionStatus.FAILED, message=f"Unsafe path: {p}")
            if not resolved_path.exists():
                return ActionResult(action_id=request.action_id, integration=request.integration, action_type=request.action_type, status=ActionStatus.FAILED, message="FILE_NOT_FOUND")
            if resolved_path.is_dir():
                return ActionResult(action_id=request.action_id, integration=request.integration, action_type=request.action_type, status=ActionStatus.FAILED, message="DIRECTORY_NOT_ALLOWED")
            
            # Check ignore
            ign_proc = subprocess.run(["git", "check-ignore", "--quiet", "--", p], cwd=root, env=env, shell=False)
            if ign_proc.returncode == 0:
                return ActionResult(action_id=request.action_id, integration=request.integration, action_type=request.action_type, status=ActionStatus.FAILED, message="IGNORED_FILE")
            
            validated_paths.append(p)
            
        cmd = ["git", "add", "--"] + validated_paths
        
        start_time = time.time()
        timed_out = False
        output_truncated = False
        proc = None
        
        try:
            if sys.platform == "win32":
                proc = subprocess.Popen(cmd, cwd=root, stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=False, env=env, text=True, creationflags=subprocess.CREATE_NEW_PROCESS_GROUP)
            else:
                proc = subprocess.Popen(cmd, cwd=root, stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=False, env=env, text=True, preexec_fn=os.setsid)
            stdout, stderr = proc.communicate(timeout=timeout)
        except subprocess.TimeoutExpired as e:
            timed_out = True
            if proc:
                try:
                    if sys.platform == "win32": subprocess.run(['taskkill', '/F', '/T', '/PID', str(proc.pid)], capture_output=True)
                    else:
                        import signal; os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
                except Exception: proc.kill()
                stdout = e.stdout.decode() if isinstance(e.stdout, bytes) else (e.stdout or "")
                stderr = e.stderr.decode() if isinstance(e.stderr, bytes) else (e.stderr or "")
                proc.wait()
        except Exception as e:
            return ActionResult(action_id=request.action_id, integration=request.integration, action_type=request.action_type, status=ActionStatus.FAILED, message=f"Git staging failed: {str(e)}")
            
        duration = round(time.time() - start_time, 2)
        
        if stdout and len(stdout) > max_bytes:
            stdout = stdout[:max_bytes] + "\\n...[TRUNCATED]"
            output_truncated = True
        if stderr and len(stderr) > max_bytes:
            stderr = stderr[:max_bytes] + "\\n...[TRUNCATED]"
            output_truncated = True
            
        final_exit_code = proc.returncode if not timed_out and proc is not None else -1
        success = final_exit_code == 0
        
        return ActionResult(
            action_id=request.action_id,
            integration=request.integration,
            action_type=request.action_type,
            status=ActionStatus.SUCCESS if success else ActionStatus.FAILED,
            message=f"Staged {len(paths)} files" if success else "Git staging failed",
            data={"operation": "git_stage_files", "success": success, "exit_code": final_exit_code, "stdout": stdout or "", "stderr": stderr or "", "duration": duration, "timed_out": timed_out, "output_truncated": output_truncated}
        )


    def _execute_git_switch_branch(self, request: ActionRequest, branch_name: str) -> ActionResult:
        import subprocess
        import sys
        import time
        import os
        
        settings = get_settings()
        timeout = settings.workspace_execution_timeout_seconds
        max_bytes = settings.workspace_execution_max_output_bytes
        env = os.environ.copy()
        root = self._get_workspace_root()
        
        # TOCTOU checks / Precondition checks
        
        # 1. Check if Git is available
        try:
            # Check current branch
            curr_proc = subprocess.run(
                ["git", "branch", "--show-current"],
                cwd=root,
                env=env,
                shell=False,
                capture_output=True,
                text=True
            )
        except FileNotFoundError:
            return ActionResult(
                action_id=request.action_id,
                integration=request.integration,
                action_type=request.action_type,
                status=ActionStatus.FAILED,
                message="Git executable not found."
            )
            
        current_branch = curr_proc.stdout.strip()
        if current_branch == branch_name:
            return ActionResult(
                action_id=request.action_id,
                integration=request.integration,
                action_type=request.action_type,
                status=ActionStatus.FAILED,
                message="ALREADY_ON_BRANCH"
            )
            
        # 2. Check if target branch exists locally
        try:
            exist_proc = subprocess.run(
                ["git", "show-ref", "--verify", "--quiet", f"refs/heads/{branch_name}"],
                cwd=root,
                env=env,
                shell=False
            )
            if exist_proc.returncode != 0:
                return ActionResult(
                    action_id=request.action_id,
                    integration=request.integration,
                    action_type=request.action_type,
                    status=ActionStatus.FAILED,
                    message="BRANCH_NOT_FOUND"
                )
        except Exception as e:
            return ActionResult(
                action_id=request.action_id,
                integration=request.integration,
                action_type=request.action_type,
                status=ActionStatus.FAILED,
                message=f"Failed to check branch existence: {str(e)}"
            )
            
        # 3. Check for dirty working tree
        try:
            status_proc = subprocess.run(
                ["git", "status", "--porcelain"],
                cwd=root,
                env=env,
                shell=False,
                capture_output=True,
                text=True
            )
            if status_proc.stdout.strip():
                return ActionResult(
                    action_id=request.action_id,
                    integration=request.integration,
                    action_type=request.action_type,
                    status=ActionStatus.FAILED,
                    message="DIRTY_WORKTREE_REQUIRES_REVIEW"
                )
        except Exception as e:
            return ActionResult(
                action_id=request.action_id,
                integration=request.integration,
                action_type=request.action_type,
                status=ActionStatus.FAILED,
                message=f"Failed to check working tree status: {str(e)}"
            )
            
        # 4. Execute Switch
        # Using git switch -- branch_name
        cmd = ["git", "switch", "--", branch_name]
        
        start_time = time.time()
        timed_out = False
        output_truncated = False
        proc = None
        
        try:
            if sys.platform == "win32":
                proc = subprocess.Popen(
                    cmd,
                    cwd=root,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    shell=False,
                    env=env,
                    text=True,
                    creationflags=subprocess.CREATE_NEW_PROCESS_GROUP
                )
            else:
                proc = subprocess.Popen(
                    cmd,
                    cwd=root,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    shell=False,
                    env=env,
                    text=True,
                    preexec_fn=os.setsid
                )
                
            stdout, stderr = proc.communicate(timeout=timeout)
            
        except subprocess.TimeoutExpired as e:
            timed_out = True
            if proc:
                try:
                    if sys.platform == "win32":
                        subprocess.run(['taskkill', '/F', '/T', '/PID', str(proc.pid)], capture_output=True)
                    else:
                        import signal
                        os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
                except Exception:
                    proc.kill()
                    
                stdout = e.stdout.decode() if isinstance(e.stdout, bytes) else (e.stdout or "")
                stderr = e.stderr.decode() if isinstance(e.stderr, bytes) else (e.stderr or "")
                proc.wait()
        except Exception as e:
            return ActionResult(
                action_id=request.action_id,
                integration=request.integration,
                action_type=request.action_type,
                status=ActionStatus.FAILED,
                message=f"Git switch failed: {str(e)}"
            )
            
        duration = round(time.time() - start_time, 2)
        
        if stdout and len(stdout) > max_bytes:
            stdout = stdout[:max_bytes] + "\\n...[TRUNCATED]"
            output_truncated = True
        if stderr and len(stderr) > max_bytes:
            stderr = stderr[:max_bytes] + "\\n...[TRUNCATED]"
            output_truncated = True
            
        final_exit_code = proc.returncode if not timed_out and proc is not None else -1
        success = final_exit_code == 0
        
        return ActionResult(
            action_id=request.action_id,
            integration=request.integration,
            action_type=request.action_type,
            status=ActionStatus.SUCCESS if success else ActionStatus.FAILED,
            message=f"Switched to branch {branch_name}" if success else "Git switch failed",
            data={
                "operation": "git_switch_branch",
                "success": success,
                "exit_code": final_exit_code,
                "stdout": stdout or "",
                "stderr": stderr or "",
                "duration": duration,
                "timed_out": timed_out,
                "output_truncated": output_truncated
            }
        )


    def _execute_git_unstage_files(self, request: ActionRequest, paths: list[str]) -> ActionResult:
        import subprocess
        import sys
        import time
        import os
        
        settings = get_settings()
        timeout = settings.workspace_execution_timeout_seconds
        max_bytes = settings.workspace_execution_max_output_bytes
        env = os.environ.copy()
        root = self._get_workspace_root()
        
        # Verify it's a Git repo
        try:
            repo_proc = subprocess.run(["git", "rev-parse", "--is-inside-work-tree"], cwd=root, env=env, shell=False, capture_output=True, text=True)
            if repo_proc.returncode != 0:
                return ActionResult(action_id=request.action_id, integration=request.integration, action_type=request.action_type, status=ActionStatus.FAILED, message="NOT_A_GIT_REPOSITORY")
        except Exception:
            return ActionResult(action_id=request.action_id, integration=request.integration, action_type=request.action_type, status=ActionStatus.FAILED, message="NOT_A_GIT_REPOSITORY")
            
        validated_paths = []
        for p in paths:
            is_safe, resolved_path, err = self._safe_resolve(p)
            if not is_safe:
                return ActionResult(action_id=request.action_id, integration=request.integration, action_type=request.action_type, status=ActionStatus.FAILED, message=f"Unsafe path: {p}")
            
            # For unstaging, the file might not exist in the working tree if it's a staged deletion.
            # We can check if it exists in the index or working tree.
            # But we must reject directories.
            if resolved_path.exists() and resolved_path.is_dir():
                return ActionResult(action_id=request.action_id, integration=request.integration, action_type=request.action_type, status=ActionStatus.FAILED, message="DIRECTORY_NOT_ALLOWED")
            
            # We can use git status to check if it's staged.
            st_proc = subprocess.run(["git", "status", "--porcelain", "--", p], cwd=root, env=env, shell=False, capture_output=True, text=True)
            out = st_proc.stdout
            if not out:
                # Completely clean or doesn't exist
                if not resolved_path.exists():
                    return ActionResult(action_id=request.action_id, integration=request.integration, action_type=request.action_type, status=ActionStatus.FAILED, message="FILE_NOT_FOUND")
                return ActionResult(action_id=request.action_id, integration=request.integration, action_type=request.action_type, status=ActionStatus.FAILED, message="NOT_STAGED")
            else:
                xy = out[:2]
                if xy[0] not in ("M", "A", "D", "R", "C"):
                    return ActionResult(action_id=request.action_id, integration=request.integration, action_type=request.action_type, status=ActionStatus.FAILED, message="NOT_STAGED")
            
            validated_paths.append(p)
            
        cmd = ["git", "restore", "--staged", "--"] + validated_paths
        
        start_time = time.time()
        timed_out = False
        output_truncated = False
        proc = None
        
        try:
            if sys.platform == "win32":
                proc = subprocess.Popen(cmd, cwd=root, stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=False, env=env, text=True, creationflags=subprocess.CREATE_NEW_PROCESS_GROUP)
            else:
                proc = subprocess.Popen(cmd, cwd=root, stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=False, env=env, text=True, preexec_fn=os.setsid)
            stdout, stderr = proc.communicate(timeout=timeout)
        except subprocess.TimeoutExpired as e:
            timed_out = True
            if proc:
                try:
                    if sys.platform == "win32": subprocess.run(['taskkill', '/F', '/T', '/PID', str(proc.pid)], capture_output=True)
                    else:
                        import signal; os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
                except Exception: proc.kill()
                stdout = e.stdout.decode() if isinstance(e.stdout, bytes) else (e.stdout or "")
                stderr = e.stderr.decode() if isinstance(e.stderr, bytes) else (e.stderr or "")
                proc.wait()
        except Exception as e:
            return ActionResult(action_id=request.action_id, integration=request.integration, action_type=request.action_type, status=ActionStatus.FAILED, message=f"Git unstaging failed: {str(e)}")
            
        duration = round(time.time() - start_time, 2)
        
        if stdout and len(stdout) > max_bytes:
            stdout = stdout[:max_bytes] + "\\n...[TRUNCATED]"
            output_truncated = True
        if stderr and len(stderr) > max_bytes:
            stderr = stderr[:max_bytes] + "\\n...[TRUNCATED]"
            output_truncated = True
            
        final_exit_code = proc.returncode if not timed_out and proc is not None else -1
        success = final_exit_code == 0
        
        return ActionResult(
            action_id=request.action_id,
            integration=request.integration,
            action_type=request.action_type,
            status=ActionStatus.SUCCESS if success else ActionStatus.FAILED,
            message=f"Unstaged {len(paths)} files" if success else "Git unstaging failed",
            data={"operation": "git_unstage_files", "success": success, "exit_code": final_exit_code, "stdout": stdout or "", "stderr": stderr or "", "duration": duration, "timed_out": timed_out, "output_truncated": output_truncated}
        )



    def _execute_git_fetch(self, request: ActionRequest) -> ActionResult:
        import subprocess
        import os
        from app.tools.local_git_tools import _sanitize_remote_url, _validate_remote_name
        
        settings = get_settings()
        timeout = settings.workspace_execution_timeout_seconds
        max_bytes = settings.workspace_execution_max_output_bytes
        root = self._get_workspace_root()
        env = os.environ.copy()
        
        remote_name = request.arguments.get("remote_name")
        pinned_url = request.arguments.get("pinned_url")
        
        if not _validate_remote_name(remote_name):
            return ActionResult(action_id=request.action_id, integration=request.integration, action_type=request.action_type, status=ActionStatus.FAILED, message="INVALID_REMOTE_NAME")
            
        try:
            repo_proc = subprocess.run(["git", "rev-parse", "--is-inside-work-tree"], cwd=root, env=env, shell=False, capture_output=True, text=True)
            if repo_proc.returncode != 0:
                return ActionResult(action_id=request.action_id, integration=request.integration, action_type=request.action_type, status=ActionStatus.FAILED, message="NOT_A_GIT_REPOSITORY")
        except Exception:
            return ActionResult(action_id=request.action_id, integration=request.integration, action_type=request.action_type, status=ActionStatus.FAILED, message="NOT_A_GIT_REPOSITORY")
            
        remotes_proc = subprocess.run(["git", "remote"], cwd=root, env=env, shell=False, capture_output=True, text=True)
        if remote_name not in remotes_proc.stdout.splitlines():
            return ActionResult(action_id=request.action_id, integration=request.integration, action_type=request.action_type, status=ActionStatus.FAILED, message="REMOTE_NOT_FOUND")
            
        url_proc = subprocess.run(["git", "remote", "get-url", remote_name], cwd=root, env=env, shell=False, capture_output=True, text=True)
        if url_proc.returncode != 0:
            return ActionResult(action_id=request.action_id, integration=request.integration, action_type=request.action_type, status=ActionStatus.FAILED, message="REMOTE_NOT_FOUND")
            
        current_url = url_proc.stdout.strip()
        if current_url != pinned_url:
            return ActionResult(action_id=request.action_id, integration=request.integration, action_type=request.action_type, status=ActionStatus.FAILED, message="REMOTE_CONFIGURATION_CHANGED")
            
        try:
            proc = subprocess.Popen(["git", "fetch", remote_name], cwd=root, env=env, shell=False, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            stdout, stderr = proc.communicate(timeout=timeout)
            
            output_truncated = False
            combined = stdout + (stderr if stderr else "")
            if len(combined) > max_bytes:
                combined = combined[:max_bytes] + "... (truncated)"
                output_truncated = True
                
            safe_output = _sanitize_remote_url(combined)
                
            if proc.returncode == 0:
                return ActionResult(
                    action_id=request.action_id, 
                    integration=request.integration, 
                    action_type=request.action_type, 
                    status=ActionStatus.SUCCESS, 
                    message="Fetch completed",
                    data={"network_operation": True, "output_truncated": output_truncated, "output": safe_output}
                )
            else:
                return ActionResult(
                    action_id=request.action_id, 
                    integration=request.integration, 
                    action_type=request.action_type, 
                    status=ActionStatus.FAILED, 
                    message=safe_output,
                    data={"network_operation": True, "output_truncated": output_truncated}
                )
                
        except subprocess.TimeoutExpired as e:
            proc.kill()
            proc.wait()
            return ActionResult(
                action_id=request.action_id, 
                integration=request.integration, 
                action_type=request.action_type, 
                status=ActionStatus.FAILED, 
                message="Fetch timed out",
                data={"network_operation": True, "timed_out": True}
            )
        except Exception as e:
            return ActionResult(
                action_id=request.action_id, 
                integration=request.integration, 
                action_type=request.action_type, 
                status=ActionStatus.FAILED, 
                message=f"Fetch failed: {_sanitize_remote_url(str(e))}",
                data={"network_operation": True}
            )

    def _execute_git_fetch_result_inspection(self, request: ActionRequest) -> ActionResult:
        import subprocess
        import os
        from app.tools.local_git_tools import _validate_remote_name
        
        settings = get_settings()
        root = self._get_workspace_root()
        env = os.environ.copy()
        
        remote_name = request.arguments.get("remote_name")
        
        if not _validate_remote_name(remote_name):
            return ActionResult(action_id=request.action_id, integration=request.integration, action_type=request.action_type, status=ActionStatus.FAILED, message="INVALID_REMOTE_NAME")
            
        try:
            repo_proc = subprocess.run(["git", "rev-parse", "--is-inside-work-tree"], cwd=root, env=env, shell=False, capture_output=True, text=True)
            if repo_proc.returncode != 0:
                return ActionResult(action_id=request.action_id, integration=request.integration, action_type=request.action_type, status=ActionStatus.FAILED, message="NOT_A_GIT_REPOSITORY")
        except Exception:
            return ActionResult(action_id=request.action_id, integration=request.integration, action_type=request.action_type, status=ActionStatus.FAILED, message="NOT_A_GIT_REPOSITORY")
            
        remotes_proc = subprocess.run(["git", "remote"], cwd=root, env=env, shell=False, capture_output=True, text=True)
        if remote_name not in remotes_proc.stdout.splitlines():
            return ActionResult(action_id=request.action_id, integration=request.integration, action_type=request.action_type, status=ActionStatus.FAILED, message="REMOTE_NOT_FOUND")

        curr_branch_proc = subprocess.run(["git", "branch", "--show-current"], cwd=root, env=env, shell=False, capture_output=True, text=True)
        current_branch = curr_branch_proc.stdout.strip() if curr_branch_proc.returncode == 0 else None
        if not current_branch:
            current_branch = None

        local_branches_proc = subprocess.run(["git", "for-each-ref", "--format=%(refname:short) %(upstream:short)", "refs/heads/"], cwd=root, env=env, shell=False, capture_output=True, text=True)
        
        remote_branches_proc = subprocess.run(["git", "for-each-ref", "--format=%(refname:short)", f"refs/remotes/{remote_name}/"], cwd=root, env=env, shell=False, capture_output=True, text=True)
        remote_tracking_branches = remote_branches_proc.stdout.splitlines()

        if not remote_tracking_branches:
            return ActionResult(action_id=request.action_id, integration=request.integration, action_type=request.action_type, status=ActionStatus.SUCCESS, message="NO_REMOTE_TRACKING_BRANCHES", data={"success": True, "remote_name": remote_name, "remote_tracking_branches": []})

        branch_comparisons = []
        newly_available_commits = []
        local_only_commits = []
        
        lines = local_branches_proc.stdout.splitlines()
        for line in lines:
            parts = line.strip().split()
            if len(parts) == 2:
                local = parts[0]
                upstream = parts[1]
                if upstream.startswith(f"{remote_name}/"):
                    rev_list_proc = subprocess.run(["git", "rev-list", "--left-right", "--count", f"{local}...{upstream}"], cwd=root, env=env, shell=False, capture_output=True, text=True)
                    
                    ahead = 0
                    behind = 0
                    diverged = False
                    state = "UNKNOWN"
                    
                    if rev_list_proc.returncode == 0:
                        counts = rev_list_proc.stdout.strip().split()
                        if len(counts) == 2:
                            ahead = int(counts[0])
                            behind = int(counts[1])
                            
                            if ahead == 0 and behind == 0:
                                state = "UP_TO_DATE"
                            elif ahead == 0 and behind > 0:
                                state = "BEHIND"
                            elif ahead > 0 and behind == 0:
                                state = "AHEAD"
                            elif ahead > 0 and behind > 0:
                                state = "DIVERGED"
                                diverged = True
                    
                    branch_comparisons.append({
                        "remote_branch": upstream,
                        "local_branch": local,
                        "ahead": ahead,
                        "behind": behind,
                        "diverged": diverged,
                        "state": state
                    })

                    if behind > 0:
                        log_proc = subprocess.run(["git", "log", "-n", "50", "--format=%H|%an|%aI|%s", f"{local}..{upstream}"], cwd=root, env=env, shell=False, capture_output=True, text=True)
                        for log_line in log_proc.stdout.splitlines():
                            if "|" in log_line:
                                try:
                                    h, a, t, s = log_line.split("|", 3)
                                    newly_available_commits.append({
                                        "branch": local,
                                        "commit_hash": h,
                                        "author_name": a,
                                        "timestamp": t,
                                        "subject": s
                                    })
                                except ValueError:
                                    pass

                    if ahead > 0:
                        log_proc = subprocess.run(["git", "log", "-n", "50", "--format=%H|%an|%aI|%s", f"{upstream}..{local}"], cwd=root, env=env, shell=False, capture_output=True, text=True)
                        for log_line in log_proc.stdout.splitlines():
                            if "|" in log_line:
                                try:
                                    h, a, t, s = log_line.split("|", 3)
                                    local_only_commits.append({
                                        "branch": local,
                                        "commit_hash": h,
                                        "author_name": a,
                                        "timestamp": t,
                                        "subject": s
                                    })
                                except ValueError:
                                    pass

        result_data = {
            "success": True,
            "remote_name": remote_name,
            "current_branch": current_branch,
            "remote_tracking_branches": remote_tracking_branches,
            "branch_comparisons": branch_comparisons,
            "newly_available_commits": newly_available_commits,
            "local_only_commits": local_only_commits,
            "warnings": [],
            "sanitized_error": None
        }
        
        return ActionResult(action_id=request.action_id, integration=request.integration, action_type=request.action_type, status=ActionStatus.SUCCESS, message="Git fetch result inspected", data=result_data)

    def _execute_git_pull_proposal(self, request: ActionRequest) -> ActionResult:
        # We reuse the read-only inspection result to generate the proposal
        inspection_req = ActionRequest(
            integration=request.integration,
            action_type=request.action_type,
            session_id=request.session_id,
            arguments={"operation": "git_fetch_result_inspection", "remote_name": request.arguments.get("remote_name")}
        )
        inspection_res = self._execute_git_fetch_result_inspection(inspection_req)
        
        from app.services.git_pull_proposer import GitPullProposer
        proposer = GitPullProposer()
        
        # Determine what data to pass. If it failed, we pass minimal data.
        inspection_data = inspection_res.data if inspection_res.data else {"success": False, "message": inspection_res.message, "remote_name": request.arguments.get("remote_name")}
        proposal = proposer.propose(inspection_data)
        
        return ActionResult(
            action_id=request.action_id,
            integration=request.integration,
            action_type=request.action_type,
            status=ActionStatus.SUCCESS,
            message="Proposal generated",
            data=proposal.model_dump()
        )

    def _execute_git_pull_fast_forward(self, request: ActionRequest) -> ActionResult:
        import subprocess
        import os
        settings = get_settings()
        root = self._get_workspace_root()
        env = os.environ.copy()
        args = request.arguments
        
        expected_branch = args.get("current_branch")
        expected_head_sha = args.get("expected_head_sha")
        expected_upstream_sha = args.get("expected_upstream_sha")
        upstream_branch = args.get("upstream_branch")
        upstream_ref = args.get("upstream_ref")
        behind_count = args.get("behind")
        remote_name = args.get("remote_name")
        
        # 1. Re-verify TOCTOU
        repo_proc = subprocess.run(["git", "rev-parse", "--is-inside-work-tree"], cwd=root, env=env, shell=False, capture_output=True, text=True)
        if repo_proc.returncode != 0:
            return ActionResult(action_id=request.action_id, integration=request.integration, action_type=request.action_type, status=ActionStatus.FAILED, message="STALE_PULL_PROPOSAL: Not a repository")
            
        curr_branch_proc = subprocess.run(["git", "branch", "--show-current"], cwd=root, env=env, shell=False, capture_output=True, text=True)
        if curr_branch_proc.stdout.strip() != expected_branch:
            return ActionResult(action_id=request.action_id, integration=request.integration, action_type=request.action_type, status=ActionStatus.FAILED, message="STALE_PULL_PROPOSAL: Branch changed")
            
        head_check = subprocess.run(["git", "rev-parse", "HEAD"], cwd=root, env=env, shell=False, capture_output=True, text=True)
        if head_check.stdout.strip() != expected_head_sha:
            return ActionResult(action_id=request.action_id, integration=request.integration, action_type=request.action_type, status=ActionStatus.FAILED, message="STALE_PULL_PROPOSAL: HEAD changed")
            
        up_check = subprocess.run(["git", "rev-parse", "--verify", upstream_ref], cwd=root, env=env, shell=False, capture_output=True, text=True)
        if up_check.stdout.strip() != expected_upstream_sha:
            return ActionResult(action_id=request.action_id, integration=request.integration, action_type=request.action_type, status=ActionStatus.FAILED, message="STALE_PULL_PROPOSAL: Upstream SHA changed")
            
        status_proc = subprocess.run(["git", "status", "--porcelain", "--untracked-files=all"], cwd=root, env=env, shell=False, capture_output=True, text=True)
        if status_proc.stdout.strip() != "":
            return ActionResult(action_id=request.action_id, integration=request.integration, action_type=request.action_type, status=ActionStatus.FAILED, message="STALE_PULL_PROPOSAL: Dirty worktree")
            
        rev_list_proc = subprocess.run(["git", "rev-list", "--left-right", "--count", f"{expected_branch}...{upstream_branch}"], cwd=root, env=env, shell=False, capture_output=True, text=True)
        ahead = 0
        behind = 0
        if rev_list_proc.returncode == 0:
            counts = rev_list_proc.stdout.strip().split()
            if len(counts) == 2:
                ahead = int(counts[0])
                behind = int(counts[1])
        if ahead != 0 or behind <= 0:
            return ActionResult(action_id=request.action_id, integration=request.integration, action_type=request.action_type, status=ActionStatus.FAILED, message="STALE_PULL_PROPOSAL: State no longer BEHIND")
            
        # 2. Execute Fast-Forward Merge
        merge_proc = subprocess.run(["git", "merge", "--ff-only", upstream_ref], cwd=root, env=env, shell=False, capture_output=True, text=True)
        if merge_proc.returncode != 0:
            return ActionResult(action_id=request.action_id, integration=request.integration, action_type=request.action_type, status=ActionStatus.FAILED, message="FAILED_RECOVERY: Merge failed", data={"stderr": merge_proc.stderr})
            
        # 3. Postcondition Verification
        curr_branch_proc2 = subprocess.run(["git", "branch", "--show-current"], cwd=root, env=env, shell=False, capture_output=True, text=True)
        if curr_branch_proc2.stdout.strip() != expected_branch:
            return ActionResult(action_id=request.action_id, integration=request.integration, action_type=request.action_type, status=ActionStatus.FAILED, message="POSTCONDITION_FAILED: Branch changed unexpectedly")
            
        head_check2 = subprocess.run(["git", "rev-parse", "HEAD"], cwd=root, env=env, shell=False, capture_output=True, text=True)
        new_head = head_check2.stdout.strip()
        if new_head != expected_upstream_sha:
            return ActionResult(action_id=request.action_id, integration=request.integration, action_type=request.action_type, status=ActionStatus.FAILED, message="POSTCONDITION_FAILED: HEAD does not match upstream")
            
        status_proc2 = subprocess.run(["git", "status", "--porcelain", "--untracked-files=all"], cwd=root, env=env, shell=False, capture_output=True, text=True)
        if status_proc2.stdout.strip() != "":
            return ActionResult(action_id=request.action_id, integration=request.integration, action_type=request.action_type, status=ActionStatus.FAILED, message="POSTCONDITION_FAILED: Worktree dirtied unexpectedly")
            
        rev_list_proc2 = subprocess.run(["git", "rev-list", "--left-right", "--count", f"{expected_branch}...{upstream_branch}"], cwd=root, env=env, shell=False, capture_output=True, text=True)
        if rev_list_proc2.returncode == 0:
            counts = rev_list_proc2.stdout.strip().split()
            if len(counts) == 2 and (int(counts[0]) != 0 or int(counts[1]) != 0):
                return ActionResult(action_id=request.action_id, integration=request.integration, action_type=request.action_type, status=ActionStatus.FAILED, message="POSTCONDITION_FAILED: Not UP_TO_DATE")
                
        # Make sure no merge commit was created (it shouldn't be since --ff-only was passed)
        # But we can explicitly check that parent count of HEAD is 1 or 0
        parents_proc = subprocess.run(["git", "log", "-1", "--format=%P"], cwd=root, env=env, shell=False, capture_output=True, text=True)
        if len(parents_proc.stdout.strip().split()) > 1:
            return ActionResult(action_id=request.action_id, integration=request.integration, action_type=request.action_type, status=ActionStatus.FAILED, message="POSTCONDITION_FAILED: Merge commit was created")

        result_data = {
            "success": True,
            "operation": "git_pull_fast_forward",
            "branch": expected_branch,
            "upstream": upstream_branch,
            "old_head": expected_head_sha,
            "new_head": new_head,
            "commits_applied": behind_count,
            "relationship_before": "BEHIND",
            "relationship_after": "UP_TO_DATE",
            "network_used": False,
            "merge_commit_created": False,
            "working_tree_clean": True
        }
        
        return ActionResult(action_id=request.action_id, integration=request.integration, action_type=request.action_type, status=ActionStatus.SUCCESS, message="Successfully synchronized fast-forward", data=result_data)

    def _execute_git_pull_result_inspection(self, request: ActionRequest) -> ActionResult:
        import subprocess
        import os
        settings = get_settings()
        root = self._get_workspace_root()
        env = os.environ.copy()
        
        remote_name = request.arguments.get("remote_name")
        
        repo_proc = subprocess.run(["git", "rev-parse", "--is-inside-work-tree"], cwd=root, env=env, shell=False, capture_output=True, text=True)
        if repo_proc.returncode != 0:
            return ActionResult(action_id=request.action_id, integration=request.integration, action_type=request.action_type, status=ActionStatus.SUCCESS, message="INVALID_REPOSITORY", data={"success": False, "relationship": "INVALID_REPOSITORY"})
            
        curr_branch_proc = subprocess.run(["git", "branch", "--show-current"], cwd=root, env=env, shell=False, capture_output=True, text=True)
        current_branch = curr_branch_proc.stdout.strip()
        if not current_branch or curr_branch_proc.returncode != 0:
            return ActionResult(action_id=request.action_id, integration=request.integration, action_type=request.action_type, status=ActionStatus.SUCCESS, message="DETACHED_HEAD", data={"success": False, "relationship": "DETACHED_HEAD"})
            
        local_branches_proc = subprocess.run(["git", "for-each-ref", "--format=%(refname:short) %(upstream:short)", "refs/heads/"], cwd=root, env=env, shell=False, capture_output=True, text=True)
        upstream = None
        for line in local_branches_proc.stdout.splitlines():
            parts = line.strip().split()
            if len(parts) == 2 and parts[0] == current_branch:
                upstream = parts[1]
                break
                
        if not upstream or not upstream.startswith(f"{remote_name}/"):
            return ActionResult(action_id=request.action_id, integration=request.integration, action_type=request.action_type, status=ActionStatus.SUCCESS, message="NO_UPSTREAM", data={"success": False, "relationship": "NO_UPSTREAM"})
            
        upstream_ref = f"refs/remotes/{upstream}"
        up_check = subprocess.run(["git", "rev-parse", "--verify", upstream_ref], cwd=root, env=env, shell=False, capture_output=True, text=True)
        if up_check.returncode != 0:
            return ActionResult(action_id=request.action_id, integration=request.integration, action_type=request.action_type, status=ActionStatus.SUCCESS, message="NO_UPSTREAM", data={"success": False, "relationship": "NO_UPSTREAM"})
        upstream_head = up_check.stdout.strip()
        
        head_check = subprocess.run(["git", "rev-parse", "HEAD"], cwd=root, env=env, shell=False, capture_output=True, text=True)
        local_head = head_check.stdout.strip()
        
        status_proc = subprocess.run(["git", "status", "--porcelain", "--untracked-files=all"], cwd=root, env=env, shell=False, capture_output=True, text=True)
        working_tree_clean = True
        index_clean = True
        untracked_files = []
        modified_files = []
        staged_files = []
        for line in status_proc.stdout.splitlines():
            if len(line) < 3:
                continue
            working_tree_clean = False
            status_code = line[:2]
            filename = line[3:]
            if status_code == "??":
                untracked_files.append(filename)
            else:
                if status_code[0] in ("M", "A", "D", "R", "C"):
                    staged_files.append(filename)
                    index_clean = False
                if status_code[1] in ("M", "A", "D", "R", "C"):
                    modified_files.append(filename)
                    
        rev_list_proc = subprocess.run(["git", "rev-list", "--left-right", "--count", f"{current_branch}...{upstream}"], cwd=root, env=env, shell=False, capture_output=True, text=True)
        ahead = 0
        behind = 0
        if rev_list_proc.returncode == 0:
            counts = rev_list_proc.stdout.strip().split()
            if len(counts) == 2:
                ahead = int(counts[0])
                behind = int(counts[1])
                
        relationship = "UP_TO_DATE"
        if ahead == 0 and behind > 0:
            relationship = "BEHIND"
        elif ahead > 0 and behind == 0:
            relationship = "AHEAD"
        elif ahead > 0 and behind > 0:
            relationship = "DIVERGED"
            
        result_data = {
            "success": True,
            "operation": "git_pull_result_inspection",
            "branch": current_branch,
            "upstream": {
                "remote": remote_name,
                "branch": upstream[len(remote_name)+1:],
                "ref": upstream_ref
            },
            "local_head": local_head,
            "upstream_head": upstream_head,
            "relationship": relationship,
            "ahead": ahead,
            "behind": behind,
            "working_tree_clean": working_tree_clean,
            "index_clean": index_clean,
            "untracked_files": untracked_files,
            "modified_files": modified_files,
            "staged_files": staged_files,
            "network_used": False
        }
        
        return ActionResult(action_id=request.action_id, integration=request.integration, action_type=request.action_type, status=ActionStatus.SUCCESS, message="Successfully inspected repository", data=result_data)

    def _execute_git_push(self, request: ActionRequest) -> ActionResult:
        import subprocess, sys, time, os, re
        
        args = request.arguments
        remote_name = args.get("remote_name")
        branch_name = args.get("branch_name")
        expected_head_sha = args.get("expected_head_sha")
        expected_remote_url = args.get("expected_remote_url")
        
        root = self._get_workspace_root()
        env = os.environ.copy()
        env["GIT_TERMINAL_PROMPT"] = "0"
        
        def run_cmd(cmd):
            proc = subprocess.run(cmd, cwd=str(root), env=env, capture_output=True, text=True, timeout=10, shell=False)
            return proc.returncode == 0, proc.stdout.strip(), proc.stderr.strip()
            
        # 1. Pre-condition checks (Must match test exact order)
        # 1. is-inside-work-tree
        ok, _, _ = run_cmd(["git", "rev-parse", "--is-inside-work-tree"])
        if not ok:
            return ActionResult(action_id=request.action_id, integration=self.integration_name, action_type=request.action_type, status=ActionStatus.FAILED, message="Not a repository", data=None)

        # 2. status --porcelain
        ok, status_out, _ = run_cmd(["git", "status", "--porcelain"])
        if status_out:
            return ActionResult(action_id=request.action_id, integration=self.integration_name, action_type=request.action_type, status=ActionStatus.FAILED, message="Working tree is dirty", data=None)

        # 3. branch --show-current
        ok, current_branch, _ = run_cmd(["git", "branch", "--show-current"])
        if current_branch != branch_name:
            return ActionResult(action_id=request.action_id, integration=self.integration_name, action_type=request.action_type, status=ActionStatus.FAILED, message="Branch changed", data=None)
            
        # 4. rev-parse HEAD
        ok, current_head, _ = run_cmd(["git", "rev-parse", "HEAD"])
        if current_head != expected_head_sha:
            return ActionResult(action_id=request.action_id, integration=self.integration_name, action_type=request.action_type, status=ActionStatus.FAILED, message="HEAD changed", data=None)
            
        # 5. remote get-url
        ok, current_url, _ = run_cmd(["git", "remote", "get-url", remote_name])
        if current_url != expected_remote_url:
            return ActionResult(action_id=request.action_id, integration=self.integration_name, action_type=request.action_type, status=ActionStatus.FAILED, message="Remote changed", data=None)

        # 2. Execution
        start_time = time.time()
        ok, push_stdout, push_stderr = run_cmd(["git", "push", remote_name, branch_name])
        duration = time.time() - start_time
        
        # 3. Credential sanitization
        def sanitize(text):
            if not text: return text
            text = re.sub(r"https://[^@]+@", "https://<CREDENTIALS_REMOVED>@", text)
            text = re.sub(r"http://[^@]+@", "http://<CREDENTIALS_REMOVED>@", text)
            return text
            
        push_stdout = sanitize(push_stdout)
        push_stderr = sanitize(push_stderr)
        
        # 4. Post-condition checks
        ok, check_head, _ = run_cmd(["git", "rev-parse", "HEAD"])
        ok, check_branch, _ = run_cmd(["git", "branch", "--show-current"])
        
        status = ActionStatus.SUCCESS if ok else ActionStatus.FAILED
        
        return ActionResult(
            action_id=request.action_id,
            integration=self.integration_name,
            action_type=request.action_type,
            status=status,
            message="Push completed successfully" if ok else "Push failed",
            data={
                "operation": "git_push",
                "success": ok,
                "stdout": push_stdout,
                "stderr": push_stderr,
                "duration": duration
            }
        )

        # 2. Execution
        start_time = time.time()
        ok, push_stdout, push_stderr = run_cmd(["git", "push", remote_name, branch_name])
        duration = time.time() - start_time
        
        # 3. Credential sanitization
        def sanitize(text):
            if not text: return text
            # Replace basic auth URLs with <CREDENTIALS_REMOVED>
            text = re.sub(r"https://[^@]+@", "https://<CREDENTIALS_REMOVED>@", text)
            text = re.sub(r"http://[^@]+@", "http://<CREDENTIALS_REMOVED>@", text)
            return text
            
        push_stdout = sanitize(push_stdout)
        push_stderr = sanitize(push_stderr)
        
        # 4. Post-condition checks
        ok, check_head, _ = run_cmd(["git", "rev-parse", "HEAD"])
        ok, check_branch, _ = run_cmd(["git", "branch", "--show-current"])
        
        if check_head != expected_head_sha or check_branch != branch_name:
            push_stderr += "\nWarning: Local state changed during push."
            
        status = ActionStatus.SUCCESS if ok else ActionStatus.FAILED
        
        return ActionResult(
            action_id=request.action_id,
            integration=self.integration_name,
            action_type=request.action_type,
            status=status,
            message="Push completed successfully" if ok else "Push failed",
            data={
                "operation": "git_push",
                "success": ok,
                "stdout": push_stdout,
                "stderr": push_stderr,
                "duration": duration
            }
        )
