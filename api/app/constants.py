"""
Shared constants for the application.
"""
from decimal import Decimal

from app.models import QuoteStatus

# Excluded from list UIs (quotes index, opportunities, customer/lead quote panels)
QUOTE_LIST_EXCLUDED_STATUSES = (QuoteStatus.REJECTED, QuoteStatus.EXPIRED)

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

# Shown on every quote PDF and public quote view
QUOTE_BALANCE_BEFORE_DELIVERY_NOTE = (
    "Please Note: All balances must be paid in full before delivery"
)
