import pytest
import json
from unittest.mock import MagicMock, patch
from urllib.error import URLError
from app.job_sources.arbeitnow_source import ArbeitnowSource

@pytest.fixture
def source():
    return ArbeitnowSource()

@pytest.fixture
def mock_api_response():
    return {
        "data": [
            {
                "slug": "job-1",
                "company_name": "Test Company",
                "title": "Software Engineer",
                "description": "<p>We are looking for a <strong>Senior</strong> developer.</p>",
                "remote": True,
                "url": "https://example.com/job1",
                "tags": ["senior", "python"],
                "location": "Berlin"
            },
            {
                "slug": "job-2",
                "company_name": "Other Co",
                "title": "Junior Python Dev",
                "description": "Entry level job.",
                "remote": False,
                "url": "https://example.com/job2",
                "tags": ["junior"],
                "location": "Munich"
            }
        ]
    }

@patch("urllib.request.urlopen")
def test_arbeitnow_successful_fetch(mock_urlopen, source, mock_api_response):
    # Setup mock
    mock_response = MagicMock()
    mock_response.status = 200
    mock_response.read.return_value = json.dumps(mock_api_response).encode('utf-8')
    # urlopen behaves as a context manager
    mock_urlopen.return_value.__enter__.return_value = mock_response
    
    jobs = source.search()
    
    assert len(jobs) == 2
    
    # Test normalization
    assert jobs[0].title == "Software Engineer"
    assert jobs[0].company == "Test Company"
    assert jobs[0].location == "Berlin (Remote)"
    assert jobs[0].experience == "Senior"
    assert jobs[0].description == "We are looking for a Senior developer." # HTML stripped
    
    assert jobs[1].title == "Junior Python Dev"
    assert jobs[1].location == "Munich"
    assert jobs[1].experience == "Junior"

@patch("urllib.request.urlopen")
def test_arbeitnow_filtering(mock_urlopen, source, mock_api_response):
    mock_response = MagicMock()
    mock_response.status = 200
    mock_response.read.return_value = json.dumps(mock_api_response).encode('utf-8')
    mock_urlopen.return_value.__enter__.return_value = mock_response
    
    # Role filter
    res = source.search(role="Python")
    assert len(res) == 1
    assert res[0].title == "Junior Python Dev"
    
    # Location filter
    res2 = source.search(location="Berlin")
    assert len(res2) == 1
    assert res2[0].company == "Test Company"

@patch("urllib.request.urlopen")
def test_arbeitnow_api_error(mock_urlopen, source):
    mock_response = MagicMock()
    mock_response.status = 500
    mock_urlopen.return_value.__enter__.return_value = mock_response
    
    jobs = source.search()
    assert len(jobs) == 0

@patch("urllib.request.urlopen")
def test_arbeitnow_network_error(mock_urlopen, source):
    mock_urlopen.side_effect = URLError("Network down")
    
    jobs = source.search()
    assert len(jobs) == 0

@patch("urllib.request.urlopen")
def test_arbeitnow_malformed_json(mock_urlopen, source):
    mock_response = MagicMock()
    mock_response.status = 200
    mock_response.read.return_value = b"Not JSON"
    mock_urlopen.return_value.__enter__.return_value = mock_response
    
    jobs = source.search()
    assert len(jobs) == 0
