import pytest
from app.job_sources.base import Job
from app.profile.models import CandidateProfile
from app.matching.matcher import JobCandidateMatcher

@pytest.fixture
def matcher():
    return JobCandidateMatcher()

@pytest.fixture
def mock_candidate():
    return CandidateProfile(
        name="Test Dev",
        experience_level="Senior",
        education="B.S. Computer Science",
        preferred_locations=["Remote", "Berlin"],
        programming_languages=["Python", "JavaScript", "Go"],
        frameworks=["FastAPI", "ReactJS"],
        ai_ml_technologies=["PyTorch", "NLP"],
        skills=["Agile", "AWS"]
    )

def test_exact_skill_matches(matcher, mock_candidate):
    job = Job(
        title="Python Developer",
        company="Tech",
        location="Remote",
        experience="Senior",
        description="We need someone good with Python, FastAPI, and Agile.",
        url="http"
    )
    
    res = matcher.match(job, mock_candidate)
    
    assert "Python" in res.matching_programming_languages
    assert "FastAPI" in res.matching_frameworks
    assert "Agile" in res.matched_skills
    assert res.location_match == "Matched"
    assert res.experience_match == "Matched"
    assert "Python" in res.matched_skills

def test_case_insensitive_and_alias_matching(matcher, mock_candidate):
    job = Job(
        title="AI Engineer",
        company="Tech",
        location="berlin",
        experience="senior",
        description="Must know PyTorch, React, natural language processing, and amazon web services.",
        url="http"
    )
    
    res = matcher.match(job, mock_candidate)
    
    # 'React' matches 'ReactJS' because of alias map? No, my alias map maps 'reactjs' to 'react'. 
    # And candidate has 'ReactJS', so it normalizes to 'react'.
    # Job text has 'react', which matches the normalized candidate skill.
    assert "ReactJS" in res.matching_frameworks
    
    # NLP is aliased to natural language processing
    assert "NLP" in res.matching_ai_ml_technologies
    
    # AWS aliased to amazon web services
    assert "AWS" in res.matched_skills
    
    assert res.location_match == "Matched"

def test_missing_skills(matcher, mock_candidate):
    job = Job(
        title="Full Stack",
        company="Tech",
        location="New York",
        experience="Junior",
        description="Required: Python, Django, Docker, Kubernetes.",
        url="http"
    )
    
    res = matcher.match(job, mock_candidate)
    
    assert "django" in res.missing_skills
    assert "docker" in res.missing_skills
    assert "kubernetes" in res.missing_skills
    # Python is not missing
    assert "python" not in res.missing_skills
    
    assert res.location_match == "Not Matched"
    assert res.experience_match == "Not Matched"

def test_no_matches(matcher, mock_candidate):
    job = Job(
        title="Java Developer",
        company="Tech",
        location="London",
        experience="Junior",
        description="Need Java and Spring Boot.",
        url="http"
    )
    
    res = matcher.match(job, mock_candidate)
    assert len(res.matching_programming_languages) == 0
    assert len(res.matching_frameworks) == 0
    assert "java" in res.missing_skills
