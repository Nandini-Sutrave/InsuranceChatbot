"""Service-user bootstrap for embeddable chat widget API-key authentication."""
import secrets
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.user import Role, User


def get_or_create_widget_service_user(db: Session) -> User:
    """Return the dedicated service account used by widget API-key requests."""
    stmt = select(User).where(User.email == settings.WIDGET_SERVICE_USER_EMAIL)
    user = db.scalar(stmt)

    if user:
        return user

    stmt_role = select(Role).where(Role.name == "posp_agent")
    role = db.scalar(stmt_role)
    if not role:
        role = Role(name="posp_agent", description="Default user role for POSP agents")
        db.add(role)
        db.flush()

    user = User(
        email=settings.WIDGET_SERVICE_USER_EMAIL,
        full_name="Widget Service Account",
        hashed_password=None,
        is_active=True,
        roles=[role],
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def is_valid_widget_api_key(provided_key: Optional[str]) -> bool:
    """Validate the embeddable widget API key when configured."""
    expected = (settings.WIDGET_API_KEY or "").strip()
    if not expected or not provided_key:
        return False
    return secrets.compare_digest(provided_key.strip(), expected)
