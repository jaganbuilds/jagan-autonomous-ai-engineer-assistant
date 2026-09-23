import pytest
from app.memory.retrieval import get_relevant_memories, build_memory_context, build_memory_context_with_trace
from app.memory.service import memory_service
from app.memory.models import MemoryScope, MemoryType, MemoryImportance

def test_retrieval_trace(mock_db_repository):
    session_id = "test_trace_1"
    memory_service.remember(session_id, "User prefers Chennai for jobs.")
    memory_service.remember(session_id, "User prefers Python for backend.", importance=MemoryImportance.HIGH)
    
    # Matching query
    context, trace = build_memory_context_with_trace(session_id, "python jobs in chennai")
    
    assert trace is not None
    assert trace.query == "python jobs in chennai"
    assert trace.total_items == 2
    assert len(trace.session_memory_ids) == 2
    assert len(trace.personal_memory_ids) == 0
    assert "Chennai" in context
    assert "Python" in context

def test_retrieval_result_models(mock_db_repository):
    session_id = "test_models_1"
    memory_service.remember(session_id, "User likes FastAPI.")
    memory_service.remember(session_id, "User's GitHub username is jaganbuilds.", scope=MemoryScope.PERSONAL, importance=MemoryImportance.HIGH)
    
    res = get_relevant_memories(session_id, "I love fastapi and github")
    
    # We should have both items
    assert len(res.selected_memories) == 2
    assert len(res.session_memories) == 1
    assert len(res.personal_memories) == 1
    
    session_item = res.session_memories[0]
    assert "fastapi" in session_item.matched_keywords
    assert session_item.relevance_score > 0
    assert "semantic" in session_item.retrieval_reason.lower() or "keyword" in session_item.retrieval_reason.lower()
    
    personal_item = res.personal_memories[0]
    assert "github" in personal_item.matched_keywords
    assert personal_item.importance == MemoryImportance.HIGH
    assert personal_item.relevance_score > 0
    assert "semantic" in personal_item.retrieval_reason.lower() or "keyword" in personal_item.retrieval_reason.lower()

def test_budget_limits(mock_db_repository):
    from app.config import get_settings
    settings = get_settings()
    
    # Override settings for this test
    old_items = settings.max_memory_context_items
    old_chars = settings.max_memory_context_chars
    
    settings.max_memory_context_items = 1
    settings.max_memory_context_chars = 100
    
    try:
        session_id = "test_budget"
        memory_service.remember(session_id, "User prefers Go.", importance=MemoryImportance.LOW)
        memory_service.remember(session_id, "User prefers Rust.", importance=MemoryImportance.HIGH)
        
        # Test max items
        res = get_relevant_memories(session_id, "go rust")
        # Should only get the HIGH importance one because score is tied (both 1 match), but importance wins
        assert len(res.selected_memories) == 1
        assert "Rust" in res.selected_memories[0].content
        
        # Test max chars
        context, trace = build_memory_context_with_trace(session_id, "go rust")
        assert len(context) > 0 # Includes formatting
        
        # Add a very long memory
        settings.max_memory_context_items = 5
        long_mem = "A" * 150
        memory_service.remember(session_id, f"{long_mem} with Rust.", importance=MemoryImportance.HIGH)
        
        context_long, trace_long = build_memory_context_with_trace(session_id, "rust")
        assert len(trace_long.session_memory_ids) == 0 # None fit
        
    finally:
        # Restore settings
        settings.max_memory_context_items = old_items
        settings.max_memory_context_chars = old_chars
