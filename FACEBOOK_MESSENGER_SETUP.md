# Facebook Messenger setup

LeadLock receives Facebook Messenger messages via a webhook and can send replies using the Graph API. Configure your Meta App and Page so that messages flow to your API.

## 1. Webhook URL

Your API must be publicly reachable (e.g. deployed on Railway). The webhook path is:

- **Verification (GET):** `https://<YOUR_API_HOST>/api/webhooks/facebook/messenger`
- **Events (POST):** same URL

**Examples:**

- Railway API: `https://leadlock-production.up.railway.app/api/webhooks/facebook/messenger`
- Local (ngrok): `https://abc123.ngrok.io/api/webhooks/facebook/messenger`

Use **HTTPS** in production. Meta will send a GET for verification and POST for message events.

## 2. Create a Meta App and add Messenger

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

## 3. Environment variables (API)

Set these in your API environment (e.g. Railway):

| Variable | Description |
|----------|-------------|
| `FACEBOOK_PAGE_ACCESS_TOKEN` | Page access token with `pages_messaging` permission (from Meta App → Messenger → Access Tokens). |
| `FACEBOOK_VERIFY_TOKEN` | Arbitrary string you set in the Meta App webhook configuration; must match exactly for verification. |

**Optional:**

| Variable | Description |
|----------|-------------|
| `FACEBOOK_MESSENGER_WEBHOOK_URL` | Full public URL (e.g. `https://your-api.railway.app/api/webhooks/facebook/messenger`) if you need it for logging or proxy configuration. |
| `FACEBOOK_ACTIVITY_USER_ID` | User ID to use for "Messenger received" activity records (default `1`). Set if user id 1 does not exist. |

## 4. Behaviour

- **Verification:** GET requests with `hub.mode=subscribe`, `hub.verify_token` matching `FACEBOOK_VERIFY_TOKEN`, and `hub.challenge` are answered with the challenge string. Otherwise → 403.
- **Incoming messages:** POST body is parsed for `entry` → `messaging` events. For each `message` (and optionally `postback`), the sender PSID is used to find a **Customer** or **Lead** by `messenger_psid`. If no match, the app fetches the user profile from the Graph API and creates a new **Lead** (source FACEBOOK) and **Customer** with `messenger_psid`, then stores the message and creates a **MESSENGER_RECEIVED** activity.
- **Replies:** Use **Customers** → customer → **View Messenger** to send messages. Replies use `messaging_type: RESPONSE` (valid within the 24-hour messaging window after the user last messaged).
- **Response:** The webhook returns 200 quickly so Meta does not retry.

## 5. Permissions and policies

- **pages_messaging:** Required for sending and receiving messages.
- **User-initiated:** Users must message your Page first; you can then reply within the standard messaging window (24 hours unless using approved message tags).
- **Profile:** The app uses `first_name` and `last_name` from the Graph API to name new Lead/Customer records when an unknown user messages.

## 6. Testing

1. Set `FACEBOOK_VERIFY_TOKEN` and `FACEBOOK_PAGE_ACCESS_TOKEN` in your API environment.
2. In Meta App → Messenger → Webhooks, enter your callback URL and verify token; click **Verify and Save**.
3. Subscribe to **messages** and ensure your Page is subscribed to the app.
4. Send a message to your Page from a Facebook account. The message should appear in LeadLock: **Dashboard** (Unread Messenger) or **Customers** → [auto-created or matched customer] → **View Messenger**.
5. Reply from LeadLock (**View Messenger** → type message → Send). The reply should appear in Facebook Messenger.

## 7. Troubleshooting

| Symptom | Likely cause | Fix |
|--------|---------------|-----|
| **403 on verification** | Verify token mismatch or wrong hub.mode. | Ensure `FACEBOOK_VERIFY_TOKEN` in your API exactly matches the value in Meta App → Webhooks. |
| **Messages not received** | Webhook not subscribed or URL wrong. | In Meta App → Messenger → Webhooks, confirm callback URL is correct and **messages** is subscribed. Check that the Page is linked and has the correct token. |
| **Send fails (500)** | Missing or invalid Page Access Token. | Set `FACEBOOK_PAGE_ACCESS_TOKEN` to the Page token from Messenger → Access Tokens, with `pages_messaging` permission. |
| **New user not created** | Graph API or token issue. | Ensure the Page token has permission to access user profile. Check API logs for errors when fetching profile or creating Lead/Customer. |
