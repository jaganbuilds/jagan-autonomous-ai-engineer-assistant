import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../')))

from app.job_sources.registry import source_registry
from app.job_sources.aggregator import JobSourceAggregator

def test_manual_job_sources_live():
    print("WARNING: This manual test connects to LIVE APIs.")
    
    # Temporarily override environment variables to force all enabled
    # We do NOT hardcode keys here. They must be in the environment or .env.
    os.environ["ENABLE_ARBEITNOW"] = "True"
    
    # Reload registry
    from app.job_sources.registry import SourceRegistry
    registry = SourceRegistry()
    aggregator = registry.get_aggregator()
    
    print("\nExecuting live aggregated search...")
    res = aggregator.search(role="Python", location="Berlin")
    
    print(f"\nAttempted {res.sources_attempted} sources.")
    print(f"Succeeded: {res.sources_succeeded}")
    
    if res.source_errors:
        print("\nErrors:")
        for err in res.source_errors:
            print(f"- {err.source}: {err.error_type} ({err.message})")
            
    print(f"\nTotal jobs (before deduplication): {res.total_results_before_deduplication}")
    print(f"Total jobs (after deduplication): {res.total_results_after_deduplication}")
    
    print("\nSample Jobs:")
    for job in res.jobs[:5]:
        print(f"- [{job.source}] {job.title} at {job.company} ({job.location})")

if __name__ == "__main__":
    test_manual_job_sources_live()
