from fastapi import APIRouter, Depends, HTTPException, Query
from sqlmodel import Session, select
from typing import Optional, List
from app.database import get_session
from app.models import Product, ProductCategory, User
from app.auth import get_current_user, require_role
from app.schemas import ProductCreate, ProductUpdate, ProductResponse
from app.models import UserRole
from datetime import datetime

router = APIRouter(prefix="/api/products", tags=["products"])


@router.get("", response_model=List[ProductResponse])
async def get_products(
    category: Optional[ProductCategory] = Query(None),
    is_extra: Optional[bool] = Query(None),
    is_active: Optional[bool] = Query(None, default=True),
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """Get list of products with optional filters."""
    statement = select(Product)
    
    if category:
        statement = statement.where(Product.category == category)
    
    if is_extra is not None:
        statement = statement.where(Product.is_extra == is_extra)
    
    if is_active is not None:
        statement = statement.where(Product.is_active == is_active)
    
    statement = statement.order_by(Product.category, Product.name)
    products = session.exec(statement).all()
    
    return [ProductResponse(**product.dict()) for product in products]


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


@router.get("/{product_id}", response_model=ProductResponse)
async def get_product(
    product_id: int,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """Get product details."""
    statement = select(Product).where(Product.id == product_id)
    product = session.exec(statement).first()
    
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    
    return ProductResponse(**product.dict())


@router.post("", response_model=ProductResponse)
async def create_product(
    product_data: ProductCreate,
    session: Session = Depends(get_session),
    current_user: User = Depends(require_role([UserRole.DIRECTOR]))
):
    """Create a new product. DIRECTOR only."""
    product = Product(**product_data.dict())
    session.add(product)
    session.commit()
    session.refresh(product)
    
    return ProductResponse(**product.dict())


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
    for field, value in update_data.items():
        setattr(product, field, value)
    
    product.updated_at = datetime.utcnow()
    session.add(product)
    session.commit()
    session.refresh(product)
    
    return ProductResponse(**product.dict())


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
