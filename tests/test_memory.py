import pytest
from app.memory import MemoryType, MemorySource, MemoryValidationError, memory_service
from app.memory.repository import MemoryRepository

def test_create_and_retrieve_memory():
    mem = memory_service.remember(
        session_id="session-A",
        content="User prefers Chennai.",
        memory_type=MemoryType.PREFERENCE
    )
    assert mem.id is not None
    assert mem.session_id == "session-A"
    assert mem.content == "User prefers Chennai."
    
    retrieved = memory_service.get_memory(mem.id, "session-A")
    assert retrieved is not None
    assert retrieved.id == mem.id
    assert retrieved.content == "User prefers Chennai."

def test_list_memories_current_session():
    memory_service.remember("session-A", "Memory 1")
    memory_service.remember("session-A", "Memory 2")
    
    memories = memory_service.list_memories("session-A")
    assert len(memories) == 2
    assert memories[0].content == "Memory 1"
    assert memories[1].content == "Memory 2"

def test_session_isolation_list():
    memory_service.remember("session-A", "A's Memory")
    memory_service.remember("session-B", "B's Memory")
    
    memories_a = memory_service.list_memories("session-A")
    assert len(memories_a) == 1
    assert memories_a[0].content == "A's Memory"
    
    memories_b = memory_service.list_memories("session-B")
    assert len(memories_b) == 1
    assert memories_b[0].content == "B's Memory"

def test_cross_session_get_protection():
    mem = memory_service.remember("session-A", "Secret for A")
    
    # Session B tries to get it
    retrieved = memory_service.get_memory(mem.id, "session-B")
    assert retrieved is None

def test_cross_session_delete_protection():
    mem = memory_service.remember("session-A", "Keep me")
    
    # Session B tries to delete it
    success = memory_service.forget(mem.id, "session-B")
    assert success is False
    
    # Still exists for A
    assert memory_service.get_memory(mem.id, "session-A") is not None

def test_update_memory():
    mem = memory_service.remember("session-A", "Old content")
    updated = memory_service.update_memory(mem.id, "session-A", "New content")
    
    assert updated is not None
    assert updated.content == "New content"
    assert updated.updated_at != updated.created_at
    
    retrieved = memory_service.get_memory(mem.id, "session-A")
    assert retrieved.content == "New content"

def test_delete_memory():
    mem = memory_service.remember("session-A", "Delete me")
    success = memory_service.forget(mem.id, "session-A")
    assert success is True
    assert memory_service.get_memory(mem.id, "session-A") is None

def test_empty_content_rejected():
    with pytest.raises(MemoryValidationError):
        memory_service.remember("session-A", "")
        
    with pytest.raises(MemoryValidationError):
        memory_service.remember("session-A", "   ")
        
    mem = memory_service.remember("session-A", "valid")
    with pytest.raises(MemoryValidationError):
        memory_service.update_memory(mem.id, "session-A", " ")

def test_duplicate_protection():
    mem1 = memory_service.remember("session-A", "User likes Python")
    mem2 = memory_service.remember("session-A", "User likes Python")
    mem3 = memory_service.remember("session-A", "  user likes python  ")
    
    assert mem1.id == mem2.id
    assert mem1.id == mem3.id
    
    # Only 1 memory in DB
    assert len(memory_service.list_memories("session-A")) == 1

def test_secret_protection():
    secrets = [
        "My token is ghp_123456789012345678901234567890123456",
        "Here is the secret sk-123456789012345678901234567890123456",
        "API_KEY=ABCDE12345",
        "password: mysecretpassword123"
    ]
    
    for secret in secrets:
        with pytest.raises(MemoryValidationError) as exc:
            memory_service.remember("session-A", secret)
        assert "secrets" in str(exc.value)
        
def test_database_persistence(mock_db_repository):
    """
    Simulate process restart by creating a new repository instance pointing to the same DB file.
    """
    mem = memory_service.remember("session-A", "Persistent memory test")
    
    # Create a fresh repository instance pointing to the same shared memory DB
    fresh_repo = MemoryRepository("file:memdb_global?mode=memory&cache=shared")
    
    # Retrieve it
    retrieved = fresh_repo.get_memory(mem.id, "session-A")
    assert retrieved is not None
    assert retrieved.content == "Persistent memory test"
