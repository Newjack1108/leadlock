# Logo Setup Instructions

## Adding the LeadLock Logo

1. **Save your logo file** as `logo.svg` in the `web/public/` directory

2. **Logo specifications:**
   - Format: SVG (preferred) or PNG
   - Recommended size: 200x200px minimum for SVG, or 400x400px for PNG
   - The logo should include:
     - The horse jumping over the "L" shape graphic
     - The "LeadLock" text
     - The "SALES CONTROL —" tagline

3. **File location:** `web/public/logo.svg`

4. **Alternative formats:**
   - If using PNG: Save as `logo.png` and update `Logo.tsx` to use `/logo.png`
   - If using a different name: Update the `src` in `web/components/Logo.tsx`

## Current Logo Component

The `Logo` component is configured to:
- Display the logo image (48x48px in header, scales on login)
- Show "LeadLock" text in white
- Show "SALES CONTROL —" tagline in muted grey

The component automatically adapts to both the header and login screen layouts.
