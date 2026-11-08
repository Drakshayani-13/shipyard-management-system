# Shipyard Vessel Management Portal (Full-Stack)

Flask REST API (SQLite locally / PostgreSQL in production), vanilla HTML/CSS/JS frontend.

Features: dashboard with live statistics, vessel registration/search/filter/CSV export, maintenance management, vessel arrival/departure history, and login with role-based access (admin / staff / viewer).

```
frontend/   index.html, style.css, script.js, config.js   -> Netlify
backend/    app.py, requirements.txt, render.yaml          -> Render Web Service
```

## API

| Method | Endpoint | Description |
|---|---|---|
| GET | /api/ships | List ships. Optional: `?search=`, `?type=`, `?status=` |
| GET | /api/ships/<id> | Get one ship |
| POST | /api/ships | Register a ship |
| PUT | /api/ships/<id> | Update a ship |
| DELETE | /api/ships/<id> | Delete a ship |
| POST | /api/auth/login | `{username, password}` -> `{token, user}`. All other `/api/*` routes need `Authorization: Bearer <token>` |
| GET | /api/auth/me, POST /api/auth/logout | Current user / logout |
| GET/POST | /api/maintenance | List (`?status=`, `?ship_pk=`) / create maintenance record |
| PUT/DELETE | /api/maintenance/<id> | Update / delete (delete: admin only) |
| GET/POST | /api/movements | Movement history (`?ship_pk=`) / record Arrival or Departure |
| GET | /api/dashboard/stats | `{total, ready, in_service, under_maintenance, inactive, by_type}` |

`<id>` is the database id returned in each record. Ship JSON fields: `ship_id, ship_name, ship_type, registration_date (YYYY-MM-DD), status, berth_number`.
Vessel statuses: Ready, In Service, Docked, Under Maintenance, Inactive. Maintenance statuses: Scheduled, In Progress, Completed, Delayed. "Active" on the dashboard = In Service. The `ships` table is created automatically on first start.

## Database: SQLite locally, PostgreSQL in production

The same `app.py` works with both. It chooses the database from `DATABASE_URL`:

| Environment | `DATABASE_URL` | Database |
|---|---|---|
| Local development | not set | SQLite file `backend/shipyard.db` (created automatically) |
| Production (Render) | set to the Render PostgreSQL URL | PostgreSQL |

The `ships` table is created automatically in both cases. No database installation is needed locally.

## Login & roles

On first start an admin is created from `ADMIN_USERNAME` / `ADMIN_PASSWORD` (default `admin` / `admin123` locally, with a warning - **always set `ADMIN_PASSWORD` and `SECRET_KEY` in production**). Passwords are stored hashed. Roles: **admin** (everything, incl. delete), **staff** (create/edit, no delete), **viewer** (read-only). Add users with `python create_user.py <username> <password> <admin|staff|viewer>`.
Movement rules: Arrival (needs berth) sets the vessel to Docked; Departure sets it to In Service. In Progress/Delayed maintenance sets a vessel to Under Maintenance.

## Quick start (one command)

> **Mac note:** the app uses port **5001** because macOS AirPlay Receiver occupies port 5000 and answers it with "403 Access denied".


- **Windows:** double-click `run.bat`  |  **Mac/Linux:** `./run.sh`
- Then open **http://127.0.0.1:5001/portal/** and sign in with `admin` / `admin123`.

This installs the dependencies, loads demo vessels, maintenance records and movement history, and serves both the API and the website from one server.

## Run locally (manual, frontend and backend separate)

1. Backend:
   ```
   cd backend
   python -m venv venv && source venv/bin/activate     # Windows: venv\Scripts\activate
   pip install -r requirements.txt
   cp .env.example .env        # optional; only needed to change CORS_ORIGINS
   python app.py               # runs on http://127.0.0.1:5001
   ```
   Sign in at the frontend with the admin account above. Leave `DATABASE_URL` unset so SQLite is used. To delete all local data, stop the server and delete `backend/shipyard.db`.
2. Frontend: open `frontend/` with VS Code Live Server (port 5500) or run `python -m http.server 5500` inside `frontend/`, then visit http://localhost:5500.
   `frontend/config.js` already points to `http://127.0.0.1:5001`.

## Deploy

### 1. GitHub
Push this whole folder to a GitHub repository (`.env` is git-ignored).

### 2. Database + backend on Render
1. Render dashboard -> **New -> PostgreSQL** (free plan). Copy its **Internal Database URL**.
2. **New -> Web Service**, connect your GitHub repo, then set:
   - Root Directory: `backend`
   - Runtime: Python 3
   - Build Command: `pip install -r requirements.txt`
   - Start Command: `gunicorn app:app`
3. Environment variables:
   - `DATABASE_URL` = the Internal Database URL
   - `SECRET_KEY` = long random string, `ADMIN_PASSWORD` = strong password
   - `CORS_ORIGINS` = your Netlify URL, e.g. `https://my-ships.netlify.app` (no trailing slash; comma-separate several)
4. Deploy, then open `https://<your-service>.onrender.com/` - you should see the "API is running" message.

(Alternative: `backend/render.yaml` is a Blueprint that creates both the database and web service.)

Note: Render's free web service sleeps after inactivity, so the first request can take ~30-60 seconds.

### 3. Frontend on Netlify
1. Edit `frontend/config.js` and set `API_BASE_URL` to your Render URL, commit and push.
2. Netlify -> **Add new site -> Import from Git**, choose the repo:
   - Base directory: `frontend`
   - Build command: *(leave empty)*
   - Publish directory: `frontend`
   (Or simply drag-and-drop the `frontend` folder onto Netlify Drop.)
3. Copy the Netlify URL into `CORS_ORIGINS` on Render and redeploy the backend if you haven't yet.


## Sample data

```
cd backend
python seed.py     # adds 8 demo vessels + maintenance records + movement history (safe to re-run)
```
