import uuid
from datetime import datetime
from typing import Optional
from pydantic import BaseModel

class ProductKBBase(BaseModel):
    name: str
    description: Optional[str] = None

class ProductKBCreate(ProductKBBase):
    pass

class ProductKBResponse(ProductKBBase):
    id: uuid.UUID
    created_at: datetime

    class Config:
        from_attributes = True

class DocumentResponse(BaseModel):
    id: uuid.UUID
    filename: str
    file_size: int
    mime_type: str
    status: str
    error_message: Optional[str] = None
    product_id: uuid.UUID
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True
