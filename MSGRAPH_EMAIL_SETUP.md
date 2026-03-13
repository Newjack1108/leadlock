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

## 4. Redeploy

After adding the variables, redeploy the API service so it picks them up.

## Testing

1. Send a quote email or compose an email to a customer
2. Check that the email is delivered
3. If it fails, check Railway logs for Graph API errors

## Troubleshooting

- **401 Unauthorized**: Check CLIENT_ID, CLIENT_SECRET, TENANT_ID. Ensure admin consent was granted for Mail.Send.
- **403 Forbidden / Mailbox not found**: Ensure MSGRAPH_FROM_EMAIL matches a valid mailbox in your tenant and the app has Mail.Send (Application) permission.
- **400 Bad Request**: The request payload may be malformed; check logs for the exact error message.
