# CarePoint Hospital Management System

A Flask and PostgreSQL hospital portal with patient registration, doctor-managed appointments and medical records, and an administrator dashboard. The HTML/CSS/JavaScript frontend is served by Flask from the same origin as the API.

## Features

- Patients can register, sign in, browse doctors, request future appointments, cancel their own pending or confirmed appointments, and view their own medical records.
- Doctors can sign in, view their appointments, confirm or complete appointments, and create one medical record for each confirmed/completed appointment assigned to them.
- Administrators can create doctor accounts and monitor hospital-wide patient, doctor, appointment, and medical record totals and records.
- Passwords are stored as Werkzeug password hashes. Role checks and record ownership are enforced by the backend.
- Local development uses SQLite when `DATABASE_URL` is omitted. Production requires PostgreSQL, `DATABASE_URL`, and `SECRET_KEY`.

## Run locally

1. Install Python 3.11 or newer.
2. Create and activate a virtual environment from this project directory.
3. Install dependencies:

   ```powershell
   python -m venv .venv
   .\.venv\Scripts\Activate.ps1
   python -m pip install -r backend\requirements.txt
   ```

4. Copy `.env.example` to `.env`. Create a strong local `SECRET_KEY`; for example, run `python -c "import secrets; print(secrets.token_urlsafe(48))"` and put the result in `.env`. Optionally set `ADMIN_EMAIL` and `ADMIN_PASSWORD` to seed the first administrator. The admin password must be at least 12 characters.
5. Start the app from the project directory:

   ```powershell
   python -m backend.app
   ```

6. Open `http://127.0.0.1:5000`. Patients can register in the UI. Doctor accounts are created by an administrator.

The server creates missing application tables at startup and adds the optional `phone` and `specialty` columns when upgrading an older `users` table. `database/schema.sql` documents the PostgreSQL schema and can also be applied manually to a fresh Neon database; do not apply it over an existing schema without checking for conflicts.

## Run tests

```powershell
python -m unittest discover -s tests -v
```

The tests use an isolated in-memory SQLite database and do not need Neon credentials.

## Deploy the source to GitHub

1. Create an empty GitHub repository.
2. From the project directory, initialize and push the source:

   ```powershell
   git init
   git add .
   git commit -m "Prepare hospital management system for deployment"
   git branch -M main
   git remote add origin https://github.com/YOUR_ACCOUNT/YOUR_REPOSITORY.git
   git push -u origin main
   ```

3. Confirm `.env`, database files, and credentials are not included in the commit. The `.gitignore` excludes them; `.env.example` is safe to commit.

## Create the Neon PostgreSQL database

1. Create a Neon project and database.
2. Copy the connection string for the database role. Use the pooled connection string for the web service and ensure it includes `sslmode=require`.
3. Keep the connection string private. Add it to Render as `DATABASE_URL`, not to GitHub or source code.

## Deploy the web service to Render

1. In Render, create a **Blueprint** from the GitHub repository, or create a Python web service using the included `render.yaml`.
2. Set the required service environment variables:
   - `APP_ENV=production`
   - `SECRET_KEY`: a long, random secret; Render generates one for the Blueprint.
   - `DATABASE_URL`: the Neon PostgreSQL connection string.
   - `ADMIN_EMAIL`: the initial administrator's email.
   - `ADMIN_PASSWORD`: a unique password with at least 12 characters.
3. Deploy. Render installs `backend/requirements.txt`, starts `backend.app:app` with Gunicorn on Render's `PORT`, and checks `/ready`.
4. Open the generated `https://...onrender.com` service URL. Sign in as the seeded administrator, create doctor accounts, then register patient accounts.
5. For every subsequent deployment, Render uses the latest GitHub commit. Keep production secrets in Render's environment settings and rotate them if exposed.

Optional `CORS_ORIGINS` is only needed if the browser frontend is moved to another origin. Set it to a comma-separated list of exact trusted origins, including `https://`, with no wildcard when using session credentials. The current frontend is same-origin and does not need it.

## Important operational and privacy notes

- Configure Neon backups/retention and monitor Render/Neon availability. The free Render service may sleep when idle; first requests can be delayed.
- Set a long, unique administrator password and keep `SECRET_KEY` stable between deploys so user sessions remain valid.
- This starter application is not a certification of HIPAA or other healthcare regulatory compliance. Before storing real patient/clinical data, arrange a security and privacy review, confirm applicable legal/regulatory requirements and vendor agreements, implement operational controls/auditing/backup retention, and test recovery and access policies.
- Do not add real credentials, database dumps, or patient data to this repository or its issue tracker.
