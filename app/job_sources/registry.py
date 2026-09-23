import logging
from typing import List

from app.config import get_settings
from app.job_sources.base import BaseJobSource
from app.job_sources.arbeitnow_source import ArbeitnowSource
from app.job_sources.adzuna_source import AdzunaSource
from app.job_sources.remotive_source import RemotiveSource
from app.job_sources.aggregator import JobSourceAggregator

logger = logging.getLogger(__name__)

class SourceRegistry:
    """Manages active job sources based on configuration."""
    
    def __init__(self):
        self._sources: List[BaseJobSource] = []
        self._load_from_config()
        
    def _load_from_config(self):
        settings = get_settings()
        
        if settings.enable_arbeitnow:
            self.register(ArbeitnowSource())
            
        if settings.enable_adzuna:
            self.register(AdzunaSource())
            
        if settings.enable_remotive:
            self.register(RemotiveSource())
            
        if not self._sources:
            logger.warning("No job sources enabled! Search will return 0 results.")

    def register(self, source: BaseJobSource):
        self._sources.append(source)
        
    def get_aggregator(self) -> JobSourceAggregator:
        return JobSourceAggregator(self._sources)

# Global registry instance
source_registry = SourceRegistry()
