"""Storage helpers for reusable sales documents.

New uploads prefer Cloudinary for durable production storage. Legacy rows may
still point at local disk, so downloads and quote attachments support both.
"""

import os
import sys
import uuid
from pathlib import Path
from typing import Any, Dict
from urllib.parse import quote

import httpx
from fastapi import HTTPException
from fastapi.responses import FileResponse, Response

from app.models import SalesDocument

try:
    import cloudinary
    import cloudinary.uploader

    CLOUDINARY_AVAILABLE = True
except ImportError:
    CLOUDINARY_AVAILABLE = False

if CLOUDINARY_AVAILABLE:
    cloudinary.config(
        cloud_name=os.getenv("CLOUDINARY_CLOUD_NAME"),
        api_key=os.getenv("CLOUDINARY_API_KEY"),
        api_secret=os.getenv("CLOUDINARY_API_SECRET"),
        secure=True,
    )


SALES_DOCUMENTS_DIR = Path(__file__).parent.parent / "static" / "sales-documents"


def _cloudinary_configured() -> bool:
    return CLOUDINARY_AVAILABLE and bool(
        os.getenv("CLOUDINARY_CLOUD_NAME")
        and os.getenv("CLOUDINARY_API_KEY")
        and os.getenv("CLOUDINARY_API_SECRET")
    )


def _is_remote_reference(value: str) -> bool:
    lowered = (value or "").strip().lower()
    return lowered.startswith("http://") or lowered.startswith("https://")


def _content_disposition(filename: str) -> str:
    safe_name = os.path.basename((filename or "").strip()) or "document"
    ascii_name = safe_name.encode("ascii", "ignore").decode("ascii").replace('"', "") or "document"
    return f'attachment; filename="{ascii_name}"; filename*=UTF-8\'\'{quote(safe_name)}'


def _ensure_local_storage_dir() -> None:
    SALES_DOCUMENTS_DIR.mkdir(parents=True, exist_ok=True)


def store_sales_document_content(content: bytes, *, original_filename: str) -> Dict[str, Any]:
    """Persist document bytes to durable storage when configured."""
    if _cloudinary_configured():
        try:
            upload_result = cloudinary.uploader.upload(
                content,
                folder="sales-documents",
                resource_type="auto",
                use_filename=True,
                unique_filename=True,
            )
        except Exception as exc:  # pragma: no cover - network/cloud failure
            raise HTTPException(status_code=500, detail=f"Failed to upload document: {exc}")

        secure_url = upload_result.get("secure_url")
        public_id = upload_result.get("public_id")
        if not secure_url or not public_id:
            raise HTTPException(status_code=500, detail="Upload completed without a durable document URL")
        return {
            "file_path": secure_url,
            "cloudinary_public_id": public_id,
            "cloudinary_resource_type": upload_result.get("resource_type") or "raw",
        }

    if os.getenv("RAILWAY_ENVIRONMENT"):
        raise HTTPException(
            status_code=500,
            detail="Cloudinary is not configured for sales documents",
        )

    _ensure_local_storage_dir()
    extension = Path(original_filename or "").suffix or ".bin"
    stored_filename = f"{uuid.uuid4()}{extension}"
    file_path = SALES_DOCUMENTS_DIR / stored_filename
    try:
        file_path.write_bytes(content)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to save file: {exc}")
    return {
        "file_path": str(file_path),
        "cloudinary_public_id": None,
        "cloudinary_resource_type": None,
    }


async def load_sales_document_bytes(doc: SalesDocument) -> bytes:
    """Return document bytes from remote storage or the legacy local path."""
    file_ref = (doc.file_path or "").strip()
    if _is_remote_reference(file_ref):
        try:
            async with httpx.AsyncClient(follow_redirects=True, timeout=30.0) as client:
                response = await client.get(file_ref)
        except Exception as exc:  # pragma: no cover - network/cloud failure
            raise HTTPException(status_code=502, detail=f"Failed to fetch stored document: {exc}")
        if response.status_code == 404:
            raise HTTPException(status_code=404, detail="Stored document no longer exists in cloud storage")
        if not response.is_success:
            raise HTTPException(
                status_code=502,
                detail=f"Stored document fetch failed ({response.status_code})",
            )
        if not response.content:
            raise HTTPException(status_code=404, detail="Stored document is empty")
        return response.content

    path = Path(file_ref)
    if not path.is_file():
        raise HTTPException(status_code=404, detail="File not found on disk")
    return path.read_bytes()


async def build_sales_document_download_response(doc: SalesDocument) -> Response:
    """Return an authenticated download response for local or cloud-backed documents."""
    file_ref = (doc.file_path or "").strip()
    media_type = doc.content_type or "application/octet-stream"
    filename = os.path.basename((doc.filename or "").strip()) or "document"

    if not _is_remote_reference(file_ref):
        path = Path(file_ref)
        if not path.exists():
            raise HTTPException(status_code=404, detail="File not found on disk")
        return FileResponse(path, media_type=media_type, filename=filename)

    content = await load_sales_document_bytes(doc)
    return Response(
        content=content,
        media_type=media_type,
        headers={"Content-Disposition": _content_disposition(filename)},
    )


def delete_sales_document_storage(doc: SalesDocument) -> None:
    """Best-effort cleanup for Cloudinary-backed or legacy local sales docs."""
    if doc.cloudinary_public_id:
        if not _cloudinary_configured():
            print(
                f"Cloudinary not configured during sales document delete for {doc.cloudinary_public_id}",
                file=sys.stderr,
                flush=True,
            )
            return
        try:
            cloudinary.uploader.destroy(
                doc.cloudinary_public_id,
                resource_type=doc.cloudinary_resource_type or "raw",
                invalidate=True,
            )
        except Exception as exc:  # pragma: no cover - network/cloud failure
            print(
                (
                    "Cloudinary delete failed for sales document "
                    f"{doc.cloudinary_public_id} ({doc.cloudinary_resource_type}): {exc}"
                ),
                file=sys.stderr,
                flush=True,
            )
        return

    file_ref = (doc.file_path or "").strip()
    if not file_ref or _is_remote_reference(file_ref):
        return

    path = Path(file_ref)
    if path.exists():
        try:
            path.unlink()
        except Exception:
            pass
