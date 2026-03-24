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
   - Add `Mail.Send`
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

## 4. Inbound replies (IMAP)

Replies arrive in the **same mailbox** you send from. LeadLock pulls them in with **IMAP** (background poll) and attaches them to the **customer email thread** when it can match the reply (headers, subject, or latest sent mail to that customer).

Add these **API service** variables (same mailbox as `MSGRAPH_FROM_EMAIL`):

| Variable | Example | Description |
|----------|---------|-------------|
| `IMAP_HOST` | `outlook.office365.com` | Microsoft 365 IMAP server |
| `IMAP_PORT` | `993` | SSL port |
| `IMAP_USER` | Same as `MSGRAPH_FROM_EMAIL` | Mailbox login |
| `IMAP_PASSWORD` | *(secret)* | Password or [app password](https://support.microsoft.com/account-billing/using-app-passwords-with-apps-that-don-t-support-two-step-verification-5896ed9b-4263-e681-128a-a6f2979a7944) if MFA is on |
| `IMAP_USE_SSL` | `true` | Use SSL (default) |
| `IMAP_POLL_INTERVAL` | `120` | Seconds between inbox checks (default `300`) |

**Note:** Per-user IMAP fields under **My Settings → Email** are not used by the server poller; set the variables above on Railway so the API process can log in.

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
- **Replies not appearing**: Set `IMAP_*` variables, confirm IMAP is enabled for the mailbox, and that the customer’s **email** in LeadLock matches the address they reply from. Poll interval defaults to 5 minutes unless you lower `IMAP_POLL_INTERVAL`.
