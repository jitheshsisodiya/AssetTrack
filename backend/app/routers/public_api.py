"""Read-only integration API (/api/v1, X-API-Key) and Admin key management (/api/keys)."""
import csv
import hashlib
import io
import json
import secrets
import time
from collections import defaultdict, deque
from datetime import date, datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from fastapi.security import APIKeyHeader
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.auth.jwt import get_current_user
from app.database import get_db
from app.models.models import ApiKey, Asset, AssetClassCount, Class, FarAudit, Institution, User
from app.routers import far, ops
from app.services import audit

router = APIRouter(prefix="/api/v1", tags=["public-api"])
keys_router = APIRouter(prefix="/api/keys", tags=["api-keys"])

KEY_PREFIX = "atk_"
MAX_ACTIVE_KEYS = 10
RATE_LIMIT_PER_MINUTE = 120
MAX_PAGE = 1000
_hits: dict = defaultdict(deque)
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False, description="Read-only key created by an Admin under Admin > API access.")


def _hash(key: str) -> str:
    return hashlib.sha256(key.encode()).hexdigest()


class ApiPrincipal:
    """Stands in for a user when reusing the app's own report functions; read-only by construction."""
    role = "Admin"

    def __init__(self, institution_id: int, name: str):
        self.institution_id = institution_id
        self.username = f"api:{name}"


def api_key_auth(key: Optional[str] = Depends(api_key_header), db: Session = Depends(get_db)) -> ApiPrincipal:
    bad = HTTPException(status_code=401, detail="Missing, invalid or revoked API key.", headers={"WWW-Authenticate": "ApiKey"})
    if not key or not key.startswith(KEY_PREFIX):
        raise bad
    row = db.query(ApiKey).filter(ApiKey.key_hash == _hash(key), ApiKey.revoked_at.is_(None)).first()
    if not row:
        raise bad
    inst = db.get(Institution, row.institution_id)
    if not inst or not inst.is_active:
        raise HTTPException(status_code=403, detail="This institution has been disabled.")
    now, q = time.monotonic(), _hits[row.id]
    while q and now - q[0] > 60:
        q.popleft()
    if len(q) >= RATE_LIMIT_PER_MINUTE:
        raise HTTPException(status_code=429, detail=f"Rate limit is {RATE_LIMIT_PER_MINUTE} requests per minute.", headers={"Retry-After": "60"})
    q.append(now)
    stamp = datetime.now(timezone.utc)
    if row.last_used_at is None or (stamp - row.last_used_at).total_seconds() > 60:
        row.last_used_at = stamp
        db.commit()
    return ApiPrincipal(row.institution_id, row.name)


# ── CSV output ───────────────────────────────────────────────────────────────

def _cell(v):
    if v is None:
        return ""
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (dict, list)):
        v = json.dumps(v, ensure_ascii=False)
    if isinstance(v, str) and v[:1] in ("=", "+", "-", "@", "\t", "\r"):
        return "'" + v  # stop spreadsheets from running text as a formula
    return v


def _csv(rows: list, filename: str) -> Response:
    buf = io.StringIO()
    if rows:
        cols = list(rows[0].keys())
        w = csv.writer(buf)
        w.writerow(cols)
        for r in rows:
            w.writerow([_cell(r.get(c)) for c in cols])
    return Response(buf.getvalue(), media_type="text/csv; charset=utf-8", headers={"Content-Disposition": f'attachment; filename="{filename}.csv"'})


def _page(rows: list, limit: int, offset: int, fmt: str, filename: str):
    part = rows[offset: offset + limit]
    if fmt == "csv":
        return _csv(part, filename)
    return dict(total=len(rows), limit=limit, offset=offset, items=part)


Limit = Query(200, ge=1, le=MAX_PAGE, description="Page size (max 1000)")
Offset = Query(0, ge=0)
Fmt = Query("json", pattern="^(json|csv)$", description="json (default) or csv for spreadsheets and BI tools")


# ── Read-only data endpoints ─────────────────────────────────────────────────

@router.get("/ping")
def ping(p: ApiPrincipal = Depends(api_key_auth), db: Session = Depends(get_db)):
    """Check that a key works. Returns the company the key belongs to."""
    return dict(ok=True, company=db.get(Institution, p.institution_id).name)


@router.get("/assets")
def assets(fy: Optional[int] = Query(None, description="Financial year start, e.g. 2025 for FY 2025-26"), limit: int = Limit, offset: int = Offset, format: str = Fmt,
           p: ApiPrincipal = Depends(api_key_auth), db: Session = Depends(get_db)):
    """The fixed asset register with depreciation figures for the financial year."""
    rows = far.list_assets(fy, db, p)["assets"]
    return _page(rows, limit, offset, format, "assets")


@router.get("/assets/{far_no}")
def asset(far_no: str, fy: Optional[int] = Query(None), p: ApiPrincipal = Depends(api_key_auth), db: Session = Depends(get_db)):
    for a in far.list_assets(fy, db, p)["assets"]:
        if a["far_no"] == far_no:
            return a
    raise HTTPException(status_code=404, detail="Asset not found.")


@router.get("/reports/movement")
def movement(fy: Optional[int] = Query(None), format: str = Fmt, p: ApiPrincipal = Depends(api_key_auth), db: Session = Depends(get_db)):
    """Schedule III movement of gross block, accumulated depreciation and net block by class."""
    m = far.movement(fy, db, p)
    if format == "csv":
        rows = [dict(section="PPE", **r) for r in m["ppe"]] + [dict(section="Intangible", **r) for r in m["intangible"]]
        return _csv(rows, "movement")
    return m


