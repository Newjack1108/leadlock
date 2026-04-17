from app.schemas import DealerProfileUpdate, DealerQuoteCreate


def test_dealer_quote_create_accepts_manual_customer_address():
    payload = DealerQuoteCreate(
        customer_name="Jane Customer",
        customer_email="jane@example.com",
        customer_phone="01234 567890",
        customer_address="1 Test Street, London",
        product_items=[{"product_id": 1, "quantity": 1}],
    )
    assert payload.customer_address == "1 Test Street, London"


def test_dealer_profile_update_partial_payload():
    payload = DealerProfileUpdate(company_name="Trade Brand", website="https://trade.example.com")
    dumped = payload.model_dump(exclude_unset=True)
    assert dumped == {
        "company_name": "Trade Brand",
        "website": "https://trade.example.com",
    }
