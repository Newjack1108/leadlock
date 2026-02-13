# Quote PDF logo not showing

The API generates quote PDFs and needs to load your logo.

## Default placeholder logo

The repo includes `web/public/logo1.jpg` and `web/public/logo1.png` as minimal placeholders. Replace these with your real logo (recommended size: at least 200×80px, PNG or JPG).

## Preferred: upload your logo in the app

Go to **Settings → Company** and use **Company logo (for quote PDFs)** to upload an image. The logo is stored and used for all quote PDFs; no environment variables or file placement needed. This is the recommended way to set the quote PDF logo. For production, configure Cloudinary so uploaded logos persist across deployments.

The options below (logo filename and env vars) remain as a fallback for existing deployments.

## Fallback: set a variable on the **API** service

1. In **Railway**, open your **API/backend** service (not the frontend).
2. Go to **Variables**.
3. Add **one** of these:

### Option A (recommended): full logo URL

- **Name:** `LOGO_URL`
- **Value:** The full URL to your logo image.

Use your **frontend** app URL + the path to the logo. For example, if your frontend is  
`https://leadlock-frontend-production.up.railway.app` and the logo is `web/public/logo1.jpg` (served at `/logo1.jpg`):

```text
LOGO_URL=https://leadlock-frontend-production.up.railway.app/logo1.jpg
```

Replace with your real frontend URL if it’s different. No trailing slash.

### Option B: frontend base URL

- **Name:** `FRONTEND_URL`
- **Value:** The base URL of your frontend (no path, no trailing slash).

Example:

```text
FRONTEND_URL=https://leadlock-frontend-production.up.railway.app
```

The API will then try `FRONTEND_URL/logo1.jpg` (and `logo1.png` if needed). The logo filename is the one set in **Settings → Company → Logo filename** (default `logo1.jpg`).

4. Save and **redeploy** the API service so the new variable is applied.

## Check the logo URL in the browser

Before setting the variable, open the logo URL in your browser. You should see the image.

- If your frontend is `https://leadlock-frontend-production.up.railway.app`, open:
  - `https://leadlock-frontend-production.up.railway.app/logo1.jpg`
- If that loads, set `LOGO_URL` to that exact URL on the API service.

## If it still doesn’t show

- Confirm the variable is on the **API** service, not the frontend.
- Ensure there’s no typo and no trailing slash in `LOGO_URL` (e.g. `.../logo1.jpg` not `.../logo1.jpg/`).
- Redeploy the API after changing variables.
- If your frontend URL is different (e.g. different project name), use that URL in `LOGO_URL` or `FRONTEND_URL`.
