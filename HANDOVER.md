# SK254 Store: Technical Handover

Everything needed to run, change, or rebuild the SK254 store from zero, even with no chat history.
Last updated: 2026-11-08.

---

## 1. What it is

A custom online store for **Soccer Kits 254** (official licensed jerseys, Kenya) that replaced Take.app ($29/month).
Total running cost: **$0/month** (Cloudflare free tier). The only cost is the domain renewal at Namecheap.

| Thing | Where |
|---|---|
| Live store | https://sk254.com and https://www.sk254.com |
| Admin panel (owner edits everything here) | https://sk254.com/admin |
| Backup URL (always works, ignores DNS) | https://sk254-site.soccerkits254.workers.dev |
| Code | GitHub: https://github.com/sk254group/sk254-site (branch `main`) |
| Hosting + backend + storage | Cloudflare account **Soccerkits254@gmail.com**, account ID `8232898be364587feac24d0b8d164963` |
| Worker name | `sk254-site` |
| KV namespace (database + photos) | `sk254-store`, ID `7d8991a850984562978fb25eb69bb98a`, bound as `KV` |
| Domain registrar | Namecheap (account user `hcoolj`), domain `sk254.com`, paid to 2027-08-23, auto-renew ON |
| Nameservers | `edna.ns.cloudflare.com`, `wilson.ns.cloudflare.com` (DNS is managed in Cloudflare now) |
| Orders go to | WhatsApp `254737170911` (editable in admin > Settings) |
| Local copy of the code | `C:\CLAUDE stuff\sk254-site` |
| Design options (unused drafts) | `C:\CLAUDE stuff\sk254-sample` (option-4 "Street" was chosen) |
| Owner's guide (PDF) | `C:\CLAUDE stuff\sk254-guides\SK254-Store-Guide.pdf` |

Secrets: **`ADMIN_PASSWORD`** is a Cloudflare Worker secret (Worker > Settings > Variables and Secrets).
It is not in the code or this doc. To change it: edit the secret in the dashboard and deploy. Every admin login session ends automatically, because tokens are signed with the password.

---

## 2. Architecture

```
Customer phone ──> sk254.com (Cloudflare DNS, proxied)
                      │
                      ▼
            Cloudflare Worker "sk254-site"  (src/index.js)
              ├─ static files from ./public  (ASSETS binding)
              │     /            -> public/index.html   (storefront, Street design)
              │     /admin/      -> public/admin/index.html (admin app)
              ├─ GET  /api/store        -> store JSON from KV key "store" (falls back to src/seed.json)
              ├─ GET  /img/<id>         -> photo bytes from KV key "img:<id>" (edge-cached 1 year)
              ├─ POST /api/login        -> {password} -> {token}   (30-day HMAC token)
              ├─ PUT  /api/store        -> save whole store JSON   (auth)
              ├─ POST /api/upload       -> raw image body -> {url:"/img/<id>"} (auth)
              └─ POST /api/import-images-> copies up to 40 external photo URLs into KV per call (auth)

Checkout = no payments on site. Bag -> pre-filled WhatsApp message (items, sizes, total) -> owner confirms, takes M-Pesa.
```

* **No database server, no build step, no npm deps.** Plain HTML/CSS/JS plus one Worker file.
* **Deploys are automatic.** Push to `main` on GitHub, Cloudflare Workers Builds runs `npx wrangler deploy` (about 40 seconds). Watch it at dash.cloudflare.com > Workers & Pages > sk254-site > Deployments.
* The GitHub repo is connected via the "Cloudflare Workers and Pages" GitHub App installed on `sk254group`.

### Files

```
sk254-site/
├─ wrangler.jsonc          # worker name, main, assets dir, KV binding
├─ src/index.js            # the whole backend (~130 lines)
├─ src/seed.json           # starter data used ONLY if KV "store" key is empty
├─ public/index.html       # storefront (reads /api/store at load)
├─ public/admin/index.html # admin single-page app
├─ public/admin/takeapp-import.json  # 65 products scraped from Take.app (for the one-tap import)
├─ tools/import_takeapp.py # re-scrapes Take.app -> takeapp-import.json
└─ HANDOVER.md             # this file
```

---

## 3. Data model (KV key `store`)

```jsonc
{
  "settings": {
    "name": "SK254", "whatsapp": "254737170911", "logo": "/img/<id> or URL",
    "hero1": "Jerseys", "hero2": "On", "hero3": "Jerseys", "heroText": "...",
    "sticker1": "100% Official", "sticker2": "From Ksh 1,499", "sticker3": "26/27 Season",
    "marquee": "Arsenal, Chelsea, ...",            // comma separated
    "shopTitle": "New Drops", "shopText": "...",   // last word of shopTitle is shown red
    "customTitle": "Your name. Your number.", "customText": "...", "customImg": "...",
    "about": "...", "instagram": "soccerkits254", "channel": "https://whatsapp.com/channel/..."
  },
  "categories": [ { "id": "epl", "name": "Premier League" } ],   // order = filter chip order
  "products": [ {
    "id": "t04zhhh0agw",          // "p<digits>" = starter seed, "t..." = imported from Take.app, "p<base36>" = made in admin
    "name": "Arsenal Home - 26/27 Fan Authentic",
    "label": "Fan Version",       // small green text above name
    "price": 1499, "was": null,   // was > price shows SALE + strikethrough
    "imgs": ["/img/abc", "..."],  // first = cover, max 6
    "cats": ["epl", "fan-kits"],
    "sizes": ["S","M","L","XL","XXL"],
    "out": false,                 // sold out
    "hidden": false,              // not shown on store
    "featured": true,             // rotates in hero banner + "New" tag
    "src": "takeapp:<take.app product id>"   // only on imported products
  } ]
}
```

