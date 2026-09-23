import re
from typing import List

from app.memory.models import MemoryCandidate, MemoryExtractionResult, MemoryType, MemorySource, MemoryScope, MemoryImportance
from app.memory.service import memory_service

class MemoryExtractor:
    """
    Deterministic Memory Extraction Engine.
    Produces candidates for persistent memory without writing to the database.
    """

    def __init__(self):
        # We define simple regex-based extraction rules
        # (pattern, memory_type, confidence, extraction_template, reason, scope, importance)
        self.rules = [
            # Profile: GitHub
            (
                r"(?i)my\s+(?:new\s+)?github(?:\s+username|\s+profile)?\s+(?:is|:|equals)\s+([a-zA-Z0-9_-]+)",
                MemoryType.GENERAL,
                0.9,
                "User's GitHub username is {0}.",
                "Explicit GitHub profile statement.",
                MemoryScope.PERSONAL,
                MemoryImportance.HIGH
            ),
            (
                r"(?i)i\s+(?:now\s+)?use\s+github\s+username\s+([a-zA-Z0-9_-]+)",
                MemoryType.GENERAL,
                0.9,
                "User's GitHub username is {0}.",
                "Explicit GitHub profile statement.",
                MemoryScope.PERSONAL,
                MemoryImportance.HIGH
            ),
            
            # Preference
            (
                r"(?i)my\s+(?:new\s+)?preferred\s+(?:job\s+)?location\s+is\s+([a-zA-Z0-9_\-\s]+?)(?:\.|$|and)",
                MemoryType.PREFERENCE,
                0.9,
                "User prefers {0} for job opportunities.",
                "Explicit location preference statement.",
                MemoryScope.PERSONAL,
                MemoryImportance.HIGH
            ),
            (
                r"(?i)i\s+(?:now\s+)?prefer\s+([a-zA-Z0-9_\-\s]+?)\s+for\s+jobs",
                MemoryType.PREFERENCE,
                0.9,
                "User prefers {0} for job opportunities.",
                "Explicit location preference statement.",
                MemoryScope.PERSONAL,
                MemoryImportance.HIGH
            ),
            (
                r"(?i)i\s+(?:now\s+)?prefer\s+([a-zA-Z0-9_\-\s]+?)(?:\.|$|and)",
                MemoryType.PREFERENCE,
                0.8,
                "User prefers {0}.",
                "Explicit preference statement.",
                MemoryScope.PERSONAL,
                MemoryImportance.HIGH
            ),
            
            # Project
            (
                r"(?i)i\s+am\s+building\s+(?:a\s+project\s+called\s+)?([a-zA-Z0-9_\-\s]+?)(?:\.|$|and)",
                MemoryType.PROJECT,
                0.9,
                "User is building a project called {0}.",
                "Explicit project building statement.",
                MemoryScope.SESSION,
                MemoryImportance.NORMAL
            ),
            (
                r"(?i)i\'?m\s+building\s+(?:a\s+project\s+called\s+)?([a-zA-Z0-9_\-\s]+?)(?:\.|$|and)",
                MemoryType.PROJECT,
                0.9,
                "User is building a project called {0}.",
                "Explicit project building statement.",
                MemoryScope.SESSION,
                MemoryImportance.NORMAL
            ),
            (
                r"(?i)i\s+am\s+working\s+on\s+([a-zA-Z0-9_\-\s]+?)(?:\.|$|and)",
                MemoryType.PROJECT,
                0.8,
                "User is working on {0}.",
                "Explicit project working statement.",
                MemoryScope.SESSION,
                MemoryImportance.NORMAL
            ),
            (
                r"(?i)i\'?m\s+working\s+on\s+([a-zA-Z0-9_\-\s]+?)(?:\.|$|and)",
                MemoryType.PROJECT,
                0.8,
                "User is working on {0}.",
                "Explicit project working statement.",
                MemoryScope.SESSION,
                MemoryImportance.NORMAL
            ),
            
            # Learning
            (
                r"(?i)i\s+am\s+(?:currently\s+)?learning\s+([a-zA-Z0-9_\-\s]+?)(?:\.|$|and)",
                MemoryType.LEARNING,
                0.9,
                "User is learning {0}.",
                "Explicit learning statement.",
                MemoryScope.SESSION,
                MemoryImportance.NORMAL
            ),
            (
                r"(?i)i\'?m\s+(?:currently\s+)?learning\s+([a-zA-Z0-9_\-\s]+?)(?:\.|$|and)",
                MemoryType.LEARNING,
                0.9,
                "User is learning {0}.",
                "Explicit learning statement.",
                MemoryScope.SESSION,
                MemoryImportance.NORMAL
            ),
            
            # General tech stack usage
            (
                r"(?i)i\s+(?:now\s+)?use\s+([a-zA-Z0-9_\-\s]+?)(?:\.|$|and)",
                MemoryType.GENERAL,
                0.8,
                "User uses {0}.",
                "Explicit usage statement.",
                MemoryScope.SESSION,
                MemoryImportance.NORMAL
            )
        ]
        
        self.negation_patterns = [
            r"(?i)don'?t",
            r"(?i)do\s+not",
            r"(?i)not\s+",
            r"(?i)no\s+"
        ]
        
        # We no longer strictly skip temporary patterns, but we might downgrade them to SESSION
        # if they matched something that normally would be PERSONAL.
        self.temporary_patterns = [
            r"(?i)\btoday\b",
            r"(?i)\byesterday\b",
            r"(?i)\btomorrow\b",
            r"(?i)\bthis\s+week\b",
            r"(?i)\bthis\s+month\b"
        ]
        
        self.explicit_remember_patterns = [
            r"(?i)remember\s+that\b",
            r"(?i)remember\s+this\b",
            r"(?i)keep\s+this\s+in\s+memory\b",
            r"(?i)remember\b"
        ]
        
        self.memory_command_patterns = [
            r"(?i)\bshow\s+(?:my\s+)?memor(?:y|ies)\b",
            r"(?i)\bwhat\s+do\s+you\s+remember\b",
            r"(?i)\bforget\b",
            r"(?i)\bclear\s+(?:my\s+|this\s+session\'?s\s+)?memor(?:y|ies)\b",
            r"(?i)\bdelete\s+(?:my\s+|that\s+)?memor(?:y|ies)\b",
            r"(?i)\bsearch\s+(?:my\s+)?memor(?:y|ies)\b"
        ]

    def _clean_match(self, text: str) -> str:
        # Strip trailing punctuation, extra spaces, fix basic casing if appropriate
        val = text.strip()
        if val.endswith('.') or val.endswith(',') or val.endswith(';'):
            val = val[:-1]
        return val.strip()

    def _has_negation(self, text: str) -> bool:
        for pat in self.negation_patterns:
            if re.search(pat, text):
                return True
        return False
        
    def _has_temporary_context(self, text: str) -> bool:
        for pat in self.temporary_patterns:
            if re.search(pat, text):
                return True
        return False
        
    def _has_explicit_remember(self, text: str) -> bool:
        for pat in self.explicit_remember_patterns:
            if re.search(pat, text):
                return True
        return False
        
    def _is_memory_command(self, text: str) -> bool:
        for pat in self.memory_command_patterns:
            if re.search(pat, text):
                return True
        return False

    def extract(self, text: str) -> MemoryExtractionResult:
        if not text or not text.strip():
            return MemoryExtractionResult(has_memory=False, candidates=[])
            
        if self._is_memory_command(text):
            return MemoryExtractionResult(has_memory=False, candidates=[])
            
        if not memory_service._is_safe(text):
            return MemoryExtractionResult(has_memory=False, candidates=[])
            
        candidates: List[MemoryCandidate] = []
        
        clauses = re.split(r'\s+and\s+|\.|\;|\,', text)
        has_explicit = self._has_explicit_remember(text)
        
        for clause in clauses:
            clause = clause.strip()
            if not clause:
                continue
                
            if self._has_negation(clause):
                continue
                
            # If clause has temporary context, it definitely is session scoped.
            is_temporary = self._has_temporary_context(clause)
            
            # Evaluate rules
            for pattern, mem_type, conf, template, reason, default_scope, default_importance in self.rules:
                match = re.search(pattern, clause)
                if match:
                    extracted_val = self._clean_match(match.group(1))
                    
                    if extracted_val.lower() == "a project called":
                         continue
                         
                    content = template.format(extracted_val)
                    
                    # Classification
                    final_scope = default_scope
                    final_importance = default_importance
                    
                    if is_temporary:
                        final_scope = MemoryScope.SESSION
                        final_importance = MemoryImportance.LOW
                    elif has_explicit:
                        final_scope = MemoryScope.PERSONAL
                        final_importance = MemoryImportance.HIGH
                    
                    candidates.append(MemoryCandidate(
                        memory_type=mem_type,
                        content=content,
                        source=MemorySource.USER,
                        scope=final_scope,
                        importance=final_importance,
                        confidence=conf,
                        reason=reason
                    ))
                    break
                    
        return MemoryExtractionResult(
            has_memory=len(candidates) > 0,
            candidates=candidates
        )

memory_extractor = MemoryExtractor()
