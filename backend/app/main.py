try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from sqlalchemy import select

from app.api.v1 import auth, users, documents, chat
from app.core.config import settings
from app.core.database import Base, engine, SessionLocal
from app.models.user import Role

app = FastAPI(
    title=settings.PROJECT_NAME,
    openapi_url=f"{settings.API_V1_STR}/openapi.json",
    docs_url="/docs",
    redoc_url="/redoc"
)

# Set CORS middleware
if settings.BACKEND_CORS_ORIGINS:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[str(origin) for origin in settings.BACKEND_CORS_ORIGINS],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

# Register routers
app.include_router(auth.router, prefix=f"{settings.API_V1_STR}/auth", tags=["auth"])
app.include_router(users.router, prefix=f"{settings.API_V1_STR}/users", tags=["users"])
app.include_router(documents.router, prefix=f"{settings.API_V1_STR}/documents", tags=["documents"])
app.include_router(chat.router, prefix=f"{settings.API_V1_STR}/chat", tags=["chat"])

@app.on_event("startup")
def on_startup() -> None:
    """Startup trigger to execute database diagnostics and bootstrap required system roles."""
    # Auto-generate tables if they do not exist (enables easy SQLite development)
    Base.metadata.create_all(bind=engine)
    
    db: Session = SessionLocal()
    try:
        # Seed standard authorization roles if missing
        required_roles = {
            "admin": "Full system administration and knowledge base management.",
            "posp_agent": "Access insurance documents, knowledge base search, and support chat.",
            "support_staff": "Manage support queue tickets, review agent logs, and view feedback."
        }
        for name, desc in required_roles.items():
            stmt = select(Role).where(Role.name == name)
            existing_role = db.scalar(stmt)
            if not existing_role:
                new_role = Role(name=name, description=desc)
                db.add(new_role)
        db.commit()
    except Exception as e:
        print(f"Error executing startup database seeding: {e}")
    finally:
        db.close()

@app.get("/")
def read_root():
    return {
        "status": "online",
        "project": settings.PROJECT_NAME,
        "environment": settings.ENV,
        "docs": "/docs"
    }
