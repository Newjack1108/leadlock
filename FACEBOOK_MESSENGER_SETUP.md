# Facebook Messenger and Lead Ads setup

LeadLock can receive leads from Facebook in two ways:

1. **Facebook Messenger** – when someone messages your Facebook Page, LeadLock creates or matches a Customer/Lead and stores the conversation.
2. **Facebook Lead Ads** – when someone submits a lead form on a Facebook or Instagram ad, LeadLock fetches the lead data and creates a Customer and Lead.

Both use the same Meta App and the same **Verify Token** and **Page Access Token** (the token must include the permissions required for each product you use).

---

## Messenger

### 1. Webhook URL (Messenger)

Your API must be publicly reachable (e.g. deployed on Railway). The webhook path is:

- **Verification (GET):** `https://<YOUR_API_HOST>/api/webhooks/facebook/messenger`
- **Events (POST):** same URL

**Examples:**

- Railway API: `https://leadlock-production.up.railway.app/api/webhooks/facebook/messenger`
- Local (ngrok): `https://abc123.ngrok.io/api/webhooks/facebook/messenger`

Use **HTTPS** in production. Meta will send a GET for verification and POST for message events.

### 2. Create a Meta App and add Messenger

1. Go to [Meta for Developers](https://developers.facebook.com/) → **My Apps** → **Create App**.
2. Choose **Business** (or **Other**) and complete the app setup.
3. In the app dashboard, open **Add Products** and add **Messenger**.
4. Under **Messenger** → **Settings**:
   - **Webhooks**: click **Add Callback URL**.
   - **Callback URL**: `https://<YOUR_API_HOST>/api/webhooks/facebook/messenger`
   - **Verify Token**: choose an arbitrary secret string (e.g. a long random value) and set the same value in your API env as `FACEBOOK_VERIFY_TOKEN`.
   - Click **Verify and Save** (Meta will send a GET request; your API must return the `hub.challenge` query parameter).
5. Under **Webhooks**, click **Subscribe** for your callback and subscribe to **messages** (and optionally **messaging_postbacks** for button clicks).
6. **Subscribe your Page to the app**: Under **Messenger** → **Settings** → **Access Tokens**, select your Facebook Page and generate a **Page Access Token** with `pages_messaging` permission. Copy this token and set it as `FACEBOOK_PAGE_ACCESS_TOKEN` in your API environment.

### 3. Environment variables (API)

Set these in your API environment (e.g. Railway):

| Variable | Description |
|----------|-------------|
| `FACEBOOK_PAGE_ACCESS_TOKEN` | Page access token. For Messenger: `pages_messaging`. For Lead Ads: also `leads_retrieval`. From Meta App → Messenger → Access Tokens (or Page subscription). |
| `FACEBOOK_VERIFY_TOKEN` | Arbitrary string you set in the Meta App webhook configuration; must match exactly for verification (used for both Messenger and Lead Ads). |

**Optional:**

| Variable | Description |
|----------|-------------|
| `FACEBOOK_MESSENGER_WEBHOOK_URL` | Full public URL (e.g. `https://your-api.railway.app/api/webhooks/facebook/messenger`) if you need it for logging or proxy configuration. |
| `FACEBOOK_ACTIVITY_USER_ID` | User ID to use for "Messenger received" and "Lead from Facebook Lead Ad" activity records (default `1`). Set if user id 1 does not exist. |

### 4. Behaviour

- **Verification:** GET requests with `hub.mode=subscribe`, `hub.verify_token` matching `FACEBOOK_VERIFY_TOKEN`, and `hub.challenge` are answered with the challenge string. Otherwise → 403.
- **Incoming messages:** POST body is parsed for `entry` → `messaging` events. For each `message` (and optionally `postback`), the sender PSID is used to find a **Customer** or **Lead** by `messenger_psid`. If no match, the app may try **phone fallback** (see below). If still no match, it fetches the user profile from the Graph API and creates a new **Lead** (source FACEBOOK) and **Customer** with `messenger_psid`, then stores the message and creates a **MESSENGER_RECEIVED** activity.
- **Phone fallback:** When a message comes from an unknown PSID, the app requests the sender’s profile (including optional phone) from the Graph API. If a phone number is returned, it is normalized and matched against existing **Customer** or **Lead** phone numbers. If a match is found, that record’s `messenger_psid` is set to the sender’s PSID so future messages match by PSID, and the message is assigned to that customer. Getting the sender’s phone may require the `user_phone_number` (or equivalent) permission and might not be available for all users or app configurations. If phone is not returned or does not match any contact, the app creates a new Customer and Lead as above.
- **Replies:** Use **Customers** → customer → **View Messenger** to send messages. Replies use `messaging_type: RESPONSE` (valid within the 24-hour messaging window after the user last messaged).
- **Response:** The webhook returns 200 quickly so Meta does not retry.

### 5. Permissions and policies

- **pages_messaging:** Required for sending and receiving messages.
- **User-initiated:** Users must message your Page first; you can then reply within the standard messaging window (24 hours unless using approved message tags).
- **Profile:** The app uses `first_name` and `last_name` from the Graph API to name new Lead/Customer records when an unknown user messages.
- **Phone fallback (optional):** To match unknown Messenger senders to existing contacts by phone, the app may request the sender’s phone from the profile API. This can require additional permissions (e.g. `user_phone_number`) and is not guaranteed to be returned for all users. If unavailable, only PSID matching and new-user creation apply.

### 6. Testing

1. Set `FACEBOOK_VERIFY_TOKEN` and `FACEBOOK_PAGE_ACCESS_TOKEN` in your API environment.
2. In Meta App → Messenger → Webhooks, enter your callback URL and verify token; click **Verify and Save**.
3. Subscribe to **messages** and ensure your Page is subscribed to the app.
4. Send a message to your Page from a Facebook account. The message should appear in LeadLock: **Dashboard** (Unread Messenger) or **Customers** → [auto-created or matched customer] → **View Messenger**.
5. Reply from LeadLock (**View Messenger** → type message → Send). The reply should appear in Facebook Messenger.

### 7. Troubleshooting

| Symptom | Likely cause | Fix |
|--------|---------------|-----|
| **403 on verification** | Verify token mismatch or wrong hub.mode. | Ensure `FACEBOOK_VERIFY_TOKEN` in your API exactly matches the value in Meta App → Webhooks. |
| **Messages not received** | Webhook not subscribed or URL wrong. | In Meta App → Messenger → Webhooks, confirm callback URL is correct and **messages** is subscribed. Check that the Page is linked and has the correct token. |
| **Send fails (500)** | Missing or invalid Page Access Token. | Set `FACEBOOK_PAGE_ACCESS_TOKEN` to the Page token from Messenger → Access Tokens, with `pages_messaging` permission. |
| **New user not created** | Graph API or token issue. | Ensure the Page token has permission to access user profile. Check API logs for errors when fetching profile or creating Lead/Customer. |

---

## Facebook Lead Ads

LeadLock receives **Lead Ad** form submissions via a separate webhook. When a lead is submitted on a Facebook or Instagram Lead Ad, Meta sends a notification; LeadLock fetches the lead’s field data (name, email, phone, etc.) from the Graph API and creates a **Customer** and **Lead** (source FACEBOOK).

### Lead Ads webhook URL

- **Verification (GET):** `https://<YOUR_API_HOST>/api/webhooks/facebook/leadgen`
- **Events (POST):** same URL

Use the **same** `FACEBOOK_VERIFY_TOKEN` as for Messenger when configuring this URL in Meta.

### Configure Lead Ads in Meta

1. In your [Meta for Developers](https://developers.facebook.com/) app, open **Webhooks** (product **Webhooks**, not Messenger).
2. Click **Add Subscription** and select the **Page** object (not Messenger).
3. **Callback URL:** `https://<YOUR_API_HOST>/api/webhooks/facebook/leadgen`
4. **Verify Token:** use the same value as `FACEBOOK_VERIFY_TOKEN` in your API.
5. After verification, subscribe to the **leadgen** field.
6. **Install the app on your Page** so it receives leadgen events:
   - Either use [Graph API Explorer](https://developers.facebook.com/tools/explorer): get a Page access token (with `leads_retrieval`, `pages_manage_metadata`) and send:
     - `POST /{page-id}/subscribed_apps?subscribed_fields=leadgen&access_token=...`
   - Or ensure your Page has the app installed and the Page subscription includes **leadgen**.

### Token permissions (Lead Ads)

The **Page Access Token** used as `FACEBOOK_PAGE_ACCESS_TOKEN` must have:

- **leads_retrieval** – required to fetch lead form data by `leadgen_id`
- **pages_manage_metadata** / **pages_show_list** / **pages_read_engagement** – often required for Page webhooks and subscription

The token must be from a user who can perform the **ADVERTISE** task on the Page. You can use the same token as for Messenger if it has both `pages_messaging` and `leads_retrieval`.

### Behaviour

- **Verification:** GET with `hub.mode=subscribe` and matching `hub.verify_token` returns `hub.challenge`.
- **Incoming lead:** POST body contains `object: "page"` and `entry[].changes[]` with `field: "leadgen"` and `value.leadgen_id`. LeadLock fetches the lead from the Graph API (`GET /{leadgen_id}?fields=id,created_time,field_data`), maps fields (e.g. `full_name`, `email`, `phone_number`, `postcode`) to Lead/Customer, creates or matches a Customer by email/phone, creates a Lead with `lead_source=FACEBOOK`, and adds a NOTE activity “Lead from Facebook Lead Ad form”.

### Testing Lead Ads

1. Set `FACEBOOK_VERIFY_TOKEN` and `FACEBOOK_PAGE_ACCESS_TOKEN` (with `leads_retrieval`) in your API.
2. In Meta App → Webhooks → Page, add the leadgen callback URL and verify.
3. Subscribe to **leadgen** and install the app on your Page (see above).
4. Create a test Lead Ad or use Meta’s test lead tool; submit a lead. The lead should appear in LeadLock as a new Lead (and Customer) with source FACEBOOK.
