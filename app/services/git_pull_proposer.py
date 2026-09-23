from pydantic import BaseModel
from typing import List, Optional, Dict, Any

class GitPullProposal(BaseModel):
    success: bool
    remote_name: str
    local_branch: Optional[str]
    upstream_branch: Optional[str]
    relationship: str
    ahead: int
    behind: int
    strategy: str
    affected_files: str = "unknown"
    affected_commits: List[Dict[str, Any]]
    requires_confirmation: bool
    executable: bool
    reason: str
    warnings: List[str]

class GitPullProposer:
    def propose(self, inspection_result: Dict[str, Any]) -> GitPullProposal:
        if not inspection_result.get("success"):
            return GitPullProposal(
                success=False,
                remote_name=inspection_result.get("remote_name", "unknown"),
                local_branch=None,
                upstream_branch=None,
                relationship="UNKNOWN",
                ahead=0,
                behind=0,
                strategy="CANNOT_PROPOSE",
                affected_commits=[],
                requires_confirmation=False,
                executable=False,
                reason=inspection_result.get("message", "Inspection failed or returned unsuccessful state."),
                warnings=["Inspection data is invalid or failed."]
            )

        remote_name = inspection_result["remote_name"]
        current_branch = inspection_result.get("current_branch")
        
        if not current_branch:
            return GitPullProposal(
                success=False,
                remote_name=remote_name,
                local_branch=None,
                upstream_branch=None,
                relationship="UNKNOWN",
                ahead=0,
                behind=0,
                strategy="CANNOT_PROPOSE",
                affected_commits=[],
                requires_confirmation=False,
                executable=False,
                reason="No current local branch.",
                warnings=[]
            )

        branch_comparisons = inspection_result.get("branch_comparisons", [])
        
        # Find comparison for current branch
        current_comparison = None
        for comp in branch_comparisons:
            if comp.get("local_branch") == current_branch:
                current_comparison = comp
                break
                
        if not current_comparison:
            return GitPullProposal(
                success=False,
                remote_name=remote_name,
                local_branch=current_branch,
                upstream_branch=None,
                relationship="UNKNOWN",
                ahead=0,
                behind=0,
                strategy="CANNOT_PROPOSE",
                affected_commits=[],
                requires_confirmation=False,
                executable=False,
                reason=f"No upstream relationship found for {current_branch} corresponding to remote {remote_name}.",
                warnings=[]
            )
            
        state = current_comparison.get("state", "UNKNOWN")
        ahead = current_comparison.get("ahead", 0)
        behind = current_comparison.get("behind", 0)
        upstream_branch = current_comparison.get("remote_branch")
        
        strategy = "CANNOT_PROPOSE"
        requires_confirmation = False
        executable = False
        reason = ""
        
        # Gather commits based on state
        affected_commits = []
        if state in ["BEHIND", "DIVERGED"]:
            for c in inspection_result.get("newly_available_commits", []):
                if c.get("branch") == current_branch:
                    affected_commits.append(c)
        if state in ["AHEAD", "DIVERGED"]:
            for c in inspection_result.get("local_only_commits", []):
                if c.get("branch") == current_branch:
                    affected_commits.append(c)

        if state == "UP_TO_DATE":
            strategy = "NO_ACTION_REQUIRED"
            reason = f"Local branch {current_branch} is already synchronized with {upstream_branch}."
        elif state == "BEHIND":
            strategy = "FAST_FORWARD_ONLY"
            requires_confirmation = True
            executable = False
            reason = f"Local branch {current_branch} is {behind} commits behind {upstream_branch}. A fast-forward synchronization can be performed."
        elif state == "AHEAD":
            strategy = "NO_PULL_REQUIRED"
            reason = f"Local branch {current_branch} is {ahead} commits ahead of {upstream_branch}. No remote commits need to be applied."
        elif state == "DIVERGED":
            strategy = "MANUAL_REVIEW_REQUIRED"
            reason = f"Local branch {current_branch} and {upstream_branch} have diverged ({ahead} ahead, {behind} behind). Automatic synchronization is not proposed."
        
        return GitPullProposal(
            success=True,
            remote_name=remote_name,
            local_branch=current_branch,
            upstream_branch=upstream_branch,
            relationship=state,
            ahead=ahead,
            behind=behind,
            strategy=strategy,
            affected_commits=affected_commits,
            requires_confirmation=requires_confirmation,
            executable=executable,
            reason=reason,
            warnings=[]
        )
