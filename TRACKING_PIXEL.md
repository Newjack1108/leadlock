# Website visit tracking pixel

LeadLock can record when a **customer** visits one of your three websites (Cheshire Stables, CSGB, BLC). The pixel is a 1×1 image loaded from the LeadLock API. Visits are shown under **Websites Visited** on the customer detail page.

## How it works

1. You send the customer a link that includes their tracking token, e.g.  
   `https://cheshirestables.com?ltk=<tracking_pixel_token>`  
   The token is the customer’s unguessable **`tracking_pixel_token`** (returned on customer API responses), not the customer number.

2. When they open that link, your website loads the pixel with that token and the site identifier. The API records the visit and returns a transparent 1×1 GIF.

3. In LeadLock, open the customer and check the **Websites Visited** section to see which sites they visited and when.

## Pixel URL

```
GET https://<your-api-domain>/api/public/pixel?token=TOKEN&site=SITE_SLUG
```

- **token** (required): The customer `tracking_pixel_token` (opaque, high-entropy).
- **site** (required): One of:
  - `cheshire_stables` – Cheshire Stables
  - `csgb` – CSGB
  - `blc` – BLC

Example:

```
https://your-api.railway.app/api/public/pixel?token=xY7opaqueTokenHere&site=cheshire_stables
```

The endpoint always returns HTTP 200 and a 1×1 transparent GIF. If the token is missing or unknown, no visit is stored (so you don’t leak whether a token is valid).

## Snippet for your websites

Add this script to each of the three sites. Replace `API_BASE` with your LeadLock API base URL (e.g. `https://your-api.railway.app`). On each site, set `SITE_SLUG` to the correct value: `cheshire_stables`, `csgb`, or `blc`.

```html
<script>
(function () {
  var API_BASE = 'https://your-api.railway.app';
  var SITE_SLUG = 'cheshire_stables'; // change per site
  var params = new URLSearchParams(window.location.search);
  var token = params.get('ltk');
  if (!token) return;
  var img = new Image();
  img.src = API_BASE + '/api/public/pixel?token=' + encodeURIComponent(token) + '&site=' + encodeURIComponent(SITE_SLUG);
})();
</script>
```

Use the same pattern on CSGB and BLC with the matching `SITE_SLUG`.

Staff can copy each customer’s `tracking_pixel_token` from the customer record / API response when building tracked links.
