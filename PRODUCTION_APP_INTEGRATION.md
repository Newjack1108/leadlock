# Production app integration (LeadLock → work orders)

LeadLock sends accepted orders to the **production app** (CSGB Production / `ai-sms-chat`) when a user clicks **Send to production** on an order. This document covers configuration on both sides and the webhook contract.

---

## Overview

```text
LeadLock API  --POST-->  Production app
           /api/orders/{id}/send-to-production
                        |
                        v
           POST {PRODUCTION_APP_API_URL}/api/webhooks/work-orders
           Authorization: Bearer {PRODUCTION_APP_API_KEY}
```

The production app may also expose the same handler at `/production/api/webhooks/work-orders` when mounted behind a path prefix.

---

## LeadLock API environment

Set on the LeadLock API service (e.g. Railway):

| Variable | Description |
|----------|-------------|
| `PRODUCTION_APP_API_URL` | Base URL of the production app, **no trailing slash** (e.g. `https://your-production-app.up.railway.app`) |
| `PRODUCTION_APP_API_KEY` | Shared secret; sent as `Authorization: Bearer <key>` |

If either is missing, **Send to production** returns HTTP 500: *Production app not configured*.

---

## Production app environment

Set on the production app (e.g. Railway):

| Variable | Description |
|----------|-------------|
| `LEADLOCK_WEBHOOK_API_KEY` | **Same value** as LeadLock’s `PRODUCTION_APP_API_KEY` |

Fallback: `SALES_APP_WEBHOOK_API_KEY` (legacy). If unset, the webhook returns HTTP 503.

See `ai-sms-chat/env.example` for comments.

---

## Pre-send rules (LeadLock)

LeadLock blocks the push unless:

- **Payment:** `deposit_paid` or `paid_in_full` is true on the order.
- **Address (delivery only):** Customer has address line 1, city, and postcode, **or** the order uses a complete alternate delivery location.
- **Collection:** Address validation is skipped; `fulfillment_method` is `"collection"`.

LeadLock allows re-sending the same order; the production app upserts by `order_id` when present.

---

## Webhook request

| Item | Value |
|------|--------|
| Method / path | `POST /api/webhooks/work-orders` |
| Auth | `Authorization: Bearer <shared key>` |
| Body | `Content-Type: application/json` |
| Timeout | LeadLock client timeout: 30 seconds |

### Core fields (always sent)

| Field | Type | Notes |
|-------|------|--------|
| `order_number` | string | e.g. `ORD-2026-001` |
| `order_id` | number | LeadLock order primary key; used for idempotent upsert |
| `fulfillment_method` | string | `"delivery"` or `"collection"` (lowercase) |
| `customer_name` | string | |
| `customer_postcode` | string | Routing postcode (delivery site or CRM) |
| `customer_address` | string | Routing address |
| `customer_email` | string | |
| `customer_phone` | string | |
| `items` | array | See line items below |
| `total_amount` | number | |
| `currency` | string | e.g. `GBP` |
| `installation_booked` | boolean | |
| `created_at` | string | ISO datetime |
| `notes` | string | Production notes; may include delivery location notes |
| `deposit_paid` | boolean | |
| `balance_paid` | boolean | |
| `paid_in_full` | boolean | |
| `deposit_amount` | number | |
| `balance_amount` | number | |
| `invoice_number` | string \| null | |

### Line items (`items[]`)

| Field | Type |
|-------|------|
| `product_name` | string |
| `description` | string |
| `quantity` | number |
| `unit_price` | number |
| `install_hours` | number |
| `number_of_boxes` | integer |

### Conditional fields

| Field | When sent |
|-------|-----------|
| `travel_time_hours_round_trip` | Delivery only, when order has one-way travel time in LeadLock (value = 2 × one-way hours). **Omitted** for collection. |
| `address_is_delivery_location` | `true` when alternate delivery address is used (not collection) |
| `delivery_location_notes` | With alternate delivery |
| `crm_customer_address` | With alternate delivery (CRM/home address while routing uses delivery site) |

