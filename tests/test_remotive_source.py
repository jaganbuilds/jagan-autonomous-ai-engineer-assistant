import pytest
import json
from unittest.mock import patch, MagicMock
from app.job_sources.remotive_source import RemotiveSource

@patch("app.job_sources.remotive_source.urllib.request.urlopen")
def test_remotive_source_success(mock_urlopen):
    source = RemotiveSource()
    
    mock_response = MagicMock()
    mock_response.status = 200
    mock_response.read.return_value = json.dumps({
        "jobs": [
            {
                "id": 999,
                "title": "Remote Go Dev",
                "company_name": "GoCo",
                "candidate_required_location": "Worldwide",
                "description": "Golang",
                "url": "http://remotive.com/999"
            }
        ]
    }).encode('utf-8')
    
    mock_urlopen.return_value.__enter__.return_value = mock_response
    
    jobs = source.search()
    
    assert len(jobs) == 1
    job = jobs[0]
    
    assert job.title == "Remote Go Dev"
    assert job.company == "GoCo"
    assert job.location == "Remote (Worldwide)"
    assert job.external_id == "999"
    assert job.source == "remotive"

@patch("app.job_sources.remotive_source.urllib.request.urlopen")
def test_remotive_source_location_filtering(mock_urlopen):
    source = RemotiveSource()
    
    mock_response = MagicMock()
    mock_response.status = 200
    mock_response.read.return_value = json.dumps({
        "jobs": [
            {
                "id": 1,
                "title": "US Only Dev",
                "candidate_required_location": "USA Only"
            },
            {
                "id": 2,
                "title": "Global Dev",
                "candidate_required_location": "Anywhere"
            },
            {
                "id": 3,
                "title": "Europe Dev",
                "candidate_required_location": "Europe"
            }
        ]
    }).encode('utf-8')
    
    mock_urlopen.return_value.__enter__.return_value = mock_response
    
    # Search for Europe
    jobs = source.search(location="Europe")
    
    assert len(jobs) == 2
    titles = [j.title for j in jobs]
    assert "Europe Dev" in titles
    assert "Global Dev" in titles
    assert "US Only Dev" not in titles
