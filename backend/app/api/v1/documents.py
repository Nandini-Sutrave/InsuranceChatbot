import uuid
from typing import Any, List, Optional
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, BackgroundTasks, status, Response
from sqlalchemy.orm import Session
from sqlalchemy import select

from app.api import deps
from app.models.document import Document, ProductKnowledgeBase
from app.schemas.document import DocumentResponse, ProductKBResponse, ProductKBCreate
from app.services.storage import StorageService

router = APIRouter()
storage_service = StorageService()

from app.services.ingestion import IngestionService

def trigger_ingestion_background(document_id: uuid.UUID, file_path: str):
    """Executes the document chunking and vector embedding indexing pipeline in the background."""
    IngestionService.ingest_document(document_id)


@router.get("/kb", response_model=List[ProductKBResponse])
def list_knowledge_bases(db: Session = Depends(deps.get_db)) -> Any:
    """List all product knowledge base categories."""
    stmt = select(ProductKnowledgeBase).order_by(ProductKnowledgeBase.name)
    return db.scalars(stmt).all()

@router.post("/kb", response_model=ProductKBResponse, status_code=status.HTTP_201_CREATED)
def create_knowledge_base(
    kb_in: ProductKBCreate,
    db: Session = Depends(deps.get_db),
    current_user: Any = Depends(deps.RoleChecker(["admin"]))
) -> Any:
    """Create a new product knowledge base category. Admin only."""
    stmt = select(ProductKnowledgeBase).where(ProductKnowledgeBase.name == kb_in.name)
    existing_kb = db.scalar(stmt)
    if existing_kb:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="A product knowledge base with this name already exists."
        )
    
    new_kb = ProductKnowledgeBase(
        name=kb_in.name,
        description=kb_in.description
    )
    db.add(new_kb)
    db.commit()
    db.refresh(new_kb)
    return new_kb

@router.post("/upload", response_model=DocumentResponse, status_code=status.HTTP_201_CREATED)
def upload_document(
    background_tasks: BackgroundTasks,
    product_id: str = Form(...),
    file: UploadFile = File(...),
    db: Session = Depends(deps.get_db),
    current_user: Any = Depends(deps.RoleChecker(["admin"]))
) -> Any:
    """
    Upload an insurance document linked to a product category.
    Saves the file to local vault and schedules ChromaDB vector ingestion in background. Admin only.
    """
    # Parse UUID
    try:
        kb_uuid = uuid.UUID(product_id)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid product_id UUID format.")

    # Validate product category
    stmt = select(ProductKnowledgeBase).where(ProductKnowledgeBase.id == kb_uuid)
    kb = db.scalar(stmt)
    if not kb:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Target Product Knowledge Base not found.")

    # Save to disk
    try:
        saved_path = storage_service.save_file(file)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Could not save file to disk storage: {e}"
        )

    # Register in DB
    file.file.seek(0, 2)  # Seek to end of file to read size
    file_size = file.file.tell()
    file.file.seek(0)     # Reset file cursor

    new_doc = Document(
        filename=file.filename or "unnamed_file",
        file_path=saved_path,
        file_size=file_size,
        mime_type=file.content_type or "application/octet-stream",
        status="pending",
        product_id=kb.id
    )
    
    db.add(new_doc)
    db.commit()
    db.refresh(new_doc)

    # Queue background parsing & vector database embedding pipeline
    background_tasks.add_task(trigger_ingestion_background, new_doc.id, saved_path)

    return new_doc

@router.get("/", response_model=List[DocumentResponse])
def list_documents(
    product_id: Optional[str] = None,
    status: Optional[str] = None,
    db: Session = Depends(deps.get_db)
) -> Any:
    """Retrieve list of documents, optionally filtered by product category and ingestion status."""
    stmt = select(Document)
    
    if product_id:
        try:
            stmt = stmt.where(Document.product_id == uuid.UUID(product_id))
        except ValueError:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid product_id UUID format.")
            
    if status:
        stmt = stmt.where(Document.status == status)

    stmt = stmt.order_by(Document.created_at.desc())
    return db.scalars(stmt).all()

@router.delete("/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_document(
    document_id: str,
    db: Session = Depends(deps.get_db),
    current_user: Any = Depends(deps.RoleChecker(["admin"]))
):
    """Deletes a document from relational storage and local disk. Admin only."""
    try:
        doc_uuid = uuid.UUID(document_id)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid document_id UUID format.")

    stmt = select(Document).where(Document.id == doc_uuid)
    doc = db.scalar(stmt)
    if not doc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found.")

    # Remove from disk
    storage_service.delete_file(doc.file_path)

    # Clean vector collections in ChromaDB
    IngestionService.remove_document_vectors(doc_uuid)

    # Delete relational mapping
    db.delete(doc)
    db.commit()
