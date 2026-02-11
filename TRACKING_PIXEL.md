# Website visit tracking pixel

LeadLock can record when a **customer** visits one of your three websites (Cheshire Stables, CSGB, BLC). The pixel is a 1×1 image loaded from the LeadLock API. Visits are shown under **Websites Visited** on the customer detail page.

## How it works

1. You send the customer a link that includes their tracking token, e.g.  
   `https://cheshirestables.com?ltk=CUST-2024-001`  
   The token is the customer’s **customer number** (e.g. `CUST-2024-001`).

2. When they open that link, your website loads the pixel with that token and the site identifier. The API records the visit and returns a transparent 1×1 GIF.

3. In LeadLock, open the customer and check the **Websites Visited** section to see which sites they visited and when.

## Pixel URL

```
GET https://<your-api-domain>/api/public/pixel?token=TOKEN&site=SITE_SLUG
```

- **token** (required): The customer number, e.g. `CUST-2024-001`.
- **site** (required): One of:
  - `cheshire_stables` – Cheshire Stables
  - `csgb` – CSGB
  - `blc` – BLC

Example:

```
https://your-api.railway.app/api/public/pixel?token=CUST-2024-001&site=cheshire_stables
```

The endpoint always returns HTTP 200 and a 1×1 transparent GIF. If the token is missing or unknown, no visit is stored (so you don’t leak whether a token is valid).

## Snippet for your websites

Add this script to each of the three sites. Replace `API_BASE` with your LeadLock API base URL (e.g. `https://your-api.railway.app`). On each site, set `SITE_SLUG` to the correct value: `cheshire_stables`, `csgb`, or `blc`.

```html
<script>
(function() {
  var API_BASE = 'https://your-api.railway.app';
  var SITE_SLUG = 'cheshire_stables'; // use 'csgb' or 'blc' on the other sites

  function getQueryParam(name) {
    var match = new RegExp('[?&]' + name + '=([^&]*)').exec(window.location.search);
    return match ? decodeURIComponent(match[1]) : null;
  }

  var token = getQueryParam('ltk');
  if (token) {
    var img = new Image();
    img.src = API_BASE + '/api/public/pixel?token=' + encodeURIComponent(token) + '&site=' + encodeURIComponent(SITE_SLUG);
    document.body.appendChild(img);
  }
})();
</script>
```

Or as a single pixel image (e.g. in the footer), only when `ltk` is present:

- Cheshire Stables: use `site=cheshire_stables`
- CSGB: use `site=csgb`
- BLC: use `site=blc`

## Links you send to customers

For visits to be attributed to a customer, the link they use must include the token. Use the query parameter `ltk` with the customer number:

- Cheshire Stables: `https://cheshirestables.com?ltk=CUST-2024-001`
- CSGB: `https://yoursite-csgb.com?ltk=CUST-2024-001`
- BLC: `https://yoursite-blc.com?ltk=CUST-2024-001`

You can add this to emails, quote emails, or any other channel. When the customer opens the link, the page loads and the pixel fires, and LeadLock records the visit.

---

## Adding the pixel to a WordPress site

Use one of the methods below. You need:

- **API base URL** – your LeadLock API URL (e.g. `https://your-app.railway.app`).
- **Site slug** – `cheshire_stables`, `csgb`, or `blc` depending on which site you’re editing.

### Option 1: Insert Headers and Footers (recommended)

1. Install the plugin **Insert Headers and Footers** (by WPCode) or similar.
2. In WordPress admin go to **Settings → Insert Headers and Footers** (or **Code Snippets → Header & Footer**).
3. In **Scripts in Footer**, paste the script below (after replacing `API_BASE` and `SITE_SLUG`).
4. Save. The script will run on every page; the pixel only loads when the URL contains `?ltk=...`.

```html
<script>
(function() {
  var API_BASE = 'https://YOUR-API-URL.railway.app';
  var SITE_SLUG = 'cheshire_stables';

  function getQueryParam(name) {
    var match = new RegExp('[?&]' + name + '=([^&]*)').exec(window.location.search);
    return match ? decodeURIComponent(match[1]) : null;
  }

  var token = getQueryParam('ltk');
  if (token) {
    var img = new Image();
    img.src = API_BASE + '/api/public/pixel?token=' + encodeURIComponent(token) + '&site=' + encodeURIComponent(SITE_SLUG);
    document.body.appendChild(img);
  }
})();
</script>
```

### Option 2: Theme customizer / “Additional code”

Many themes (e.g. Astra, Kadence, GeneratePress) have a **Customizer → Additional CSS / Scripts** or **Header / Footer Scripts** option.

1. Go to **Appearance → Customize**.
2. Find a section like **Additional JS**, **Footer Scripts**, or **Code injection**.
3. Paste the same script as above (with your `API_BASE` and `SITE_SLUG`).
4. Publish.

### Option 3: Code Snippets plugin

1. Install **Code Snippets**.
2. Add a new snippet: **Snippets → Add New**.
3. Give it a name (e.g. “LeadLock visit pixel”).
4. In the code box, paste only the **JavaScript** (no `<script>` tags if the snippet type is “JavaScript”):

```javascript
(function() {
  var API_BASE = 'https://YOUR-API-URL.railway.app';
  var SITE_SLUG = 'cheshire_stables';

  function getQueryParam(name) {
    var match = new RegExp('[?&]' + name + '=([^&]*)').exec(window.location.search);
    return match ? decodeURIComponent(match[1]) : null;
  }

  var token = getQueryParam('ltk');
  if (token) {
    var img = new Image();
    img.src = API_BASE + '/api/public/pixel?token=' + encodeURIComponent(token) + '&site=' + encodeURIComponent(SITE_SLUG);
    document.body.appendChild(img);
  }
})();
```

5. Set **Run snippet everywhere** and **Only run in footer** (recommended).
6. Save and activate.

### One site per WordPress install

- **Cheshire Stables** site → use `SITE_SLUG = 'cheshire_stables'`.
- **CSGB** site → use `SITE_SLUG = 'csgb'`.
- **BLC** site → use `SITE_SLUG = 'blc'`.

Replace `YOUR-API-URL.railway.app` with your real LeadLock API host in all cases.
