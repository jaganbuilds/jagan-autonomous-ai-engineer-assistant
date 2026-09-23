from pydantic import BaseModel, Field
from typing import List, Optional
from datetime import datetime, timezone
import uuid
from enum import Enum

from app.memory.models import Memory, MemoryScope, MemoryImportance
from app.memory.consolidation import consolidation_engine, ConsolidationReason
from app.config import get_settings

class MaintenanceAction(str, Enum):
    KEEP = "KEEP"
    REVIEW = "REVIEW"
    ARCHIVE = "ARCHIVE"
    FORGET = "FORGET"

class ConfidenceLevel(str, Enum):
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"

class MemoryMaintenanceCandidate(BaseModel):
    memory_id: int
    content: str
    scope: MemoryScope
    importance: MemoryImportance
    age_days: int
    last_updated: str
    reason: str
    recommended_action: MaintenanceAction
    confidence: ConfidenceLevel

class MemoryMaintenanceProposal(BaseModel):
    proposal_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    session_id: str
    owner_id: str
    candidates: List[MemoryMaintenanceCandidate]
    generated_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

class MaintenanceEngine:
    """
    Evaluates memory lifecycle and proposes maintenance actions like KEEP, REVIEW, FORGET.
    """
    
    def generate_proposal(self, session_id: str, owner_id: str) -> MemoryMaintenanceProposal:
        from app.memory.repository import get_memory_repository
        repo = get_memory_repository()
        session_memories = repo.get_all_in_scope(session_id, owner_id, MemoryScope.SESSION)
        personal_memories = repo.get_all_in_scope(session_id, owner_id, MemoryScope.PERSONAL)
        
        all_memories = session_memories + personal_memories
        
        if not all_memories:
            return MemoryMaintenanceProposal(session_id=session_id, owner_id=owner_id, candidates=[])
            
        settings = get_settings()
        
        # Integration with Consolidation Engine for redundancy and supersession
        consolidation_proposal = consolidation_engine.generate_proposal(session_id, owner_id)
        
        redundant_ids = set()
        superseded_ids = set()
        
        for group in consolidation_proposal.groups:
            if group.reason in (ConsolidationReason.EXACT_DUPLICATE, ConsolidationReason.NEAR_DUPLICATE):
                if group.proposed_content:
                    # The older ones are redundant
                    group_mems = [m for m in all_memories if m.id in group.memory_ids]
                    group_mems.sort(key=lambda m: m.updated_at, reverse=True)
                    if group_mems:
                        canonical_id = group_mems[0].id
                        for m in group_mems:
                            if m.id != canonical_id:
                                redundant_ids.add(m.id)
                else:
                    for mid in group.memory_ids:
                        redundant_ids.add(mid)
            elif group.reason == ConsolidationReason.CONFLICTING:
                # The older ones are superseded by the newest
                group_mems = [m for m in all_memories if m.id in group.memory_ids]
                group_mems.sort(key=lambda m: m.updated_at, reverse=True)
                if group_mems:
                    newest_id = group_mems[0].id
                    for m in group_mems:
                        if m.id != newest_id:
                            superseded_ids.add(m.id)
                        
        candidates = []
        now = datetime.now(timezone.utc)
        
        for m in all_memories:
            updated = datetime.fromisoformat(m.updated_at)
            age_days = (now - updated).days
            
            action = MaintenanceAction.KEEP
            reason = "Memory is active and relevant."
            confidence = ConfidenceLevel.HIGH
            
            # Prioritize signals
            if m.id in superseded_ids:
                action = MaintenanceAction.FORGET
                reason = "Memory was superseded by a newer conflicting preference."
                confidence = ConfidenceLevel.HIGH
            elif m.id in redundant_ids:
                action = MaintenanceAction.REVIEW
                reason = "Memory appears redundant with an existing consolidation candidate."
                confidence = ConfidenceLevel.HIGH
            else:
                # Freshness signals
                if m.importance == MemoryImportance.LOW and age_days > settings.memory_low_importance_age_days:
                    action = MaintenanceAction.REVIEW
                    reason = "Low-importance memory has exceeded the configured freshness window."
                    confidence = ConfidenceLevel.MEDIUM
                elif m.importance == MemoryImportance.NORMAL and age_days > settings.memory_normal_importance_age_days:
                    action = MaintenanceAction.REVIEW
                    reason = "Normal-importance memory has exceeded the configured freshness window."
                    confidence = ConfidenceLevel.MEDIUM
                elif m.importance == MemoryImportance.HIGH and age_days > settings.memory_high_importance_age_days:
                    # High importance doesn't get forgotten, just kept with note
                    action = MaintenanceAction.KEEP
                    reason = "High-importance memory is old but retained due to importance."
                    confidence = ConfidenceLevel.HIGH
                    
            candidates.append(MemoryMaintenanceCandidate(
                memory_id=m.id,
                content=m.content,
                scope=m.scope,
                importance=m.importance,
                age_days=age_days,
                last_updated=m.updated_at,
                reason=reason,
                recommended_action=action,
                confidence=confidence
            ))
            
        return MemoryMaintenanceProposal(
            session_id=session_id,
            owner_id=owner_id,
            candidates=candidates
        )

    def apply_proposal(self, proposal: MemoryMaintenanceProposal) -> dict:
        """
        Executes a confirmed maintenance proposal.
        Only applies FORGET actions deterministically. REVIEW and KEEP are no-ops here.
        Validates memory existence and stale states.
        """
        from app.memory.repository import get_memory_repository
        repo = get_memory_repository()
        results = {"status": "success", "processed": 0, "errors": []}
        
        forget_candidates = [c for c in proposal.candidates if c.recommended_action == MaintenanceAction.FORGET]
        
        if not forget_candidates:
            return {"status": "success", "processed": 0, "message": "No destructive actions to apply."}
            
        valid_ids_to_forget = []
        
        for c in forget_candidates:
            m = repo.get_memory_safe(c.memory_id, proposal.session_id, proposal.owner_id)
            if not m:
                results["errors"].append(f"Memory {c.memory_id} missing or unauthorized.")
                continue
                
            if m.updated_at > proposal.generated_at:
                results["errors"].append(f"Memory {c.memory_id} has changed since proposal was generated. Stale proposal.")
                continue
                
            valid_ids_to_forget.append(c.memory_id)
            
        if results["errors"]:
            results["status"] = "partial_failure" if valid_ids_to_forget else "failure"
            if not valid_ids_to_forget:
                return results
                
        # Perform atomistic batch forget
        success = repo.delete_memories_atomically(valid_ids_to_forget, proposal.session_id, proposal.owner_id)
        if success:
            results["processed"] = len(valid_ids_to_forget)
        else:
            results["status"] = "failure"
            results["errors"].append("Failed to apply FORGET actions atomically.")
            
        return results

maintenance_engine = MaintenanceEngine()
