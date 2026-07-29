from typing import Any
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import select

from app.api import deps
from app.core.security import get_password_hash
from app.models.user import User
from app.schemas.user import UserResponse, UserUpdate

router = APIRouter()

@router.get("/me", response_model=UserResponse)
def get_current_user_profile(current_user: User = Depends(deps.get_current_user)) -> Any:
    """Retrieve details for the currently logged in user."""
    return current_user

@router.put("/me", response_model=UserResponse)
def update_user_profile(
    user_in: UserUpdate,
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user)
) -> Any:
    """Update profile information (e.g., full name, email, or password) for the current user."""
    # Check if email updates conflict with existing user accounts
    if user_in.email and user_in.email != current_user.email:
        stmt = select(User).where(User.email == user_in.email)
        existing_user = db.scalar(stmt)
        if existing_user:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="A user with this email address already exists"
            )
        current_user.email = user_in.email

    if user_in.full_name is not None:
        current_user.full_name = user_in.full_name
        
    if user_in.password is not None:
        if len(user_in.password) < 8:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Password must be at least 8 characters long"
            )
        current_user.hashed_password = get_password_hash(user_in.password)

    if user_in.is_active is not None:
        # Only allow user state modification if they are an admin
        # We can dynamically check roles
        is_admin = any(role.name == "admin" for role in current_user.roles)
        if not is_admin:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only administrators can modify user status flags"
            )
        current_user.is_active = user_in.is_active

    db.add(current_user)
    db.commit()
    db.refresh(current_user)
    return current_user
