# Twilio SMS webhook setup

Inbound SMS are received by your LeadLock API via a Twilio webhook. Configure Twilio to send "A MESSAGE COMES IN" to your API.

## 1. Webhook URL

Your API must be publicly reachable (e.g. deployed on Railway). The webhook path is:

```
POST https://<YOUR_API_HOST>/api/webhooks/twilio/sms
```

**Examples:**

- Railway API: `https://leadlock-production.up.railway.app/api/webhooks/twilio/sms`
- Local (ngrok): `https://abc123.ngrok.io/api/webhooks/twilio/sms`

Use **HTTPS** in production. Twilio will send a form-encoded POST with `From`, `To`, `Body`, `MessageSid`, etc.

## 2. Configure in Twilio Console

1. Go to [Twilio Console](https://console.twilio.com/) → **Phone Numbers** → **Manage** → **Active Numbers**.
2. Click the phone number you use for SMS (the one in `TWILIO_PHONE_NUMBER`).
3. Under **Messaging configuration**:
   - **A MESSAGE COMES IN**: set to **Webhook**.
   - URL: `https://<YOUR_API_HOST>/api/webhooks/twilio/sms`
   - HTTP: **POST**.
4. Save.

Twilio will send every inbound SMS to that URL and validate the request using the `X-Twilio-Signature` header (your app does this automatically using `TWILIO_AUTH_TOKEN`).

## 3. Environment variables (API)

Set these in your API environment (e.g. Railway):

| Variable | Description |
|----------|-------------|
| `TWILIO_ACCOUNT_SID` | From Twilio Console → Account Info |
| `TWILIO_AUTH_TOKEN` | From Twilio Console → Account Info |
| `TWILIO_PHONE_NUMBER` | Your Twilio number (e.g. +44…) used for sending and receiving |

**Optional:**

| Variable | Description |
|----------|-------------|
| `TWILIO_SMS_WEBHOOK_URL` | Full public URL of the webhook (e.g. `https://leadlock-production.up.railway.app/api/webhooks/twilio/sms`). Set this if the app is behind a proxy so signature validation uses the same URL Twilio uses instead of the internal request URL. |
| `TWILIO_ACTIVITY_USER_ID` | User id to use for the "SMS received" activity (default `1`). Set if user id 1 does not exist. |

## 4. Behaviour

- **Signature:** Requests are validated with `X-Twilio-Signature` and `TWILIO_AUTH_TOKEN`. Invalid signature → 403.
- **Match by phone:** The sender number is matched to a **Customer** or **Lead** by phone. If no match, the request is accepted (200) but the message is not stored.
- **Storage:** When a customer (or lead with a customer) is found, the message is stored as `SmsMessage` and an **Activity** `SMS_RECEIVED` is created for that customer.
- **Response:** The endpoint returns empty TwiML `<Response></Response>` so Twilio does not retry.

## 5. Testing

- Send an SMS to your Twilio number from a phone that belongs to a customer or lead in LeadLock. The message should appear in **Customers** → customer → **View SMS**.
- If you get **403 Invalid signature**, set `TWILIO_SMS_WEBHOOK_URL` to the exact URL you configured in Twilio (including `https://` and no trailing slash).
- If you get **503 Twilio not configured**, ensure `TWILIO_AUTH_TOKEN` (and the other Twilio env vars) are set in the API environment.

## 6. Troubleshooting

| Symptom | Likely cause | Fix |
|--------|---------------|-----|
| **403 Invalid signature** | App is behind a reverse proxy; request URL used for validation does not match the URL Twilio calls. | Set **`TWILIO_SMS_WEBHOOK_URL`** to the exact public HTTPS URL (e.g. `https://your-api.railway.app/api/webhooks/twilio/sms`), no trailing slash. |
| **500** or replies not stored (no error in Twilio) | Activity requires a valid `created_by_id` (user). If no user exists or user id 1 is missing, the commit fails. | Ensure at least one user exists in the app (e.g. run seed). Optionally set **`TWILIO_ACTIVITY_USER_ID`** to a valid user id (default is 1). |
| **200 OK but reply never appears** | Sender number did not match any Customer or Lead phone, or matched a Lead that has no Customer yet. | Replies are only stored when the sender phone matches a **Customer** or a **Lead** that has a **customer_id**. Check that the contact’s phone in LeadLock matches the number they’re texting from (format can vary; the app normalizes for comparison). Check API logs for a line like `Twilio SMS: no customer/lead match for From=...****` to confirm the webhook was hit. |

### Still no replies?

1. **Check Railway logs** (or your API logs) when someone sends a reply. Look for one of these lines:
   - **`Twilio SMS webhook signature validation failed`** → Set `TWILIO_SMS_WEBHOOK_URL` to the exact URL Twilio uses (no trailing slash).
   - **`Twilio SMS webhook: missing From or Body`** → The request reached the app but the body was empty. Check that Twilio is POSTing to the correct URL and that no proxy is stripping the body.
   - **`Twilio SMS: no customer/lead match for From=...`** → The sender number did not match any Customer or Lead phone. Ensure the contact's phone in LeadLock is the number they're texting from (the app normalizes formats; try with and without spaces or leading zero).
   - **`Twilio SMS: stored inbound message for customer_id=...`** → The reply was stored. If the UI still doesn't show it, check you're viewing the correct customer or refresh the SMS page.

2. **Confirm** `TWILIO_SMS_WEBHOOK_URL` is exactly `https://leadlock-production.up.railway.app/api/webhooks/twilio/sms` (no trailing slash).

3. **Confirm** the contact replying has that phone number stored on the **Customer** (or on a **Lead** that has a **customer_id**) in LeadLock.
