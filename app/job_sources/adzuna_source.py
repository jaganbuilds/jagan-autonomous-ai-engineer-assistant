import json
import urllib.request
import urllib.parse
import urllib.error
import re
from typing import List, Optional
import logging

from app.job_sources.base import BaseJobSource, Job
from app.config import get_settings

logger = logging.getLogger(__name__)

class AdzunaSource(BaseJobSource):
    """
    Job source using the official Adzuna REST API.
    Requires ADZUNA_APP_ID and ADZUNA_APP_KEY.
    """
    
    def __init__(self):
        settings = get_settings()
        self.app_id = settings.adzuna_app_id
        self.app_key = settings.adzuna_app_key
        self.country = settings.adzuna_country
        self.base_url = f"https://api.adzuna.com/v1/api/jobs/{self.country}/search/1"

    def _strip_html(self, html_content: str) -> str:
        text = re.sub(r'<[^>]+>', ' ', html_content)
        return re.sub(r'\s+', ' ', text).strip()

    def search(self, role: Optional[str] = None, location: Optional[str] = None, experience: Optional[str] = None) -> List[Job]:
        if not self.app_id or not self.app_key:
            raise ValueError("configuration_missing: Adzuna credentials not configured.")
            
        params = {
            'app_id': self.app_id,
            'app_key': self.app_key,
            'results_per_page': 20,
        }
        
        # Build query
        query_parts = []
        if role:
            query_parts.append(role)
        if experience:
            # We add it to the search query if provided, though Adzuna has limited direct experience filtering in free tier
            query_parts.append(experience)
            
        if query_parts:
            params['what'] = " ".join(query_parts)
            
        if location:
            params['where'] = location

        query_string = urllib.parse.urlencode(params)
        url = f"{self.base_url}?{query_string}"
        
        try:
            req = urllib.request.Request(
                url, 
                headers={'User-Agent': 'JaganAI-Assistant/1.0', 'Accept': 'application/json'}
            )
            with urllib.request.urlopen(req, timeout=10) as response:
                if response.status != 200:
                    raise ValueError(f"api_error: Adzuna returned status {response.status}")
                data = json.loads(response.read().decode('utf-8'))
        except urllib.error.URLError as e:
            if isinstance(e.reason, TimeoutError):
                raise ValueError("timeout: Adzuna API request timed out.")
            raise ValueError(f"network_error: {e.reason}")
        except ValueError as e:
            raise e
        except Exception as e:
            raise ValueError(f"parsing_error: {str(e)}")
            
        jobs = []
        for item in data.get("results", []):
            title = item.get("title") or "Unknown Title"
            company_obj = item.get("company", {})
            company = company_obj.get("display_name") or "Unknown Company"
            
            loc_obj = item.get("location", {})
            loc_display = loc_obj.get("display_name") or "Unknown Location"
            
            desc = self._strip_html(item.get("description", ""))
            
            # Adzuna doesn't explicitly return experience level directly in free tier usually,
            # so we'll leave it empty unless we can reliably parse it. The prompt says:
            # "If experience is not explicitly available, leave it empty rather than inventing it."
            exp = ""
            
            jobs.append(Job(
                title=self._strip_html(title), # Sometimes title has bold tags
                company=company,
                location=loc_display,
                experience=exp,
                description=desc[:600] + "..." if len(desc) > 600 else desc,
                url=item.get("redirect_url") or "",
                source="adzuna",
                external_id=str(item.get("id")) if item.get("id") else ""
            ))
            
        return jobs
