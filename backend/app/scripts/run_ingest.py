import os
import sys
import uuid
from typing import Dict, Any
from sqlalchemy.orm import Session
from sqlalchemy import select

# Ensure backend root is in system path for app.* imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from app.core.database import SessionLocal, Base, engine
from app.models.document import Document, ProductKnowledgeBase
from app.services.ingestion import IngestionService

# Deterministic File to Metadata Registry
METADATA_MAP = {
    "Brochure_Star_Health_Assure_Insurance_Policy": {
        "carrier_name": "Star Health",
        "lob": "Health",
        "document_type": "Brochure",
        "description": "Star Health Assure brochure details."
    },
    "Policy_Star_Comprehensive_Insurance_Policy": {
        "carrier_name": "Star Health",
        "lob": "Health",
        "document_type": "Policy Wording",
        "description": "Star Health Comprehensive terms."
    },
    "Guidelines_on_POS_Person_07112016": {
        "carrier_name": "IRDAI",
        "lob": "Regulatory",
        "document_type": "Guideline",
        "description": "Official POSP agent regulations."
    },
    "handbook-posp-non-life-and-health-insurance": {
        "carrier_name": "NIILM",
        "lob": "Regulatory",
        "document_type": "Handbook",
        "description": "POSP non-life training manual."
    },
    "HDFC-Life-click-2-protect-supreme-plus": {
        "carrier_name": "HDFC Life",
        "lob": "Life",
        "document_type": "Policy Wording",
        "description": "HDFC Click 2 Protect insurance clauses."
    },
    "Health Protector Policy Wording": {
        "carrier_name": "IFFCO Tokio",
        "lob": "Health",
        "document_type": "Policy Wording",
        "description": "IFFCO Health Protector policy booklet."
    },
    "indianbank-policy-wordings": {
        "carrier_name": "Indian Bank",
        "lob": "Health",
        "document_type": "Policy Wording",
        "description": "Indian Bank health insurance details."
    },
    "ILP": {
        "carrier_name": "SBI General",
        "lob": "Health",
        "document_type": "Policy Wording",
        "description": "SBI General Individual Health Wording."
    },
    "Freshteam’s-New-Employee-Onboarding-Checklist-": {
        "carrier_name": "Internal",
        "lob": "HR",
        "document_type": "Checklist",
        "description": "New hire checklist guidelines."
    }
}

from pathlib import Path

def resolve_metadata_from_path(file_path: Path, docs_path: Path) -> Dict[str, str]:
    """
    Resolves the metadata dynamically by inspecting the subfolders leading to the file (relative to docs_path).
    """
    relative_path = file_path.relative_to(docs_path)
    parts = relative_path.parts[:-1]  # exclude filename
    levels = len(parts)

    scheme_name = None
    if levels >= 3:
        carrier_name = parts[0]
        lob = parts[1]
        scheme_name = parts[2]
    elif levels == 2:
        carrier_name = parts[0]
        lob = parts[1]
    elif levels == 1:
        carrier_name = "General"
        lob = parts[0]
    else:
        carrier_name = "General"
        lob = "Other"

    # Default document type logic based on filename keywords
    filename_lower = file_path.name.lower()
    if "brochure" in filename_lower:
        doc_type = "Brochure"
    elif "policy" in filename_lower or "wording" in filename_lower or "pw" in filename_lower:
        doc_type = "Policy Wording"
    elif "guideline" in filename_lower:
        doc_type = "Guideline"
    elif "handbook" in filename_lower:
        doc_type = "Handbook"
    elif "prospectus" in filename_lower:
        doc_type = "Prospectus"
    elif "cis" in filename_lower:
        doc_type = "Customer Information Sheet"
    else:
        doc_type = "Document"

    metadata = {
        "carrier_name": carrier_name,
        "carrier": carrier_name,
        "lob": lob,
        "product_name": lob,
        "product": lob,
        "document_type": doc_type,
        "description": f"Dynamic metadata resolved document for {carrier_name} {lob}."
    }
    if scheme_name:
        metadata["scheme_name"] = scheme_name

    return metadata

def main():
    db: Session = SessionLocal()
    docs_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))), "docs")
    docs_path = Path(docs_dir)
    
    if not os.path.exists(docs_dir):
        print(f"Error: Target docs folder not found at: {docs_dir}")
        sys.exit(1)

    # Auto-generate tables on startup if they don't exist
    print("Verifying database schema tables...")
    Base.metadata.create_all(bind=engine)

    pdf_files = sorted(list(docs_path.rglob("*.pdf")))
    print(f"Found {len(pdf_files)} PDF files inside {docs_dir}.")

    for file_index, file_path in enumerate(pdf_files):
        relative_path = file_path.relative_to(docs_path)
        filename = relative_path.as_posix()
        
        meta = resolve_metadata_from_path(file_path, docs_path)
        lob = meta["lob"]
        carrier_name = meta["carrier_name"]
        doc_type = meta["document_type"]
        description = meta["description"]
        scheme_name = meta.get("scheme_name")

        print("\n" + "="*50)
        print(f"Processing File {file_index + 1}/{len(pdf_files)}: {filename}")
        print(f"LOB: {lob} | Carrier: {carrier_name} | Type: {doc_type}" + (f" | Scheme: {scheme_name}" if scheme_name else ""))
        print("="*50)

        # 1. Resolve product knowledge base category in DB
        stmt_kb = select(ProductKnowledgeBase).where(ProductKnowledgeBase.name == lob)
        kb = db.scalar(stmt_kb)
        if not kb:
            kb = ProductKnowledgeBase(
                name=lob,
                description=f"Documents associated with {lob} product segment."
            )
            db.add(kb)
            db.flush()

        # 2. Check if document already indexed in relational DB
        stmt_doc = select(Document).where(Document.filename == filename)
        doc = db.scalar(stmt_doc)
        if not doc:
            # Create a Document mapping in DB
            file_size = os.path.getsize(file_path)
            doc = Document(
                filename=filename,
                file_path=str(file_path.resolve()),
                file_size=file_size,
                mime_type="application/pdf",
                status="pending",
                product_id=kb.id
            )
            db.add(doc)
            db.flush()
        elif doc.status == "completed":
            print(f"Document {filename} is already completed. Skipping.")
            continue

        db.commit()

        # 3. Trigger layout-aware ingestion and vector indexing
        print(f"Triggering Gemini ingestion and ChromaDB vector mapping for: {filename}")
        
        custom_metadata = {
            "carrier_name": carrier_name,
            "carrier": carrier_name,
            "lob": lob,
            "product_name": lob,
            "product": lob,
            "document_type": doc_type
        }
        if scheme_name:
            custom_metadata["scheme_name"] = scheme_name

        IngestionService.ingest_document(
            document_id=doc.id,
            custom_metadata=custom_metadata
        )

    print("\nIngestion pipeline execution complete!")
    db.close()

if __name__ == "__main__":
    main()
