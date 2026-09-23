import re
from typing import Optional, List
from datetime import datetime, timezone

from app.memory.models import Memory, MemoryType, MemorySource, MemoryScope, MemoryImportance
from app.memory.repository import get_memory_repository
from app.config import get_settings

class MemoryValidationError(ValueError):
    pass

class MemoryService:
    def __init__(self):
        # We will fetch the repository dynamically to support testing DI
        pass
        
    def _get_repo(self):
        return get_memory_repository()
        
    def _get_owner_id(self):
        return get_settings().jagan_ai_owner_id

    def _is_safe(self, content: str) -> bool:
        """
        Conservative secret detection.
        Rejects obvious API keys, passwords, or tokens.
        """
        # Obvious tokens/keys
        patterns = [
            r'ey[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}', # JWT
            r'sk-[a-zA-Z0-9]{20,}', # OpenAI/Anthropic/generic secret keys
            r'ghp_[a-zA-Z0-9]{36}', # GitHub tokens
            r'AIza[0-9A-Za-z-_]{35}', # Google API Keys
            r'(?i)(password|secret|api_key|access_token)[\s=:]+[^\s]{5,}', # Generic key-value secrets
        ]
        
        for pattern in patterns:
            if re.search(pattern, content):
                return False
        return True

    def remember(self, session_id: str, content: str, memory_type: MemoryType = MemoryType.GENERAL, source: MemorySource = MemorySource.USER, confidence: Optional[float] = None, scope: MemoryScope = MemoryScope.SESSION, importance: MemoryImportance = MemoryImportance.NORMAL) -> Memory:
        if not session_id or not session_id.strip():
            raise MemoryValidationError("session_id is required")
            
        if not content or not content.strip():
            raise MemoryValidationError("Memory content cannot be empty")
            
        content = content.strip()
        
        if not self._is_safe(content):
            raise MemoryValidationError("Memory content contains potential secrets and was rejected")
            
        repo = self._get_repo()
        owner_id = self._get_owner_id()
        
        from app.memory.lifecycle import lifecycle_manager
        
        # Check for duplicates or conflicts in the same scope
        existing_memories = repo.get_all_in_scope(session_id, owner_id, scope)
        candidate_category = lifecycle_manager.get_conflict_category(content)
        
        for mem in existing_memories:
            # 1. Duplicate check (harmless text differences)
            if mem.memory_type == memory_type and lifecycle_manager.is_duplicate(content, mem.content):
                return mem
                
            # 2. Conflict category check (e.g. updating location)
            if candidate_category and mem.memory_type == memory_type:
                existing_category = lifecycle_manager.get_conflict_category(mem.content)
                if candidate_category == existing_category:
                    # Update instead of creating new
                    updated_at = datetime.now(timezone.utc).isoformat()
                    return repo.update_memory(mem.id, mem.session_id, content, updated_at)
            
        memory = Memory(
            session_id=session_id,
            owner_id=owner_id,
            memory_type=memory_type,
            content=content,
            source=source,
            scope=scope,
            importance=importance,
            confidence=confidence
        )
        return repo.create_memory(memory)

    def get_memory_safe(self, memory_id: int, session_id: str) -> Optional[Memory]:
        if not session_id:
            return None
        return self._get_repo().get_memory_safe(memory_id, session_id, self._get_owner_id())

    def list_memories(self, session_id: str, memory_type: Optional[MemoryType] = None) -> List[Memory]:
        """Lists SESSION scope memories for the given session_id"""
        if not session_id:
            return []
        m_type = memory_type.value if memory_type else None
        return self._get_repo().list_memories(session_id, m_type)

    def list_personal_memories(self, memory_type: Optional[MemoryType] = None) -> List[Memory]:
        """Lists PERSONAL scope memories for the current owner"""
        owner_id = self._get_owner_id()
        m_type = memory_type.value if memory_type else None
        return self._get_repo().list_personal_memories(owner_id, m_type)

    def search_memories(self, session_id: str, query: str) -> List[Memory]:
        """
        Uses the existing retrieval logic to search both session and personal memories.
        Returns a flat list of memories matching the query.
        """
        from app.memory.retrieval import get_relevant_memories
        sess, pers = get_relevant_memories(session_id, query)
        return sess + pers

    def update_memory(self, memory_id: int, session_id: str, new_content: str) -> Optional[Memory]:
        if not session_id:
            raise MemoryValidationError("session_id is required")
            
        if not new_content or not new_content.strip():
            raise MemoryValidationError("Memory content cannot be empty")
            
        new_content = new_content.strip()
        
        if not self._is_safe(new_content):
            raise MemoryValidationError("Memory content contains potential secrets and was rejected")
            
        updated_at = datetime.now(timezone.utc).isoformat()
        return self._get_repo().update_memory(memory_id, session_id, new_content, updated_at)

    def forget_memory(self, memory_id: int, session_id: str) -> bool:
        if not session_id:
            return False
        return self._get_repo().delete_memory_safe(memory_id, session_id, self._get_owner_id())
        
    def forget(self, memory_id: int, session_id: str) -> bool:
        """Alias for backward compatibility"""
        return self.forget_memory(memory_id, session_id)
        
    def get_memory(self, memory_id: int, session_id: str) -> Optional[Memory]:
        """Alias for backward compatibility"""
        return self.get_memory_safe(memory_id, session_id)
        
    def clear_session_memories(self, session_id: str) -> int:
        if not session_id:
            return 0
        return self._get_repo().clear_session_memories(session_id)
        
    def clear_personal_memories(self) -> int:
        return self._get_repo().clear_personal_memories(self._get_owner_id())
        
    def clear_all_memories(self) -> int:
        return self._get_repo().clear_all_memories(self._get_owner_id())

memory_service = MemoryService()
