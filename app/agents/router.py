from enum import Enum
from pydantic import BaseModel
import re

class Intent(str, Enum):
    GENERAL_CHAT = "general_chat"
    CALCULATE = "calculate"
    FILE_OPERATION = "file_operation"
    PROJECT_INFORMATION = "project_information"
    ORCHESTRATION = "orchestration"
    UNKNOWN = "unknown"
    
    # Placeholders for future extensibility
    # JOB_SEARCH = "job_search"
    # EMAIL_DRAFTING = "email_drafting"
    # EMAIL_SENDING = "email_sending"
    # RAG = "rag"
    # CODING_HELP = "coding_help"
    # VOICE_COMMAND = "voice_command"

class RouterResult(BaseModel):
    intent: Intent
    confidence: float = 1.0

class TaskRouter:
    """
    Analyzes user input to determine the core intent.
    Currently uses simple deterministic keyword/regex matching.
    Designed to be easily upgraded to an LLM-based classifier in the future.
    """
    def __init__(self):
        # Regex patterns for deterministic matching
        self.patterns = {
            Intent.CALCULATE: re.compile(r'\b(calculate|math|multiply|multiplied|divide|divided|add|subtract|plus|minus|times)\b|[\+\-\*\/]\s*\d', re.IGNORECASE),
            Intent.FILE_OPERATION: re.compile(r'\b(file|files|directory|directories|folder|folders)\b', re.IGNORECASE),
            Intent.PROJECT_INFORMATION: re.compile(r'\b(project structure|project info|analyze.*project|requirements\.txt|architecture)\b', re.IGNORECASE),
            Intent.ORCHESTRATION: re.compile(r'\b(find.*jobs|search.*jobs)\b', re.IGNORECASE),
            Intent.GENERAL_CHAT: re.compile(r'^(hello|hi|hey|how are you|who are you|thanks|thank you)\b', re.IGNORECASE)
        }

    def route(self, message: str) -> RouterResult:
        """Determines the intent of the message."""
        # Check against defined patterns
        for intent, pattern in self.patterns.items():
            if pattern.search(message):
                return RouterResult(intent=intent)
                
        # Default fallback
        return RouterResult(intent=Intent.UNKNOWN)

# Global router instance
router = TaskRouter()
