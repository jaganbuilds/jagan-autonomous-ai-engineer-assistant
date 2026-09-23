import logging
from typing import Optional

from app.job_sources import source_registry
from app.database import get_job_repository
from app.profile.manager import profile_manager
from app.matching.matcher import JobCandidateMatcher
from app.matching.semantic_matcher import SemanticJobMatcher
from app.discovery.models import JobDiscoveryResult, DiscoveredJobSummary

logger = logging.getLogger(__name__)

class JobDiscoveryService:
    def __init__(self):
        self.matcher = JobCandidateMatcher()
        self.semantic_matcher = SemanticJobMatcher()

    def run(self, role: Optional[str] = None, location: Optional[str] = None, experience: Optional[str] = None, session_id: Optional[str] = None) -> JobDiscoveryResult:
        repo = get_job_repository()
        
        # 1. Start discovery run record
        run_id = repo.create_discovery_run(role, location, experience)
        
        # 2. Get profile if available
        profile = None
        if session_id:
            profile = profile_manager.get_profile(session_id)
            
        # 3. Search using aggregator
        aggregator = source_registry.get_aggregator()
        try:
            agg_result = aggregator.search(role=role, location=location, experience=experience)
        except Exception as e:
            logger.error(f"Discovery aggregation failed completely: {e}")
            repo.complete_discovery_run(run_id, 0, 0, 0, 0, 0, "failed")
            return JobDiscoveryResult(
                status="failed", role=role, location=location, experience=experience, run_id=run_id,
                sources_attempted=0, sources_succeeded=0, source_errors=[],
                total_found=0, new_jobs=0, existing_jobs=0, jobs_processed=0, jobs_skipped=0, jobs=[]
            )

        # 4. Identify new jobs and process
        new_jobs_count = 0
        existing_jobs_count = 0
        jobs_processed = 0
        jobs_skipped = 0
        
        job_summaries = []
        
        # Prevent deduplication within this run (aggregator already does it, but we also track it locally just in case)
        processed_keys = set()
        
        for job in agg_result.jobs:
            try:
                job_key = repo.generate_job_key(job)
                
                if job_key in processed_keys:
                    continue
                processed_keys.add(job_key)
                
                is_new = not repo.job_exists(job_key)
                
                # Persist the job (creates or updates)
                status, saved_job = repo.save_job(job)
                
                # Update statistics
                if is_new:
                    new_jobs_count += 1
                else:
                    existing_jobs_count += 1
                    
                # Record relationship
                repo.record_discovery_job(run_id, saved_job.db_id, is_new)
                
                # Match if new and we have a profile
                match_result = None
                error_msg = None
                
                if is_new and profile:
                    try:
                        match_result = self.matcher.match(saved_job, profile)
                        semantic_res = self.semantic_matcher.analyze(saved_job, profile, match_result)
                        match_result.semantic_analysis = semantic_res
                    except Exception as match_e:
                        logger.error(f"Matching failed for discovered job {saved_job.db_id}: {match_e}")
                        error_msg = str(match_e)
                
                summary = DiscoveredJobSummary(
                    job_id=saved_job.db_id,
                    title=saved_job.title,
                    company=saved_job.company,
                    location=saved_job.location,
                    url=saved_job.url,
                    source=saved_job.source,
                    is_new=is_new,
                    match_result=match_result,
                    error=error_msg
                )
                job_summaries.append(summary)
                jobs_processed += 1
                
                # Minimum fix: Store the new job and its match result in the session state
                if session_id and is_new:
                    from app.agents.state import state_manager
                    from app.workflows.models import JobMatchPair
                    state = state_manager.get_session(session_id)
                    pair = JobMatchPair(job=saved_job, match_result=match_result)
                    state.job_results[f"job_{saved_job.db_id}"] = pair
                    
            except Exception as e:
                logger.error(f"Error processing discovered job: {e}")
                jobs_skipped += 1
                
        # 5. Complete run
        final_status = "profile_not_available" if not profile else "completed"
        repo.complete_discovery_run(
            run_id=run_id,
            total_found=len(processed_keys),
            new_jobs=new_jobs_count,
            existing_jobs=existing_jobs_count,
            jobs_processed=jobs_processed,
            jobs_skipped=jobs_skipped,
            status=final_status
        )
        
        return JobDiscoveryResult(
            status=final_status,
            role=role,
            location=location,
            experience=experience,
            run_id=run_id,
            sources_attempted=agg_result.sources_attempted,
            sources_succeeded=agg_result.sources_succeeded,
            source_errors=agg_result.source_errors,
            total_found=len(processed_keys),
            new_jobs=new_jobs_count,
            existing_jobs=existing_jobs_count,
            jobs_processed=jobs_processed,
            jobs_skipped=jobs_skipped,
            jobs=job_summaries
        )
