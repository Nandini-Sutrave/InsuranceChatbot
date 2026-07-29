import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional, Tuple, Dict, Any
import httpx
from urllib.parse import urlencode
from sqlalchemy.orm import Session
from sqlalchemy import select

from app.core.config import settings
from app.core.security import verify_password, get_password_hash, create_access_token
from app.models.user import User, Role, OAuthAccount, RefreshToken, Session as UserSession, user_roles


class AuthService:
    @staticmethod
    def authenticate_user(db: Session, email: str, password: str) -> Optional[User]:
        """Authenticate a user by email and password."""
        stmt = select(User).where(User.email == email)
        user = db.scalar(stmt)
        if not user or not user.is_active or not user.hashed_password:
            return None
        if not verify_password(password, user.hashed_password):
            return None
        return user

    @staticmethod
    def create_refresh_token(db: Session, user_id: uuid.UUID) -> str:
        """Create a new refresh token and persist it in the database."""
        token_str = secrets.token_urlsafe(64)
        expires_at = datetime.now(timezone.utc) + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
        
        db_token = RefreshToken(
            user_id=user_id,
            token=token_str,
            expires_at=expires_at,
            is_revoked=False
        )
        db.add(db_token)
        db.commit()
        return token_str

    @staticmethod
    def rotate_refresh_token(db: Session, old_token_str: str) -> Optional[Tuple[str, str]]:
        """
        Rotates a refresh token.
        If a token reuse is detected (revoked token presented), it revokes ALL tokens for that user.
        """
        stmt = select(RefreshToken).where(RefreshToken.token == old_token_str)
        db_token = db.scalar(stmt)
        
        if not db_token:
            return None

        # Breach detection: if token is already revoked, revoke all tokens for this user
        if db_token.is_revoked:
            stmt_revoke_all = select(RefreshToken).where(RefreshToken.user_id == db_token.user_id)
            user_tokens = db.scalars(stmt_revoke_all).all()
            for t in user_tokens:
                t.is_revoked = True
            db.commit()
            return None

        # Check expiration
        if db_token.expires_at.replace(tzinfo=timezone.utc) < datetime.now(timezone.utc):
            return None

        # Revoke old token
        db_token.is_revoked = True
        
        # Fetch user
        stmt_user = select(User).where(User.id == db_token.user_id)
        user = db.scalar(stmt_user)
        if not user or not user.is_active:
            db.commit()
            return None

        # Issue new pair
        roles = [r.name for r in user.roles]
        new_access_token = create_access_token(subject=user.id, email=user.email, roles=roles)
        new_refresh_token = AuthService.create_refresh_token(db, user.id)
        
        return new_access_token, new_refresh_token

    @staticmethod
    def revoke_refresh_token(db: Session, token_str: str) -> None:
        """Revoke a refresh token on logout."""
        stmt = select(RefreshToken).where(RefreshToken.token == token_str)
        db_token = db.scalar(stmt)
        if db_token:
            db_token.is_revoked = True
            db.commit()

    @staticmethod
    def get_google_auth_url(state: str, redirect_uri: str) -> str:
        """Construct the URL to redirect the user to Google OAuth."""
        if not settings.GOOGLE_CLIENT_ID:
            raise ValueError("GOOGLE_CLIENT_ID is not configured")
        base_url = "https://accounts.google.com/o/oauth2/v2/auth"
        params = {
            "client_id": settings.GOOGLE_CLIENT_ID,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": "openid email profile",
            "state": state,
            "access_type": "offline",
            "prompt": "select_account"
        }
        return f"{base_url}?{urlencode(params)}"

    @staticmethod
    def get_microsoft_auth_url(state: str, redirect_uri: str) -> str:
        """Construct the URL to redirect the user to Microsoft OAuth."""
        if not settings.MICROSOFT_CLIENT_ID:
            raise ValueError("MICROSOFT_CLIENT_ID is not configured")
        tenant = settings.MICROSOFT_TENANT_ID
        base_url = f"https://login.microsoftonline.com/{tenant}/oauth2/v2.0/authorize"
        params = {
            "client_id": settings.MICROSOFT_CLIENT_ID,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": "openid email profile User.Read",
            "state": state,
            "response_mode": "query"
        }
        return f"{base_url}?{urlencode(params)}"

    @classmethod
    def process_oauth_callback(
        cls, db: Session, provider: str, code: str, redirect_uri: str
    ) -> Optional[User]:
        """Exchanges authorization code for user details and links/creates account."""
        if provider == "google":
            user_info = cls._fetch_google_user_info(code, redirect_uri)
        elif provider == "microsoft":
            user_info = cls._fetch_microsoft_user_info(code, redirect_uri)
        else:
            raise ValueError(f"Unknown OAuth provider: {provider}")

        if not user_info:
            return None

        email = user_info["email"]
        provider_user_id = user_info["id"]
        full_name = user_info.get("name", email.split("@")[0])

        # Find or create user
        stmt_user = select(User).where(User.email == email)
        user = db.scalar(stmt_user)

        if not user:
            # Check if role 'posp_agent' exists, create if not
            stmt_role = select(Role).where(Role.name == "posp_agent")
            role = db.scalar(stmt_role)
            if not role:
                role = Role(name="posp_agent", description="Point of Sales Person agent")
                db.add(role)
                db.flush()

            # Auto-register user
            user = User(
                email=email,
                full_name=full_name,
                hashed_password=None,  # No local password set yet
                is_active=True,
                roles=[role]
            )
            db.add(user)
            db.flush()

        # Check if OAuth mapping exists, create if not
        stmt_oauth = select(OAuthAccount).where(
            OAuthAccount.user_id == user.id, OAuthAccount.provider == provider
        )
        oauth_account = db.scalar(stmt_oauth)

        if not oauth_account:
            oauth_account = OAuthAccount(
                user_id=user.id,
                provider=provider,
                provider_user_id=provider_user_id
            )
            db.add(oauth_account)
            db.commit()
        else:
            db.commit()

        return user

    @staticmethod
    def _fetch_google_user_info(code: str, redirect_uri: str) -> Optional[Dict[str, Any]]:
        """Exchanges Google auth code for user details."""
        token_url = "https://oauth2.googleapis.com/token"
        data = {
            "code": code,
            "client_id": settings.GOOGLE_CLIENT_ID,
            "client_secret": settings.GOOGLE_CLIENT_SECRET,
            "redirect_uri": redirect_uri,
            "grant_type": "authorization_code",
        }
        try:
            with httpx.Client() as client:
                res = client.post(token_url, data=data)
                res.raise_for_status()
                tokens = res.json()
                access_token = tokens.get("access_token")

                # Fetch user details
                userinfo_url = "https://www.googleapis.com/oauth2/v3/userinfo"
                headers = {"Authorization": f"Bearer {access_token}"}
                userinfo_res = client.get(userinfo_url, headers=headers)
                userinfo_res.raise_for_status()
                return userinfo_res.json()
        except Exception:
            return None

    @staticmethod
    def _fetch_microsoft_user_info(code: str, redirect_uri: str) -> Optional[Dict[str, Any]]:
        """Exchanges Microsoft Entra ID code for user details via MS Graph."""
        tenant = settings.MICROSOFT_TENANT_ID
        token_url = f"https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token"
        data = {
            "code": code,
            "client_id": settings.MICROSOFT_CLIENT_ID,
            "client_secret": settings.MICROSOFT_CLIENT_SECRET,
            "redirect_uri": redirect_uri,
            "grant_type": "authorization_code",
            "scope": "openid email profile User.Read"
        }
        try:
            with httpx.Client() as client:
                res = client.post(token_url, data=data)
                res.raise_for_status()
                tokens = res.json()
                access_token = tokens.get("access_token")

                # Fetch profile from Microsoft Graph
                graph_url = "https://graph.microsoft.com/v1.0/me"
                headers = {"Authorization": f"Bearer {access_token}"}
                graph_res = client.get(graph_url, headers=headers)
                graph_res.raise_for_status()
                profile = graph_res.json()

                # Entra ID API returns standard properties, email is under mail or userPrincipalName
                email = profile.get("mail") or profile.get("userPrincipalName")
                return {
                    "id": profile.get("id"),
                    "email": email,
                    "name": profile.get("displayName")
                }
        except Exception:
            return None
