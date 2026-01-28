# Cloudinary Setup Guide

This guide will help you set up Cloudinary for product image uploads in LeadLock.

## What is Cloudinary?

Cloudinary is a cloud-based image and video management service that provides:
- Image storage and delivery via CDN
- Automatic image optimization and transformation
- Secure uploads with API keys
- Free tier with generous limits

## Step 1: Create a Cloudinary Account

1. Go to [https://cloudinary.com/users/register/free](https://cloudinary.com/users/register/free)
2. Sign up for a free account (no credit card required)
3. Verify your email address

## Step 2: Get Your Cloudinary Credentials

1. After logging in, you'll be taken to your Dashboard
2. On the Dashboard, you'll see your **Account Details** which include:
   - **Cloud Name** (e.g., `your-cloud-name`)
   - **API Key** (e.g., `123456789012345`)
   - **API Secret** (e.g., `abcdefghijklmnopqrstuvwxyz123456`)

3. Copy these three values - you'll need them for the next step

**Note:** Keep your API Secret secure and never commit it to version control!

## Step 3: Install Cloudinary Package

The Cloudinary package is already in `requirements.txt`, so if you haven't installed dependencies yet:

```bash
cd api
pip install -r requirements.txt
```

Or install just Cloudinary:

```bash
pip install cloudinary==1.36.0
```

## Step 4: Configure Environment Variables

### For Local Development

Add these variables to your `api/.env` file:

```env
# Cloudinary Configuration
CLOUDINARY_CLOUD_NAME=your-cloud-name
CLOUDINARY_API_KEY=your-api-key
CLOUDINARY_API_SECRET=your-api-secret
```

**Example:**
```env
CLOUDINARY_CLOUD_NAME=mycompany
CLOUDINARY_API_KEY=123456789012345
CLOUDINARY_API_SECRET=abcdefghijklmnopqrstuvwxyz123456
```

### For Railway Deployment

1. Go to your Railway project dashboard
2. Select your backend service
3. Go to the **Variables** tab
4. Add the following environment variables:
   - `CLOUDINARY_CLOUD_NAME` = your cloud name
   - `CLOUDINARY_API_KEY` = your API key
   - `CLOUDINARY_API_SECRET` = your API secret

5. Click **Deploy** to apply the changes

## Step 5: Verify Setup

### Test Local Setup

1. Start your backend server:
   ```bash
   cd api
   uvicorn app.main:app --reload --port 8000
   ```

2. Try uploading an image through the product creation page:
   - Go to `/products/create`
   - Upload an image
   - Check the browser console and server logs for any errors

3. If successful, the image URL should start with `https://res.cloudinary.com/...`

### Check Cloudinary Dashboard

1. Log in to your Cloudinary dashboard
2. Go to **Media Library**
3. You should see a `products` folder with your uploaded images

## Fallback to Local Storage

If Cloudinary is not configured, the system will automatically fall back to local storage:
- Images will be saved to `api/static/products/`
- Images will be accessible via `/static/products/{filename}`
- This works for development but is not recommended for production

## Troubleshooting

### Error: "Cloudinary is not configured"

**Solution:** Make sure all three environment variables are set:
- `CLOUDINARY_CLOUD_NAME`
- `CLOUDINARY_API_KEY`
- `CLOUDINARY_API_SECRET`

### Error: "Invalid API credentials"

**Solution:** 
- Double-check that you copied the credentials correctly
- Make sure there are no extra spaces in your `.env` file
- Verify your Cloudinary account is active

### Images not uploading

**Solution:**
1. Check server logs for detailed error messages
2. Verify file size is under 10MB
3. Ensure file is a valid image format (JPG, PNG, GIF, etc.)
4. Check Cloudinary dashboard for upload limits (free tier has limits)

### Images not displaying

**Solution:**
1. Check that the image URL is accessible
2. Verify CORS settings if accessing from a different domain
3. Check browser console for CORS or network errors

## Cloudinary Free Tier Limits

The free tier includes:
- **25 GB** storage
- **25 GB** monthly bandwidth
- **25,000** monthly transformations
- Unlimited uploads

For most small to medium businesses, this is sufficient. Upgrade plans are available if needed.

## Security Best Practices

1. **Never commit credentials to Git:**
   - Keep `.env` in `.gitignore` (already configured)
   - Use environment variables in production

2. **Restrict API access:**
   - In Cloudinary dashboard, go to **Settings** > **Security**
   - Consider restricting uploads to specific IPs in production
   - Use signed uploads for additional security (optional)

3. **Monitor usage:**
   - Check Cloudinary dashboard regularly for usage
   - Set up alerts if approaching limits

## Additional Configuration (Optional)

### Custom Upload Presets

You can create upload presets in Cloudinary for more control:

1. Go to **Settings** > **Upload** > **Upload presets**
2. Create a new preset with your desired settings
3. Update `image_upload_service.py` to use the preset:

```python
upload_result = cloudinary.uploader.upload(
    contents,
    upload_preset="your-preset-name",  # Add this
    folder="products",
    resource_type="image",
)
```

### Image Transformations

The current setup automatically:
- Resizes images to max 1200x1200px
- Optimizes quality automatically

You can customize transformations in `api/app/image_upload_service.py` in the `upload_image_to_cloudinary` function.

## Support

- Cloudinary Documentation: [https://cloudinary.com/documentation](https://cloudinary.com/documentation)
- Cloudinary Support: [https://support.cloudinary.com](https://support.cloudinary.com)
- LeadLock Issues: Check your project's issue tracker
