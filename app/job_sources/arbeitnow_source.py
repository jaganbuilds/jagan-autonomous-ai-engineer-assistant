import json
import urllib.request
import urllib.error
import re
from typing import List, Optional
import logging

from app.job_sources.base import BaseJobSource, Job

logger = logging.getLogger(__name__)

class ArbeitnowSource(BaseJobSource):
    """
    Legitimate, public API source using Arbeitnow.
    Requires no API keys and is free for public use.
    Endpoint: https://www.arbeitnow.com/api/job-board-api
    """
    API_URL = "https://www.arbeitnow.com/api/job-board-api"
    
    def _strip_html(self, html_content: str) -> str:
        """Strips HTML tags from the description for cleaner LLM consumption."""
        text = re.sub(r'<[^>]+>', ' ', html_content)
        # Clean up multiple spaces
        return re.sub(r'\s+', ' ', text).strip()

    def search(self, role: Optional[str] = None, location: Optional[str] = None, experience: Optional[str] = None) -> List[Job]:
        try:
            req = urllib.request.Request(
                self.API_URL, 
                headers={'User-Agent': 'JaganAI-Assistant/1.0'}
            )
            with urllib.request.urlopen(req, timeout=10) as response:
                if response.status != 200:
                    logger.error(f"Arbeitnow API returned status {response.status}")
                    return []
                    
                data = json.loads(response.read().decode('utf-8'))
                
        except urllib.error.URLError as e:
            logger.error(f"Network error fetching jobs from Arbeitnow: {e}")
            return []
        except Exception as e:
            logger.error(f"Unexpected error parsing Arbeitnow response: {e}")
            return []
            
        jobs = []
        for item in data.get("data", []):
            title = item.get("title") or "Unknown Title"
            company = item.get("company_name") or "Unknown Company"
            
            loc = item.get("location") or ""
            if item.get("remote"):
                loc = f"{loc} (Remote)" if loc else "Remote"
            if not loc:
                loc = "Not specified"
                
            raw_desc = item.get("description") or ""
            clean_desc = self._strip_html(raw_desc)
            
            # Arbeitnow does not explicitly define experience, so we try to extract or default
            exp = "Not specified"
            tags = item.get("tags", [])
            if "senior" in tags or "Senior" in title:
                exp = "Senior"
            elif "junior" in tags or "Junior" in title:
                exp = "Junior"
                
            job = Job(
                title=title,
                company=company,
                location=loc,
                experience=exp,
                # Truncate description to prevent token overload
                description=clean_desc[:600] + "..." if len(clean_desc) > 600 else clean_desc,
                url=item.get("url") or "",
                source="arbeitnow",
                external_id=item.get("slug") or str(item.get("id")) or ""
            )
            jobs.append(job)
            
        # The API returns a general recent feed. We apply filters client-side.
        if role:
            r_lower = role.lower()
            jobs = [j for j in jobs if r_lower in j.title.lower() or r_lower in j.description.lower()]
            
        if location:
            l_lower = location.lower()
            jobs = [j for j in jobs if l_lower in j.location.lower()]
            
        if experience:
            e_lower = experience.lower()
            jobs = [j for j in jobs if e_lower in j.experience.lower() or e_lower in j.description.lower()]
            
        # Return a maximum of 10 results to fit comfortably in LLM context
        return jobs[:10]