@router.get("/reports/verification")
def verification(as_on: Optional[date] = Query(None), format: str = Fmt, p: ApiPrincipal = Depends(api_key_auth), db: Session = Depends(get_db)):
    """Register against physical counts, with shortages valued at cost and net book value."""
    rep = far.verification_report(as_on, db, p)
    return _csv(rep["lines"], "verification") if format == "csv" else rep


@router.get("/counts")
def counts(limit: int = Limit, offset: int = Offset, format: str = Fmt, p: ApiPrincipal = Depends(api_key_auth), db: Session = Depends(get_db)):
    """Physical counts recorded per item and location."""
    q = (db.query(Asset.item_name, Asset.asset_code, Class.class_name, func.sum(AssetClassCount.count))
         .join(AssetClassCount, AssetClassCount.asset_id == Asset.id).join(Class, Class.id == AssetClassCount.class_id)
         .filter(Asset.institution_id == p.institution_id).group_by(Asset.item_name, Asset.asset_code, Class.class_name)
         .order_by(Class.class_name, Asset.item_name).all())
    rows = [dict(item=i, item_code=c, location=l, quantity=float(n or 0)) for i, c, l, n in q if n]
    return _page(rows, limit, offset, format, "counts")


@router.get("/maintenance")
def maintenance(limit: int = Limit, offset: int = Offset, format: str = Fmt, p: ApiPrincipal = Depends(api_key_auth), db: Session = Depends(get_db)):
    return _page(ops.list_tasks(None, db, p), limit, offset, format, "maintenance")


@router.get("/custody")
def custody(history: bool = Query(False, description="Include returned items"), limit: int = Limit, offset: int = Offset, format: str = Fmt,
            p: ApiPrincipal = Depends(api_key_auth), db: Session = Depends(get_db)):
    return _page(ops.custody(None, history, None, db, p), limit, offset, format, "custody")


@router.get("/warranties")
def warranties(days: int = Query(60, ge=1, le=730), format: str = Fmt, p: ApiPrincipal = Depends(api_key_auth), db: Session = Depends(get_db)):
    rows = ops.warranties(None, days, db, p)
    return _csv(rows, "warranties") if format == "csv" else rows


@router.get("/audit")
def audit_feed(after_id: int = Query(0, ge=0, description="Return entries newer than this id (oldest first), for incremental sync"),
               limit: int = Query(200, ge=1, le=MAX_PAGE), format: str = Fmt, p: ApiPrincipal = Depends(api_key_auth), db: Session = Depends(get_db)):
    """Append-only change feed. Poll with the highest id you have seen."""
    rows = (db.query(FarAudit).filter(FarAudit.institution_id == p.institution_id, FarAudit.id > after_id).order_by(FarAudit.id).limit(limit).all())
    out = [dict(id=r.id, at=r.created_at.isoformat() if r.created_at else "", username=r.username, action=r.action, far_no=r.far_no or "",
                description=r.description or "", details=json.loads(r.details) if r.details else None) for r in rows]
    return _csv(out, "audit") if format == "csv" else dict(items=out, last_id=out[-1]["id"] if out else after_id)


# ── Key management (Admin, signed-in) ────────────────────────────────────────

def _admin(user: User):
    if user.role != "Admin":
        raise HTTPException(status_code=403, detail="Admin only.")


def _key_out(k: ApiKey) -> dict:
    return dict(id=k.id, name=k.name, prefix=k.key_prefix, created_by=k.created_by, created_at=k.created_at.isoformat() if k.created_at else "",
                last_used_at=k.last_used_at.isoformat() if k.last_used_at else None, revoked_at=k.revoked_at.isoformat() if k.revoked_at else None,
                active=k.revoked_at is None)


class KeyIn(BaseModel):
    name: str


@keys_router.get("")
def list_keys(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    _admin(user)
    rows = db.query(ApiKey).filter(ApiKey.institution_id == user.institution_id).order_by(ApiKey.id.desc()).all()
    return [_key_out(k) for k in rows]


@keys_router.post("", status_code=201)
def create_key(d: KeyIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Creates a read-only key. The full key is returned once and cannot be shown again."""
    _admin(user)
    name = d.name.strip()
    if not name or len(name) > 100:
        raise HTTPException(status_code=400, detail="Give the key a name (up to 100 characters), for example the name of the system that will use it.")
    if db.query(ApiKey).filter(ApiKey.institution_id == user.institution_id, ApiKey.revoked_at.is_(None)).count() >= MAX_ACTIVE_KEYS:
        raise HTTPException(status_code=409, detail=f"At most {MAX_ACTIVE_KEYS} active keys. Revoke one first.")
    key = KEY_PREFIX + secrets.token_urlsafe(32)
    row = ApiKey(institution_id=user.institution_id, name=name, key_prefix=key[:12], key_hash=_hash(key), created_by=user.username)
    db.add(row)
    audit.record(db, user, "API key created", description=name, details={"prefix": row.key_prefix})
    db.commit(); db.refresh(row)
    return dict(_key_out(row), key=key)


@keys_router.delete("/{key_id}", status_code=204)
def revoke_key(key_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    _admin(user)
    k = db.query(ApiKey).filter(ApiKey.id == key_id, ApiKey.institution_id == user.institution_id).first()
    if not k:
        raise HTTPException(status_code=404, detail="Key not found.")
    if k.revoked_at is None:
        k.revoked_at = datetime.now(timezone.utc)
        audit.record(db, user, "API key revoked", description=k.name, details={"prefix": k.key_prefix})
        db.commit()
