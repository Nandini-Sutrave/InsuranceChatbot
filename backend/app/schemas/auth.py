import uuid
from typing import List, Optional
from pydantic import BaseModel, EmailStr

class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"

class TokenPayload(BaseModel):
    sub: Optional[str] = None
    email: Optional[EmailStr] = None
    roles: List[str] = []

class LoginCredentials(BaseModel):
    email: EmailStr
    password: str

class OAuthCallbackRequest(BaseModel):
    code: str
    state: str

class RefreshTokenRequest(BaseModel):
    # Used if refresh tokens are passed in request bodies instead of cookies
    refresh_token: str
