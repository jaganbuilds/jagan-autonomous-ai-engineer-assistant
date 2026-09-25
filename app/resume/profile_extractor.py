import logging
from typing import Optional
from pydantic import ValidationError

from app.config import get_settings
from app.profile.models import CandidateProfile

logger = logging.getLogger(__name__)

class ResumeProfileExtractor:
    """
    Extracts structured CandidateProfile from raw resume text using LLM.
    """
    
    def __init__(self):
        settings = get_settings()
        self.api_key = settings.openrouter_api_key
        
    def extract_profile(self, resume_text: str) -> Optional[CandidateProfile]:
        """
        Extracts structured information from resume text.
        Returns None if extraction fails, text is empty, or validation fails.
        """
        if not resume_text or not resume_text.strip():
            logger.warning("Empty resume text provided for extraction.")
            return None
            
        if not self.api_key:
            logger.error("API key not initialized.")
            return None

        prompt = f"""
You are an expert technical recruiter AI. Extract structured profile information from the following resume text.

STRICT RULES:
1. ONLY extract information explicitly stated or heavily implied by the text.
2. DO NOT invent, guess, or hallucinate skills, education, or experience.
3. DO NOT infer unsupported technologies (e.g. if it says "SQL", don't assume "PostgreSQL" unless specified).
4. If information for a field is missing, leave it empty (or use "Unknown" for strings).
5. Projects must preserve their name, description, and exact technologies used.
6. Extract programming languages, frameworks, databases, and AI/ML tech into their distinct arrays.

Resume Text:
{resume_text}
"""
        
        try:
            logger.info("Sending resume text to LLM for structured extraction.")
            
            from app.llm.gateway import gateway
            profile = gateway.generate_json(
                prompt,
                schema=CandidateProfile,
                temperature=0.0
            )
            
            if not profile:
                logger.error("Received empty response from LLM.")
                return None
                
            logger.info("Successfully extracted and validated CandidateProfile.")
            return profile
                
        except Exception as e:
            logger.error(f"Error communicating with LLM API: {type(e).__name__} - {str(e)}")
            return None
