from typing import List, Optional
from app.job_sources.base import BaseJobSource, Job

class MockJobSource(BaseJobSource):
    """
    A deterministic, local mock job source for testing and Phase 4A.
    """
    def __init__(self):
        self.mock_jobs = [
            Job(
                title="AI Engineer Fresher",
                company="TechCorp",
                location="Chennai",
                experience="0-1 years",
                description="Looking for an AI engineer fresher with knowledge of Python and LLMs.",
                url="https://example.com/jobs/1", source="mock", external_id="mock_1"
            ),
            Job(
                title="Senior ML Engineer",
                company="DataSystems",
                location="Bangalore",
                experience="5+ years",
                description="Expert in machine learning models, deploying on AWS.",
                url="https://example.com/jobs/2", source="mock", external_id="mock_2"
            ),
            Job(
                title="GenAI Developer",
                company="StartupInc",
                location="Chennai",
                experience="0-2 years",
                description="Build LLM applications using Langchain and LLM API.",
                url="https://example.com/jobs/3", source="mock", external_id="mock_3"
            ),
            Job(
                title="Python Backend Developer",
                company="WebSolutions",
                location="Remote",
                experience="2-4 years",
                description="Develop APIs using FastAPI.",
                url="https://example.com/jobs/4", source="mock", external_id="mock_4"
            )
        ]

    def search(self, role: Optional[str] = None, location: Optional[str] = None, experience: Optional[str] = None) -> List[Job]:
        results = self.mock_jobs
        
        if role:
            role_lower = role.lower()
            results = [job for job in results if role_lower in job.title.lower() or role_lower in job.description.lower()]
            
        if location:
            loc_lower = location.lower()
            results = [job for job in results if loc_lower in job.location.lower()]
            
        if experience:
            exp_lower = experience.lower()
            is_fresher_query = "fresh" in exp_lower or "entry" in exp_lower or "0" in exp_lower
            
            filtered = []
            for job in results:
                job_exp_lower = job.experience.lower()
                if exp_lower in job_exp_lower:
                    filtered.append(job)
                elif is_fresher_query and ("0" in job_exp_lower or "fresher" in job_exp_lower):
                    filtered.append(job)
            
            results = filtered
            
        return results
