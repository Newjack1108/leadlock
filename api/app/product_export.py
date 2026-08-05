"""CSV export for the products catalogue."""
import csv
import io
from datetime import datetime
from decimal import Decimal
from typing import List, Optional

from sqlmodel import Session, select

from app.models import Product, ProductCategory


CSV_HEADERS = [
    "id",
    "production_product_id",
    "name",
    "description",
    "category",
    "subcategory",
    "is_extra",
    "allow_in_configurator",
    "configurator_per_box",
    "configurator_width",
    "configurator_length",
    "configurator_is_starter_box",
    "configurator_is_corner_box",
    "base_price",
    "unit",
    "sku",
    "is_active",
    "is_production_synced",
    "production_pushed_at",
    "installation_hours",
    "boxes_per_product",
]


def _fmt_bool(value: Optional[bool]) -> str:
    if value is None:
        return ""
    return "true" if value else "false"


def _fmt_decimal(value) -> str:
    if value is None:
        return ""
    return str(Decimal(str(value)))


def _fmt_dt(value: Optional[datetime]) -> str:
    if value is None:
        return ""
    return value.isoformat(sep=" ", timespec="seconds")


def _fmt_enum(value) -> str:
    if value is None:
        return ""
    return value.value if hasattr(value, "value") else str(value)


def query_products_for_export(
    session: Session,
    *,
    category: Optional[ProductCategory] = None,
    is_extra: Optional[bool] = None,
    is_active: Optional[bool] = None,
    subcategory: Optional[List[str]] = None,
    allow_in_configurator: Optional[bool] = None,
) -> List[Product]:
    """Same filters as GET /api/products (default active when is_active omitted)."""
    statement = select(Product)

    if category:
        statement = statement.where(Product.category == category)

    if is_extra is not None:
        statement = statement.where(Product.is_extra == is_extra)

    if subcategory:
        statement = statement.where(Product.subcategory.in_(subcategory))

    if allow_in_configurator is not None:
        statement = statement.where(Product.allow_in_configurator == allow_in_configurator)

    if is_active is None:
        is_active = True
    statement = statement.where(Product.is_active == is_active)

    statement = statement.order_by(Product.category, Product.name)
    return list(session.exec(statement).all())


def export_products_to_csv(products: List[Product]) -> str:
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(CSV_HEADERS)

    for product in products:
        writer.writerow(
            [
                product.id,
                product.production_product_id if product.production_product_id is not None else "",
                product.name or "",
                product.description or "",
                _fmt_enum(product.category),
                product.subcategory or "",
                _fmt_bool(product.is_extra),
                _fmt_bool(product.allow_in_configurator),
                _fmt_bool(getattr(product, "configurator_per_box", False)),
                _fmt_decimal(product.configurator_width),
                _fmt_decimal(product.configurator_length),
                _fmt_bool(getattr(product, "configurator_is_starter_box", False)),
                _fmt_bool(getattr(product, "configurator_is_corner_box", False)),
                _fmt_decimal(product.base_price),
                product.unit or "",
                product.sku or "",
                _fmt_bool(product.is_active),
                _fmt_bool(product.production_product_id is not None),
                _fmt_dt(product.production_pushed_at),
                _fmt_decimal(product.installation_hours),
                product.boxes_per_product if product.boxes_per_product is not None else "",
            ]
        )

    return output.getvalue()
