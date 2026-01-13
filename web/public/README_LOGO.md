# Logo Setup Instructions

## Adding the LeadLock Logo

1. **Save your logo file** as `logo.png` in the `web/public/` directory

2. **Logo specifications:**
   - Format: PNG (currently configured)
   - Recommended size: 400x400px or higher for best quality
   - The logo should include:
     - The horse jumping over the "L" shape graphic
     - The "LeadLock" text
     - The "SALES CONTROL —" tagline

3. **File location:** `web/public/logo.png`

4. **Alternative formats:**
   - If using SVG: Save as `logo.svg` and update `Logo.tsx` to use `/logo.svg`
   - If using a different name: Update the `src` in `web/components/Logo.tsx`

## Current Logo Component

The `Logo` component is configured to:
- Display the logo image (48x48px in header, scales on login)
- Show "LeadLock" text in white
- Show "SALES CONTROL —" tagline in muted grey

The component automatically adapts to both the header and login screen layouts.
