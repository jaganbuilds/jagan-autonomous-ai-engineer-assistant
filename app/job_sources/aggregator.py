import logging
from typing import List, Optional

from app.job_sources.base import BaseJobSource, Job, AggregatedJobSearchResult, SourceError

logger = logging.getLogger(__name__)

class JobSourceAggregator:
    def __init__(self, sources: List[BaseJobSource]):
        self.sources = sources
        
    def search(self, role: Optional[str] = None, location: Optional[str] = None, experience: Optional[str] = None) -> AggregatedJobSearchResult:
        all_jobs: List[Job] = []
        errors: List[SourceError] = []
        succeeded = 0
        
        for source in self.sources:
            try:
                jobs = source.search(role=role, location=location, experience=experience)
                all_jobs.extend(jobs)
                succeeded += 1
            except ValueError as e:
                # Our sources raise ValueError formatted as "error_type: message"
                error_str = str(e)
                parts = error_str.split(":", 1)
                if len(parts) == 2:
                    err_type = parts[0].strip()
                    msg = parts[1].strip()
                else:
                    err_type = "unknown_error"
                    msg = error_str
                    
                errors.append(SourceError(
                    source=source.__class__.__name__.replace("Source", "").lower(),
                    error_type=err_type,
                    message=msg
                ))
            except Exception as e:
                logger.error(f"Unexpected error in {source.__class__.__name__}: {e}")
                errors.append(SourceError(
                    source=source.__class__.__name__.replace("Source", "").lower(),
                    error_type="unexpected_error",
                    message=str(e)
                ))
                
        total_before = len(all_jobs)
        
        # Deduplicate memory collection before returning
        from app.database import get_job_repository
        repo = get_job_repository()
        seen_keys = set()
        unique_jobs = []
        
        for job in all_jobs:
            # We also deduplicate on normalized URL as a cross-source safety
            key = repo.generate_job_key(job)
            
            # Additional cross-source deduplication:
            # If URLs are identical, it's the exact same job post regardless of source
            url_key = job.url.strip().lower() if job.url else None
            
            is_dup = False
            if key in seen_keys:
                is_dup = True
            elif url_key and url_key in seen_keys:
                is_dup = True
                
            if not is_dup:
                seen_keys.add(key)
                if url_key:
                    seen_keys.add(url_key)
                unique_jobs.append(job)

        return AggregatedJobSearchResult(
            jobs=unique_jobs,
            sources_attempted=len(self.sources),
            sources_succeeded=succeeded,
            source_errors=errors,
            total_results_before_deduplication=total_before,
            total_results_after_deduplication=len(unique_jobs)
        )
