# Facebook Messenger and Lead Ads setup

LeadLock can receive leads from Facebook in two ways:

1. **Facebook Messenger** – when someone messages your Facebook Page, LeadLock creates or matches a Customer/Lead and stores the conversation so sales can reply from the CRM.
2. **Facebook Lead Ads** – when someone submits a lead form on a Facebook or Instagram ad, LeadLock fetches the lead data and creates a Customer and Lead.

These should use **separate Meta apps**:

| Meta app | Purpose |
|----------|---------|
| **LeadLock Messenger** | Chat only (`pages_messaging`) |
| **LeadLock Ads** | Lead forms only (`leads_retrieval`) |

They share the same **Verify Token** value in Railway (`FACEBOOK_VERIFY_TOKEN`) if you configure both webhooks with that string, but they use **different access tokens**.

---

## Messenger

### Intended behaviour

Someone messages **CSGB Group** or **Cheshire Stables** with a text question → LeadLock creates a Customer + Lead (source FACEBOOK) with the question stored → sales open **View Messenger** and reply within Meta’s 24-hour window.

### 1. Webhook URL (Messenger)

Your API must be publicly reachable (e.g. deployed on Railway). The webhook path is:

- **Verification (GET):** `https://<YOUR_API_HOST>/api/webhooks/facebook/messenger`
- **Events (POST):** same URL

**Examples:**

- Railway API: `https://leadlock-production.up.railway.app/api/webhooks/facebook/messenger`
- Local (ngrok): `https://abc123.ngrok.io/api/webhooks/facebook/messenger`

Use **HTTPS** in production. Meta will send a GET for verification and POST for message events.

### 2. Create a Meta App and add Messenger

