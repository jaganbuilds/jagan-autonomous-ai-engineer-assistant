import pytest
from app.job_sources.base import BaseJobSource, Job
from app.job_sources.mock_source import MockJobSource

def test_base_source_is_abstract():
    with pytest.raises(TypeError):
        BaseJobSource()

def test_mock_source_interface():
    source = MockJobSource()
    assert isinstance(source, BaseJobSource)
    
    # Test search with no filters returns all jobs
    all_jobs = source.search()
    assert len(all_jobs) == 4
    
    # Test all return types are Job models
    for job in all_jobs:
        assert isinstance(job, Job)

def test_mock_source_filtering():
    source = MockJobSource()
    
    # Role
    ai_jobs = source.search(role="AI")
    assert len(ai_jobs) >= 1
    
    # Location
    chennai_jobs = source.search(location="Chennai")
    assert len(chennai_jobs) == 2
    
    # Experience
    senior_jobs = source.search(experience="5+ years")
    assert len(senior_jobs) == 1
    assert senior_jobs[0].title == "Senior ML Engineer"
    
    # Multiple
    dev_remote = source.search(role="Developer", location="Remote")
    assert len(dev_remote) == 1
    
    # No matches
    none_jobs = source.search(role="Astronaut")
    assert len(none_jobs) == 0

def test_job_model_conversion():
    job = Job(
        title="Test",
        company="Co",
        location="Loc",
        experience="Exp",
        description="Desc",
        url="Url"
    )
    assert job.title == "Test"
    
    dump = job.model_dump()
    assert isinstance(dump, dict)
    assert dump["company"] == "Co"
