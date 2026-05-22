# Deploy RoboClub to Vercel

Vercel hosts **both** the UI (static HTML) and the API (FastAPI serverless) in one project.

## Before you deploy

1. Create a free account at [vercel.com](https://vercel.com)
2. Install Vercel CLI (optional): `npm i -g vercel`
3. Push this project to **GitHub** (Vercel deploys from Git)

## Deploy from GitHub (recommended)

1. Go to [vercel.com/new](https://vercel.com/new)
2. Import your `roboclub` repository
3. Leave settings as detected:
   - **Framework Preset:** Other
   - **Build Command:** `python scripts/build_static.py` (or use `vercel.json` defaults)
   - **Output Directory:** `public`
   - **Install Command:** `python3 -m pip install --break-system-packages -r requirements.txt`
4. Click **Deploy**

Your app will be at: `https://your-project.vercel.app`

- UI: `https://your-project.vercel.app/dashboard`
- API: `https://your-project.vercel.app/api/health`
- Docs: `https://your-project.vercel.app/docs`

## Deploy from your PC (CLI)

```powershell
cd C:\Users\user\Downloads\roboclub
npm i -g vercel
vercel login
vercel
```

Follow prompts. For production:

```powershell
vercel --prod
```

## How it works on Vercel

| Part | On Vercel |
|------|-----------|
| Pages | Pre-built HTML in `public/` (from Jinja templates) |
| API | `api/index.py` → FastAPI serverless |
| Database | SQLite in `/tmp` (resets on cold starts — OK for demo) |
| Live updates | **Polling** every 4s (`/api/live/tick`) — SSE is disabled on serverless |

Locally you still get full SSE; on Vercel, attendance and alerts update via polling automatically.

## Limits to know

- **Inventory data** may reset when the serverless function cold-starts (SQLite in `/tmp`)
- **SSE streams** do not run on Vercel; polling is used instead
- For permanent DB + long-lived SSE, use Railway, Render, or a VPS later

## Troubleshooting

| Problem | Fix |
|---------|-----|
| Build fails: `python` not found | In Vercel project **Settings → General**, set Python version or use build command with `python3` |
| 404 on `/dashboard` | Redeploy; `vercel.json` rewrites must be included |
| API 500 | Check **Deployments → Functions** logs |
| Empty inventory | Expected on cold start; add items again or use external DB later |

## Environment variables (optional)

In Vercel → Project → Settings → Environment Variables:

| Name | Value |
|------|--------|
| `DATA_DIR` | `/tmp/roboclub-data` (default on Vercel) |

No `API_URL` needed — the static site calls the API on the same domain.
