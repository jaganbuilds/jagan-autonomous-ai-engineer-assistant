import logging
from typing import Optional
from app.job_sources.base import Job
from app.matching.matcher import JobCandidateMatcher
from app.matching.semantic_matcher import SemanticJobMatcher
from app.profile.manager import profile_manager
from app.workflows.models import WorkflowResult, JobMatchPair
from app.database import get_job_repository

logger = logging.getLogger(__name__)

class JobMatchingWorkflow:
    """
    Deterministic workflow that chains Job Search and Candidate Matching.
    Ensures safe, bounded execution without arbitrary scoring or autonomous looping.
    """
    
    def __init__(self, max_jobs: int = 5):
        self.max_jobs = max_jobs
        self.matcher = JobCandidateMatcher()
        self.semantic_matcher = SemanticJobMatcher()

    def execute(self, session_id: str, role: Optional[str] = None, location: Optional[str] = None, experience: Optional[str] = None) -> WorkflowResult:
        # Retrieve real profile from session
        profile = profile_manager.get_profile(session_id)
        if not profile:
            logger.warning(f"Session {session_id} attempted matching without a profile.")
            return WorkflowResult(
                status="profile_required",
                message="A CandidateProfile is required to perform job matching. Please extract or upload a resume first."
            )
            
        # 1. Search for jobs using the unified Aggregator
        try:
            from app.job_sources import source_registry
            aggregator = source_registry.get_aggregator()
            agg_result = aggregator.search(role=role, location=location, experience=experience)
            jobs = agg_result.jobs
            
            # We could log source failures here if needed
            for err in agg_result.source_errors:
                logger.warning(f"Source {err.source} failed: {err.error_type} - {err.message}")
                
        except Exception as e:
            logger.error(f"Workflow search phase failed entirely: {e}")
            jobs = []

        jobs_found = len(jobs)
        jobs_to_process = jobs[:self.max_jobs]
        jobs_skipped = max(0, jobs_found - self.max_jobs)
        
        # 1.5 Persist discovered jobs
        try:
            repo = get_job_repository()
            repo.save_jobs(jobs_to_process)
        except Exception as e:
            logger.error(f"Failed to persist jobs to database: {e}")

        results = []
        
        # 2. Match each job against the actual session profile
        for job in jobs_to_process:
            try:
                match_res = self.matcher.match(job, profile)
                
                # 3. Optional Semantic Analysis
                # This does not stop the workflow if it fails
                semantic_res = self.semantic_matcher.analyze(job, profile, match_res)
                match_res.semantic_analysis = semantic_res
                
                # 4. Actionable Explanation Synthesis
                next_steps = []
                why_text = f"Exactly matched {len(match_res.matched_skills)} core skills."
                
                if semantic_res:
                    if semantic_res.semantically_related_skills:
                        why_text += f" Found {len(semantic_res.semantically_related_skills)} semantic matches."
                    if semantic_res.next_steps:
                        next_steps.extend(semantic_res.next_steps)
                
                if match_res.missing_skills:
                    why_text += f" Missing {len(match_res.missing_skills)} explicit requirements."
                    if not next_steps:
                        next_steps.append(f"Review missing core skills: {', '.join(match_res.missing_skills[:3])}.")
                
                if not match_res.matched_skills and not (semantic_res and semantic_res.semantically_related_skills):
                    why_text = "No explicit or semantic skill matches were detected for this role."
                    
                if not next_steps:
                    next_steps.append("Consider highlighting your existing projects if applying.")
                    
                match_res.explanation = why_text.strip()
                match_res.next_steps = next_steps
                
                results.append(JobMatchPair(job=job, match_result=match_res))
            except Exception as e:
                logger.error(f"Workflow match phase failed for job '{job.title}': {e}")
                results.append(JobMatchPair(job=job, error=str(e)))
        
        return WorkflowResult(
            status="success",
            jobs_found=jobs_found,
            jobs_processed=len(jobs_to_process),
            jobs_skipped=jobs_skipped,
            results=results
        )
