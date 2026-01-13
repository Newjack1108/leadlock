# Railway Frontend Deployment Guide

## Step-by-Step: Deploying Next.js Frontend to Railway

### Option 1: Delete and Recreate (Recommended if having issues)

1. **Delete the existing frontend service:**
   - In Railway dashboard, go to your frontend service
   - Click "Settings" → Scroll down → "Delete Service"
   - Confirm deletion

2. **Create a new service:**
   - In your Railway project, click "+ New" → "GitHub Repo"
   - Select your `leadlock` repository
   - Railway will create a new service

3. **Configure the service:**
   - Click on the new service
   - Go to "Settings" → "Source"
   - Set **Root Directory** to exactly: `web` (lowercase, no quotes, no trailing slash)
   - Click "Save"

4. **Verify Root Directory:**
   - In Railway, click "View Files" or browse the service
   - You should see:
     - ✅ `package.json`
     - ✅ `next.config.ts`
     - ✅ `app/` directory
     - ✅ `components/` directory
     - ❌ NOT `api/` directory

5. **Set Environment Variables:**
   - Go to "Variables" tab
   - Add: `NEXT_PUBLIC_API_URL` = `https://leadlock-production.up.railway.app` (your backend URL)
   - Click "Add"

6. **Deploy:**
   - Railway should automatically detect the push and start building
   - Watch the "Deployments" tab for build progress
   - Check logs if it fails

### Option 2: Fix Existing Service

If you want to keep the existing service:

1. **Verify Root Directory:**
   - Settings → Source → Root Directory should be exactly `web`

2. **Clear Build Cache (if available):**
   - Settings → Advanced → "Clear Build Cache"

3. **Redeploy:**
   - Go to "Deployments" → Click "Redeploy" on the latest deployment

### Troubleshooting

**If Railway still detects Python:**
- Make sure Root Directory is set to `web` (not `/web` or `web/`)
- Check that you can see `package.json` when browsing files in Railway
- Try deleting and recreating the service

**If build fails:**
- Check the "Logs" tab in the deployment
- Look for error messages about missing dependencies or build failures
- Ensure `NEXT_PUBLIC_API_URL` is set correctly

**If deployment succeeds but app doesn't load:**
- Check that the port is correctly set (Railway provides `$PORT`)
- Verify `NEXT_PUBLIC_API_URL` points to your backend
- Check Railway logs for runtime errors

### Expected Build Output

When Railway builds successfully, you should see:
```
✓ Compiled successfully
✓ Generating static pages
✓ Build completed
```

Then it should start with:
```
> next start -p 8080
```

### Verification

After successful deployment:
1. Visit your Railway frontend URL
2. You should see the LeadLock login screen
3. Try logging in with:
   - Email: `director@cheshirestables.com`
   - Password: `director123`
