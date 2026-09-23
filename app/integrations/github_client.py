import requests
from typing import Dict, Any, List, Optional
from urllib.parse import urljoin
from app.config import get_settings
import logging

logger = logging.getLogger(__name__)

class GitHubError(Exception):
    def __init__(self, message: str, status_code: int = 500):
        super().__init__(message)
        self.status_code = status_code
        self.message = message

class GitHubClient:
    def __init__(self):
        self.settings = get_settings()
        self.base_url = self.settings.github_api_base_url
        self.token = self.settings.github_token
        
    def _get_headers(self) -> Dict[str, str]:
        headers = {
            "Accept": "application/vnd.github.v3+json",
        }
        if self.token:
            headers["Authorization"] = f"token {self.token}"
        return headers
        
    def check_credentials_state(self) -> dict:
        if not self.token:
            return {"configured": False, "authenticated": False, "reason": "Missing github_token in configuration"}
            
        try:
            # Lightweight authenticated read
            response = requests.get(
                url=urljoin(self.base_url, "user"),
                headers=self._get_headers(),
                timeout=5
            )
            if response.status_code == 200:
                return {"configured": True, "authenticated": True, "reason": "Authenticated"}
            elif response.status_code in (401, 403):
                return {"configured": True, "authenticated": False, "reason": "Token invalid, expired, or insufficient permissions"}
            else:
                return {"configured": True, "authenticated": False, "reason": f"Provider error {response.status_code}"}
        except requests.exceptions.RequestException:
            return {"configured": True, "authenticated": False, "reason": "Network error or timeout"}
        
    def _request(self, method: str, endpoint: str, params: Optional[Dict[str, Any]] = None, json: Optional[Dict[str, Any]] = None) -> Any:
        url = urljoin(self.base_url, endpoint)
        
        try:
            response = requests.request(
                method=method,
                url=url,
                headers=self._get_headers(),
                params=params,
                json=json,
                timeout=10
            )
            
            if response.status_code in (401, 403):
                reason = "AUTHENTICATION_REQUIRED" if response.status_code == 401 else "FORBIDDEN"
                # Check for rate limiting
                if response.status_code == 403 and "API rate limit exceeded" in response.text:
                    reason = "RATE_LIMITED"
                raise GitHubError(reason, response.status_code)
            elif response.status_code == 404:
                raise GitHubError("NOT_FOUND", 404)
            
            response.raise_for_status()
            return response.json()
            
        except requests.exceptions.RequestException as e:
            if hasattr(e, 'response') and e.response is not None:
                raise GitHubError("PROVIDER_ERROR", e.response.status_code)
            raise GitHubError("NETWORK_TIMEOUT", 500)
            
    def list_repositories(self) -> List[Dict[str, Any]]:
        # Without token, we can't reliably list "my" repos, we would need a username.
        # But we assume the token implies the user.
        if not self.token:
            raise GitHubError("AUTHENTICATION_REQUIRED", 401)
            
        params = {
            "sort": "updated",
            "per_page": self.settings.github_repository_limit
        }
        data = self._request("GET", "/user/repos", params=params)
        
        repos = []
        for repo in data:
            repos.append({
                "name": repo.get("name"),
                "full_name": repo.get("full_name"),
                "description": repo.get("description"),
                "private": repo.get("private"),
                "default_branch": repo.get("default_branch"),
                "html_url": repo.get("html_url"),
                "language": repo.get("language"),
                "updated_at": repo.get("updated_at")
            })
        return repos
        
    def get_repository(self, owner: str, repo: str) -> Dict[str, Any]:
        data = self._request("GET", f"/repos/{owner}/{repo}")
        return {
            "name": data.get("name"),
            "full_name": data.get("full_name"),
            "description": data.get("description"),
            "visibility": data.get("visibility"),
            "default_branch": data.get("default_branch"),
            "language": data.get("language"),
            "stars": data.get("stargazers_count"),
            "forks": data.get("forks_count"),
            "open_issues": data.get("open_issues_count"),
            "updated_at": data.get("updated_at"),
            "url": data.get("html_url")
        }
        
    def get_repository_files(self, owner: str, repo: str, path: str = "") -> List[Dict[str, Any]]:
        endpoint = f"/repos/{owner}/{repo}/contents/{path}".strip("/")
        try:
            data = self._request("GET", endpoint)
        except GitHubError as e:
            if e.status_code == 404:
                return []
            raise e
            
        if not isinstance(data, list):
            data = [data]
            
        # Enforce limits
        data = data[:self.settings.github_file_limit]
        
        files = []
        for item in data:
            files.append({
                "name": item.get("name"),
                "path": item.get("path"),
                "type": item.get("type"),
                "size": item.get("size"),
                "url": item.get("html_url")
            })
        return files
        
    def get_recent_commits(self, owner: str, repo: str, limit: int = None) -> List[Dict[str, Any]]:
        if limit is None:
            limit = self.settings.github_commit_limit
            
        limit = min(limit, 50)
            
        params = {
            "per_page": limit
        }
        data = self._request("GET", f"/repos/{owner}/{repo}/commits", params=params)
        
        commits = []
        for item in data:
            commit_data = item.get("commit", {})
            author_data = commit_data.get("author", {})
            commits.append({
                "sha": item.get("sha"),
                "message": commit_data.get("message"),
                "author": author_data.get("name"),
                "timestamp": author_data.get("date"),
                "url": item.get("html_url")
            })
        return commits

    def get_readme(self, owner: str, repo: str) -> Dict[str, Any]:
        try:
            data = self._request("GET", f"/repos/{owner}/{repo}/readme")
            import base64
            content = data.get("content", "")
            if data.get("encoding") == "base64":
                content = base64.b64decode(content).decode("utf-8", errors="replace")
                
            return {
                "name": data.get("name"),
                "path": data.get("path"),
                "content": content,
                "size": data.get("size")
            }
        except GitHubError as e:
            if e.status_code == 404:
                return {"found": False}
            raise e

    def get_file_content(self, owner: str, repo: str, path: str) -> Dict[str, Any]:
        try:
            data = self._request("GET", f"/repos/{owner}/{repo}/contents/{path}")
            if isinstance(data, list):
                # It's a directory, not a file
                raise GitHubError("NOT_A_FILE", 400)
                
            if data.get("type") != "file":
                raise GitHubError("UNSUPPORTED_TYPE", 400)
                
            import base64
            content = data.get("content", "")
            if data.get("encoding") == "base64":
                try:
                    content = base64.b64decode(content).decode("utf-8")
                except UnicodeDecodeError:
                    raise GitHubError("BINARY_FILE", 400)
            elif not content:
                # Could be a very large file or sub-module, requiring raw download
                raise GitHubError("NO_CONTENT", 400)
                
            return {
                "name": data.get("name"),
                "path": data.get("path"),
                "content": content,
                "size": data.get("size")
            }
        except GitHubError as e:
            raise e

    def get_repository_tree(self, owner: str, repo: str, branch: str = "main") -> List[Dict[str, Any]]:
        # Get tree recursively, but we will bound the response later
        data = self._request("GET", f"/repos/{owner}/{repo}/git/trees/{branch}?recursive=1")
        tree = data.get("tree", [])
        return tree

    def create_branch(self, owner: str, repo: str, branch_name: str, source_branch: str) -> Dict[str, Any]:
        # 1. Get the source branch SHA
        try:
            ref_data = self._request("GET", f"/repos/{owner}/{repo}/git/ref/heads/{source_branch}")
            sha = ref_data.get("object", {}).get("sha")
        except GitHubError as e:
            raise GitHubError(f"SOURCE_BRANCH_ERROR: {e.message}", e.status_code)
            
        # 2. Create new branch reference
        payload = {
            "ref": f"refs/heads/{branch_name}",
            "sha": sha
        }
        
        try:
            self._request("POST", f"/repos/{owner}/{repo}/git/refs", json=payload)
        except GitHubError as e:
            if e.status_code == 422:
                raise GitHubError("BRANCH_ALREADY_EXISTS", 422)
            raise e
            
        return {
            "repository": f"{owner}/{repo}",
            "branch_name": branch_name,
            "source_branch": source_branch,
            "created": True
        }

    def create_commit(self, owner: str, repo: str, branch: str, file_path: str, content: str, commit_message: str) -> Dict[str, Any]:
        import base64
        # 1. Try to get the existing file's SHA if it exists
        file_sha = None
        try:
            file_data = self._request("GET", f"/repos/{owner}/{repo}/contents/{file_path}?ref={branch}")
            if isinstance(file_data, list):
                raise GitHubError("TARGET_IS_DIRECTORY", 400)
            file_sha = file_data.get("sha")
        except GitHubError as e:
            if e.status_code != 404:
                raise e
                
        # 2. Base64 encode the new content
        encoded_content = base64.b64encode(content.encode("utf-8")).decode("utf-8")
        
        # 3. Create or update file
        payload = {
            "message": commit_message,
            "content": encoded_content,
            "branch": branch
        }
        if file_sha:
            payload["sha"] = file_sha
            
        result = self._request("PUT", f"/repos/{owner}/{repo}/contents/{file_path}", json=payload)
        
        commit = result.get("commit", {})
        return {
            "repository": f"{owner}/{repo}",
            "branch": branch,
            "file_path": file_path,
            "commit_sha": commit.get("sha"),
            "commit_url": commit.get("html_url"),
            "committed": True
        }

    def create_pull_request(self, owner: str, repo: str, title: str, head: str, base: str, body: str = "") -> Dict[str, Any]:
        payload = {
            "title": title,
            "head": head,
            "base": base,
            "body": body
        }
        
        try:
            result = self._request("POST", f"/repos/{owner}/{repo}/pulls", json=payload)
        except GitHubError as e:
            if e.status_code == 422:
                raise GitHubError("PR_CREATION_FAILED", 422)
            raise e
            
        return {
            "repository": f"{owner}/{repo}",
            "pull_request_number": result.get("number"),
            "title": result.get("title"),
            "head": head,
            "base": base,
            "url": result.get("html_url"),
            "created": True
        }

    def create_repository(self, name: str, description: str = "", private: bool = True, owner: str = None) -> dict:
        import re
        if not name or not name.strip():
            raise GitHubError("EMPTY_REPOSITORY_NAME", 400)
            
        if len(name) > 100:
            raise GitHubError("OVERSIZED_REPOSITORY_NAME", 400)
            
        if not re.match(r'^[a-zA-Z0-9_\-\.]+$', name):
            raise GitHubError("INVALID_REPOSITORY_NAME", 400)
            
        if name in ('.', '..'):
            raise GitHubError("INVALID_REPOSITORY_NAME", 400)
            
        target_owner = owner.strip() if owner and owner.strip() else None
        
        if not target_owner:
            try:
                user_data = self._request("GET", "/user")
                target_owner = user_data.get("login")
            except GitHubError:
                pass
                
        if target_owner:
            try:
                existing = self.get_repository(target_owner, name)
                if existing:
                    return {
                        "status": "ALREADY_EXISTS",
                        "repository": f"{target_owner}/{name}",
                        "message": "Repository already exists"
                    }
            except GitHubError as e:
                if e.status_code != 404:
                    raise e

        payload = {
            "name": name,
            "description": description,
            "private": private
        }
        
        endpoint = "/user/repos"
        if owner and owner.strip():
            endpoint = f"/orgs/{owner.strip()}/repos"
            
        try:
            result = self._request("POST", endpoint, json=payload)
        except GitHubError as e:
            if e.status_code == 422:
                return {
                    "status": "ALREADY_EXISTS",
                    "message": "Repository name conflict or validation failure on GitHub."
                }
            raise e
            
        return {
            "status": "SUCCESS",
            "name": result.get("name"),
            "owner": result.get("owner", {}).get("login"),
            "visibility": result.get("visibility") or ("private" if result.get("private") else "public"),
            "url": result.get("html_url"),
            "id": result.get("id"),
            "created": True
        }
