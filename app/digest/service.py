import logging
from typing import Optional, List
from app.database import get_job_repository
from app.agents.state import state_manager
from app.digest.models import JobDigest, JobDigestItem

logger = logging.getLogger(__name__)

class JobDigestService:
    def get_digest(self, discovery_run_id: int, session_id: Optional[str] = None) -> JobDigest:
        repo = get_job_repository()
        
        # 1. Load the discovery run
        run = repo.get_discovery_run(discovery_run_id)
        if not run:
            return JobDigest(
                status="discovery_run_not_found",
                discovery_run_id=discovery_run_id,
                total_new_jobs=0,
                jobs_with_profile_match=0,
                jobs_without_match_data=0,
                items=[],
                message=f"Discovery run {discovery_run_id} does not exist."
            )
            
        # 2. Load NEW jobs from that run
        run_jobs = repo.list_discovery_run_jobs(discovery_run_id, new_only=True)
        job_ids = [rj.job_id for rj in run_jobs]
        
        persisted_jobs = repo.get_jobs_by_ids(job_ids)
        # Create a lookup dictionary
        persisted_jobs_dict = {job.id: job for job in persisted_jobs}
        
        # 3. Retrieve available session-level match data
        # We need to look through the session's job_matches to find matching ones.
        session_matches = {}
        if session_id:
            try:
                state = state_manager.get_session(session_id)
                for pair in state.job_results.values():
                    session_matches[pair.job.job_key] = pair.match_result
            except Exception as e:
                logger.error(f"Failed to load session match data: {e}")
        
        # 4. Construct digest items
        items: List[JobDigestItem] = []
        jobs_with_match = 0
        jobs_without_match = 0
        
        for job_id in job_ids:
            if job_id not in persisted_jobs_dict:
                continue
                
            job = persisted_jobs_dict[job_id]
            match_data = session_matches.get(job.job_key)
            
            explanation = None
            matched_skills = []
            missing_skills = []
            next_steps = []
            
            if match_data:
                jobs_with_match += 1
                try:
                    matched_skills = match_data.matched_skills or []
                    missing_skills = match_data.missing_skills or []
                    explanation = match_data.explanation
                    
                    if hasattr(match_data, 'semantic_analysis') and match_data.semantic_analysis:
                        if match_data.semantic_analysis.semantically_related_skills:
                            matched_skills.extend(match_data.semantic_analysis.semantically_related_skills)
                        if getattr(match_data.semantic_analysis, 'additional_missing_skills', None):
                            missing_skills.extend(match_data.semantic_analysis.additional_missing_skills)
                        if getattr(match_data.semantic_analysis, 'actionable_next_steps', None):
                            next_steps = match_data.semantic_analysis.actionable_next_steps
                            
                except Exception as e:
                    logger.warning(f"Malformed match data for job {job_id}: {e}")
            else:
                jobs_without_match += 1
                
            item = JobDigestItem(
                job_id=job.id,
                job_key=job.job_key,
                title=job.title,
                company=job.company,
                location=job.location or "Unknown",
                experience=job.experience or "Unknown",
                url=job.url or "",
                match_explanation=explanation,
                matched_skills=matched_skills,
                missing_skills=missing_skills,
                next_steps=next_steps,
                source=job.source,
                discovered_at=job.discovered_at
            )
            items.append(item)
            
        return JobDigest(
            status="success",
            discovery_run_id=discovery_run_id,
            role=run.role,
            location=run.location,
            experience=run.experience,
            total_new_jobs=len(items),
            jobs_with_profile_match=jobs_with_match,
            jobs_without_match_data=jobs_without_match,
            items=items,
            source_errors=[], # Omitted for brevity since runs don't store them currently
            message=f"Generated digest for {len(items)} new jobs."
        )
