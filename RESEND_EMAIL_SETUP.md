# Resend Email Setup (Railway)

Railway blocks outbound SMTP (ports 25, 465, 587) on most plans. Use **Microsoft Graph** (recommended) or **Resend**—both send via HTTPS and work on Railway. See [MSGRAPH_EMAIL_SETUP.md](MSGRAPH_EMAIL_SETUP.md) for Microsoft Graph setup.

## Quick Setup

1. **Sign up** at [resend.com](https://resend.com)
2. **Create API key** → API Keys → Create API Key → Copy (starts with `re_`)
3. **Railway** → API service → Variables → Add:
   - `RESEND_API_KEY` = `re_your_key_here`
4. **Redeploy** the API service

## Optional: Sender address

- **Testing:** `onboarding@resend.dev` works by default
- **Production:** Verify your domain in Resend, then add:
  - `RESEND_FROM_EMAIL` = `quotes@yourcompany.com`
  - `RESEND_FROM_NAME` = `Your Company`

Users can also set From Email/Name in **My Settings → Email Settings**—those override when present.