1. Go to [Meta for Developers](https://developers.facebook.com/) → **My Apps** → open **LeadLock Messenger** (or create a Business app).
2. Set app mode to **Live** for real customers (Development only delivers for testers/admins/developers).
3. In the app dashboard, open **Add Products** and add **Messenger**.
4. Under **Messenger** → **Settings**:
   - **Webhooks**: click **Add Callback URL**.
   - **Callback URL**: `https://<YOUR_API_HOST>/api/webhooks/facebook/messenger`
   - **Verify Token**: choose an arbitrary secret string (e.g. a long random value) and set the same value in your API env as `FACEBOOK_VERIFY_TOKEN`.
   - Click **Verify and Save** (Meta will send a GET request; your API must return the `hub.challenge` query parameter).
5. Under **Webhooks**, click **Subscribe** for your callback and subscribe to **messages** (and optionally **messaging_postbacks** for button clicks).
6. **Subscribe each Page to the app** with `messages`:
   - CSGB Group — Page ID `485666198220603`
   - Cheshire Stables — Page ID `1806797756222550`

   Generate a **never-expiring Page Access Token** for each Page (permission `pages_messaging`). Then install the app on the Page:

   ```text
   POST /{page-id}/subscribed_apps?subscribed_fields=messages&access_token={PAGE_ACCESS_TOKEN}
   ```

### 3. Environment variables (API)

Set these in your API environment (e.g. Railway):

| Variable | Description |
|----------|-------------|
| `FACEBOOK_VERIFY_TOKEN` | Arbitrary string you set in the Meta App webhook configuration; must match exactly for verification (used for Messenger and Lead Ads webhook verify). |
| `FACEBOOK_PAGE_ACCESS_TOKEN` | Default / fallback Messenger Page access token (`pages_messaging`). Used when a customer has no `messenger_page_id`, or when the Page is not listed in the map below. |
| `FACEBOOK_MESSENGER_PAGE_TOKENS` | **Required for dual-Page replies.** JSON object mapping Facebook Page ID → Page access token. Example: `{"485666198220603":"<CSGB token>","1806797756222550":"<Cheshire token>"}`. |

Do **not** put the Lead Ads system-user token into Messenger vars. Leave `FACEBOOK_LEADS_ACCESS_TOKEN` for Lead Ads only.

**Optional / unused by current code:**

| Variable | Notes |
|----------|-------|
| `FACEBOOK_MESSENGER_WEBHOOK_URL` | Documented historically; not read by the API. |
| `FACEBOOK_ACTIVITY_USER_ID` | Documented historically; Messenger/Lead Ads activities use the System user. |

### 4. Behaviour

- **Verification:** GET requests with `hub.mode=subscribe`, `hub.verify_token` matching `FACEBOOK_VERIFY_TOKEN`, and `hub.challenge` are answered with the challenge string. Otherwise → 403.
- **Incoming messages:** POST body is parsed for `entry` → `messaging` events. `entry.id` is the Facebook **Page ID**. For each text `message` (and optionally `postback`), the sender PSID is used to find a **Customer** or **Lead** by `messenger_psid`. If no match, the app may try **phone fallback**. If still no match, it fetches the user profile from the Graph API and creates a new **Lead** (source FACEBOOK, description = question text) and **Customer** with `messenger_psid` + `messenger_page_id`, then stores the message and creates a **MESSENGER_RECEIVED** activity.
- **Phone fallback:** When a message comes from an unknown PSID, the app requests the sender’s profile (including optional phone) from the Graph API using the token for that Page. If a phone number is returned, it is normalized and matched against existing **Customer** or **Lead** phone numbers. If a match is found, that record’s `messenger_psid` / `messenger_page_id` are set so future messages and replies use the correct Page.
- **Replies:** Use **Customers** → customer → **View Messenger** to send messages. LeadLock selects the Page token from `FACEBOOK_MESSENGER_PAGE_TOKENS` using `customer.messenger_page_id`, falling back to `FACEBOOK_PAGE_ACCESS_TOKEN`. Replies use `messaging_type: RESPONSE` (valid within the 24-hour messaging window after the user last messaged).
- **Response:** The webhook returns 200 quickly so Meta does not retry.
- **Attachments:** Image/sticker-only messages (no text) are skipped in v1.

### 5. Permissions and policies

- **pages_messaging:** Required for sending and receiving messages.
- **pages_manage_metadata:** Often required to subscribe Pages to the app.
- **User-initiated:** Users must message your Page first; you can then reply within the standard messaging window (24 hours unless using approved message tags).
- **Profile:** The app uses `first_name` and `last_name` from the Graph API to name new Lead/Customer records when an unknown user messages.
- **Phone fallback (optional):** Getting the sender’s phone may require additional permissions and is not guaranteed. If unavailable, only PSID matching and new-user creation apply.

### 5b. Meta App Dashboard – Privacy Policy and User Data Deletion

Meta requires public HTTPS URLs for apps that access user data. LeadLock uses **instructions URLs** (not a signed data-deletion callback), because there is no Facebook Login — only Messenger and Lead Ads.

After the frontend is deployed, set these in **Meta App Dashboard → Settings → Basic**:

| Field | URL |
|-------|-----|
| **Privacy Policy URL** | `https://www.csgbsales.co.uk/privacy` |
| **User Data Deletion** (instructions URL) | `https://www.csgbsales.co.uk/data-deletion` |

Local equivalents while developing: `http://localhost:3000/privacy` and `http://localhost:3000/data-deletion`. Meta requires HTTPS for the live app settings.

The data-deletion page explains how people can email `cheshirestables@csgbsales.co.uk` to request removal of Lead Ad / Messenger data from LeadLock. Staff delete matching customer/lead/Messenger records in the CRM.

### 6. Ops checklist (audit)

Before expecting production Messenger to work, confirm:

1. LeadLock Messenger app is **Live**.
2. Callback URL is verified against Railway `FACEBOOK_VERIFY_TOKEN`.
3. Webhook field **`messages`** is subscribed.
4. Both Pages are installed with `subscribed_fields=messages`.
5. Railway has `FACEBOOK_VERIFY_TOKEN`, `FACEBOOK_PAGE_ACCESS_TOKEN`, and `FACEBOOK_MESSENGER_PAGE_TOKENS` (both Page tokens).
6. `FACEBOOK_LEADS_ACCESS_TOKEN` is unchanged (Ads only).

### 7. Testing

1. Set the Messenger env vars above in your API environment.
2. In Meta App → Messenger → Webhooks, enter your callback URL and verify token; click **Verify and Save**.
3. Subscribe to **messages** and ensure **both** Pages are subscribed to the app.
4. From a normal Facebook account (app Live), send a text message to each Page. Each should create a Lead in LeadLock with the question in the lead description and under **View Messenger**.
5. Reply from LeadLock; the reply should appear in that visitor’s Messenger thread for the same Page.

### 8. Troubleshooting

| Symptom | Likely cause | Fix |
|--------|---------------|-----|
| **403 on verification** | Verify token mismatch or wrong hub.mode. | Ensure `FACEBOOK_VERIFY_TOKEN` in your API exactly matches the value in Meta App → Webhooks. |
| **Messages not received** | Webhook not subscribed or URL wrong. | Confirm callback URL and **messages** subscription; confirm each Page is installed. |
| **Send fails (500)** | Missing or wrong Page token for that conversation. | Ensure `FACEBOOK_MESSENGER_PAGE_TOKENS` includes the customer’s `messenger_page_id`, or set `FACEBOOK_PAGE_ACCESS_TOKEN`. |
| **Reply works for one Page only** | Single token only. | Add both Page tokens to `FACEBOOK_MESSENGER_PAGE_TOKENS`. |
| **New user not created** | Graph API or token issue. | Ensure the Page token can access the user profile. Check API logs. |

---

## Facebook Lead Ads

LeadLock receives **Lead Ad** form submissions via a separate webhook. When a lead is submitted on a Facebook or Instagram Lead Ad, Meta sends a notification; LeadLock fetches the lead’s field data (name, email, phone, etc.) from the Graph API and creates a **Customer** and **Lead** (source FACEBOOK).

Use the **LeadLock Ads** Meta app and `FACEBOOK_LEADS_ACCESS_TOKEN` (Graph API v26.0). Do not replace Messenger’s Page tokens with the Ads token.

### Lead Ads webhook URL

- **Verification (GET):** `https://<YOUR_API_HOST>/api/webhooks/facebook/leadgen`
- **Events (POST):** same URL

Use the **same** `FACEBOOK_VERIFY_TOKEN` as for Messenger when configuring this URL in Meta.

### Configure Lead Ads in Meta

1. In your [Meta for Developers](https://developers.facebook.com/) **LeadLock Ads** app, open **Webhooks** (product **Webhooks**, not Messenger).
2. Click **Add Subscription** and select the **Page** object (not Messenger).
3. **Callback URL:** `https://<YOUR_API_HOST>/api/webhooks/facebook/leadgen`
4. **Verify Token:** use the same value as `FACEBOOK_VERIFY_TOKEN` in your API.
5. After verification, subscribe to the **leadgen** field.
6. **Install the app on your Page** so it receives leadgen events:
   - Either use [Graph API Explorer](https://developers.facebook.com/tools/explorer): get a Page access token (with `leads_retrieval`, `pages_manage_metadata`) and send:
     - `POST /{page-id}/subscribed_apps?subscribed_fields=leadgen&access_token=...`
   - Or ensure your Page has the app installed and the Page subscription includes **leadgen**.

### System user and ad account (required for advert name)

Use a **never-expiring system-user token** (e.g. **CSGB Lead Sync**) generated on the **LeadLock Ads** app. In Meta Business settings → Users → System users → that user:

1. Assign **both Pages** (CSGB Group and Cheshire Stables).
2. Assign the **Ad account** that runs the Lead Ads (Pages alone are not enough for `ad_id` / `ad_name`).
3. Generate a new token on **LeadLock Ads** with the permissions below, then set **only** Railway `FACEBOOK_LEADS_ACCESS_TOKEN` to that value.
4. Do **not** change `FACEBOOK_PAGE_ACCESS_TOKEN` or `FACEBOOK_MESSENGER_PAGE_TOKENS`.

### Token permissions (Lead Ads)

The token used as `FACEBOOK_LEADS_ACCESS_TOKEN` must have:

- **leads_retrieval** – required to fetch lead form data by `leadgen_id`
- **pages_manage_metadata** / **pages_show_list** / **pages_read_engagement** – Page webhooks and subscription
- **business_management** – Business Manager / asset access
- **ads_management** – required for Graph to return `ad_id` / `ad_name` on the lead
- **pages_manage_ads** – also required for ad-level fields on leads (without it Graph often returns form answers with `ad_id` / `ad_name` omitted, not an error)

### Behaviour

- **Verification:** GET with `hub.mode=subscribe` and matching `hub.verify_token` returns `hub.challenge`.
- **Incoming lead:** POST body contains `object: "page"` and `entry[].changes[]` with `field: "leadgen"` and `value.leadgen_id` (Meta may also send `ad_id` on the webhook). LeadLock fetches the lead from Graph API v26.0 (`GET /{leadgen_id}?fields=id,created_time,field_data,ad_id,ad_name`). If Meta rejects the advert fields, it retries with form fields only so the lead is still created. Prefer Graph `ad_name` / `ad_id`; if Graph omits `ad_id`, fall back to the webhook `ad_id`. Map fields to Lead/Customer (case-insensitive), create a Lead with `lead_source=FACEBOOK` and `lead_type=STABLES`, and add a NOTE activity “Lead from Facebook Lead Ad form”. When advert metadata is present, the Lead description starts with `Facebook Advert:` / `Facebook Ad ID:` then custom form questions.

### Troubleshooting advert name

| Log / symptom | Meaning | Fix |
|---------------|---------|-----|
| `fetched lead ... ad_id=- ad_name=-` (no retry warning) | Graph returned form data but stripped advert fields | System user needs **ad account** access; regenerate token with **ads_management** and **pages_manage_ads**; update only `FACEBOOK_LEADS_ACCESS_TOKEN` |
| `advert metadata unavailable; retrying without ad_id/ad_name` | Graph rejected advert fields | Same permission / asset fix as above |
| Lead has `Facebook Ad ID:` but no `Facebook Advert:` | Webhook supplied `ad_id`; Graph still omitted `ad_name` | Token / ad-account access still short for `ad_name` |
| Meta Lead Ads Testing Tool | Often has no `ad_id` / `ad_name` | Expected; use a real ad click for advert metadata |

Existing leads are not updated automatically. Do not replay webhooks (duplicates).

### Testing Lead Ads

1. Set `FACEBOOK_VERIFY_TOKEN` and `FACEBOOK_LEADS_ACCESS_TOKEN` in your API (system-user token with the permissions above).
2. In Meta App → Webhooks → Page, add the leadgen callback URL and verify.
3. Subscribe to **leadgen** and install the app on your Page (see above).
4. Create a test Lead Ad or use Meta’s test lead tool; submit a lead. The lead should appear in LeadLock as a new Lead (and Customer) with source FACEBOOK and type STABLES.
5. For advert name, use a **real** form fill from a live ad (not the testing tool). Railway should log `ad_name=` with a real name, and the Lead description should start with `Facebook Advert:` / `Facebook Ad ID:`.