Storefront rules: hidden products are dropped, and categories with no visible products are hidden. Featured products feed the hero slideshow (it falls back to the first 4 products). Product order = array order (admin "Reorder").

---

## 4. Day-to-day ops

| Task | How |
|---|---|
| Owner edits products/prices/stock/text | sk254.com/admin (phone friendly) |
| Change admin password | Cloudflare > sk254-site > Settings > Variables and Secrets > edit `ADMIN_PASSWORD` > Deploy |
| Change code | edit in `C:\CLAUDE stuff\sk254-site`, then `git add -A && git commit -m "..." && git push`. It auto-deploys. |
| Roll back a bad deploy | Cloudflare > sk254-site > Deployments > pick previous version > "Rollback". Or `git revert` + push. |
| Back up store data | Open https://sk254.com/api/store and save the JSON. Photos live in KV under `img:*` keys. |
| Restore data | Log in to admin, then in browser devtools on /admin: `store = <json>; save()` |
| Re-scrape Take.app | `python -I tools/import_takeapp.py` then commit + push. Then admin > Settings > "Import all products". It skips products already imported (matched by `src`). |
| Move photos off Take.app CDN | admin > Settings > "Copy photos from Take.app" (loops automatically, 40 per request) |

### Migration status checklist
- [x] Store live on sk254.com with HTTPS
- [x] Admin panel + password
- [ ] Owner taps **Import all products from Take.app** (65 products, 19 categories)
- [ ] Owner taps **Copy photos from Take.app** until it says "All photos are stored on your own site"
- [ ] Only then cancel the Take.app subscription (the photos die with it)
- [ ] Optional: replace placeholder trust text (delivery times, size swaps) if wrong

---

## 5. Free-tier limits (Cloudflare Workers Free)

* Worker requests: 100k/day.
* KV: 100k reads/day, **1,000 writes/day**, 1 GB storage. Each photo upload = 1 write and each save = 1 write. Photo copy uses about 250 writes once.
* `/img/*` is cached at the edge (Cache API) so repeat views don't count as KV reads.
* Worker subrequests: 50 per request on free, which is why photo copy runs 40 at a time.
* If the store grows past about 1,000 photos or heavy traffic, move photos to R2 (needs a card on file but has a free 10 GB tier).

---

## 6. Security notes

* Admin auth: `POST /api/login` compares against the `ADMIN_PASSWORD` secret (constant-time), then returns `exp.HMAC(password, "sk254-admin."+exp)`. That token is stored in the browser's localStorage and sent as `Authorization: Bearer`. Wrong attempts get a 900 ms delay.
* No customer data is stored anywhere. Orders go straight to WhatsApp. No payment data.
* Main risk = account takeover. Use strong passwords plus 2FA on **GitHub (sk254group)**, **Cloudflare (Soccerkits254@gmail.com)** and **Namecheap (hcoolj)**.
* Upload endpoint accepts only jpeg/png/webp up to 8 MB. Store JSON is capped at 2 MB.
* The admin password was once pasted in a chat, so change it if it hasn't been changed since setup.
* The GitHub repo is **public**. Never commit passwords, `.dev.vars`, or API tokens.

---

## 7. DNS (Cloudflare zone sk254.com)

* Custom Domains on the Worker: `sk254.com`, `www.sk254.com` (Cloudflare manages those records automatically).
* The old Take.app A records (`@`, `www`, `*` → 216.150.1.1) were deleted.
* MX/TXT records from Namecheap email forwarding (`eforward*.registrar-servers.com`) were imported but **no forwards were configured**, so email does nothing. For `orders@sk254.com`-style email, set up Cloudflare **Email Routing** (free) and delete the eforward MX records.

---

## 8. Local dev

No Node on this PC. Options:
* **Preview static files only:** `python -m http.server 5500 --directory public`. The API won't work, so the store shows "Couldn't load".
* **Full local dev:** install Node LTS, then `npx wrangler dev` (uses a local KV; set `ADMIN_PASSWORD` in `.dev.vars`, and never commit that file).
* Or just push to `main` and test on the workers.dev URL. That's how it was built.

Git auth on this PC uses Git Credential Manager (browser popup, signed in as `sk254group`). Run `git push` from a normal terminal so the popup can appear.

---

## 9. Ideas / backlog

* Product add-ons from Take.app weren't migrated: **name & number print (+Ksh 400)** and **sleeve badges (+Ksh 200)**. Add an optional "extras" field and checkboxes in the product popup.
* Per-size prices (a few products had different prices per variant; the import uses the lowest).
* Size guide page, delivery info page, Instagram feed, M-Pesa STK push (Daraja API) checkout.
* Order log: write each WhatsApp checkout to KV so the owner sees order history in admin.

---

## 10. Resuming with Claude Code

Open Claude Code in `C:\CLAUDE stuff\sk254-site` and say:

> Read HANDOVER.md. This is the SK254 jersey store (Cloudflare Worker + KV, deployed by pushing to GitHub main). I want to: <task>.
