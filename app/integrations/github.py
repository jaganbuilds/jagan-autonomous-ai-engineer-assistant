from typing import Dict, Any, Tuple
from app.integrations.models import ActionType, ActionRequest, ActionResult, ActionStatus, ActionRiskLevel
from app.integrations.gateway import BaseIntegration
from app.integrations.github_client import GitHubClient, GitHubError

class GitHubIntegration(BaseIntegration):
    @property
    def integration_name(self) -> str:
        return "github"
        
    @property
    def supported_actions(self) -> list[ActionType]:
        return [ActionType.READ, ActionType.WRITE]
        
    def get_action_risk(self, request: ActionRequest) -> ActionRiskLevel:
        if request.action_type == ActionType.WRITE:
            return ActionRiskLevel.HIGH
        return ActionRiskLevel.LOW
        
    def check_health(self) -> 'IntegrationCapability':
        from app.integrations.capabilities import IntegrationCapability, ActionCapability
        
        client = GitHubClient()
        state = client.check_credentials_state()
        
        # Determine risk per action type
        actions = []
        for a in self.supported_actions:
            # We construct a dummy request to check risk level if needed, or we just hardcode logic here since we know WRITE is HIGH, READ is LOW
            risk = ActionRiskLevel.HIGH if a == ActionType.WRITE else ActionRiskLevel.LOW
            actions.append(ActionCapability(
                action_type=a,
                risk_level=risk,
                requires_confirmation=risk.value == "HIGH"
            ))
            
        return IntegrationCapability(
            integration_name=self.integration_name,
            display_name="GitHub",
            available=state["configured"],
            authenticated=state["authenticated"],
            healthy=state["authenticated"],
            supported_actions=actions,
            unavailable_reason=None if state["configured"] else state["reason"],
            health_message=state["reason"]
        )
        
    def validate_arguments(self, action_type: ActionType, arguments: Dict[str, Any]) -> Tuple[bool, str]:
        action = arguments.get("action")
        if not action:
            return False, "Missing 'action' argument."
            
        if action == "LIST_REPOSITORIES":
            return True, ""
            
        elif action in ["GET_REPOSITORY", "GET_RECENT_COMMITS", "GET_README", "GET_PROJECT_STRUCTURE", "INSPECT_REPOSITORY"]:
            if not arguments.get("owner"):
                return False, "Missing 'owner'."
            if not arguments.get("repo"):
                return False, "Missing 'repo'."
            return True, ""
            
        elif action in ["GET_REPOSITORY_FILES", "GET_FILE"]:
            if not arguments.get("owner"):
                return False, "Missing 'owner'."
            if not arguments.get("repo"):
                return False, "Missing 'repo'."
            return True, ""
            
        elif action == "CREATE_BRANCH":
            if not arguments.get("owner") or not arguments.get("repo"):
                return False, "Missing 'owner' or 'repo'."
            branch_name = arguments.get("branch_name")
            if not branch_name or len(branch_name) > 200 or not str(branch_name).strip():
                return False, "Invalid or missing 'branch_name'."
            if not arguments.get("source_branch") or not str(arguments.get("source_branch")).strip():
                return False, "Missing 'source_branch'."
            return True, ""
            
        elif action == "CREATE_COMMIT":
            if not arguments.get("owner") or not arguments.get("repo"):
                return False, "Missing 'owner' or 'repo'."
            if not arguments.get("branch") or not str(arguments.get("branch")).strip():
                return False, "Missing 'branch'."
            if not arguments.get("file_path") or not str(arguments.get("file_path")).strip():
                return False, "Missing 'file_path'."
            content = arguments.get("content")
            if content is None or len(str(content)) > 200000:
                return False, "Invalid, missing, or oversized 'content'."
            msg = arguments.get("commit_message")
            if not msg or not str(msg).strip() or len(msg) > 500:
                return False, "Invalid or missing 'commit_message'."
            return True, ""
            
        elif action == "CREATE_PULL_REQUEST":
            if not arguments.get("owner") or not arguments.get("repo"):
                return False, "Missing 'owner' or 'repo'."
            title = arguments.get("title")
            if not title or not str(title).strip() or len(title) > 200:
                return False, "Invalid or missing 'title'."
            if not arguments.get("head") or not str(arguments.get("head")).strip():
                return False, "Missing 'head' branch."
            if not arguments.get("base") or not str(arguments.get("base")).strip():
                return False, "Missing 'base' branch."
            body = arguments.get("body", "")
            if len(body) > 10000:
                return False, "Oversized 'body'."
            return True, ""
            
        return False, f"Unsupported action: {action}"
        
    def execute(self, request: ActionRequest) -> ActionResult:
        client = GitHubClient()
        action = request.arguments.get("action")
        
        try:
            data = None
            if action == "LIST_REPOSITORIES":
                data = client.list_repositories()
                
            elif action == "GET_REPOSITORY":
                owner = request.arguments.get("owner")
                repo = request.arguments.get("repo")
                data = client.get_repository(owner, repo)
                
            elif action == "GET_REPOSITORY_FILES":
                owner = request.arguments.get("owner")
                repo = request.arguments.get("repo")
                path = request.arguments.get("path", "")
                data = client.get_repository_files(owner, repo, path)
                
            elif action == "GET_RECENT_COMMITS":
                owner = request.arguments.get("owner")
                repo = request.arguments.get("repo")
                limit = request.arguments.get("limit")
                data = client.get_recent_commits(owner, repo, limit)
                
            elif action in ["GET_README", "GET_FILE", "GET_PROJECT_STRUCTURE", "INSPECT_REPOSITORY"]:
                from app.integrations.github_intelligence import GitHubIntelligence
                intel = GitHubIntelligence()
                owner = request.arguments.get("owner")
                repo = request.arguments.get("repo")
                
                if action == "GET_README":
                    data = intel.get_readme(owner, repo)
                elif action == "GET_FILE":
                    path = request.arguments.get("path", "")
                    data = intel.get_file(owner, repo, path)
                elif action == "GET_PROJECT_STRUCTURE":
                    data = intel.get_project_structure(owner, repo)
                elif action == "INSPECT_REPOSITORY":
                    data = intel.inspect_repository(owner, repo)
                
            elif action == "CREATE_BRANCH":
                owner = request.arguments.get("owner")
                repo = request.arguments.get("repo")
                branch_name = request.arguments.get("branch_name")
                source_branch = request.arguments.get("source_branch")
                data = client.create_branch(owner, repo, branch_name, source_branch)
                
            elif action == "CREATE_COMMIT":
                owner = request.arguments.get("owner")
                repo = request.arguments.get("repo")
                branch = request.arguments.get("branch")
                file_path = request.arguments.get("file_path")
                content = request.arguments.get("content")
                commit_message = request.arguments.get("commit_message")
                data = client.create_commit(owner, repo, branch, file_path, content, commit_message)
                
            elif action == "CREATE_PULL_REQUEST":
                owner = request.arguments.get("owner")
                repo = request.arguments.get("repo")
                title = request.arguments.get("title")
                head = request.arguments.get("head")
                base = request.arguments.get("base")
                body = request.arguments.get("body", "")
                data = client.create_pull_request(owner, repo, title, head, base, body)
                
            else:
                return ActionResult(action_id=request.action_id, integration=request.integration, action_type=request.action_type, status=ActionStatus.FAILED, message=f"Unsupported action: {action}")
                
            return ActionResult(action_id=request.action_id, integration=request.integration, action_type=request.action_type, status=ActionStatus.SUCCESS, message="GitHub action successful", data=data)
            
        except GitHubError as e:
            return ActionResult(action_id=request.action_id, integration=request.integration, action_type=request.action_type, status=ActionStatus.FAILED, message=e.message)
        except Exception as e:
            return ActionResult(action_id=request.action_id, integration=request.integration, action_type=request.action_type, status=ActionStatus.FAILED, message=f"PROVIDER_ERROR: {str(e)}")
