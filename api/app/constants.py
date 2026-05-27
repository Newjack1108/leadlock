"""
Shared constants for the application.
"""
from decimal import Decimal

from app.models import QuoteStatus

# Excluded from list UIs (quotes index, opportunities, customer/lead quote panels)
QUOTE_LIST_EXCLUDED_STATUSES = (QuoteStatus.REJECTED, QuoteStatus.EXPIRED)

# Quotes list lifecycle buckets (GET /api/quotes?lifecycle=...)
QUOTE_LIVE_STATUSES = (QuoteStatus.DRAFT, QuoteStatus.SENT, QuoteStatus.VIEWED)
QUOTE_CLOSED_STATUSES = (QuoteStatus.ACCEPTED, QuoteStatus.REJECTED, QuoteStatus.EXPIRED)

# List endpoints: default page size and max per request
LIST_PAGE_SIZE_DEFAULT = 50
LIST_PAGE_SIZE_MAX = 200

# Soft-archive eligible leads/quotes after this many days without update
ARCHIVE_AFTER_DAYS = 200

# VAT rate: all prices are Ex VAT @ 20%
VAT_RATE_PERCENT = 20
VAT_RATE_DECIMAL = Decimal("0.20")

# Website base URLs for visit tracking links (?ltk=customer_number)
TRACKING_WEBSITE_BASE_URLS = [
    ("https://www.csgbgroup.co.uk", "www.csgbgroup.co.uk"),
    ("https://www.beaverlogcabins.co.uk", "www.beaverlogcabins.co.uk"),
    ("https://www.cheshirestables.co.uk", "www.cheshirestables.co.uk"),
]

# Shown on quote PDF / public view when quote.include_delivery_installation_contact_note is True
DELIVERY_INSTALLATION_CONTACT_NOTE = (
    "Delivery and installation available on request please contact us via SMS 07782352354, "
    "Email cheshirestables@csgbsales.co.uk or Call on 01606 272788"
)

# Shown on every quote PDF and public quote view (delivery fulfillment)
QUOTE_BALANCE_BEFORE_DELIVERY_NOTE = (
    "Please Note: All balances must be paid in full before delivery"
)

# Shown on quote PDF and public quote view when fulfillment is collection
QUOTE_BALANCE_BEFORE_COLLECTION_NOTE = (
    "Please Note: All balances must be paid in full before collection"
)

# Delivery-only: max physical boxes per trailer run
DELIVERY_ONLY_BOXES_PER_TRIP = 3

# Canonical sandbox customer (seeded on startup; excluded from stats and automation)
TEST_CUSTOMER_NAME = "LeadLock Test Customer"
TEST_CUSTOMER_EMAIL = "test-customer@leadlock.internal"
