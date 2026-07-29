import logging
import uuid
from typing import Any, List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import select

from app.api import deps
from app.models.chat import Conversation, Message, Feedback
from app.schemas.chat import (
    MessageCreate,
    MessageResponse,
    ConversationResponse,
    ConversationDetailResponse,
    FeedbackCreate,
    FeedbackResponse
)
from app.services.rag import RAGService

logger = logging.getLogger(__name__)
router = APIRouter()

RAG_FAILURE_MESSAGE = (
    "I'm temporarily unable to process your request. "
    "Please try again in a moment or contact support if the issue persists."
)


@router.get("/health")
def chat_health() -> dict:
    """Public health probe for the chat service."""
    return {"status": "ok", "service": "chat"}


@router.post("/message", response_model=MessageResponse, status_code=status.HTTP_201_CREATED)
def send_chat_message(
    payload: MessageCreate,
    db: Session = Depends(deps.get_db),
    current_user: Any = Depends(deps.get_chat_user)
) -> Any:
    """
    Sends a query to the AI Chatbot.
    If conversation_id is omitted, initiates a new chat session automatically.
    Query outputs are resolved through vector semantic context search and LLM synthesis.
    """
    conversation = None
    
    # 1. Resolve or create conversation session
    if payload.conversation_id:
        stmt = select(Conversation).where(
            Conversation.id == payload.conversation_id,
            Conversation.user_id == current_user.id
        )
        conversation = db.scalar(stmt)
        if not conversation:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Conversation session not found."
            )
    else:
        # Create a new conversation session
        title = payload.content[:50] + "..." if len(payload.content) > 50 else payload.content
        conversation = Conversation(
            user_id=current_user.id,
            title=title
        )
        db.add(conversation)
        db.flush()  # populate ID

    # 2. Log user message
    user_msg = Message(
        conversation_id=conversation.id,
        role="user",
        content=payload.content,
        sources=None
    )
    db.add(user_msg)
    db.flush()

    # 3. Pull historical context for multi-turn chat (limit to last 6 messages)
    stmt_history = select(Message).where(
        Message.conversation_id == conversation.id
    ).order_by(Message.created_at.desc()).limit(7)
    
    history_records = db.scalars(stmt_history).all()
    # Reverse to keep ascending chronological order, exclude current user message
    history_records = reversed(history_records[1:])
    chat_history = [
        {"role": "assistant" if r.role == "assistant" else "user", "content": r.content}
        for r in history_records
    ]

    # 4. Invoke RAG retriever and model inference
    try:
        rag_result = RAGService.answer_query(
            query=payload.content,
            product_id=payload.product_id,
            chat_history=chat_history
        )
    except Exception:
        logger.exception("RAG pipeline failed for conversation %s", conversation.id)
        rag_result = {
            "answer": RAG_FAILURE_MESSAGE,
            "sources": [],
            "confidence": "Low",
            "intent": "SystemError",
            "clause_type": "Unknown",
            "latency_ms": 0,
        }

    # 5. Log assistant response
    assistant_msg = Message(
        conversation_id=conversation.id,
        role="assistant",
        content=rag_result["answer"],
        sources=rag_result["sources"]
    )
    db.add(assistant_msg)
    db.commit()
    
    db.refresh(assistant_msg)
    return assistant_msg

@router.get("/history", response_model=List[ConversationResponse])
def get_chat_history_sessions(
    db: Session = Depends(deps.get_db),
    current_user: Any = Depends(deps.get_current_user)
) -> Any:
    """Retrieve all historical chat threads initiated by the current user."""
    stmt = select(Conversation).where(
        Conversation.user_id == current_user.id
    ).order_by(Conversation.created_at.desc())
    return db.scalars(stmt).all()

@router.get("/history/{conversation_id}", response_model=ConversationDetailResponse)
def get_chat_session_details(
    conversation_id: str,
    db: Session = Depends(deps.get_db),
    current_user: Any = Depends(deps.get_current_user)
) -> Any:
    """Retrieve full message transcripts for a specific chat thread."""
    try:
        conv_uuid = uuid.UUID(conversation_id)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid conversation_id UUID format.")

    stmt = select(Conversation).where(
        Conversation.id == conv_uuid,
        Conversation.user_id == current_user.id
    )
    conversation = db.scalar(stmt)
    if not conversation:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation session not found.")
        
    return conversation

@router.post("/feedback", response_model=FeedbackResponse, status_code=status.HTTP_201_CREATED)
def submit_message_feedback(
    payload: FeedbackCreate,
    db: Session = Depends(deps.get_db),
    current_user: Any = Depends(deps.get_current_user)
) -> Any:
    """
    Submits user feedback (thumbs up/down rating and comments) for a chatbot message.
    Only allows rating messages belonging to the user's conversations.
    """
    # Verify target message validity
    stmt_msg = select(Message).join(Conversation).where(
        Message.id == payload.message_id,
        Conversation.user_id == current_user.id
    )
    msg = db.scalar(stmt_msg)
    if not msg:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Target chatbot message not found or unauthorized."
        )

    # Check if feedback already logged
    stmt_fb = select(Feedback).where(Feedback.message_id == payload.message_id)
    existing_fb = db.scalar(stmt_fb)
    if existing_fb:
        existing_fb.rating = payload.rating
        existing_fb.comment = payload.comment
        db.commit()
        db.refresh(existing_fb)
        return existing_fb

    new_feedback = Feedback(
        message_id=payload.message_id,
        rating=payload.rating,
        comment=payload.comment
    )
    db.add(new_feedback)
    db.commit()
    db.refresh(new_feedback)
    return new_feedback
