"""
Shared constants for the application.
"""
from decimal import Decimal

# VAT rate: all prices are Ex VAT @ 20%
VAT_RATE_PERCENT = 20
VAT_RATE_DECIMAL = Decimal("0.20")

# Website base URLs for visit tracking links (?ltk=customer_number)
TRACKING_WEBSITE_BASE_URLS = [
    ("https://www.csgbgroup.co.uk", "www.csgbgroup.co.uk"),
    ("https://www.beaverlogcabins.co.uk", "www.beaverlogcabins.co.uk"),
    ("https://www.cheshirestables.co.uk", "www.cheshirestables.co.uk"),
]
