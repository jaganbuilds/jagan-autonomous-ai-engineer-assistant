from typing import Dict, Any, List
from app.integrations.github_client import GitHubClient, GitHubError
from app.config import get_settings

class GitHubIntelligence:
    def __init__(self):
        self.client = GitHubClient()
        self.settings = get_settings()
        
        # Safe bounds
        self.max_readme_chars = 10000
        self.max_file_chars = 20000
        self.max_important_files = 30
        
    def get_readme(self, owner: str, repo: str) -> Dict[str, Any]:
        result = self.client.get_readme(owner, repo)
        if not result.get("found", True):
            return {
                "repository": f"{owner}/{repo}",
                "readme_found": False
            }
            
        content = result.get("content", "")
        truncated = False
        
        if len(content) > self.max_readme_chars:
            content = content[:self.max_readme_chars] + "\n\n...[TRUNCATED BY JAGAN AI]..."
            truncated = True
            
        return {
            "repository": f"{owner}/{repo}",
            "readme_found": True,
            "readme_content": content,
            "truncated": truncated
        }
        
    def get_file(self, owner: str, repo: str, path: str) -> Dict[str, Any]:
        result = self.client.get_file_content(owner, repo, path)
        content = result.get("content", "")
        truncated = False
        
        if len(content) > self.max_file_chars:
            content = content[:self.max_file_chars] + "\n\n...[TRUNCATED BY JAGAN AI]..."
            truncated = True
            
        return {
            "repository": f"{owner}/{repo}",
            "path": path,
            "content": content,
            "size": result.get("size"),
            "truncated": truncated
        }
        
    def get_project_structure(self, owner: str, repo: str) -> Dict[str, Any]:
        # Determine default branch
        repo_metadata = self.client.get_repository(owner, repo)
        default_branch = repo_metadata.get("default_branch", "main")
        
        tree = self.client.get_repository_tree(owner, repo, default_branch)
        
        important_patterns = [
            "readme", "requirements.txt", "pyproject.toml", "package.json", 
            "dockerfile", ".env.example", ".gitignore"
        ]
        
        important_files = []
        for item in tree:
            if item.get("type") != "blob":
                continue
                
            path = item.get("path", "")
            path_lower = path.lower()
            
            is_important = False
            for pattern in important_patterns:
                if pattern in path_lower:
                    is_important = True
                    break
                    
            if not is_important:
                if path_lower.endswith(".py") and ("app/" in path_lower or "src/" in path_lower or "tests/" in path_lower or "/" not in path_lower):
                    is_important = True
                elif path_lower.endswith(".js") or path_lower.endswith(".ts") or path_lower.endswith(".go") or path_lower.endswith(".rs"):
                    if "src/" in path_lower or "app/" in path_lower or "/" not in path_lower:
                        is_important = True
                        
            if is_important:
                important_files.append({
                    "path": path,
                    "file_type": path.split(".")[-1] if "." in path else "unknown",
                    "size": item.get("size", 0)
                })
                
            if len(important_files) >= self.max_important_files:
                break
                
        return {
            "repository": f"{owner}/{repo}",
            "important_files": important_files,
            "truncated": len(important_files) >= self.max_important_files
        }
        
    def inspect_repository(self, owner: str, repo: str) -> Dict[str, Any]:
        repo_metadata = self.client.get_repository(owner, repo)
        
        readme = self.get_readme(owner, repo)
        readme_available = readme.get("readme_found", False)
        
        recent_commits = self.client.get_recent_commits(owner, repo, limit=5)
        
        structure = self.get_project_structure(owner, repo)
        
        return {
            "repository": repo_metadata.get("full_name"),
            "description": repo_metadata.get("description"),
            "language": repo_metadata.get("language"),
            "visibility": repo_metadata.get("visibility"),
            "default_branch": repo_metadata.get("default_branch"),
            "stars": repo_metadata.get("stars"),
            "forks": repo_metadata.get("forks"),
            "readme_available": readme_available,
            "recent_commits_count": len(recent_commits),
            "recent_commits_preview": recent_commits,
            "important_files_preview": structure.get("important_files", [])[:10]
        }
