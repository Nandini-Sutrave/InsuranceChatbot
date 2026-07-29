import uuid
from datetime import datetime
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field

class FeedbackCreate(BaseModel):
    message_id: uuid.UUID
    rating: str = Field(..., description="Must be 'thumbs_up' or 'thumbs_down'")
    comment: Optional[str] = None

class FeedbackResponse(BaseModel):
    id: uuid.UUID
    message_id: uuid.UUID
    rating: str
    comment: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True

class MessageResponse(BaseModel):
    id: uuid.UUID
    conversation_id: uuid.UUID
    role: str
    content: str
    sources: Optional[Any] = None
    created_at: datetime
    feedback: Optional[FeedbackResponse] = None

    class Config:
        from_attributes = True

class MessageCreate(BaseModel):
    conversation_id: Optional[uuid.UUID] = None
    product_id: Optional[uuid.UUID] = None
    content: str

class ConversationResponse(BaseModel):
    id: uuid.UUID
    title: str
    created_at: datetime

    class Config:
        from_attributes = True

class ConversationDetailResponse(ConversationResponse):
    messages: List[MessageResponse]
