import pytest
from datetime import datetime, timedelta, timezone
from app.memory.models import MemoryScope, MemoryImportance, Memory
from app.memory.maintenance import maintenance_engine, MaintenanceAction, ConfidenceLevel
from app.memory.service import memory_service
from app.database.repository import JobRepository, set_job_repository_for_testing
from app.memory.repository import get_memory_repository, set_memory_repository_for_testing
from app.agents.confirmation import confirmation_manager
from app.config import get_settings

@pytest.fixture
def mock_db_repository():
    get_settings().memory_semantic_retrieval_enabled = False
    repo = JobRepository("file:memdb_global_maint?mode=memory&cache=shared")
    mem_repo = get_memory_repository("file:memdb_global_maint?mode=memory&cache=shared")
    set_job_repository_for_testing(repo)
    set_memory_repository_for_testing(mem_repo)
    
    # ensure it's empty
    mem_repo.clear_session_memories("test_maint")
    mem_repo.clear_personal_memories("default_owner")
    
    yield mem_repo

def get_past_time(days: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()

def test_dry_run_no_mutation(mock_db_repository):
    session_id = "test_maint"
    owner_id = "default_owner"
    memory_service.remember(session_id, "I like Python.")
    
    mems = memory_service.list_memories(session_id)
    assert len(mems) == 1
    
    proposal = maintenance_engine.generate_proposal(session_id, owner_id)
    assert len(proposal.candidates) == 1
    
    # No mutation from generating
    assert len(memory_service.list_memories(session_id)) == 1

def test_freshness_and_importance(mock_db_repository):
    session_id = "test_maint"
    owner_id = "default_owner"
    
    # 1. Recent memory -> KEEP
    m1 = mock_db_repository.create_memory(Memory(
        session_id=session_id, owner_id=owner_id, memory_type="preference", source="user", 
        content="User likes to drink black coffee every morning.", importance=MemoryImportance.NORMAL
    ))
    
    # 2. Old LOW importance -> REVIEW
    m2 = mock_db_repository.create_memory(Memory(
        session_id=session_id, owner_id=owner_id, memory_type="preference", source="user", 
        content="User drives a blue Honda Civic.", importance=MemoryImportance.LOW,
        updated_at=get_past_time(40) # > 30 days
    ))
    
    # 3. Old NORMAL importance -> REVIEW
    m3 = mock_db_repository.create_memory(Memory(
        session_id=session_id, owner_id=owner_id, memory_type="preference", source="user", 
        content="User lives in Seattle near the space needle.", importance=MemoryImportance.NORMAL,
        updated_at=get_past_time(100) # > 90 days
    ))
    
    # 4. Old HIGH importance -> KEEP
    m4 = mock_db_repository.create_memory(Memory(
        session_id=session_id, owner_id=owner_id, memory_type="preference", source="user", 
        content="User works as a senior software architect.", importance=MemoryImportance.HIGH,
        updated_at=get_past_time(400) # > 365 days
    ))
    
    proposal = maintenance_engine.generate_proposal(session_id, owner_id)
    assert len(proposal.candidates) == 4
    
    for c in proposal.candidates:
        if c.memory_id == m1.id:
            assert c.recommended_action == MaintenanceAction.KEEP
        elif c.memory_id == m2.id:
            assert c.recommended_action == MaintenanceAction.REVIEW
        elif c.memory_id == m3.id:
            assert c.recommended_action == MaintenanceAction.REVIEW
        elif c.memory_id == m4.id:
            assert c.recommended_action == MaintenanceAction.KEEP

def test_supersession(mock_db_repository):
    session_id = "test_maint"
    owner_id = "default_owner"
    
    m1 = mock_db_repository.create_memory(Memory(
        session_id=session_id, owner_id=owner_id, memory_type="preference", source="user", 
        content="User prefers Python for job opportunities.",
        updated_at=get_past_time(10)
    ))
    m2 = mock_db_repository.create_memory(Memory(
        session_id=session_id, owner_id=owner_id, memory_type="preference", source="user", 
        content="User prefers Java for job opportunities.",
        updated_at=get_past_time(2)
    ))
    
    proposal = maintenance_engine.generate_proposal(session_id, owner_id)
    assert len(proposal.candidates) == 2
    
    for c in proposal.candidates:
        if c.memory_id == m1.id:
            assert c.recommended_action == MaintenanceAction.FORGET
            assert c.reason == "Memory was superseded by a newer conflicting preference."
        elif c.memory_id == m2.id:
            assert c.recommended_action == MaintenanceAction.KEEP

def test_consolidation_redundancy(mock_db_repository):
    session_id = "test_maint"
    owner_id = "default_owner"
    
    m1 = mock_db_repository.create_memory(Memory(
        session_id=session_id, owner_id=owner_id, memory_type="preference", source="user", 
        content="User likes cats.", updated_at=get_past_time(5)
    ))
    m2 = mock_db_repository.create_memory(Memory(
        session_id=session_id, owner_id=owner_id, memory_type="preference", source="user", 
        content="User likes cats.", updated_at=get_past_time(2)
    ))
    
    proposal = maintenance_engine.generate_proposal(session_id, owner_id)
    
    for c in proposal.candidates:
        if c.memory_id == m1.id:
            assert c.recommended_action == MaintenanceAction.REVIEW
            assert c.reason == "Memory appears redundant with an existing consolidation candidate."
        elif c.memory_id == m2.id:
            assert c.recommended_action == MaintenanceAction.KEEP

@__import__('unittest.mock').mock.patch('app.memory.semantic.semantic_engine.compute_similarity')
def test_semantic_redundancy(mock_sim, mock_db_repository):
    get_settings().memory_semantic_retrieval_enabled = True
    mock_sim.return_value = [0.95]
    session_id = "test_maint"
    owner_id = "default_owner"
    
    m1 = mock_db_repository.create_memory(Memory(
        session_id=session_id, owner_id=owner_id, memory_type="preference", source="user", 
        content="User mainly writes Python for backend development.", updated_at=get_past_time(5)
    ))
    m2 = mock_db_repository.create_memory(Memory(
        session_id=session_id, owner_id=owner_id, memory_type="preference", source="user", 
        content="User mainly writes Python for backend jobs.", updated_at=get_past_time(2)
    ))
    
    proposal = maintenance_engine.generate_proposal(session_id, owner_id)
    for c in proposal.candidates:
        if c.memory_id == m1.id:
            # Consolidation catches this as near-duplicate, but without full containment it might not set proposed_content
            # If no proposed_content, ALL members of the group are marked as redundant
            assert c.recommended_action == MaintenanceAction.REVIEW

def test_confirmation_and_mutation(mock_db_repository):
    session_id = "test_maint"
    owner_id = "default_owner"
    
    m1 = mock_db_repository.create_memory(Memory(
        session_id=session_id, owner_id=owner_id, memory_type="preference", source="user", 
        content="User prefers Python for job opportunities.", updated_at=get_past_time(10)
    ))
    m2 = mock_db_repository.create_memory(Memory(
        session_id=session_id, owner_id=owner_id, memory_type="preference", source="user", 
        content="User prefers Java for job opportunities.", updated_at=get_past_time(2)
    ))
    
    proposal = maintenance_engine.generate_proposal(session_id, owner_id)
    result = confirmation_manager.create_pending_maintenance(session_id, proposal)
    
    assert result["status"] == "waiting_for_confirmation"
    
    # Confirm
    conf_result = confirmation_manager.confirm_maintenance(session_id)
    assert conf_result["status"] == "success"
    
    mems = mock_db_repository.list_memories(session_id)
    assert len(mems) == 1
    assert mems[0].id == m2.id

def test_stale_proposal(mock_db_repository):
    session_id = "test_maint"
    owner_id = "default_owner"
    
    m1 = mock_db_repository.create_memory(Memory(
        session_id=session_id, owner_id=owner_id, memory_type="preference", source="user", 
        content="User prefers Python for job opportunities.", updated_at=get_past_time(10)
    ))
    m2 = mock_db_repository.create_memory(Memory(
        session_id=session_id, owner_id=owner_id, memory_type="preference", source="user", 
        content="User prefers Java for job opportunities.", updated_at=get_past_time(2)
    ))
    
    proposal = maintenance_engine.generate_proposal(session_id, owner_id)
    
    # Mutate M1
    mock_db_repository.update_memory(m1.id, session_id, "Changed text", datetime.now(timezone.utc).isoformat())
    
    confirmation_manager.create_pending_maintenance(session_id, proposal)
    conf_result = confirmation_manager.confirm_maintenance(session_id)
    
    assert conf_result["status"] == "error"
    assert "Stale proposal" in conf_result["message"]

def test_scope_isolation(mock_db_repository):
    session_id = "test_maint"
    owner_id = "default_owner"
    
    # Add memory in different scope
    mock_db_repository.create_memory(Memory(
        session_id="other_session", owner_id=owner_id, memory_type="general", source="user", 
        content="Something"
    ))
    
    proposal = maintenance_engine.generate_proposal(session_id, owner_id)
    assert len(proposal.candidates) == 0

def test_atomicity(mock_db_repository):
    # Simulated failure by passing invalid ids to atomic delete
    # Passing a dict will cause sqlite3.InterfaceError during parameter binding
    res = mock_db_repository.delete_memories_atomically([-1, -2, {}], "sess", "owner")
    assert res == False
