# Microsoft Graph Email Setup (Railway)

Send emails via Microsoft Graph API. Uses client credentials (app-only auth) with a single shared mailbox. Works on Railway since it uses HTTPS, not SMTP.

## Prerequisites

- A Microsoft 365 / Azure AD tenant
- A shared mailbox or service account to send from (e.g. `quotes@yourcompany.com`)

## 1. Azure AD App Registration

1. Go to [Azure Portal](https://portal.azure.com) → **Microsoft Entra ID** (or Azure Active Directory) → **App registrations** → **New registration**
2. Name your app (e.g. "LeadLock Email") and click **Register**
3. Note the **Application (client) ID** and **Directory (tenant) ID**
4. Go to **Certificates & secrets** → **New client secret** → Add description, choose expiry → **Add** → Copy the secret value (you can only see it once)
5. Go to **API permissions** → **Add a permission**
   - Choose **Microsoft Graph**
   - Choose **Application permissions**
   - Add **`Mail.Send`** (outbound email)
   - Add **`Mail.ReadWrite`** (Application) — **read inbound mail and mark messages as read** after import (`Mail.Read` alone is read-only; updating `isRead` requires write)
   - *(Optional: you can keep **`Mail.Read`** as well; `Mail.ReadWrite` covers reading and updating mail.)*
   - Click **Grant admin consent for [Your Tenant]**

## 2. Mailbox Setup

The app sends on behalf of a specific mailbox. Use one of:

- **Shared mailbox**: Create in Microsoft 365 Admin → Shared mailboxes, or use an existing one
- **Service account**: A user account (e.g. `noreply@yourcompany.com`) dedicated to sending

The mailbox must exist in your tenant. The `MSGRAPH_FROM_EMAIL` variable must match the mailbox’s User Principal Name (usually the email address).

## 3. Railway Variables

Add these to your **API service** Variables in Railway:

| Variable | Description |
|----------|-------------|
| `CLIENT_ID` | Application (client) ID from step 1 |
| `CLIENT_SECRET` | Client secret value from step 1 |
| `TENANT_ID` | Directory (tenant) ID from step 1 |
| `MSGRAPH_FROM_EMAIL` | Email address of the shared mailbox to send from |
| `MSGRAPH_FROM_NAME` | (Optional) Display name, e.g. "LeadLock CRM" |

### Outbound via Resend or SMTP only

If you send email using **Resend** (`RESEND_API_KEY`) or **SMTP** without setting the **Microsoft Graph** variables above, LeadLock still needs a configured **inbound** path to import customer replies. **Resend does not receive replies into the app.** Either:

- Configure **IMAP** for the mailbox that receives replies (`IMAP_HOST`, `IMAP_USER`, `IMAP_PASSWORD`, or IMAP under **My Settings**), or  
- Add **Graph** credentials for that same mailbox so inbound uses Graph (see section 4).

The API logs one startup line describing inbound: `Inbound email: Microsoft Graph`, `Inbound email: IMAP`, or `Inbound email: not configured`.

## 4. Inbound replies (Microsoft Graph — recommended)

When **`CLIENT_ID`**, **`CLIENT_SECRET`**, **`TENANT_ID`**, and **`MSGRAPH_FROM_EMAIL`** are set, LeadLock reads inbound mail with **Microsoft Graph**. This avoids **IMAP basic authentication**, which Microsoft often blocks (`BasicAuthBlocked`).

Ensure **`Mail.ReadWrite`** (Application) is added and **admin consent** is granted (see step 1). **`Mail.Read` alone is not enough** to mark messages as read after import.

Optional variables:

| Variable | Description |
|----------|-------------|
| `GRAPH_INBOUND_TOP` | Max messages to fetch per poll (default `50`) |
| `GRAPH_INBOUND_MODE` | `unread` (default): only unread messages. `recent`: latest `GRAPH_INBOUND_TOP` messages by date, including already read — use if replies were opened in Outlook before LeadLock polled; duplicates are skipped by Message-ID. |
| `IMAP_POLL_INTERVAL` | Seconds between polls (same timer for Graph inbound; default `300`) |

---

## 4b. Inbound replies (IMAP — only if Graph is not used)

If Graph is **not** configured, LeadLock falls back to **IMAP** with username/password. Many tenants **block** this (`BasicAuthBlocked`); use Graph instead.

Add these **API service** variables (same mailbox as `MSGRAPH_FROM_EMAIL`):

| Variable | Example | Description |
|----------|---------|-------------|
| `IMAP_HOST` | `outlook.office365.com` | Microsoft 365 IMAP server |
| `IMAP_PORT` | `993` | SSL port |
| `IMAP_USER` | Same as `MSGRAPH_FROM_EMAIL` | Mailbox login |
| `IMAP_PASSWORD` | *(secret)* | Password or [app password](https://support.microsoft.com/account-billing/using-app-passwords-with-apps-that-don-t-support-two-step-verification-5896ed9b-4263-e681-128a-a6f2979a7944) if MFA is on |
| `IMAP_USE_SSL` | `true` | Use SSL (default) |
| `IMAP_POLL_INTERVAL` | `120` | Seconds between inbox checks (default `300`) |
| `IMAP_SEARCH_MODE` | `unseen` | Use `unseen` (default) for unread only, or `since_days` to also catch mail already opened in Outlook (see below) |
| `IMAP_SINCE_DAYS` | `3` | With `IMAP_SEARCH_MODE=since_days`, how far back to scan (duplicates are skipped by Message-ID) |

**Note:** If **Railway IMAP variables are not set**, the poller uses the **first user’s IMAP** saved under **My Settings → Email** (host, user, password).

**Unread vs opened:** The default mode only imports **unread** messages. If you open the customer’s reply in Outlook first, it may no longer be unread and LeadLock will skip it until you either mark it unread again or temporarily set `IMAP_SEARCH_MODE=since_days` and `IMAP_SINCE_DAYS=3` (then set back to `unseen` after mail is imported — `since_days` re-scans recent mail every poll and is heavier on large inboxes).

Ensure **IMAP is enabled** for the mailbox in Exchange Online (admin center → mailbox → email apps).

## 5. Redeploy

After adding or changing variables, redeploy the API service so it picks them up.

## Testing

1. Send a quote email or compose an email to a customer
2. Check that the email is delivered
3. Reply from the customer address; after the next IMAP poll, open **Customer → Emails** and confirm the reply appears in the same thread as the sent message
4. If it fails, check Railway logs for Graph API errors

## Troubleshooting

- **401 Unauthorized**: Check CLIENT_ID, CLIENT_SECRET, TENANT_ID. Ensure admin consent was granted for Mail.Send.
- **403 Forbidden / Mailbox not found**: Ensure MSGRAPH_FROM_EMAIL matches a valid mailbox in your tenant and the app has Mail.Send (Application) permission.
- **400 Bad Request**: The request payload may be malformed; check logs for the exact error message.
- **Replies not appearing**: With Graph configured, add **`Mail.ReadWrite`** (Application) and admin consent (not just `Mail.Read` if you need messages marked read). Ensure the customer’s **email** in LeadLock matches the address they reply from. Check logs for `Inbound email skipped: no Customer with email=...` or `Inbound email: not configured`. If the reply was already opened in another mail client, try **`GRAPH_INBOUND_MODE=recent`** (Graph) or **`IMAP_SEARCH_MODE=since_days`** (IMAP).
- **Mark read fails with 403**: Add **`Mail.ReadWrite`** (Application); `Mail.Read` cannot PATCH message properties.
- **`BasicAuthBlocked` / IMAP `LOGIN failed`**: Use **Graph inbound** (same app as send) — do not rely on IMAP password auth for Microsoft 365.
