from typing import Any
from fastapi import APIRouter, Depends, HTTPException, Response, Request, status
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session
from sqlalchemy import select

from app.api import deps
from app.core.config import settings
from app.core.security import create_access_token, get_password_hash
from app.schemas.auth import Token, LoginCredentials, OAuthCallbackRequest
from app.schemas.user import UserCreate, UserResponse
from app.services.auth import AuthService
from app.models.user import User, Role

router = APIRouter()

REFRESH_TOKEN_COOKIE_KEY = "refresh_token"

def set_refresh_cookie(response: Response, refresh_token: str) -> None:
    """Helper to set the long-lived refresh token in a secure HttpOnly cookie."""
    response.set_cookie(
        key=REFRESH_TOKEN_COOKIE_KEY,
        value=refresh_token,
        httponly=True,
        secure=settings.ENV == "production",  # only enforce HTTPS in prod
        samesite="lax",
        max_age=settings.REFRESH_TOKEN_EXPIRE_DAYS * 24 * 60 * 60,
        path="/"
    )

@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
def register_user(user_in: UserCreate, db: Session = Depends(deps.get_db)) -> Any:
    """Register a new user. Assigns the 'posp_agent' role by default."""
    # Check if user already exists
    stmt = select(User).where(User.email == user_in.email)
    existing_user = db.scalar(stmt)
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="A user with this email address already exists"
        )
    
    # Resolve default role (create if not present)
    stmt_role = select(Role).where(Role.name == "posp_agent")
    role = db.scalar(stmt_role)
    if not role:
        role = Role(name="posp_agent", description="Default user role for POSP agents")
        db.add(role)
        db.flush()

    # If this is the very first user registering, make them an Admin instead
    stmt_any_users = select(User).limit(1)
    any_users = db.scalar(stmt_any_users)
    if not any_users:
        admin_role = db.scalar(select(Role).where(Role.name == "admin"))
        if not admin_role:
            admin_role = Role(name="admin", description="Full administrative access")
            db.add(admin_role)
            db.flush()
        roles = [admin_role]
    else:
        roles = [role]

    new_user = User(
        email=user_in.email,
        full_name=user_in.full_name,
        hashed_password=get_password_hash(user_in.password),
        is_active=True,
        roles=roles
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    return new_user

@router.post("/login", response_model=Token)
def login(
    response: Response,
    credentials: LoginCredentials,
    db: Session = Depends(deps.get_db)
) -> Any:
    """Traditional sign-in endpoint returning access token and setting refresh cookie."""
    user = AuthService.authenticate_user(db, email=credentials.email, password=credentials.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Incorrect email or password"
        )
    
    # Generate tokens
    roles = [role.name for role in user.roles]
    access_token = create_access_token(subject=user.id, email=user.email, roles=roles)
    refresh_token = AuthService.create_refresh_token(db, user_id=user.id)
    
    set_refresh_cookie(response, refresh_token)
    return {"access_token": access_token, "token_type": "bearer"}

@router.get("/oauth/{provider}/login")
def oauth_login(provider: str, redirect_uri: str, state: str = "randomstate") -> Any:
    """
    Returns the authorization redirect URL for Google or Microsoft login.
    The frontend client will redirect user to this returned URL.
    """
    try:
        if provider == "google":
            url = AuthService.get_google_auth_url(state, redirect_uri)
        elif provider == "microsoft":
            url = AuthService.get_microsoft_auth_url(state, redirect_uri)
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"OAuth provider '{provider}' is not supported"
            )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc))
    return {"redirect_url": url}

@router.post("/oauth/{provider}/callback", response_model=Token)
def oauth_callback(
    provider: str,
    callback_data: OAuthCallbackRequest,
    response: Response,
    db: Session = Depends(deps.get_db)
) -> Any:
    """
    Handles the authorization code redirect callback.
    Exchanges provider code for user identity, logs in user, and issues tokens.
    """
    # In production, validate callback_data.state against CSRF token saved in state session/cookie.
    if provider == "google":
        redirect_uri = settings.GOOGLE_OAUTH_REDIRECT_URI
    elif provider == "microsoft":
        redirect_uri = settings.MICROSOFT_OAUTH_REDIRECT_URI
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"OAuth provider '{provider}' is not supported"
        )
    
    try:
        user = AuthService.process_oauth_callback(
            db, provider=provider, code=callback_data.code, redirect_uri=redirect_uri
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="OAuth authentication failed"
        )

    # Issue local session tokens
    roles = [role.name for role in user.roles]
    access_token = create_access_token(subject=user.id, email=user.email, roles=roles)
    refresh_token = AuthService.create_refresh_token(db, user_id=user.id)

    set_refresh_cookie(response, refresh_token)
    return {"access_token": access_token, "token_type": "bearer"}

@router.post("/refresh", response_model=Token)
def refresh_token(
    request: Request,
    response: Response,
    db: Session = Depends(deps.get_db)
) -> Any:
    """
    Rotates access and refresh tokens.
    Reads current refresh token from cookie, invalidates it, sets a new one, and returns access token.
    """
    old_refresh_token = request.cookies.get(REFRESH_TOKEN_COOKIE_KEY)
    if not old_refresh_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token is missing"
        )

    rotation_result = AuthService.rotate_refresh_token(db, old_refresh_token)
    if not rotation_result:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid, expired or reused refresh token"
        )

    new_access_token, new_refresh_token = rotation_result
    set_refresh_cookie(response, new_refresh_token)
    
    return {"access_token": new_access_token, "token_type": "bearer"}

@router.post("/logout")
def logout(request: Request, response: Response, db: Session = Depends(deps.get_db)) -> Any:
    """Revokes the refresh token and clears the authentication cookie."""
    old_refresh_token = request.cookies.get(REFRESH_TOKEN_COOKIE_KEY)
    if old_refresh_token:
        AuthService.revoke_refresh_token(db, old_refresh_token)
    
    response.delete_cookie(key=REFRESH_TOKEN_COOKIE_KEY, path="/")
    return {"detail": "Successfully logged out"}
