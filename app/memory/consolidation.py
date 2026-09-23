from pydantic import BaseModel, Field
from typing import List, Optional
from datetime import datetime, timezone
import uuid
from enum import Enum
import itertools

from app.memory.models import Memory, MemoryScope, MemoryImportance
from app.memory.service import memory_service
from app.memory.lifecycle import lifecycle_manager
from app.config import get_settings

class ConfidenceLevel(str, Enum):
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"

class ConsolidationReason(str, Enum):
    EXACT_DUPLICATE = "exact_duplicate"
    NEAR_DUPLICATE = "near_duplicate"
    RELATED = "related"
    CONFLICTING = "conflicting"

class MemoryConsolidationCandidate(BaseModel):
    memory_id: int
    content: str
    scope: MemoryScope
    importance: MemoryImportance
    similarity_score: float = 0.0

class MemoryConsolidationGroup(BaseModel):
    group_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    memory_ids: List[int]
    reason: ConsolidationReason
    confidence: ConfidenceLevel
    proposed_content: Optional[str] = None
    proposed_importance: MemoryImportance

class MemoryConsolidationProposal(BaseModel):
    proposal_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    session_id: str
    owner_id: str
    groups: List[MemoryConsolidationGroup]
    generated_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    requires_confirmation: bool = True

