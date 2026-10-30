# Asset Management System

A school asset physical-verification tool. Staff log in, record asset counts per classroom, and lock classes once done. Includes barcode/stickering workflow and a Super Admin dashboard.

---

## Prerequisites

- Python 3.11+
- PostgreSQL (running locally or on a server)
- A modern web browser

---

## Setup & Run

### 1. Clone the repo

```bash
git clone https://github.com/jitheshsisodiya/AssetTrack.git
cd AssetTrack
```

### 2. Configure environment

```bash
cd backend
copy .env.example .env
```

Open `.env` and fill in your values:

```
DATABASE_URL=postgresql://postgres:yourpassword@localhost:5432/asset_management
SECRET_KEY=any-long-random-string-at-least-32-characters
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Create database tables

```bash
python -m alembic upgrade head
```

### 5. Create the Super Admin user

```bash
python create_superadmin.py
```

You are asked for a username and a password of at least 8 characters. Run it again with `--reset` to change the password later.

### 6. (Optional) Import existing asset data

If you have the Excel data file:

```bash
python migrate.py
```

### 7. Start the backend server

```bash
python -m uvicorn app.main:app --reload --port 8001
```

### 8. Open the app

With the backend running on port 8001, open `http://127.0.0.1:8001/` in your browser. The backend serves the page itself, so nothing else needs configuring. (Opening `index.html` as a file also works locally.)

---

## Deploy on Railway

1. Sign in at [railway.com](https://railway.com) with GitHub, then **New Project → Deploy from GitHub repo** and pick this repository. Railway builds it from the `Dockerfile`.
2. In the same project click **+ New → Database → PostgreSQL**.
3. Open the app service → **Variables** and add:

   | Variable | Value |
   |---|---|
   | `DATABASE_URL` | `${{Postgres.DATABASE_URL}}` (reference to the database service) |
   | `SECRET_KEY` | a long random string, made with `python -c "import secrets;print(secrets.token_urlsafe(48))"` |
   | `SUPERADMIN_USERNAME` | the Super Admin username you want |
   | `SUPERADMIN_PASSWORD` | a strong password (at least 8 characters); used once to create the account |
   | `UPLOAD_DIR` | `/data/uploads` (only if you add a volume, see below) |

4. Open **Settings → Networking → Generate Domain**. Railway gives you an `https://…up.railway.app` address; open it.
5. Optional: **Settings → Volumes**, add a volume mounted at `/data`. Without one, uploaded photos and documents are lost each time the service is redeployed.

On every start the app applies pending database migrations and, if `SUPERADMIN_PASSWORD` is set and no such Super Admin exists, creates it. After the first successful start you can delete `SUPERADMIN_PASSWORD` from the variables.

---

## Logins

There are no default logins. The Super Admin is created in step 5, and company admins register themselves on the **New Institution** tab of the login screen.

---

## Project Structure

```
index.html                  ← entire frontend (HTML + CSS + JS)
backend/
  app/
    routers/                ← API endpoints (auth, assets, classes, barcodes…)
    models/models.py        ← database models
    auth/jwt.py             ← authentication
  migrations/               ← Alembic database migrations
  requirements.txt
  .env.example              ← copy to .env and fill in credentials
```
