import pytest
from app.memory.semantic import semantic_engine
from app.memory.retrieval import get_relevant_memories, build_memory_context_with_trace
from app.memory.service import memory_service
from app.config import get_settings
from app.database.repository import JobRepository, set_job_repository_for_testing
from app.memory.repository import get_memory_repository, set_memory_repository_for_testing

@pytest.fixture
def mock_db_repository():
    repo = JobRepository("file:memdb_global_sem?mode=memory&cache=shared")
    mem_repo = get_memory_repository("file:memdb_global_sem?mode=memory&cache=shared")
    set_job_repository_for_testing(repo)
    set_memory_repository_for_testing(mem_repo)
    yield repo

def test_semantic_similarity_basic():
    query = "I want a job using golang"
    candidates = [
        "User prefers Go programming language.",
        "User likes apples.",
        "User hates the Go programming language."
    ]
    scores = semantic_engine.compute_similarity(query, candidates)
    
    assert len(scores) == 3
    # First and third should have higher similarity than the second
    assert scores[0] > scores[1]
    assert scores[2] > scores[1]

def test_hybrid_retrieval(mock_db_repository):
    settings = get_settings()
    settings.memory_semantic_retrieval_enabled = True
    settings.memory_semantic_threshold = 0.2
    
    session_id = "test_hybrid"
    
    # Keyword match only (very little semantic overlap initially but keyword triggers it)
    memory_service.remember(session_id, "Apple pie.")
    
    # Semantic match only (no keyword overlap for "Python" vs "Django")
    memory_service.remember(session_id, "User is a Django developer.")
    
    # Hybrid match
    memory_service.remember(session_id, "Python and Django are great.")
    
    # Completely unrelated memory
    memory_service.remember(session_id, "User has a pet dog named Rex.")
    
    res = get_relevant_memories(session_id, "I love Python frameworks.")
    
    # Ensure Django is retrieved despite no exact keyword overlap for 'python' and 'frameworks'
    found_django = any("Django developer" in m.content for m in res.selected_memories)
    assert found_django
    
    # Ensure Hybrid match is retrieved
    found_hybrid = any("Python and Django are great" in m.content for m in res.selected_memories)
    assert found_hybrid
    
    # Ensure unrelated memory is NOT retrieved
    found_dog = any("Rex" in m.content for m in res.selected_memories)
    assert not found_dog
    
    # Check trace
    _, trace = build_memory_context_with_trace(session_id, "I love Python frameworks.")
    assert trace.retrieval_method in ["hybrid", "semantic", "keyword"]
    assert trace.total_items > 0

def test_semantic_fallback(mock_db_repository):
    settings = get_settings()
    # Temporarily break the model
    old_model = type(semantic_engine)._model
    type(semantic_engine)._model = None
    old_name = settings.memory_semantic_model
    settings.memory_semantic_model = "invalid-model-name-12345"
    
    try:
        session_id = "test_fallback"
        memory_service.remember(session_id, "User likes FastAPI.")
        
        # This will fail to load the model, catch exception, and fallback to keyword
        res = get_relevant_memories(session_id, "Do you know FastAPI?")
        
        assert len(res.selected_memories) == 1
        assert res.selected_memories[0].retrieval_method == "keyword"
        assert res.selected_memories[0].semantic_score == 0.0
    finally:
        settings.memory_semantic_model = old_name
        type(semantic_engine)._model = old_model
