# XERO Integration via Make.com

LeadLock pushes invoices to XERO when you click **Push to XERO** on an order detail page. The flow goes through Make.com, which creates the invoice in XERO. Make.com handles XERO OAuth and API access.

---

## Overview

1. Create a Make.com scenario that receives order data and creates a XERO invoice
2. Set `MAKE_XERO_WEBHOOK_URL` in Railway (or your API environment)
3. Click **Push to XERO** on an order - LeadLock POSTs the payload to Make.com; Make.com creates the invoice

---

## Part 1: LeadLock Environment Variable

Set this where your API runs (e.g. Railway):

| Variable | Description |
|----------|-------------|
| `MAKE_XERO_WEBHOOK_URL` | URL of the Make.com Custom Webhook (instant trigger) |

If not set, the API returns: "Make.com XERO webhook not configured. Set MAKE_XERO_WEBHOOK_URL."

---

## Part 2: Make.com Scenario Setup

### Step 2.1: Create a scenario

1. Log in to [Make.com](https://make.com)
2. Create a new scenario
3. Add these modules in order:

**Module 1: Webhooks - Custom webhook**

- Trigger: "Custom webhook" (instant, not scheduled)
- Create a new webhook
- Copy the webhook URL - this is your `MAKE_XERO_WEBHOOK_URL`

**Module 2: XERO - Create an invoice**

- Action: "Create an invoice"
- Connect your XERO account (Make.com handles OAuth)
- Map fields from the webhook payload:

| XERO Field | Map from webhook |
|------------|------------------|
| Contact Name | `customer.name` |
| Contact Email | `customer.email` |
| Contact Phone | `customer.phone` |
| Invoice Number | `invoice_number` |
| Reference | `order_number` |
| Date | `created_at` (or today) |
| Line Items | See payload structure below |

For line items, iterate over `line_items[]` - each has:
- `description`
- `quantity`
- `unit_price`
- `final_line_total`

**Module 3: Webhooks - Respond to webhook**

- Add "Respond to webhook" as the last module
- Set the response body to return success and XERO invoice ID so LeadLock can show "In XERO":

```json
{
  "success": true,
  "xero_invoice_id": "{{XERO.Create Invoice.InvoiceID}}",
  "message": "Invoice pushed to XERO successfully."
}
```

(Adjust the XERO module output path to match your scenario - e.g. `{{2.InvoiceID}}` if XERO is module 2)

If XERO fails, use an error handler or router to respond with:

```json
{
  "success": false,
  "error": "Description of what went wrong."
}
```

### Step 2.2: Address mapping (optional)

If your XERO setup needs full address, map from the webhook:
- `customer.address_line1`
- `customer.address_line2`
- `customer.city`
- `customer.county`
- `customer.postcode`
- `customer.country`

---

## Part 3: Webhook Payload Structure

LeadLock POSTs this JSON to your webhook:

```json
{
  "order_id": 123,
  "invoice_number": "INV-2025-001",
  "order_number": "ORD-2025-001",
  "xero_invoice_id": null,
  "customer": {
    "name": "John Smith",
    "email": "john@example.com",
    "phone": "07700 900123",
    "address_line1": "123 High Street",
    "address_line2": "",
    "city": "Manchester",
    "county": "Greater Manchester",
    "postcode": "M1 1AA",
    "country": "United Kingdom"
  },
  "line_items": [
    {
      "description": "Stable 12x10",
      "quantity": 1,
      "unit_price": 5000,
      "final_line_total": 5000,
      "sort_order": 0
    }
  ],
  "totals": {
    "subtotal": 5000,
    "discount_total": 0,
    "total_amount": 5000,
    "deposit_amount": 1000,
    "balance_amount": 4000,
    "currency": "GBP"
  },
  "created_at": "2025-02-11T10:00:00"
}
```

Use `xero_invoice_id` in the payload for idempotency - if it is already set, you may want to skip creating a duplicate in XERO or update an existing one.

---

## Part 4: Connect XERO in Make.com

1. In the XERO module, click "Add" to add a connection
2. Sign in to XERO and authorise Make.com
3. Choose the organisation (tenant) to use
4. Make.com stores the OAuth tokens; no need to manage them in LeadLock

---

## Behaviour in LeadLock

- **Push to XERO** sends the order payload to Make.com
- Make.com creates an ACCREC invoice in XERO with contact and line items
- If Make.com returns `success: true` and `xero_invoice_id`, LeadLock stores it and the button shows **In XERO**
- If the webhook URL is not configured, the API returns an error

---

## Troubleshooting

### "Make.com XERO webhook not configured"

- Set `MAKE_XERO_WEBHOOK_URL` in your API environment (Railway, etc.)
- Use the exact URL from the Make.com Custom webhook module

### Make.com scenario fails

- Check the XERO connection is authorised
- Verify field mapping (contact name, line items) matches the payload structure
- Use Make.com error handling to return `{ "success": false, "error": "..." }` so LeadLock shows a clear message

### Button still shows "Push to XERO" after successful push

- Ensure the "Respond to webhook" module returns `xero_invoice_id` in the response
- LeadLock only stores it when the response includes `success: true` and `xero_invoice_id`
