from enum import Enum
from typing import Dict, Any, Optional
from pydantic import BaseModel, Field
import uuid
from datetime import datetime, timezone

class ActionType(str, Enum):
    READ = "READ"
    WRITE = "WRITE"
    SEND = "SEND"
    DELETE = "DELETE"
    EXECUTE = "EXECUTE"

class ActionStatus(str, Enum):
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    REJECTED = "REJECTED"
    WAITING_FOR_CONFIRMATION = "WAITING_FOR_CONFIRMATION"
    VALIDATION_ERROR = "VALIDATION_ERROR"
    UNAUTHORIZED = "UNAUTHORIZED"
    NOT_SUPPORTED = "NOT_SUPPORTED"

class ActionRequest(BaseModel):
    action_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    integration: str
    action_type: ActionType
    session_id: str
    owner_id: str = "default_owner"
    arguments: Dict[str, Any] = Field(default_factory=dict)
    requires_confirmation: bool = False
    
    # Ensures action can be safely matched when re-submitted via confirmation
    idempotency_key: Optional[str] = None

class ActionResult(BaseModel):
    action_id: str
    integration: str
    action_type: ActionType
    status: ActionStatus
    message: str
    data: Optional[Any] = None
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

class ActionRiskLevel(str, Enum):
    LOW = "LOW"
    HIGH = "HIGH"

def get_action_risk_level(action_type: ActionType) -> ActionRiskLevel:
    if action_type == ActionType.READ:
        return ActionRiskLevel.LOW
    return ActionRiskLevel.HIGH