### Example (delivery + alternate address)

```json
{
  "order_number": "ORD-2026-042",
  "order_id": 42,
  "fulfillment_method": "delivery",
  "customer_name": "Jane Smith",
  "customer_postcode": "SY1 2AB",
  "customer_address": "Farm Lane, Shrewsbury, Shropshire, SY1 2AB, United Kingdom",
  "customer_email": "jane@example.com",
  "customer_phone": "07700900123",
  "items": [
    {
      "product_name": "Stable",
      "description": "Stable",
      "quantity": 1,
      "unit_price": 10000,
      "install_hours": 8,
      "number_of_boxes": 4
    }
  ],
  "total_amount": 10000,
  "currency": "GBP",
  "installation_booked": false,
  "created_at": "2026-05-27T10:00:00",
  "notes": "Oak finish\n\nDelivery location notes: Use rear gate",
  "deposit_paid": true,
  "balance_paid": false,
  "paid_in_full": false,
  "deposit_amount": 6000,
  "balance_amount": 4000,
  "invoice_number": "INV-2026-042",
  "travel_time_hours_round_trip": 2.5,
  "address_is_delivery_location": true,
  "delivery_location_notes": "Use rear gate",
  "crm_customer_address": "1 High Street, Chester, CH1 1AA, United Kingdom"
}
```

---

## Webhook response

Production app should return **HTTP 2xx** with optional JSON, for example:

```json
{
  "success": true,
  "work_order_id": "123",
  "updated": false
}
```

On failure, return non-2xx with `{ "error": "..." }` or `{ "detail": "..." }` so LeadLock can show a useful message (502 to the user).

LeadLock records `ORDER_SENT_TO_PRODUCTION` in customer history on success. `sent_to_production_at` / `sent_to_production_by_name` on the order API are **not** sent in the webhook; they are derived from audit events in LeadLock only.

---

## Production app implementation

The reference implementation lives in the **ai-sms-chat** repo:

- `leadlock-work-order.js` — payload validation and normalization
- `production-routes.js` — `POST /webhooks/work-orders` + Bearer auth
- `production-database.js` — `createLeadLockWorkOrder` / upsert by `leadlock_order_id`
- `public/production/common.js` — address, payment, and fulfilment display on load sheets and job sheets

Run production app tests: `npm test` (includes `test/leadlock-work-order*.test.js`).

---

## Reverse direction (products)

Products are pushed **production → LeadLock** via `POST /api/webhooks/products` on LeadLock with Bearer `PRODUCT_IMPORT_API_KEY` or `WEBHOOK_API_KEY`. That flow is independent of work-order push.

---

## Deployment checklist

1. Deploy production app with LeadLock webhook support (`LEADLOCK_WEBHOOK_API_KEY` set).
2. Deploy LeadLock API with recent order-push commits.
3. Set `PRODUCTION_APP_API_URL` to the production app’s public base URL.
4. Set `PRODUCTION_APP_API_KEY` on LeadLock and the **same** value as `LEADLOCK_WEBHOOK_API_KEY` on production.
5. Test on staging: delivery order, collection order, alternate delivery address; confirm work order in production UI.

---

## Troubleshooting

| Symptom | Check |
|---------|--------|
| *Production app not configured* | LeadLock `PRODUCTION_APP_API_URL` and `PRODUCTION_APP_API_KEY` |
| 401 from production | Keys match; `Authorization: Bearer` header present |
| 503 from production | `LEADLOCK_WEBHOOK_API_KEY` set on production app |
| 400 address / deposit | LeadLock pre-send rules on order page |
| 502 from LeadLock | Production app logs; URL reachable from LeadLock API host |

LeadLock unit tests: `api/tests/test_orders_fulfillment.py`, `api/tests/test_orders_travel_time.py`.
