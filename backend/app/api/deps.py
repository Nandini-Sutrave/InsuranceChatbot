import uuid
from typing import Generator, List, Optional
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials, APIKeyHeader
from jose import JWTError
from sqlalchemy.orm import Session
from sqlalchemy import select

from app.core.config import settings
from app.core.database import SessionLocal
from app.core.security import decode_access_token
from app.models.user import User
from app.services.widget_auth import get_or_create_widget_service_user, is_valid_widget_api_key

reusable_oauth2 = HTTPBearer()
optional_oauth2 = HTTPBearer(auto_error=False)
widget_api_key_header = APIKeyHeader(name="X-Widget-API-Key", auto_error=False)

def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency to yield a database session and clean it up after the request."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def _resolve_user_from_token(db: Session, token: str) -> User:
    """Validate a JWT access token and return the associated user."""
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = decode_access_token(token)
        user_id_str = payload.get("sub")
        if user_id_str is None:
            raise credentials_exception
        user_id = uuid.UUID(user_id_str)
    except (JWTError, ValueError):
        raise credentials_exception

    stmt = select(User).where(User.id == user_id)
    user = db.scalar(stmt)
    if user is None:
        raise credentials_exception
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Inactive user"
        )
    return user


def get_current_user(
    db: Session = Depends(get_db),
    token: HTTPAuthorizationCredentials = Depends(reusable_oauth2)
) -> User:
    """
    FastAPI dependency to fetch the authenticated user from the JWT access token.
    Raises 401 Unauthorized if invalid or expired.
    """
    return _resolve_user_from_token(db, token.credentials)


def get_chat_user(
    db: Session = Depends(get_db),
    token: Optional[HTTPAuthorizationCredentials] = Depends(optional_oauth2),
    widget_api_key: Optional[str] = Depends(widget_api_key_header),
) -> User:
    """
    Authenticate chat requests via JWT bearer token or embeddable widget API key.
    """
    if is_valid_widget_api_key(widget_api_key):
        return get_or_create_widget_service_user(db)

    if token and token.credentials:
        return _resolve_user_from_token(db, token.credentials)

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Authentication required. Provide a Bearer token or X-Widget-API-Key header.",
        headers={"WWW-Authenticate": "Bearer"},
    )

class RoleChecker:
    """
    FastAPI dependency factory to enforce RBAC constraints on endpoints.
    Example: Depends(RoleChecker(["admin", "support_staff"]))
    """
    def __init__(self, allowed_roles: List[str]):
        self.allowed_roles = allowed_roles

    def __call__(self, current_user: User = Depends(get_current_user)) -> User:
        user_roles = [role.name for role in current_user.roles]
        # Check if the user has at least one of the allowed roles
        has_role = any(role in self.allowed_roles for role in user_roles)
        if not has_role:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have the required permissions to access this resource"
            )
        return current_user
