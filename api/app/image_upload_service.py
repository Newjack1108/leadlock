import os
from typing import Optional
from fastapi import UploadFile, HTTPException
from pathlib import Path

# Try to import Cloudinary (optional)
try:
    import cloudinary
    import cloudinary.uploader
    CLOUDINARY_AVAILABLE = True
except ImportError:
    CLOUDINARY_AVAILABLE = False

# Initialize Cloudinary if available (will use environment variables)
if CLOUDINARY_AVAILABLE:
    cloudinary.config(
        cloud_name=os.getenv("CLOUDINARY_CLOUD_NAME"),
        api_key=os.getenv("CLOUDINARY_API_KEY"),
        api_secret=os.getenv("CLOUDINARY_API_SECRET"),
        secure=True
    )


async def upload_image_to_cloudinary(file: UploadFile) -> str:
    """
    Upload an image file to Cloudinary and return the URL.
    
    Args:
        file: FastAPI UploadFile object
        
    Returns:
        str: URL of the uploaded image
        
    Raises:
        HTTPException: If upload fails or file is not an image
    """
    if not CLOUDINARY_AVAILABLE:
        raise HTTPException(status_code=500, detail="Cloudinary is not configured")
    
    # Validate file type
    if not file.content_type or not file.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="File must be an image")
    
    # Read file content
    contents = await file.read()
    
    # Validate file size (max 10MB)
    max_size = 10 * 1024 * 1024  # 10MB
    if len(contents) > max_size:
        raise HTTPException(status_code=400, detail="Image size must be less than 10MB")
    
    try:
        # Upload to Cloudinary
        upload_result = cloudinary.uploader.upload(
            contents,
            folder="products",  # Organize images in a products folder
            resource_type="image",
            transformation=[
                {"width": 1200, "height": 1200, "crop": "limit"},  # Resize if too large
                {"quality": "auto"},  # Auto optimize quality
            ]
        )
        
        return upload_result["secure_url"]
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to upload image: {str(e)}")


async def upload_image_local(file: UploadFile, upload_dir: Path) -> str:
    """
    Upload an image file to local storage and return the URL.
    This is a fallback if cloud storage is not configured.
    
    Args:
        file: FastAPI UploadFile object
        upload_dir: Directory to save the file
        
    Returns:
        str: URL path of the uploaded image
    """
    # Validate file type
    if not file.content_type or not file.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="File must be an image")
    
    # Create upload directory if it doesn't exist
    upload_dir.mkdir(parents=True, exist_ok=True)
    
    # Generate unique filename
    import uuid
    file_extension = Path(file.filename).suffix if file.filename else ".jpg"
    unique_filename = f"{uuid.uuid4()}{file_extension}"
    file_path = upload_dir / unique_filename
    
    # Save file
    contents = await file.read()
    
    # Validate file size (max 10MB)
    max_size = 10 * 1024 * 1024  # 10MB
    if len(contents) > max_size:
        raise HTTPException(status_code=400, detail="Image size must be less than 10MB")
    
    with open(file_path, "wb") as f:
        f.write(contents)
    
    # Return URL path (relative to static files)
    return f"/static/products/{unique_filename}"


async def upload_product_image(file: UploadFile) -> str:
    """
    Upload a product image. Uses cloud storage if configured, otherwise local storage.
    
    Args:
        file: FastAPI UploadFile object
        
    Returns:
        str: URL of the uploaded image
    """
    # Check if Cloudinary is configured
    cloud_name = os.getenv("CLOUDINARY_CLOUD_NAME")
    api_key = os.getenv("CLOUDINARY_API_KEY")
    api_secret = os.getenv("CLOUDINARY_API_SECRET")
    
    if cloud_name and api_key and api_secret:
        # Use Cloudinary
        return await upload_image_to_cloudinary(file)
    else:
        # Fallback to local storage
        static_dir = Path(__file__).parent.parent / "static" / "products"
        return await upload_image_local(file, static_dir)
