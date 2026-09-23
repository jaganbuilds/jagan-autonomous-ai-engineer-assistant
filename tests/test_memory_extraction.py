import pytest
from app.memory import memory_extractor, MemoryType

def test_no_memory_question():
    result = memory_extractor.extract("What is FastAPI?")
    assert result.has_memory is False
    assert len(result.candidates) == 0

def test_explicit_preference():
    result = memory_extractor.extract("My preferred job location is Chennai.")
    assert result.has_memory is True
    assert len(result.candidates) == 1
    assert result.candidates[0].memory_type == MemoryType.PREFERENCE
    assert result.candidates[0].content == "User prefers Chennai for job opportunities."

def test_project_statement():
    result = memory_extractor.extract("I'm building Jagan AI.")
    assert result.has_memory is True
    assert len(result.candidates) == 1
    assert result.candidates[0].memory_type == MemoryType.PROJECT
    assert result.candidates[0].content == "User is building a project called Jagan AI."

def test_github_profile_statement():
    result = memory_extractor.extract("My GitHub username is jaganbuilds.")
    assert result.has_memory is True
    assert len(result.candidates) == 1
    assert result.candidates[0].memory_type == MemoryType.GENERAL
    assert result.candidates[0].content == "User's GitHub username is jaganbuilds."

def test_learning_statement():
    result = memory_extractor.extract("I'm learning LangChain.")
    assert result.has_memory is True
    assert len(result.candidates) == 1
    assert result.candidates[0].memory_type == MemoryType.LEARNING
    assert result.candidates[0].content == "User is learning LangChain."

def test_multiple_candidates():
    result = memory_extractor.extract("I prefer Chennai for jobs and I'm building Jagan AI.")
    assert result.has_memory is True
    assert len(result.candidates) == 2
    types = [c.memory_type for c in result.candidates]
    assert MemoryType.PREFERENCE in types
    assert MemoryType.PROJECT in types

def test_empty_input():
    assert memory_extractor.extract("").has_memory is False
    assert memory_extractor.extract("   ").has_memory is False
    assert memory_extractor.extract(None).has_memory is False

def test_negation():
    result = memory_extractor.extract("I don't prefer Chennai.")
    assert result.has_memory is False
    assert len(result.candidates) == 0
    
    result2 = memory_extractor.extract("I'm not learning Java.")
    assert result2.has_memory is False

def test_temporary_context():
    from app.memory.models import MemoryScope
    
    # Normally "I am in Chennai" doesn't match our rules, but "I'm building Jagan AI today" does
    result = memory_extractor.extract("I'm building Jagan AI today.")
    assert result.has_memory is True
    assert result.candidates[0].scope == MemoryScope.SESSION
    
    result2 = memory_extractor.extract("I prefer Chennai for jobs today.")
    assert result2.has_memory is True
    assert result2.candidates[0].scope == MemoryScope.SESSION

def test_explicit_remember():
    from app.memory.models import MemoryScope
    
    # Learning is usually SESSION scope
    result1 = memory_extractor.extract("I'm learning LangChain.")
    assert result1.candidates[0].scope == MemoryScope.SESSION
    
    # But explicitly remembering makes it PERSONAL
    result2 = memory_extractor.extract("Remember that I'm learning LangChain.")
    assert result2.candidates[0].scope == MemoryScope.PERSONAL

def test_secret_protection():
    result = memory_extractor.extract("My preferred job location is Chennai and API_KEY=ABCDE12345.")
    # Because of the secret, the entire message is conservatively rejected
    assert result.has_memory is False
    assert len(result.candidates) == 0

def test_no_side_effects(mock_db_repository):
    from app.memory.repository import get_memory_repository
    repo = get_memory_repository()
    
    # Extract memory
    memory_extractor.extract("My preferred job location is Chennai.")
    
    # DB must still be empty
    memories = repo.list_memories("session-A")
    assert len(memories) == 0

def test_determinism():
    text = "I prefer Python for jobs."
    result1 = memory_extractor.extract(text)
    result2 = memory_extractor.extract(text)
    
    assert result1.has_memory == result2.has_memory
    assert len(result1.candidates) == len(result2.candidates)
    assert result1.candidates[0].content == result2.candidates[0].content

def test_technical_terminology_preservation():
    result = memory_extractor.extract("I am learning FastAPI.")
    assert result.candidates[0].content == "User is learning FastAPI."
    
    result = memory_extractor.extract("I'm building Jagan AI.")
    assert result.candidates[0].content == "User is building a project called Jagan AI."
    
    result = memory_extractor.extract("I prefer Python.")
    assert result.candidates[0].content == "User prefers Python."

def test_memory_commands_ignored():
    assert memory_extractor.extract("Show my memories").has_memory is False
    assert memory_extractor.extract("Forget my preferred job location is Chennai").has_memory is False
    assert memory_extractor.extract("Clear this session's memories").has_memory is False
    assert memory_extractor.extract("Search memories for Python").has_memory is False

