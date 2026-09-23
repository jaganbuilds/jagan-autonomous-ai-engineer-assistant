import logging
from typing import Optional
from pydantic import BaseModel, Field
from google import genai
from google.genai import types

from app.tools.registry import registry
from app.agents.state import state_manager
from app.profile.manager import profile_manager
from app.config import get_settings

logger = logging.getLogger(__name__)

class EmailDraft(BaseModel):
    """Structured output for an HR email draft."""
    subject: str
    body: str
    recipient: Optional[str] = None
    job_id: str

@registry.register(requires_confirmation=False)
def draft_hr_email(session_id: str, job_reference: str) -> dict:
    """
    Drafts a personalized HR/recruiter application email for a specific job.
    Use this when the user asks to "write an email", "apply for", or "draft an email" for a specific job.
    
    Args:
        session_id: Passed automatically. Do not modify.
        job_reference: The ID or position of the job (e.g., 'job_1', '1', 'job 2').
    """
    settings = get_settings()
    if not settings.gemini_api_key:
        return {
            "status": "error",
            "message": "Gemini API key is required to draft an email."
        }
        
    session = state_manager.get_session(session_id)
    if not session.job_results:
        return {
            "status": "no_jobs_in_session",
            "message": "No jobs found in the current session. Please search for jobs first."
        }
        
    job_pair = state_manager.get_job_result(session_id, job_reference)
    if not job_pair:
        return {
            "status": "job_not_found",
            "message": f"Could not find a job matching '{job_reference}'. Please specify a valid job ID."
        }
        
    profile = profile_manager.get_profile(session_id)
    if not profile:
        return {
            "status": "profile_required",
            "message": "A CandidateProfile is required to draft an email. Please upload a resume first."
        }
        
    # Extract data for grounding
    job = job_pair.job
    match_res = job_pair.match_result
    
    prompt = f"""
You are an expert career coach writing a highly professional, engaging job application email.
Your task is to draft an email from the candidate to the hiring manager/recruiter for the job below.

STRICT GROUNDING RULES:
1. ONLY use the skills, experience, and projects explicitly listed in the Candidate Profile.
2. DO NOT invent or hallucinate any work experience, certifications, degrees, projects, or skills.
3. If the job description does not mention an HR/recruiter email address, leave the recipient field null. Do not invent an email.
4. Keep the tone professional, confident, and concise.
5. Highlight the exact skills that matched, and naturally bridge any missing skills if related projects exist.

=== JOB DETAILS ===
Title: {job.title}
Company: {job.company}
Location: {job.location}
Experience Required: {job.experience}
Description:
{job.description}

=== CANDIDATE PROFILE ===
Name: {profile.name}
Education: {profile.education}
Skills: {', '.join(profile.skills)}
Programming Languages: {', '.join(profile.programming_languages)}
Frameworks: {', '.join(profile.frameworks)}
AI/ML Technologies: {', '.join(profile.ai_ml_technologies)}
Projects: {', '.join([p.name for p in profile.projects])}

=== MATCH RESULT ===
"""
    if match_res:
        prompt += f"""
Matched Skills: {', '.join(match_res.matched_skills)}
Missing Skills: {', '.join(match_res.missing_skills)}
"""
        if match_res.semantic_analysis and match_res.semantic_analysis.semantically_related_skills:
            prompt += f"Semantically Related Skills: {', '.join(match_res.semantic_analysis.semantically_related_skills)}\n"
            
    client = genai.Client(api_key=settings.gemini_api_key)
    try:
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=EmailDraft,
                temperature=0.7 # Slight creativity for email writing
            )
        )
        
        if not response.text:
            return {"status": "error", "message": "Failed to generate email draft."}
            
        draft = EmailDraft.model_validate_json(response.text)
        
        # Enforce job_id
        draft.job_id = job_reference
        
        return {
            "status": "success",
            "job_id": job_reference,
            "draft": draft.model_dump()
        }
    except Exception as e:
        logger.error(f"Failed to generate email draft: {e}")
        return {
            "status": "error",
            "message": f"An error occurred while generating the email draft: {type(e).__name__}"
        }
