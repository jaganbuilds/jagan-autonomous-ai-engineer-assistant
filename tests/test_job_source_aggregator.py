import pytest
from unittest.mock import MagicMock
from app.job_sources.aggregator import JobSourceAggregator
from app.job_sources.base import Job

def test_aggregator_success(mock_db_repository):
    mock_src_1 = MagicMock()
    mock_src_1.search.return_value = [
        Job(title="J1", company="C1", location="L1", experience="E1", description="D1", url="http://u1", source="mock1", external_id="1")
    ]
    
    mock_src_2 = MagicMock()
    mock_src_2.search.return_value = [
        Job(title="J2", company="C2", location="L2", experience="E2", description="D2", url="http://u2", source="mock2", external_id="2")
    ]
    
    aggregator = JobSourceAggregator([mock_src_1, mock_src_2])
    res = aggregator.search()
    
    assert res.sources_attempted == 2
    assert res.sources_succeeded == 2
    assert len(res.source_errors) == 0
    assert len(res.jobs) == 2
    assert res.total_results_before_deduplication == 2
    assert res.total_results_after_deduplication == 2

def test_aggregator_partial_failure(mock_db_repository):
    mock_src_success = MagicMock()
    mock_src_success.__class__.__name__ = "SuccessSource"
    mock_src_success.search.return_value = [
        Job(title="J1", company="C1", location="L1", experience="E1", description="D1", url="http://u1", source="success", external_id="1")
    ]
    
    mock_src_fail = MagicMock()
    mock_src_fail.__class__.__name__ = "FailSource"
    mock_src_fail.search.side_effect = ValueError("timeout: Server did not respond")
    
    aggregator = JobSourceAggregator([mock_src_success, mock_src_fail])
    res = aggregator.search()
    
    assert res.sources_attempted == 2
    assert res.sources_succeeded == 1
    assert len(res.source_errors) == 1
    
    err = res.source_errors[0]
    assert err.source == "fail"
    assert err.error_type == "timeout"
    
    # Still got jobs from successful source
    assert len(res.jobs) == 1

def test_aggregator_deduplication(mock_db_repository):
    mock_src_1 = MagicMock()
    # Same job from source 1
    mock_src_1.search.return_value = [
        Job(title="J1", company="C1", location="L1", experience="E1", description="D1", url="http://same-url.com", source="src1")
    ]
    
    mock_src_2 = MagicMock()
    # Identical URL from source 2
    mock_src_2.search.return_value = [
        Job(title="J1", company="C1", location="L1", experience="E1", description="D1", url="http://same-url.com", source="src2")
    ]
    
    aggregator = JobSourceAggregator([mock_src_1, mock_src_2])
    res = aggregator.search()
    
    assert res.total_results_before_deduplication == 2
    assert res.total_results_after_deduplication == 1
    assert len(res.jobs) == 1
