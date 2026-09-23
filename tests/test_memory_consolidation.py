import pytest
from datetime import datetime, timezone
import time
from app.memory.models import MemoryScope, MemoryImportance, Memory
from app.memory.consolidation import consolidation_engine, ConsolidationReason, ConfidenceLevel
from app.memory.service import memory_service
from app.database.repository import JobRepository, set_job_repository_for_testing
from app.memory.repository import get_memory_repository, set_memory_repository_for_testing
from app.config import get_settings

@pytest.fixture
def mock_db_repository():
    repo = JobRepository("file:memdb_global_conso?mode=memory&cache=shared")
    mem_repo = get_memory_repository("file:memdb_global_conso?mode=memory&cache=shared")
    set_job_repository_for_testing(repo)
    set_memory_repository_for_testing(mem_repo)
    
    # ensure it's empty
    mem_repo.clear_session_memories("test_conso")
    mem_repo.clear_personal_memories("default_owner")
    
    yield repo

def test_dry_run_no_mutation(mock_db_repository):
    session_id = "test_conso"
    owner_id = "default_owner"
    memory_service.remember(session_id, "I like python.")
    memory_service.remember(session_id, "I really like python.")
    
    # 2 memories initially
    mems = memory_service.list_memories(session_id)
    assert len(mems) == 2
    
    proposal = consolidation_engine.generate_proposal(session_id, owner_id)
    assert len(proposal.groups) == 1
    
    # Verify no mutation
    mems_after = memory_service.list_memories(session_id)
    assert len(mems_after) == 2

def test_exact_duplicates_grouping(mock_db_repository):
    session_id = "test_conso"
    owner_id = "default_owner"
    repo = get_memory_repository()
    
    # We bypass lifecycle duplicate check by injecting directly to test the engine
    m1 = repo.create_memory(Memory(
        session_id=session_id, owner_id=owner_id, memory_type="general", source="user", content="User likes cats."
    ))
    m2 = repo.create_memory(Memory(
        session_id=session_id, owner_id=owner_id, memory_type="general", source="user", content="User likes cats."
    ))
    
    proposal = consolidation_engine.generate_proposal(session_id, owner_id)
    assert len(proposal.groups) == 1
    group = proposal.groups[0]
    
    assert group.reason == ConsolidationReason.EXACT_DUPLICATE
    assert group.confidence == ConfidenceLevel.HIGH
    assert group.proposed_content == "User likes cats."

def test_near_duplicates_semantic(mock_db_repository):
    session_id = "test_conso"
    owner_id = "default_owner"
    
    memory_service.remember(session_id, "User mainly writes Python for backend development.")
    memory_service.remember(session_id, "User mainly writes Python for backend jobs.", importance=MemoryImportance.HIGH)
    
    proposal = consolidation_engine.generate_proposal(session_id, owner_id)
    assert len(proposal.groups) == 1
    group = proposal.groups[0]
    
    assert group.reason == ConsolidationReason.NEAR_DUPLICATE
    assert group.confidence in [ConfidenceLevel.HIGH, ConfidenceLevel.MEDIUM]
    # One string does not contain the other fully
    assert group.proposed_content is None 
    assert group.proposed_importance == MemoryImportance.HIGH

def test_unrelated_memories_rejected(mock_db_repository):
    session_id = "test_conso"
    owner_id = "default_owner"
    
    memory_service.remember(session_id, "I love writing Rust code.")
    memory_service.remember(session_id, "I am moving to Seattle next week.")
    
    proposal = consolidation_engine.generate_proposal(session_id, owner_id)
    assert len(proposal.groups) == 0

def test_conflict_protection(mock_db_repository):
    session_id = "test_conso"
    owner_id = "default_owner"
    repo = get_memory_repository()
    
    # Manually insert conflicting memories without triggering lifecycle update
    m1 = repo.create_memory(Memory(
        session_id=session_id, owner_id=owner_id, memory_type="preference", source="user", 
        content="User prefers Python for job opportunities."
    ))
    m2 = repo.create_memory(Memory(
        session_id=session_id, owner_id=owner_id, memory_type="preference", source="user", 
        content="User prefers Java for job opportunities."
    ))
    
    proposal = consolidation_engine.generate_proposal(session_id, owner_id)
    assert len(proposal.groups) == 1
    group = proposal.groups[0]
    
    assert group.reason == ConsolidationReason.CONFLICTING
    assert group.proposed_content is None
    assert group.confidence == ConfidenceLevel.LOW

def test_scope_isolation(mock_db_repository):
    session_id = "test_conso"
    owner_id = "default_owner"
    
    memory_service.remember(session_id, "I like dogs.", scope=MemoryScope.SESSION)
    memory_service.remember(session_id, "I really like dogs.", scope=MemoryScope.PERSONAL)
    
    proposal = consolidation_engine.generate_proposal(session_id, owner_id)
    # They should not be grouped because scopes are different
    assert len(proposal.groups) == 0

def test_apply_consolidation(mock_db_repository):
    session_id = "test_conso"
    owner_id = "default_owner"
    repo = get_memory_repository()
    
    m1 = repo.create_memory(Memory(
        session_id=session_id, owner_id=owner_id, memory_type="general", source="user", content="I love coding."
    ))
    # Wait a tiny bit so updated_at is strictly newer
    time.sleep(0.01)
    m2 = repo.create_memory(Memory(
        session_id=session_id, owner_id=owner_id, memory_type="general", source="user", content="I love coding very much."
    ))
    
    proposal = consolidation_engine.generate_proposal(session_id, owner_id)
    assert len(proposal.groups) == 1
    
    # Force a proposed content for testing
    proposal.groups[0].proposed_content = "I love coding very much."
    proposal.groups[0].proposed_importance = MemoryImportance.HIGH
    
    result = consolidation_engine.apply_proposal(proposal)
    assert result["status"] == "success"
    
    mems = memory_service.list_memories(session_id)
    assert len(mems) == 1
    assert mems[0].content == "I love coding very much."
    assert mems[0].importance == MemoryImportance.HIGH

def test_stale_proposal_protection(mock_db_repository):
    session_id = "test_conso"
    owner_id = "default_owner"
    repo = get_memory_repository()
    
    memory_service.remember(session_id, "My favorite color is blue.")
    memory_service.remember(session_id, "My absolute favorite color is blue.")
    
    proposal = consolidation_engine.generate_proposal(session_id, owner_id)
    
    # Mutate one memory after proposal is generated
    mems = memory_service.list_memories(session_id)
    repo.update_memory(
        mems[0].id, session_id, "Actually, I like red.", datetime.now(timezone.utc).isoformat()
    )
    
    # Force proposed content
    proposal.groups[0].proposed_content = "My absolute favorite color is blue."
    
    result = consolidation_engine.apply_proposal(proposal)
    assert result["status"] == "failure"
    assert "has changed since proposal was generated" in result["errors"][0]
