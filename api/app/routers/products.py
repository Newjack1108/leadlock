from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File
from sqlmodel import Session, select
from typing import Optional, List
from app.database import get_session
from app.models import Product, ProductCategory, User, ProductOptionalExtra
from app.auth import get_current_user, require_role
from app.schemas import ProductCreate, ProductUpdate, ProductResponse
from app.models import UserRole
from app.image_upload_service import upload_product_image
from datetime import datetime

router = APIRouter(prefix="/api/products", tags=["products"])


@router.get("", response_model=List[ProductResponse])
async def get_products(
    category: Optional[ProductCategory] = Query(None),
    is_extra: Optional[bool] = Query(None),
    is_active: Optional[bool] = Query(None),
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """Get list of products with optional filters."""
    statement = select(Product)
    
    if category:
        statement = statement.where(Product.category == category)
    
    if is_extra is not None:
        statement = statement.where(Product.is_extra == is_extra)
    
    # Default to active products if is_active is not specified
    if is_active is None:
        is_active = True
    
    statement = statement.where(Product.is_active == is_active)
    
    statement = statement.order_by(Product.category, Product.name)
    products = session.exec(statement).all()
    
    # Return products without nested optional_extras for list view (performance)
    return [ProductResponse(**{**product.dict(), "optional_extras": None}) for product in products]


@router.get("/categories")
async def get_categories(
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """Get all categories and their subcategories."""
    statement = select(Product.category, Product.subcategory).distinct()
    results = session.exec(statement).all()
    
    categories = {}
    for category, subcategory in results:
        if category not in categories:
            categories[category] = []
        if subcategory and subcategory not in categories[category]:
            categories[category].append(subcategory)
    
    return {
        "categories": list(categories.keys()),
        "subcategories": categories
    }


@router.post("/upload-image")
async def upload_image(
    file: UploadFile = File(...),
    current_user: User = Depends(require_role([UserRole.DIRECTOR]))
):
    """Upload a product image. DIRECTOR only."""
    try:
        image_url = await upload_product_image(file)
        return {"image_url": image_url}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to upload image: {str(e)}")


@router.get("/optional-extras", response_model=List[ProductResponse])
async def get_optional_extras(
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """Get all products marked as optional extras."""
    statement = select(Product).where(
        Product.is_extra == True,
        Product.is_active == True
    )
    products = session.exec(statement).all()
    return [ProductResponse(**product.dict()) for product in products]


@router.get("/{product_id}", response_model=ProductResponse)
async def get_product(
    product_id: int,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """Get product details with optional extras."""
    statement = select(Product).where(Product.id == product_id)
    product = session.exec(statement).first()
    
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    
    # Get optional extras for this product
    extras_statement = select(ProductOptionalExtra, Product).join(
        Product, ProductOptionalExtra.optional_extra_id == Product.id
    ).where(ProductOptionalExtra.product_id == product_id)
    
    extras_results = session.exec(extras_statement).all()
    optional_extras = []
    for extra_link, extra_product in extras_results:
        optional_extras.append(ProductResponse(**extra_product.dict()))
    
    product_dict = product.dict()
    product_dict["optional_extras"] = optional_extras if optional_extras else None
    
    return ProductResponse(**product_dict)


@router.post("", response_model=ProductResponse)
async def create_product(
    product_data: ProductCreate,
    session: Session = Depends(get_session),
    current_user: User = Depends(require_role([UserRole.DIRECTOR]))
):
    """Create a new product. DIRECTOR only."""
    product_dict = product_data.dict()
    optional_extras = product_dict.pop("optional_extras", None)
    
    product = Product(**product_dict)
    session.add(product)
    session.commit()
    session.refresh(product)
    
    # Handle optional extras
    if optional_extras:
        for extra_id in optional_extras:
            # Verify the extra exists and is marked as is_extra
            extra_statement = select(Product).where(
                Product.id == extra_id,
                Product.is_extra == True
            )
            extra_product = session.exec(extra_statement).first()
            if extra_product:
                extra_link = ProductOptionalExtra(
                    product_id=product.id,
                    optional_extra_id=extra_id
                )
                session.add(extra_link)
        session.commit()
    
    # Get optional extras for response
    extras_statement = select(ProductOptionalExtra, Product).join(
        Product, ProductOptionalExtra.optional_extra_id == Product.id
    ).where(ProductOptionalExtra.product_id == product.id)
    
    extras_results = session.exec(extras_statement).all()
    optional_extras_list = []
    for extra_link, extra_product in extras_results:
        optional_extras_list.append(ProductResponse(**extra_product.dict()))
    
    product_dict = product.dict()
    product_dict["optional_extras"] = optional_extras_list if optional_extras_list else None
    
    return ProductResponse(**product_dict)


@router.patch("/{product_id}", response_model=ProductResponse)
async def update_product(
    product_id: int,
    product_data: ProductUpdate,
    session: Session = Depends(get_session),
    current_user: User = Depends(require_role([UserRole.DIRECTOR]))
):
    """Update a product. DIRECTOR only."""
    statement = select(Product).where(Product.id == product_id)
    product = session.exec(statement).first()
    
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    
    update_data = product_data.dict(exclude_unset=True)
    optional_extras = update_data.pop("optional_extras", None)
    
    for field, value in update_data.items():
        setattr(product, field, value)
    
    # Handle optional extras update
    if optional_extras is not None:
        # Delete existing optional extras
        existing_extras_statement = select(ProductOptionalExtra).where(
            ProductOptionalExtra.product_id == product_id
        )
        existing_extras = session.exec(existing_extras_statement).all()
        for extra_link in existing_extras:
            session.delete(extra_link)
        
        # Add new optional extras
        for extra_id in optional_extras:
            # Verify the extra exists and is marked as is_extra
            extra_statement = select(Product).where(
                Product.id == extra_id,
                Product.is_extra == True
            )
            extra_product = session.exec(extra_statement).first()
            if extra_product:
                extra_link = ProductOptionalExtra(
                    product_id=product.id,
                    optional_extra_id=extra_id
                )
                session.add(extra_link)
    
    product.updated_at = datetime.utcnow()
    session.add(product)
    session.commit()
    session.refresh(product)
    
    # Get optional extras for response
    extras_statement = select(ProductOptionalExtra, Product).join(
        Product, ProductOptionalExtra.optional_extra_id == Product.id
    ).where(ProductOptionalExtra.product_id == product.id)
    
    extras_results = session.exec(extras_statement).all()
    optional_extras_list = []
    for extra_link, extra_product in extras_results:
        optional_extras_list.append(ProductResponse(**extra_product.dict()))
    
    product_dict = product.dict()
    product_dict["optional_extras"] = optional_extras_list if optional_extras_list else None
    
    return ProductResponse(**product_dict)


@router.post("/{product_id}/optional-extras")
async def add_optional_extra(
    product_id: int,
    extra_id: int = Query(...),
    session: Session = Depends(get_session),
    current_user: User = Depends(require_role([UserRole.DIRECTOR]))
):
    """Add an optional extra to a product. DIRECTOR only."""
    # Verify product exists
    product_statement = select(Product).where(Product.id == product_id)
    product = session.exec(product_statement).first()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    
    # Verify extra exists and is marked as is_extra
    extra_statement = select(Product).where(
        Product.id == extra_id,
        Product.is_extra == True
    )
    extra_product = session.exec(extra_statement).first()
    if not extra_product:
        raise HTTPException(status_code=404, detail="Optional extra not found or not marked as extra")
    
    # Check if relationship already exists
    existing_statement = select(ProductOptionalExtra).where(
        ProductOptionalExtra.product_id == product_id,
        ProductOptionalExtra.optional_extra_id == extra_id
    )
    existing = session.exec(existing_statement).first()
    if existing:
        raise HTTPException(status_code=400, detail="Optional extra already added to this product")
    
    # Create relationship
    extra_link = ProductOptionalExtra(
        product_id=product_id,
        optional_extra_id=extra_id
    )
    session.add(extra_link)
    session.commit()
    
    return {"message": "Optional extra added successfully"}


@router.delete("/{product_id}/optional-extras/{extra_id}")
async def remove_optional_extra(
    product_id: int,
    extra_id: int,
    session: Session = Depends(get_session),
    current_user: User = Depends(require_role([UserRole.DIRECTOR]))
):
    """Remove an optional extra from a product. DIRECTOR only."""
    statement = select(ProductOptionalExtra).where(
        ProductOptionalExtra.product_id == product_id,
        ProductOptionalExtra.optional_extra_id == extra_id
    )
    extra_link = session.exec(statement).first()
    
    if not extra_link:
        raise HTTPException(status_code=404, detail="Optional extra relationship not found")
    
    session.delete(extra_link)
    session.commit()
    
    return {"message": "Optional extra removed successfully"}


@router.get("/{product_id}/optional-extras", response_model=List[ProductResponse])
async def get_product_optional_extras(
    product_id: int,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """Get all optional extras for a product."""
    # Verify product exists
    product_statement = select(Product).where(Product.id == product_id)
    product = session.exec(product_statement).first()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    
    # Get optional extras
    extras_statement = select(ProductOptionalExtra, Product).join(
        Product, ProductOptionalExtra.optional_extra_id == Product.id
    ).where(ProductOptionalExtra.product_id == product_id)
    
    extras_results = session.exec(extras_statement).all()
    optional_extras = []
    for extra_link, extra_product in extras_results:
        optional_extras.append(ProductResponse(**extra_product.dict()))
    
    return optional_extras


@router.delete("/{product_id}")
async def delete_product(
    product_id: int,
    session: Session = Depends(get_session),
    current_user: User = Depends(require_role([UserRole.DIRECTOR]))
):
    """Soft delete a product (set is_active=False). DIRECTOR only."""
    statement = select(Product).where(Product.id == product_id)
    product = session.exec(statement).first()
    
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    
    product.is_active = False
    product.updated_at = datetime.utcnow()
    session.add(product)
    session.commit()
    
    return {"message": "Product deactivated successfully"}
