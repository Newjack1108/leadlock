"""
Customer CSV import/export logic for legacy data migration.
Format: First Name, Surname, Email, Phone, First of Postcode, Last modified, First of Product Type
"""
import csv
import io
from datetime import datetime
from typing import Optional, List, Tuple, Dict, Any

from sqlmodel import Session, select, desc
from app.models import Customer, Lead, LeadStatus, LeadType, LeadSource


# Header normalisation: maps possible header variants to canonical keys
HEADER_MAP = {
    "first name": "first_name",
    "firstname": "first_name",
    "first_name": "first_name",
    "surname": "surname",
    "last name": "surname",
    "lastname": "surname",
    "last_name": "surname",
    "email": "email",
    "phone": "phone",
    "first of postcode": "postcode",
    "postcode": "postcode",
    "last modified": "last_modified",
    "lastmodified": "last_modified",
    "first of product type": "product_type",
    "product type": "product_type",
    "producttype": "product_type",
}

EXPECTED_HEADERS = [
    "First Name",
    "Surname",
    "Email",
    "Phone",
    "First of Postcode",
    "Last modified",
    "First of Product Type",
]

PRODUCT_TYPE_MAP = {
    "stables": LeadType.STABLES,
    "cabins": LeadType.CABINS,
    "sheds": LeadType.SHEDS,
}


def generate_customer_number(session: Session) -> str:
    """Generate a unique customer number like CUST-2025-001."""
    from datetime import date
    year = date.today().year
    statement = select(Customer).where(Customer.customer_number.like(f"CUST-{year}-%"))
    customers = session.exec(statement).all()
    if not customers:
        return f"CUST-{year}-001"
    numbers = []
    for customer in customers:
        if customer.customer_number:
            try:
                num = int(customer.customer_number.split('-')[-1])
                numbers.append(num)
            except (ValueError, IndexError):
                continue
    if not numbers:
        return f"CUST-{year}-001"
    return f"CUST-{year}-{max(numbers) + 1:03d}"


def parse_product_type(value: str) -> LeadType:
    """Map product type string to LeadType enum."""
    if not value or not value.strip():
        return LeadType.UNKNOWN
    key = value.strip().lower()
    return PRODUCT_TYPE_MAP.get(key, LeadType.UNKNOWN)


def parse_date(value: str) -> Optional[datetime]:
    """Parse DD/MM/YYYY HH:MM or DD/MM/YYYY."""
    if not value or not value.strip():
        return None
    value = value.strip()
    for fmt in ("%d/%m/%Y %H:%M", "%d/%m/%Y %H:%M:%S", "%d/%m/%Y", "%d-%m-%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            continue
    return None


def normalize_row(headers: List[str], row: List[str]) -> Dict[str, str]:
    """Convert a CSV row to a dict using normalized header keys."""
    result = {}
    for i, h in enumerate(headers):
        if i < len(row):
            canonical = HEADER_MAP.get(h.strip().lower(), h.strip().lower().replace(" ", "_"))
            result[canonical] = row[i].strip() if row[i] else ""
    return result


def generate_example_csv() -> str:
    """Generate an example CSV template with headers and sample rows."""
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(EXPECTED_HEADERS)
    # Sample rows
    writer.writerow([
        "John",
        "Wright",
        "johnswright2@outlook.com",
        "07710721072",
        "RH1 4NA",
        "12/02/2026 12:38",
        "Stables",
    ])
    writer.writerow([
        "Jessica",
        "Keane",
        "jessica-keane@hotmail.co.uk",
        "+447581044696",
        "CV61FY",
        "11/02/2026 16:35",
        "Cabins",
    ])
    return output.getvalue()


def import_customers_from_csv(
    content: str,
    session: Session,
    skip_duplicates: bool = True,
) -> Tuple[int, int, List[Dict[str, Any]]]:
    """
    Import customers from CSV content. Creates Customer + Lead per row.
    Returns (created_count, skipped_count, errors).
    """
    created = 0
    skipped = 0
    errors = []
    reader = csv.reader(io.StringIO(content))
    rows = list(reader)
    if not rows:
        errors.append({"row": 0, "message": "File is empty"})
        return 0, 0, errors

    headers = [h.strip() for h in rows[0]]
    for row_idx, row in enumerate(rows[1:], start=2):
        if not row or all(not c.strip() for c in row):
            continue
        try:
            data = normalize_row(headers, row)
            first_name = data.get("first_name", "").strip() or data.get("firstname", "").strip()
            surname = data.get("surname", "").strip() or data.get("last_name", "").strip() or data.get("lastname", "").strip()
            name = f"{first_name} {surname}".strip() or first_name or surname
            if not name:
                errors.append({"row": row_idx, "message": "First Name or Surname required"})
                continue

            email = data.get("email", "").strip() or None
            phone = data.get("phone", "").strip() or None
            postcode = data.get("postcode", "").strip() or None
            product_type = parse_product_type(data.get("product_type", ""))
            last_modified = parse_date(data.get("last_modified", ""))

            if skip_duplicates:
                if email:
                    existing = session.exec(select(Customer).where(Customer.email == email)).first()
                    if existing:
                        skipped += 1
                        continue
                if phone:
                    existing = session.exec(select(Customer).where(Customer.phone == phone)).first()
                    if existing:
                        skipped += 1
                        continue

            customer = Customer(
                customer_number=generate_customer_number(session),
                name=name,
                email=email,
                phone=phone,
                postcode=postcode,
                updated_at=last_modified or datetime.utcnow(),
            )
            session.add(customer)
            session.flush()

            lead = Lead(
                name=name,
                email=email,
                phone=phone,
                postcode=postcode,
                status=LeadStatus.QUALIFIED,
                lead_type=product_type,
                lead_source=LeadSource.MANUAL_ENTRY,
                customer_id=customer.id,
            )
            session.add(lead)
            session.commit()
            session.refresh(customer)
            created += 1
        except Exception as e:
            session.rollback()
            errors.append({"row": row_idx, "message": str(e)})

    return created, skipped, errors


def export_customers_to_csv(session: Session) -> str:
    """Export all customers to CSV in legacy format."""
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(EXPECTED_HEADERS)

    statement = (
        select(Customer)
        .order_by(Customer.updated_at.desc())
    )
    customers = session.exec(statement).all()

    for customer in customers:
        parts = customer.name.split(maxsplit=1)
        first_name = parts[0] if parts else ""
        surname = parts[1] if len(parts) > 1 else ""

        product_type = ""
        lead_stmt = (
            select(Lead)
            .where(Lead.customer_id == customer.id)
            .order_by(desc(Lead.updated_at))
        )
        lead = session.exec(lead_stmt).first()
        if lead and lead.lead_type != LeadType.UNKNOWN:
            product_type = lead.lead_type.value.title()

        last_modified = customer.updated_at.strftime("%d/%m/%Y %H:%M") if customer.updated_at else ""

        writer.writerow([
            first_name,
            surname,
            customer.email or "",
            customer.phone or "",
            customer.postcode or "",
            last_modified,
            product_type or "Stables",
        ])

    return output.getvalue()
