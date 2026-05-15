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
git clone https://github.com/jitheshsisodiya/AssetManagment_V1.git
cd AssetManagment_V1
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

This creates username `Jithesh` with password `1234`.

### 6. (Optional) Import existing asset data

If you have the Excel data file:

```bash
python migrate.py
```

### 7. Start the backend server

```bash
python -m uvicorn app.main:app --reload --port 8000
```

### 8. Open the frontend

Open `index.html` directly in your browser (double-click the file).

> **Note:** The `API_URL` in `index.html` (line ~589) is set to `http://localhost:8000`.  
> Change this to your server's IP/domain if deploying on a remote machine.

---

## Default Logins

| Username | Password | Role |
|----------|----------|------|
| Jithesh  | 1234     | Super Admin |

Institution admins are created via the **New Institution** tab on the login screen.

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
