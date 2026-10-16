# Near & Dear — Hyperlocal Marketplace

A responsive local marketplace MVP for discovering neighborhood deals, requesting reservations, and giving merchants a simple way to manage listings. The existing Streamlit prototype files remain in the project; the new full-stack app runs through FastAPI.

## What works

- Browse, text-search, and filter local product listings by category, manual distance, and active discounts.
- Create buyer or merchant accounts and sign in.
- Merchants can create, update, and deactivate their own listings, review incoming reservations, and progress reservation status.
- Buyers can reserve available stock for pickup or request free local delivery, view reservations, and cancel eligible requests.
- Stock is deducted atomically when a reservation is submitted and restored on cancellation.
- Passwords are hashed, API access is role-checked, and session tokens expire after 24 hours.
- Sample catalog records are inserted automatically when the database is first created.

This MVP records reservation requests only. It does not process payments, confirm delivery, or collect payment details. Store distance is entered manually by the merchant; there is no live geolocation or map integration. Search currently matches text in product names, categories, stores, and descriptions.

## Run locally on Windows

Install Python 3.10 or newer. From PowerShell in the project folder:

```powershell
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
$env:SECRET_KEY = "replace-this-with-a-long-random-local-secret"
.\.venv\Scripts\python.exe -m uvicorn server:app --reload
```

Open <http://127.0.0.1:8000>. The API documentation is at <http://127.0.0.1:8000/docs>. SQLite creates `marketplace.db` in the project folder by default. Set a persistent `SECRET_KEY` before running if you want login sessions to remain valid after server restarts.

To run the tests:

```powershell
.\.venv\Scripts\python.exe -m pytest
```

## Configuration

Copy `.env.example` to `.env` for reference, then set the variables in your terminal or hosting dashboard. The application does not automatically load a `.env` file.

| Variable | Purpose |
| --- | --- |
| `SECRET_KEY` | HMAC signing key for session tokens. Required in production. Use a long random secret. |
| `DATABASE_URL` | SQLAlchemy URL. Defaults to local SQLite. |
| `CORS_ORIGINS` | Comma-separated browser origins allowed to call the API. |
| `ENVIRONMENT` | Set to `production` on the deployed backend. |

For PostgreSQL, use a SQLAlchemy URL such as `postgresql+psycopg://USER:PASSWORD@HOST/DBNAME?sslmode=require`. Keep credentials private and use the connection URL supplied by Neon.

## Deploy

The GitHub URL supplied for `rajuenduva-pixel/CUSTMOR` currently points to an empty repository. These files must be committed and pushed there before Vercel or Render can deploy them. This project has not been deployed, so there is no public application URL yet.

1. **Database — Neon**
   - Create a PostgreSQL project and database.
   - Copy its connection string and adjust it to use `postgresql+psycopg://` and `?sslmode=require`.

2. **Backend — Render**
   - Push this project to GitHub and create a Render Web Service from the repository. `render.yaml` contains the build/start commands.
   - Set `DATABASE_URL` to the Neon connection string.
   - Render generates `SECRET_KEY` from the blueprint.
   - After creating the Vercel project, set `CORS_ORIGINS` to its exact HTTPS origin, e.g. `https://your-project.vercel.app`.
   - Deploy and verify `https://<your-render-service>.onrender.com/api/health` returns `{"status":"ok"}`.

3. **Frontend — Vercel**
   - Import the same GitHub repository. Set the project output directory to `frontend` and use no build command; the frontend is static HTML/CSS/JavaScript and does not require Node or a bundler.
   - After Render has a URL, update `frontend/config.js` to set `window.MARKETPLACE_API_URL` to the backend origin, for example `https://your-service.onrender.com`, then push and redeploy.
   - Open the Vercel URL and test browsing, account creation, listing management, and reservations.

Use HTTPS URLs for deployed services. Never commit `.env` files or database credentials.

## Existing prototype

`app.py` is the original Streamlit demonstration. The complete API-backed marketplace is started with `uvicorn server:app`; the Streamlit app is not needed for the new frontend.
