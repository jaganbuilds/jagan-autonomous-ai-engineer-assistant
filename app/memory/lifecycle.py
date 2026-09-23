import re
import unicodedata
from typing import Optional
from app.memory.models import MemoryCandidate, Memory, MemoryScope, MemoryImportance, MemoryType

class MemoryLifecycleManager:
    """
    Handles memory normalization, duplicate checking logic, and conflict categories.
    """
    
    def __init__(self):
        # We define explicit deterministic conflict categories based on regex matching.
        # Format: (pattern, category)
        self.conflict_rules = [
            (r"(?i)prefers?\s+.+?\s+for\s+job\s+opportunities", "preferred_job_location"),
            (r"(?i)prefers?\s+.*?(?:python|java|go|rust|c\+\+|javascript|typescript|ruby)", "preferred_programming_language"),
            (r"(?i)github\s+username\s+is", "github_username"),
            (r"(?i)prefers?\s+.+?\s+role", "preferred_role"),
            (r"(?i)prefers?\s+.+?\s+framework", "preferred_framework"),
        ]
        
    def normalize_text(self, text: str) -> str:
        """
        Normalizes text for duplicate comparison:
        - Unicode normalization
        - Lowercasing (for comparison only, doesn't destroy original)
        - Removes punctuation at the end of string
        - Normalizes multiple spaces to a single space
        """
        if not text:
            return ""
        
        # Unicode normalization
        text = unicodedata.normalize('NFKD', text)
        
        # Lowercase
        text = text.lower()
        
        # Remove trailing punctuation
        text = re.sub(r'[.,;!]+$', '', text)
        
        # Normalize whitespace
        text = re.sub(r'\s+', ' ', text)
        
        return text.strip()

    def is_duplicate(self, candidate_content: str, existing_content: str) -> bool:
        """Determines if two memory strings are deterministic duplicates."""
        return self.normalize_text(candidate_content) == self.normalize_text(existing_content)

    def get_conflict_category(self, content: str) -> Optional[str]:
        """
        Determines if the memory content falls into a known safe conflict category.
        """
        for pattern, category in self.conflict_rules:
            if re.search(pattern, content):
                return category
        return None

lifecycle_manager = MemoryLifecycleManager()
