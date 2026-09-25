from typing import Optional, Dict
from app.tools.registry import registry
from app.resume.parser import ResumeParser
from app.resume.profile_extractor import ResumeProfileExtractor
from app.profile.manager import profile_manager

# Instantiate the parser and extractor globally for the tool
_parser = ResumeParser()
_extractor = ResumeProfileExtractor()

@registry.register(requires_confirmation=False)
def extract_and_save_profile(session_id: str, file_path: str) -> dict:
    """
    Extracts a candidate profile from a local PDF resume and saves it for the current session.
    Use this when a user wants you to read or analyze their resume.
    
    Args:
        session_id: Passed automatically. Do not modify.
        file_path: The absolute or relative local path to the user's PDF resume file.
    """
    # 1. Extract text from PDF using the secure, deterministic local parser
    text = _parser.extract_text(file_path)
    
    if not text:
        return {
            "status": "error",
            "error": "Failed to read resume. Ensure the file is a valid, readable PDF and exists at the specified path."
        }
        
    # 2. Extract structured profile using LLM
    profile = _extractor.extract_profile(text)
    
    if not profile:
        # Check if it was an API key issue or an extraction/JSON issue
        if not _extractor.api_key:
            return {
                "status": "error",
                "error": "Configuration Error: OpenRouter API key is missing. Cannot extract profile."
            }
        return {
            "status": "error",
            "error": "Failed to extract a valid candidate profile from the resume text."
        }
        
    # 3. Save profile for the session securely
    try:
        profile_manager.save_profile(session_id, profile)
    except Exception as e:
        return {
            "status": "error",
            "error": "An internal error occurred while saving the profile."
        }
        
    # 4. Return a structured success response (omitting full project details to keep context light)
    return {
        "status": "success",
        "message": "Candidate profile created successfully.",
        "profile": {
            "name": profile.name,
            "experience_level": profile.experience_level,
            "target_roles": profile.target_roles,
            "preferred_locations": profile.preferred_locations,
            "skills": profile.skills,
            "programming_languages": profile.programming_languages,
            "frameworks": profile.frameworks,
            "databases": profile.databases,
            "ai_ml_technologies": profile.ai_ml_technologies
        }
    }