class ConsolidationEngine:
    """
    Engine to identify duplicate, near-duplicate, and strongly related memories
    and produce a safe consolidation proposal.
    """
    
    def generate_proposal(self, session_id: str, owner_id: str) -> MemoryConsolidationProposal:
        from app.memory.repository import get_memory_repository
        repo = get_memory_repository()
        session_memories = repo.get_all_in_scope(session_id, owner_id, MemoryScope.SESSION)
        personal_memories = repo.get_all_in_scope(session_id, owner_id, MemoryScope.PERSONAL)
        
        groups = []
        groups.extend(self._analyze_scope(session_memories))
        groups.extend(self._analyze_scope(personal_memories))
        
        return MemoryConsolidationProposal(
            session_id=session_id,
            owner_id=owner_id,
            groups=groups
        )
        
    def _analyze_scope(self, memories: List[Memory]) -> List[MemoryConsolidationGroup]:
        if len(memories) < 2:
            return []
            
        settings = get_settings()
        groups = []
        visited = set()
        
        # We need semantic engine if enabled
        semantic_scores = {}
        if settings.memory_semantic_retrieval_enabled:
            from app.memory.semantic import semantic_engine
            # Compute pairwise similarities
            for m1, m2 in itertools.combinations(memories, 2):
                scores = semantic_engine.compute_similarity(m1.content, [m2.content])
                if scores:
                    semantic_scores[(m1.id, m2.id)] = scores[0]
                    semantic_scores[(m2.id, m1.id)] = scores[0]
                    
        for m1 in memories:
            if m1.id in visited:
                continue
                
            current_group = [m1]
            visited.add(m1.id)
            
            for m2 in memories:
                if m2.id in visited:
                    continue
                    
                # 1. Exact Duplicate
                if lifecycle_manager.is_duplicate(m1.content, m2.content):
                    current_group.append(m2)
                    visited.add(m2.id)
                    continue
                    
                # 2. Conflict check
                cat1 = lifecycle_manager.get_conflict_category(m1.content)
                cat2 = lifecycle_manager.get_conflict_category(m2.content)
                if cat1 and cat2 and cat1 == cat2:
                    # They conflict. We should potentially mark them as conflicting group
                    # But if we group them, we mark reason=CONFLICTING and proposed=None
                    # Actually, if they conflict, we should group them to surface the conflict
                    # but maybe not mix them with other duplicates.
                    current_group.append(m2)
                    visited.add(m2.id)
                    continue
                    
                # 3. Semantic similarity
                score = semantic_scores.get((m1.id, m2.id), 0.0)
                if score >= settings.memory_semantic_threshold:
                    current_group.append(m2)
                    visited.add(m2.id)
            
            if len(current_group) > 1:
                group_model = self._create_group(current_group, semantic_scores)
                if group_model:
                    groups.append(group_model)
                    
        return groups
        
    def _create_group(self, group_memories: List[Memory], semantic_scores: dict) -> Optional[MemoryConsolidationGroup]:
        # Determine reason, confidence, proposed content
        is_conflict = False
        is_exact = True
        is_near = False
        
        for m1, m2 in itertools.combinations(group_memories, 2):
            cat1 = lifecycle_manager.get_conflict_category(m1.content)
            cat2 = lifecycle_manager.get_conflict_category(m2.content)
            if cat1 and cat2 and cat1 == cat2 and not lifecycle_manager.is_duplicate(m1.content, m2.content):
                is_conflict = True
                
            if not lifecycle_manager.is_duplicate(m1.content, m2.content):
                is_exact = False
                
            score = semantic_scores.get((m1.id, m2.id), 0.0)
            if score >= 0.8: # high semantic similarity
                is_near = True

        if is_conflict:
            reason = ConsolidationReason.CONFLICTING
            confidence = ConfidenceLevel.LOW
            proposed_content = None
        elif is_exact:
            reason = ConsolidationReason.EXACT_DUPLICATE
            confidence = ConfidenceLevel.HIGH
            # Sort by recency and take content
            sorted_mems = sorted(group_memories, key=lambda m: m.updated_at, reverse=True)
            proposed_content = sorted_mems[0].content
        elif is_near:
            reason = ConsolidationReason.NEAR_DUPLICATE
            confidence = ConfidenceLevel.MEDIUM
            # Try deterministic synthesis: if one string contains the other
            sorted_by_len = sorted(group_memories, key=lambda m: len(m.content), reverse=True)
            longest = sorted_by_len[0]
            others_contained = True
            for m in group_memories:
                if m.id != longest.id:
                    # simple containment check (case insensitive)
                    if lifecycle_manager.normalize_text(m.content) not in lifecycle_manager.normalize_text(longest.content):
                        others_contained = False
                        break
            if others_contained:
                proposed_content = longest.content
                confidence = ConfidenceLevel.HIGH
            else:
                proposed_content = None
        else:
            reason = ConsolidationReason.RELATED
            confidence = ConfidenceLevel.LOW
            proposed_content = None
            
        # Importance preservation
        importances = [m.importance for m in group_memories]
        if MemoryImportance.HIGH in importances:
            proposed_importance = MemoryImportance.HIGH
        elif MemoryImportance.NORMAL in importances:
            proposed_importance = MemoryImportance.NORMAL
        else:
            proposed_importance = MemoryImportance.LOW

        return MemoryConsolidationGroup(
            memory_ids=[m.id for m in group_memories],
            reason=reason,
            confidence=confidence,
            proposed_content=proposed_content,
            proposed_importance=proposed_importance
        )

    def apply_proposal(self, proposal: MemoryConsolidationProposal) -> dict:
        """
        Executes a confirmed proposal safely.
        Validates that original memories still exist and have not been modified since proposal creation.
        """
        from app.memory.repository import get_memory_repository
        repo = get_memory_repository()
        results = {"status": "success", "groups_processed": 0, "errors": []}
        
        for group in proposal.groups:
            # We only automatically apply groups with a proposed_content (HIGH confidence usually)
            if not group.proposed_content:
                continue
                
            # Verify all memories still exist and scope matches
            valid_mems = []
            valid = True
            for mid in group.memory_ids:
                m = repo.get_memory_safe(mid, proposal.session_id, proposal.owner_id)
                if not m:
                    results["errors"].append(f"Memory {mid} missing or unauthorized.")
                    valid = False
                    break
                # Checking stale data: if memory updated_at is newer than proposal generated_at, it's stale.
                if m.updated_at > proposal.generated_at:
                    results["errors"].append(f"Memory {mid} has changed since proposal was generated. Stale proposal.")
                    valid = False
                    break
                valid_mems.append(m)
                
            if not valid:
                continue
                
            # Perform mutation
            # The strategy: update the most recent memory with the proposed content/importance, delete the rest.
            sorted_mems = sorted(valid_mems, key=lambda m: m.updated_at, reverse=True)
            canonical = sorted_mems[0]
            
            # Apply mutations atomically
            redundant_ids = [m.id for m in sorted_mems[1:]]
            success = repo.apply_consolidation_group(
                canonical.id, redundant_ids, proposal.session_id, proposal.owner_id,
                group.proposed_content, datetime.now(timezone.utc).isoformat(),
                group.proposed_importance
            )
            
            if success:
                results["groups_processed"] += 1
            else:
                results["errors"].append(f"Failed to apply group atomically for canonical memory {canonical.id}")
            
        if results["errors"]:
            results["status"] = "partial_failure" if results["groups_processed"] > 0 else "failure"
            
        return results

consolidation_engine = ConsolidationEngine()
