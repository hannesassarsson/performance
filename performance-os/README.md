# Performance OS — deploy guide (browser only, no local terminal needed)

## What's actually in this skeleton

Working end-to-end: Garmin connect (with MFA) → sync → Postgres → a bare
activities list on the frontend. This is enough to deploy and verify the
whole pipeline is alive.

NOT yet built (these are later steps from the original plan — Steps
6-11): the real dashboard UI, Recovery/Sleep/HRV/Strength/CrossFit
analytics pages, the Analytics Engine, Feature Store population, the AI
Coach/Chat layer, and automated tests. Clerk auth is wired on the
backend (JWT verification) but the frontend doesn't have `<ClerkProvider>`
wired in yet — every API call from the frontend is currently
unauthenticated. Add Clerk's Next.js middleware before this touches real
user data.

**Also still unverified** (flagged in the code itself): the exact
Garmin method names (`get_sleep_data`, `get_hrv_data`, etc.) in
`garmin_client.py` — confirm against `python-garminconnect`'s `demo.py`
the first time you actually run a sync.

---

## Step 1 — Get the code onto GitHub (no git CLI needed)

1. Download the zip file from this chat and unzip it — your OS's file
   explorer can do this, no terminal required.
2. Go to [github.com/new](https://github.com/new), create a new
   **private** repository (call it `performance-os`), don't initialize
   it with a README.
3. On the empty repo's page, click **"uploading an existing file"**.
4. Drag the *unzipped folder itself* (not a zip) into the browser drop
   zone. Chrome and Edge preserve the folder structure when you drop a
   folder here — Firefox does not, so use Chrome/Edge for this step.
5. Commit directly to `main`.

## Step 2 — Deploy the backend (Railway)

1. Go to [railway.app](https://railway.app) → New Project → **Deploy
   from GitHub repo** → pick `performance-os`.
2. Railway will try to detect a build — set the **root directory** to
   `apps/api` in the service's Settings tab (it has its own Dockerfile).
3. In the same project, click **+ New** → **Database** → **Postgres**.
   Do the same for **Redis**.
4. Go to your API service → **Variables** tab. Add each variable from
   `apps/api/.env.example`:
   - `DATABASE_URL` — click "Add Reference" and pick the Postgres
     plugin's `DATABASE_URL` instead of typing it manually
   - `REDIS_URL` — same, reference the Redis plugin
   - `GARMIN_SESSION_ENCRYPTION_KEY` — open the Postgres plugin's "Data"
     tab, or use Railway's built-in shell for any service, and run:
     `python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`
     paste the output as the value
   - `CLERK_JWKS_URL`, `CLERK_PUBLISHABLE_KEY` — from
     [clerk.com](https://clerk.com) dashboard → your app → API Keys
     (create a free Clerk app if you haven't)
   - `CORS_ALLOW_ORIGINS` — leave a placeholder for now
     (`["http://localhost:3000"]`), you'll update it once you have your
     Vercel URL in Step 3
5. Deploy. Once it's live, go to Settings → Networking → **Generate
   Domain** to get a public URL like `https://xxxx.up.railway.app`.

### Apply the database schema

Railway's Postgres plugin has a **Data** tab with a query console built
in — no local `psql` needed:

1. Open the Postgres plugin → **Data** tab → **Query**.
2. Open `apps/api/db/schema.sql` from your repo (view it on GitHub),
   copy the whole file, paste it into Railway's query console, run it.
3. You should see the new tables appear in the Data tab's table list.

## Step 3 — Deploy the frontend (Vercel)

1. Go to [vercel.com/new](https://vercel.com/new) → import the same
   GitHub repo.
2. Set **Root Directory** to `apps/web`.
3. Add environment variables (from `apps/web/.env.example`):
   - `NEXT_PUBLIC_API_URL` — your Railway public URL from Step 2
   - `NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY`, `CLERK_SECRET_KEY` — same
     Clerk app as above
4. Deploy.
5. Go back to Railway → your API service → Variables →
   `CORS_ALLOW_ORIGINS` → update to include your real Vercel URL, e.g.
   `["https://performance-os.vercel.app"]`. Redeploy the backend.

## Step 4 — Smoke test

1. Visit your Vercel URL → you should see the (bare) dashboard with "No
   activities yet."
2. Go to `/connect-garmin`, enter your real Garmin credentials. This
   calls Railway, which calls Garmin — expect a 30-45 second delay
   (deliberate, see code comments) and possibly an MFA prompt.
3. Once connected, trigger a sync manually by calling (from your
   browser's address bar, or a tool like Postman):
   `POST https://your-api.up.railway.app/api/v1/providers/garmin/sync/{provider_connection_id}`
   — you'll need the connection id, which the connect response returns.
4. Refresh the dashboard — activities should appear if the Garmin
   method names in `garmin_client.py` turned out to be correct. If not,
   Railway's service logs (Deployments tab → View Logs) will show you
   the actual exception from `garminconnect`, telling you which method
   name to fix.

---

## What to fix first if something breaks

- **500 on `/connect`**: check Railway logs — likely a Garmin method
  name mismatch, or `curl_cffi`/`ua-generator` not installing correctly
  (check the build logs).
- **CORS errors in the browser console**: `CORS_ALLOW_ORIGINS` on
  Railway doesn't match your actual Vercel URL exactly (including
  https://, no trailing slash).
- **401 on every API call**: expected right now — Clerk isn't wired
  into the frontend yet, so no Authorization header is ever sent, but
  the backend expects one. Wiring Clerk into the frontend is the
  natural next task after this smoke test passes.
