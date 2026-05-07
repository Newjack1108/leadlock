"""Cloudinary-backed file storage for customer / quote / order files.

All files for a customer live under ``customers/{customer_id}/`` in Cloudinary
regardless of which context (customer profile, quote or order) they were
uploaded from. Unlike product images we never fall back to local disk —
Railway disks are ephemeral and these files must persist.
"""

import os
import sys
from typing import Any, Dict

from fastapi import HTTPException, UploadFile

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


ALLOWED_MIME = {"application/pdf", "image/jpeg", "image/png"}
MAX_BYTES = 25 * 1024 * 1024  # 25 MB


def _ensure_configured() -> None:
    if not CLOUDINARY_AVAILABLE:
        raise HTTPException(status_code=500, detail="Cloudinary is not configured")
    if not (
        os.getenv("CLOUDINARY_CLOUD_NAME")
        and os.getenv("CLOUDINARY_API_KEY")
        and os.getenv("CLOUDINARY_API_SECRET")
    ):
        raise HTTPException(status_code=500, detail="Cloudinary is not configured")


async def upload_customer_file_to_cloudinary(
    file: UploadFile, customer_id: int
) -> Dict[str, Any]:
    """Upload a single PDF/JPG/PNG to Cloudinary under ``customers/{customer_id}``.

    Returns a dict with ``secure_url``, ``public_id``, ``resource_type``,
    ``format`` and ``bytes`` taken from Cloudinary's response.
    """
    _ensure_configured()

    content_type = (file.content_type or "").lower()
    if content_type not in ALLOWED_MIME:
        raise HTTPException(
            status_code=400,
            detail="File must be a PDF, JPG or PNG",
        )

    contents = await file.read()
    if len(contents) > MAX_BYTES:
        raise HTTPException(
            status_code=400,
            detail="File size must be 25 MB or less",
        )
    if not contents:
        raise HTTPException(status_code=400, detail="Empty file")

    try:
        upload_result = cloudinary.uploader.upload(
            contents,
            folder=f"customers/{customer_id}",
            resource_type="auto",
            use_filename=True,
            unique_filename=True,
        )
    except Exception as e:  # pragma: no cover - network/cloud failure
        raise HTTPException(status_code=500, detail=f"Failed to upload file: {str(e)}")

    return {
        "secure_url": upload_result.get("secure_url"),
        "public_id": upload_result.get("public_id"),
        "resource_type": upload_result.get("resource_type", "raw"),
        "format": upload_result.get("format"),
        "bytes": upload_result.get("bytes", len(contents)),
    }


def delete_customer_file_from_cloudinary(public_id: str, resource_type: str) -> None:
    """Best-effort delete from Cloudinary; missing assets are not an error."""
    if not CLOUDINARY_AVAILABLE:
        return
    if not (
        os.getenv("CLOUDINARY_CLOUD_NAME")
        and os.getenv("CLOUDINARY_API_KEY")
        and os.getenv("CLOUDINARY_API_SECRET")
    ):
        return
    try:
        cloudinary.uploader.destroy(
            public_id,
            resource_type=resource_type or "image",
            invalidate=True,
        )
    except Exception as e:  # pragma: no cover - network/cloud failure
        print(
            f"Cloudinary delete failed for public_id={public_id} ({resource_type}): {e}",
            file=sys.stderr,
            flush=True,
        )
