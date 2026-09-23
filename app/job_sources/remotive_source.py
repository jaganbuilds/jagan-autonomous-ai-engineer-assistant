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

class RemotiveSource(BaseJobSource):
    """
    Job source using the public Remotive API for remote jobs.
    Endpoint: https://remotive.com/api/remote-jobs
    """
    API_URL = "https://remotive.com/api/remote-jobs"

    def _strip_html(self, html_content: str) -> str:
        text = re.sub(r'<[^>]+>', ' ', html_content)
        return re.sub(r'\s+', ' ', text).strip()

    def search(self, role: Optional[str] = None, location: Optional[str] = None, experience: Optional[str] = None) -> List[Job]:
        params = {}
        if role:
            params['search'] = role
            
        # Remotive has category limits but we will just use general search
        query_string = urllib.parse.urlencode(params)
        url = f"{self.API_URL}?{query_string}" if query_string else self.API_URL
        
        try:
            req = urllib.request.Request(
                url, 
                headers={'User-Agent': 'JaganAI-Assistant/1.0'}
            )
            with urllib.request.urlopen(req, timeout=10) as response:
                if response.status != 200:
                    raise ValueError(f"api_error: Remotive returned status {response.status}")
                data = json.loads(response.read().decode('utf-8'))
        except urllib.error.URLError as e:
            if isinstance(e.reason, TimeoutError):
                raise ValueError("timeout: Remotive API request timed out.")
            raise ValueError(f"network_error: {e.reason}")
        except ValueError as e:
            raise e
        except Exception as e:
            raise ValueError(f"parsing_error: {str(e)}")
            
        jobs = []
        for item in data.get("jobs", []):
            title = item.get("title") or "Unknown Title"
            company = item.get("company_name") or "Unknown Company"
            
            # Remotive is remote-first. It provides candidate_required_location.
            req_location = item.get("candidate_required_location") or ""
            
            # If the user asked for a specific location, and this job is geographically restricted
            # to somewhere else, we filter it out.
            # But Remotive often says "Worldwide" or "Anywhere" which is fine.
            if location and location.lower() not in req_location.lower() and "worldwide" not in req_location.lower() and "anywhere" not in req_location.lower():
                continue
                
            loc_display = f"Remote ({req_location})" if req_location else "Remote"
            
            desc = self._strip_html(item.get("description", ""))
            
            jobs.append(Job(
                title=title,
                company=company,
                location=loc_display,
                experience="", # Remotive doesn't explicitly provide experience as a top-level field
                description=desc[:600] + "..." if len(desc) > 600 else desc,
                url=item.get("url") or "",
                source="remotive",
                external_id=str(item.get("id")) if item.get("id") else ""
            ))
            
        return jobs
