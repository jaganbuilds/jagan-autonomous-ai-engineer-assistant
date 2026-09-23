import logging
from typing import Optional
from google import genai
from google.genai import types
from pydantic import ValidationError

from app.config import get_settings
from app.profile.models import CandidateProfile

logger = logging.getLogger(__name__)

class ResumeProfileExtractor:
    """
    Extracts structured CandidateProfile from raw resume text using Gemini.
    """
    
    def __init__(self):
        settings = get_settings()
        self.api_key = settings.gemini_api_key
        self.client = None
        if self.api_key:
            self.client = genai.Client(api_key=self.api_key)
            
        self.model = 'gemini-2.5-flash'
        
    def extract_profile(self, resume_text: str) -> Optional[CandidateProfile]:
        """
        Extracts structured information from resume text.
        Returns None if extraction fails, text is empty, or validation fails.
        """
        if not resume_text or not resume_text.strip():
            logger.warning("Empty resume text provided for extraction.")
            return None
            
        if not self.client:
            logger.error("Gemini Client not initialized (missing API key).")
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
            logger.info("Sending resume text to Gemini for structured extraction.")
            
            response = self.client.models.generate_content(
                model=self.model,
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=CandidateProfile,
                    temperature=0.0
                )
            )
            
            # The API returns structured JSON based on our Pydantic schema
            if not response.text:
                logger.error("Received empty response from Gemini.")
                return None
                
            try:
                # Validation layer: strictly ensure the output matches our exact schema
                profile = CandidateProfile.model_validate_json(response.text)
                logger.info("Successfully extracted and validated CandidateProfile.")
                return profile
            except ValidationError as ve:
                logger.error("Gemini returned JSON that failed Pydantic validation.")
                # We do not log the full raw JSON for privacy reasons, only the fact it failed
                return None
                
        except Exception as e:
            logger.error(f"Error communicating with Gemini API: {type(e).__name__}")
            return None
