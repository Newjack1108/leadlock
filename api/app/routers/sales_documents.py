"""
Sales documents router: price lists, spec sheets, etc. for attaching to emails.
"""
import os
import uuid
from pathlib import Path
from typing import Optional, List

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from sqlmodel import Session, select

from app.database import get_session
from app.models import SalesDocument, User, UserRole
from app.auth import get_current_user, require_role


router = APIRouter(prefix="/api/sales-documents", tags=["sales-documents"])

# Allowed content types for upload (PDF, Excel, CSV, images)
ALLOWED_CONTENT_TYPES = {
    "application/pdf",
    "application/vnd.ms-excel",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "text/csv",
    "text/plain",
    "image/jpeg",
    "image/png",
    "image/gif",
    "image/webp",
}
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB

# Storage directory (relative to api/ folder)
SALES_DOCUMENTS_DIR = Path(__file__).parent.parent.parent / "static" / "sales-documents"


def _ensure_storage_dir():
    SALES_DOCUMENTS_DIR.mkdir(parents=True, exist_ok=True)


def _sanitize_filename(filename: Optional[str]) -> str:
    if not filename or not filename.strip():
        return "document"
    return os.path.basename(filename.strip())


@router.get("")
async def list_sales_documents(
    category: Optional[str] = None,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """List all sales documents. All authenticated users."""
    statement = select(SalesDocument).order_by(SalesDocument.created_at.desc())
    if category:
        statement = statement.where(SalesDocument.category == category)
    docs = session.exec(statement).all()
    return [
        {
            "id": d.id,
            "name": d.name,
            "filename": d.filename,
            "content_type": d.content_type,
            "file_size": d.file_size,
            "category": d.category,
            "created_at": d.created_at.isoformat() if d.created_at else None,
        }
        for d in docs
    ]


@router.post("")
async def upload_sales_document(
    file: UploadFile = File(...),
    name: str = Form(...),
    category: Optional[str] = Form(None),
    session: Session = Depends(get_session),
    current_user: User = Depends(require_role([UserRole.DIRECTOR, UserRole.SALES_MANAGER])),
):
    """Upload a sales document. Director/Sales Manager only."""
    if not file.filename:
        raise HTTPException(status_code=400, detail="No file provided")

    content = await file.read()
    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=400,
            detail=f"File exceeds {MAX_FILE_SIZE // (1024 * 1024)}MB limit",
        )

    content_type = file.content_type or "application/octet-stream"
    allowed = content_type in ALLOWED_CONTENT_TYPES or content_type.startswith("image/")
    if not allowed:
        raise HTTPException(
            status_code=400,
            detail="File type not allowed. Allowed: PDF, Excel, CSV, images.",
        )

    _ensure_storage_dir()
    ext = Path(file.filename).suffix or ".bin"
    stored_filename = f"{uuid.uuid4()}{ext}"
    file_path = SALES_DOCUMENTS_DIR / stored_filename

    try:
        with open(file_path, "wb") as f:
            f.write(content)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save file: {e}")

    doc = SalesDocument(
        name=name.strip() or _sanitize_filename(file.filename),
        filename=_sanitize_filename(file.filename),
        file_path=str(file_path),
        content_type=content_type,
        file_size=len(content),
        category=category.strip() if category else None,
        created_by_id=current_user.id,
    )
    session.add(doc)
    session.commit()
    session.refresh(doc)

    return {
        "id": doc.id,
        "name": doc.name,
        "filename": doc.filename,
        "content_type": doc.content_type,
        "file_size": doc.file_size,
        "category": doc.category,
        "created_at": doc.created_at.isoformat() if doc.created_at else None,
    }


@router.get("/{doc_id}/download")
async def download_sales_document(
    doc_id: int,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """Download a sales document. All authenticated users."""
    statement = select(SalesDocument).where(SalesDocument.id == doc_id)
    doc = session.exec(statement).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    path = Path(doc.file_path)
    if not path.exists():
        raise HTTPException(status_code=404, detail="File not found on disk")

    return FileResponse(
        path,
        media_type=doc.content_type or "application/octet-stream",
        filename=doc.filename,
    )


@router.delete("/{doc_id}")
async def delete_sales_document(
    doc_id: int,
    session: Session = Depends(get_session),
    current_user: User = Depends(require_role([UserRole.DIRECTOR, UserRole.SALES_MANAGER])),
):
    """Delete a sales document. Director/Sales Manager only."""
    statement = select(SalesDocument).where(SalesDocument.id == doc_id)
    doc = session.exec(statement).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    path = Path(doc.file_path)
    if path.exists():
        try:
            path.unlink()
        except Exception:
            pass  # Still delete DB record

    session.delete(doc)
    session.commit()
    return {"message": "Deleted"}
