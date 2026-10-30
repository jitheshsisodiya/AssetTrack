import hashlib
import hmac
import os
import time

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse

from app.config import settings
from app.routers import assets, auth, barcodes, branches, classes, export, far, ops, print as print_router, stickering, users

app = FastAPI(title="Asset Management API", version="2.0.0")

# ── CORS ──────────────────────────────────────────────────────────────────────
_origins = [o.strip() for o in settings.CORS_ORIGINS.split(",")]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Routers ───────────────────────────────────────────────────────────────────
app.include_router(auth.router)
app.include_router(assets.router)
app.include_router(classes.router)
app.include_router(barcodes.router)
app.include_router(stickering.router)
app.include_router(branches.router)
app.include_router(users.router)
app.include_router(export.router)
app.include_router(print_router.router)
app.include_router(far.router)
app.include_router(ops.router)

# ── Serve HTML ────────────────────────────────────────────────────────────────
_HTML_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "index.html")


@app.get("/app")
def serve_app():
    path = os.path.abspath(_HTML_PATH)
    if not os.path.exists(path):
        return JSONResponse(status_code=404, content={"detail": "index.html not found"})
    return FileResponse(path, media_type="text/html")


# ── Server fingerprint (lightweight anti-copy check) ─────────────────────────
@app.get("/api/server-check")
def server_check(request: Request):
    ts = str(int(time.time() // 60))   # changes every minute — prevents replay beyond 1 min
    sig = hmac.new(
        settings.SECRET_KEY.encode(),
        f"server-check:{ts}".encode(),
        hashlib.sha256,
    ).hexdigest()
    return {"ok": True, "sig": sig, "ts": ts}


@app.get("/")
def root():
    return {"message": "Asset Management API is running. Open /app to use the application."}
