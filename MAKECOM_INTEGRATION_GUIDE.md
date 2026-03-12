# LeadLock Form Setup Guide

Quick guide for setting up Gravity Forms and social media lead gen ads to work with LeadLock.

---

## Make.com Integration

LeadLock accepts leads via a webhook at `POST /api/webhooks/leads`. Use Make.com to capture leads from Facebook Lead Ads, email, forms, and other sources, then forward them to LeadLock.

### Webhook Configuration

| Setting | Value |
|---------|-------|
| **URL** | `https://your-api-url/api/webhooks/leads` |
| **Method** | POST |
| **Auth** | Header `X-API-Key: <WEBHOOK_API_KEY>` |
| **Content-Type** | application/json |

### Request Body Schema

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `name` | string | No* | Full name. *Can be omitted if `first_name`/`last_name` or `full_name` provided |
| `first_name` | string | No | Combined with `last_name` if `name` empty |
| `last_name` | string | No | Combined with `first_name` if `name` empty |
| `full_name` | string | No | Used if `name` empty |
| `email` | string | No | Contact email |
| `phone` | string | No | Contact phone |
| `phone_number` | string | No | Alias for `phone` (common in Facebook) |
| `postcode` | string | No | Location postcode |
| `description` | string | No | Enquiry/project details |
| `product_interest` | string | No | Product type (e.g. stables, sheds) |
| `lead_source` | string | No | One of: `FACEBOOK`, `EMAIL`, `INSTAGRAM`, `CSGB WEBSITE`, `CS WEBSITE`, `BLC WEBSITE`, `MANUAL_ENTRY`, `SMS`, `PHONE`, `REFERRAL`, `OTHER`, `UNKNOWN` |
| `lead_type` | string | No | One of: `STABLES`, `SHEDS`, `CABINS`, `UNKNOWN` |

**Behaviour:** If email or phone matches an existing Customer, the new lead is linked to that Customer (returning submitters). No Customer is created for new people until the lead is qualified in LeadLock.

---

### Make.com Scenario: Facebook Lead Ads

1. **Trigger:** Facebook Lead Ads → Watch Leads
2. **Connect** your Facebook account and select the Page/Form
3. **Add module:** HTTP → Make a request
   - URL: `https://your-api-url/api/webhooks/leads`
   - Method: POST
   - Headers: `X-API-Key` = your `WEBHOOK_API_KEY`
   - Body type: Raw / JSON

   ```json
   {
     "full_name": "{{full_name}}",
     "email": "{{email}}",
     "phone_number": "{{phone_number}}",
     "description": "{{custom_question_response}}",
     "lead_source": "FACEBOOK"
   }
   ```

4. Map the Facebook Lead Ads output fields to the JSON body. Facebook typically provides `full_name`; if you have `first_name` and `last_name` instead, use those and omit `full_name`.

---

### Make.com Scenario: Email Leads (e.g. Gmail)

1. **Trigger:** Gmail → Watch Emails (or New Email in inbox)
2. **Add module:** Parse/Extract data from email (sender, subject, body) if needed
3. **Add module:** HTTP → Make a request
   - URL: `https://your-api-url/api/webhooks/leads`
   - Method: POST
   - Headers: `X-API-Key` = your `WEBHOOK_API_KEY`
   - Body type: Raw / JSON

   ```json
   {
     "name": "{{sender_name_or_email}}",
     "email": "{{sender_email}}",
     "description": "{{email_subject}} - {{email_body_snippet}}",
     "lead_source": "EMAIL"
   }
   ```

4. Adjust mapping based on how your email source structures the data (e.g. Mailchimp, Typeform).

---

### Environment Variables

- `WEBHOOK_API_KEY` – Required. Generate a strong random string and add it to your backend env. Use the same value in Make.com’s `X-API-Key` header.
- `WEBHOOK_DEFAULT_USER_ID` – Optional. User ID to assign new leads to. If not set, leads stay unassigned.

---

## Required Fields (for forms)

**Name** - Lead's full name (required in all forms, or use first_name + last_name / full_name)

---

## Recommended Fields

- **Email** - Contact email address
- **Phone** - Contact phone number  
- **Postcode** - Location postcode
- **Description/Message** - Enquiry details

---

## Gravity Forms Setup

### Simple Contact Form

**Include these fields:**
- Name (required)
- Email (required)
- Phone (optional)
- Message (optional)

**Field names to use:**
- Name field: `name`
- Email field: `email`
- Phone field: `phone`
- Message field: `message`

### Quote Request Form

**Include these fields:**
- Name (required)
- Email (required)
- Phone (required)
- Postcode (required)
- Project Description (required)

**Field names to use:**
- Name field: `name`
- Email field: `email`
- Phone field: `phone`
- Postcode field: `postcode`
- Project Description field: `project_description` or `description`

---

## Social Media Lead Gen Ads

### Facebook/Instagram Lead Ads

**Collect these fields:**
- Full Name (required)
- Email (required)
- Phone Number (required)
- Custom Question (optional) - for project details

**Note:** Facebook automatically collects name, email, and phone. Add a custom question field for project description or enquiry details.

### Google Ads Lead Form

**Collect these fields:**
- Name (required)
- Email (required)
- Phone (required)
- Postcode (optional)

---

## Field Naming Guidelines

Use these exact field names in Gravity Forms:
- `name` - for name field
- `email` - for email field
- `phone` - for phone field
- `postcode` - for postcode field
- `message` or `description` - for message/description fields

---

## Tips

- Keep forms simple - only ask for essential information
- Ensure forms are mobile-friendly
- Use appropriate input types (email, tel) for better mobile experience
- Test forms before going live
