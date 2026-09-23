import threading
from typing import Optional, Dict
from app.profile.models import CandidateProfile

class ProfileManager:
    """
    In-memory session-based storage for user CandidateProfiles.
    Provides session isolation, copy safety, and thread-safe operations.
    """
    
    def __init__(self):
        self._profiles: Dict[str, CandidateProfile] = {}
        # Simple lock to ensure thread-safety across FastAPI async/threaded requests
        self._lock = threading.Lock()
        
    def save_profile(self, session_id: str, profile: CandidateProfile) -> None:
        """
        Saves a copy of the profile for the given session ID.
        Uses a deep copy to ensure external mutations do not affect internal state.
        """
        if not isinstance(profile, CandidateProfile):
            raise TypeError("Expected CandidateProfile")
            
        with self._lock:
            self._profiles[session_id] = profile.model_copy(deep=True)
            
    def get_profile(self, session_id: str) -> Optional[CandidateProfile]:
        """
        Retrieves a copy of the profile for the given session ID.
        Uses a deep copy to ensure the caller cannot mutate the internal state.
        Returns None if no profile exists for the session.
        """
        with self._lock:
            profile = self._profiles.get(session_id)
            if profile:
                return profile.model_copy(deep=True)
            return None
            
    def update_profile(self, session_id: str, profile: CandidateProfile) -> None:
        """Updates or replaces the profile for the given session ID."""
        # For an in-memory dictionary, update is semantically identical to save
        self.save_profile(session_id, profile)
        
    def delete_profile(self, session_id: str) -> None:
        """Safely deletes the profile for the given session ID if it exists."""
        with self._lock:
            self._profiles.pop(session_id, None)
            
    def has_profile(self, session_id: str) -> bool:
        """Checks if a profile exists for the given session ID."""
        with self._lock:
            return session_id in self._profiles

# Global instance for the application to use
profile_manager = ProfileManager()
