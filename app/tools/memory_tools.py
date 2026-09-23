import logging
from typing import Dict, Any

from app.tools.registry import registry
from app.memory.service import memory_service

logger = logging.getLogger(__name__)

@registry.register(requires_confirmation=False)
def list_memories(session_id: str) -> Dict[str, Any]:
    """
    Lists all remembered facts about the user and this session.
    Returns categorized personal and session memories with their IDs.
    """
    personal = memory_service.list_personal_memories()
    session = memory_service.list_memories(session_id)
    
    return {
        "personal_memories": [{"id": m.id, "content": m.content} for m in personal],
        "session_memories": [{"id": m.id, "content": m.content} for m in session]
    }

@registry.register(requires_confirmation=False)
def search_memories(session_id: str, query: str) -> Dict[str, Any]:
    """
    Searches stored memories for a keyword or phrase.
    Returns matching memories with their IDs. Use this to find the exact memory_id before forgetting.
    """
    results = memory_service.search_memories(session_id, query)
    return {
        "results": [{"id": m.id, "content": m.content, "scope": m.scope.value} for m in results]
    }

@registry.register(requires_confirmation=False)
def inspect_memory_context(session_id: str, query: str) -> Dict[str, Any]:
    """
    Debug tool: Inspects what memories the system WOULD retrieve into context for a given query,
    along with retrieval explanations, scores, and budget usage.
    Does not modify any state.
    """
    from app.memory.retrieval import build_memory_context_with_trace
    _, trace = build_memory_context_with_trace(session_id, query)
    
    if not trace:
        return {"status": "no_memories_retrieved", "query": query}
        
    return {
        "query": trace.query,
        "selected_memory_ids": trace.selected_memory_ids,
        "session_memory_ids": trace.session_memory_ids,
        "personal_memory_ids": trace.personal_memory_ids,
        "total_items": trace.total_items,
        "total_characters": trace.total_characters,
        "retrieval_method": trace.retrieval_method,
        "threshold_applied": trace.threshold_applied,
        "items": [
            {
                "memory_id": item.memory_id,
                "content": item.content,
                "keyword_score": item.keyword_score,
                "semantic_score": item.semantic_score,
                "relevance_score": item.relevance_score,
                "matched_keywords": item.matched_keywords,
                "retrieval_method": item.retrieval_method,
                "retrieval_reason": item.retrieval_reason
            }
            for item in trace.items
        ]
    }

@registry.register(requires_confirmation=True)
def forget_memory(session_id: str, memory_id: int) -> Dict[str, Any]:
    """
    Permanently deletes a single specific memory by its ID.
    Always search or list memories first to find the correct memory_id.
    Requires user confirmation.
    """
    success = memory_service.forget_memory(memory_id, session_id)
    if success:
        return {"status": "success", "message": f"Memory {memory_id} deleted successfully."}
    return {"status": "error", "message": f"Memory {memory_id} not found."}

@registry.register(requires_confirmation=True)
def clear_session_memories(session_id: str) -> Dict[str, Any]:
    """
    Permanently deletes ALL memories stored in the current session.
    Requires user confirmation.
    """
    count = memory_service.clear_session_memories(session_id)
    return {"status": "success", "message": f"Cleared {count} session memories."}

@registry.register(requires_confirmation=True)
def clear_personal_memories(session_id: str) -> Dict[str, Any]:
    """
    Permanently deletes ALL personal memories belonging to the user across all sessions.
    Requires user confirmation.
    """
    count = memory_service.clear_personal_memories()
    return {"status": "success", "message": f"Cleared {count} personal memories."}

@registry.register(requires_confirmation=True)
def clear_all_memories(session_id: str) -> Dict[str, Any]:
    """
    Permanently deletes EVERYTHING (all personal memories AND all session memories).
    Requires user confirmation.
    """
    count = memory_service.clear_all_memories()
    return {"status": "success", "message": f"Cleared {count} total memories."}

@registry.register(requires_confirmation=False)
def inspect_memory_consolidation(session_id: str) -> Dict[str, Any]:
    """
    Analyzes all current memories for duplicates and near-duplicates and produces a safe
    consolidation proposal.
    Does NOT mutate data. Returns a dry-run summary.
    """
    from app.memory.consolidation import consolidation_engine
    # A real implementation would extract the owner_id from session or state, but memory_service
    # currently assumes "default_owner" in many tests.
    owner_id = "default_owner"
    
    proposal = consolidation_engine.generate_proposal(session_id, owner_id)
    
    return {
        "status": "success",
        "proposal_id": proposal.proposal_id,
        "total_groups": len(proposal.groups),
        "groups": [
            {
                "memory_ids": g.memory_ids,
                "reason": g.reason.value,
                "confidence": g.confidence.value,
                "proposed_content": g.proposed_content,
                "proposed_importance": g.proposed_importance.value
            } for g in proposal.groups
        ]
    }

@registry.register(requires_confirmation=False)
def consolidate_memories(session_id: str) -> Dict[str, Any]:
    """
    Analyzes current memories and pauses the system to propose a safe consolidation 
    of duplicate, near-duplicate, and related memories.
    The system will present the proposal to the user for explicit confirmation before applying.
    """
    from app.memory.consolidation import consolidation_engine
    from app.agents.confirmation import confirmation_manager
    
    owner_id = "default_owner"
    proposal = consolidation_engine.generate_proposal(session_id, owner_id)
    
    if not proposal.groups:
        return {"status": "no_consolidation_needed", "message": "No memory consolidation opportunities were found."}
        
    return confirmation_manager.create_pending_consolidation(session_id, proposal)

@registry.register(requires_confirmation=False)
def inspect_memory_maintenance(session_id: str) -> Dict[str, Any]:
    """
    Analyzes all current memories for freshness, importance, supersession, and redundancy
    to produce a safe maintenance proposal (KEEP, REVIEW, FORGET).
    Does NOT mutate data. Returns a dry-run summary.
    """
    from app.memory.maintenance import maintenance_engine
    owner_id = "default_owner"
    
    proposal = maintenance_engine.generate_proposal(session_id, owner_id)
    
    return {
        "status": "success",
        "proposal_id": proposal.proposal_id,
        "total_candidates": len(proposal.candidates),
        "candidates": [
            {
                "memory_id": c.memory_id,
                "scope": c.scope.value,
                "importance": c.importance.value,
                "age_days": c.age_days,
                "reason": c.reason,
                "recommended_action": c.recommended_action.value,
                "confidence": c.confidence.value
            } for c in proposal.candidates
        ]
    }

@registry.register(requires_confirmation=False)
def perform_memory_maintenance(session_id: str) -> Dict[str, Any]:
    """
    Analyzes current memories and pauses the system to propose a safe lifecycle maintenance
    clean up of stale, superseded, or redundant memories.
    The system will present the proposal to the user for explicit confirmation before applying
    any destructive FORGET actions.
    """
    from app.memory.maintenance import maintenance_engine, MaintenanceAction
    from app.agents.confirmation import confirmation_manager
    
    owner_id = "default_owner"
    proposal = maintenance_engine.generate_proposal(session_id, owner_id)
    
    # We only prompt for confirmation if there are FORGET actions recommended
    forget_candidates = [c for c in proposal.candidates if c.recommended_action == MaintenanceAction.FORGET]
    
    if not forget_candidates:
        return {"status": "no_maintenance_needed", "message": "No destructive memory maintenance actions (FORGET) were recommended. All memories are healthy or only need manual review."}
        
    return confirmation_manager.create_pending_maintenance(session_id, proposal)
