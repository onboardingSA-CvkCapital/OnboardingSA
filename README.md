# OnboardingSA

A South African public-sector & parastatal job board. Static site (HTML/CSS/JS) that reads live jobs from a published Google Sheet. No backend, no build step.

## Files
- `index.html` — the job board (search, filters, two-panel list + detail)
- `about.html` — how it works
- `privacy.html` — POPIA privacy policy (also needed for AdSense later)
- `assets/` — logo icon

## 1. Connect your Google Sheet
1. In Google Sheets: **File → Share → Publish to web** → publish the **Jobs** tab.
2. Copy the link and change the end to `output=csv` (not `pubhtml`).
3. Open `index.html`, find `CSV_URL` near the bottom, and paste your link there.

Only rows where **status** is `live` show on the site. Leave a job as `draft` while you prepare it.

## 2. Job alerts link
In `index.html`, set `ALERTS_URL` to your Google Form or WhatsApp channel link. Until then the alerts button is inactive.

## 3. Put it on GitHub Pages (free)
1. Create a GitHub account and a new **public** repo, e.g. `onboardingsa`.
2. Upload these files to the repo (drag-and-drop in the browser works).
3. Repo → **Settings → Pages** → Source: `main` branch, `/root` → Save.
4. Your site goes live at `https://<username>.github.io/onboardingsa/`.

## 4. Connect your domain (onboardingsa.co.za)
1. Repo → Settings → Pages → **Custom domain** → enter `onboardingsa.co.za` → Save.
2. At your registrar (Domains.co.za) DNS, add the records GitHub shows (A records to GitHub's IPs, or a CNAME).
3. Tick **Enforce HTTPS** once it’s verified.

## Notes
- If the sheet has no `live` jobs yet, the site shows a few sample jobs so you can see the layout. They disappear as soon as you publish real live rows.
- Brand colours: navy `#12294D`, gold `#E8A33D`.
