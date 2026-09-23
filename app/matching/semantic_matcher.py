import logging
from typing import Optional
from google import genai
from google.genai import types
from pydantic import ValidationError

from app.config import get_settings
from app.job_sources.base import Job
from app.profile.models import CandidateProfile
from app.matching.models import MatchResult, SemanticMatchResult

logger = logging.getLogger(__name__)

class SemanticJobMatcher:
    """
    Optional semantic analysis layer powered by Gemini.
    Identifies related skills that the deterministic matcher may miss (e.g., 'Deep Learning' vs 'Neural Networks').
    Strictly forbids hallucinating unsupported skills.
    """
    
    def __init__(self):
        settings = get_settings()
        self.api_key = settings.gemini_api_key
        from app.llm_client import get_llm_client
        self.client = get_llm_client()
        self.model = 'gemini-2.5-flash'

    def analyze(self, job: Job, profile: CandidateProfile, deterministic_match: MatchResult) -> Optional[SemanticMatchResult]:
        """
        Runs semantic analysis on the job and profile, respecting the deterministic bounds.
        Fails safely (returns None) on any API or validation error.
        """
        if not self.client:
            logger.warning("Gemini Client not initialized (missing API key). Skipping semantic matching.")
            return None
            
        if not job.description or len(job.description.strip()) < 20:
            logger.info(f"Job '{job.title}' has insufficient description. Skipping semantic matching.")
            return None
            
        prompt = f"""
You are an expert AI technical recruiter assisting with candidate-to-job matching.
A deterministic engine has already evaluated this candidate against the job.
Your task is to identify SEMANTIC relationships the deterministic engine missed (e.g. "Deep Learning" conceptually matching "Neural Networks") and suggest actionable next steps.

STRICT RULES:
1. ONLY declare a semantic relationship if the candidate ACTUALLY has a related skill in their profile.
2. DO NOT invent or hallucinate skills, experience, projects, or certifications the candidate does not have.
3. Distinguish explicitly between semantically_related_skills (candidate has X, job wants Y, they are functionally equivalent) and additional_missing_skills (job wants Z, candidate clearly lacks it or anything like it).
4. Do NOT convert uncertain relationships into confirmed candidate skills.
5. Provide a short reasoning and a confidence score ("high", "medium", "low").
6. Provide a list of 1-3 actionable `next_steps` grounded ONLY in the profile and job (e.g., "Review the missing PyTorch requirement", "Highlight your Deep Learning project"). Do not invent candidate history.

=== JOB ===
Title: {job.title}
Experience Required: {job.experience}
Description:
{job.description}

=== CANDIDATE PROFILE ===
Experience: {profile.experience_level}
Skills: {', '.join(profile.skills)}
Programming: {', '.join(profile.programming_languages)}
Frameworks: {', '.join(profile.frameworks)}
AI/ML: {', '.join(profile.ai_ml_technologies)}
Projects: {', '.join([p.name for p in profile.projects])}

=== DETERMINISTIC MATCH RESULT ===
Already Matched: {', '.join(deterministic_match.matched_skills)}
Already Missing: {', '.join(deterministic_match.missing_skills)}
"""

        try:
            logger.info(f"Running semantic analysis for job: {job.title}")
            response = self.client.models.generate_content(
                model=self.model,
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=SemanticMatchResult,
                    temperature=0.0
                )
            )
            
            if not response.text:
                return None
                
            return SemanticMatchResult.model_validate_json(response.text)
            
        except ValidationError as ve:
            logger.error("Gemini returned invalid JSON for semantic matching.")
            return None
        except Exception as e:
            logger.error(f"Error during semantic matching: {type(e).__name__}")
            return None
