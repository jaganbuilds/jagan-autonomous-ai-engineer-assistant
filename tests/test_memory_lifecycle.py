import pytest
from app.memory.models import MemoryType, MemoryScope, MemoryImportance
from app.memory.lifecycle import lifecycle_manager
from app.memory.service import memory_service
from app.memory.extractor import memory_extractor

def test_normalization():
    # Casing and punctuation
    text1 = "I prefer Python."
    text2 = "I prefer python"
    assert lifecycle_manager.is_duplicate(text1, text2) is True
    
    # Whitespace
    text3 = "I   prefer Python  "
    assert lifecycle_manager.is_duplicate(text1, text3) is True

def test_conflict_categories():
    assert lifecycle_manager.get_conflict_category("User prefers Chennai for job opportunities.") == "preferred_job_location"
    assert lifecycle_manager.get_conflict_category("User's GitHub username is jaganbuilds.") == "github_username"
    
    # Unrelated
    assert lifecycle_manager.get_conflict_category("User is building Jagan AI.") is None

def test_lifecycle_update_preference(mock_db_repository):
    session_id = "test_lifecycle"
    
    # Initial
    mem1 = memory_service.remember(session_id, "User prefers Chennai for job opportunities.", memory_type=MemoryType.PREFERENCE, scope=MemoryScope.PERSONAL)
    assert mem1.id is not None
    
    # Update
    mem2 = memory_service.remember(session_id, "User prefers Bangalore for job opportunities.", memory_type=MemoryType.PREFERENCE, scope=MemoryScope.PERSONAL)
    
    # The IDs should be the same! It updated instead of creating new
    assert mem2.id == mem1.id
    
    # Check DB
    mems = memory_service.list_personal_memories()
    assert len(mems) == 1
    assert "Bangalore" in mems[0].content
    assert mems[0].updated_at != mems[0].created_at

def test_lifecycle_non_conflict(mock_db_repository):
    session_id = "test_lifecycle_2"
    
    # Projects shouldn't conflict by default
    mem1 = memory_service.remember(session_id, "User is building Jagan AI.", memory_type=MemoryType.PROJECT)
    mem2 = memory_service.remember(session_id, "User is building a FastAPI project.", memory_type=MemoryType.PROJECT)
    
    assert mem1.id != mem2.id
    assert len(memory_service.list_memories(session_id)) == 2

def test_lifecycle_duplicates(mock_db_repository):
    session_id = "test_lifecycle_dup"
    mem1 = memory_service.remember(session_id, "I use Python.")
    mem2 = memory_service.remember(session_id, "I use python") # same normalized
    
    assert mem1.id == mem2.id
    assert len(memory_service.list_memories(session_id)) == 1

def test_extraction_importance():
    # Normal project
    res = memory_extractor.extract("I'm building Jagan AI.")
    assert res.candidates[0].importance == MemoryImportance.NORMAL
    
    # Personal preference (high importance identity)
    res = memory_extractor.extract("My preferred job location is Chennai.")
    assert res.candidates[0].importance == MemoryImportance.HIGH
    assert res.candidates[0].scope == MemoryScope.PERSONAL
    
    # Explicit override (high)
    res = memory_extractor.extract("Remember that I am learning Java.")
    assert res.candidates[0].importance == MemoryImportance.HIGH
    assert res.candidates[0].scope == MemoryScope.PERSONAL
    
    # Temporary context (low)
    res = memory_extractor.extract("I'm building Jagan AI today.")
    assert res.candidates[0].importance == MemoryImportance.LOW
    assert res.candidates[0].scope == MemoryScope.SESSION

def test_temporal_update(mock_db_repository):
    session_id = "test_temporal"
    memory_service.remember(session_id, "User prefers Python for job opportunities.", memory_type=MemoryType.PREFERENCE, scope=MemoryScope.PERSONAL)
    
    # New statement extracted
    res = memory_extractor.extract("I now prefer Java for jobs.")
    assert res.has_memory
    
    candidate = res.candidates[0]
    
    # Store it
    mem2 = memory_service.remember(session_id, candidate.content, memory_type=candidate.memory_type, scope=candidate.scope)
    
    # Should update existing preference
    mems = memory_service.list_personal_memories()
    assert len(mems) == 1
    assert "Java" in mems[0].content
