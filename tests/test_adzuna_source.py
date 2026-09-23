import pytest
import json
from unittest.mock import patch, MagicMock
from app.job_sources.adzuna_source import AdzunaSource
from app.config import Settings

@pytest.fixture
def mock_adzuna_settings():
    return Settings(
        adzuna_app_id="fake_id",
        adzuna_app_key="fake_key",
        adzuna_country="gb"
    )

@patch("app.job_sources.adzuna_source.get_settings")
@patch("app.job_sources.adzuna_source.urllib.request.urlopen")
def test_adzuna_source_success(mock_urlopen, mock_settings_getter, mock_adzuna_settings):
    mock_settings_getter.return_value = mock_adzuna_settings
    source = AdzunaSource()
    
    mock_response = MagicMock()
    mock_response.status = 200
    mock_response.read.return_value = json.dumps({
        "results": [
            {
                "id": "123",
                "title": "<strong>Python</strong> Developer",
                "company": {"display_name": "Tech Corp"},
                "location": {"display_name": "London"},
                "description": "We need a <p>Python</p> developer.",
                "redirect_url": "http://adzuna.com/123"
            }
        ]
    }).encode('utf-8')
    
    # Needs to act as a context manager
    mock_urlopen.return_value.__enter__.return_value = mock_response
    
    jobs = source.search(role="Python", location="London")
    
    assert len(jobs) == 1
    job = jobs[0]
    
    # HTML stripped
    assert job.title == "Python Developer"
    assert job.description == "We need a Python developer."
    assert job.company == "Tech Corp"
    assert job.location == "London"
    assert job.external_id == "123"
    assert job.url == "http://adzuna.com/123"
    assert job.source == "adzuna"

@patch("app.job_sources.adzuna_source.get_settings")
def test_adzuna_source_missing_credentials(mock_settings_getter):
    mock_settings_getter.return_value = Settings(adzuna_app_id="", adzuna_app_key="")
    source = AdzunaSource()
    
    with pytest.raises(ValueError, match="configuration_missing"):
        source.search()
