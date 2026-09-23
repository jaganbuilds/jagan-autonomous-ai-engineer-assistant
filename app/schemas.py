from pydantic import BaseModel, Field

class ChatRequest(BaseModel):
    message: str
    session_id: str = Field(default="default", description="Unique session identifier")

class ChatResponse(BaseModel):
    response: str
    error: str | None = None
    status: str = Field(default="idle", description="Current status of the session")
