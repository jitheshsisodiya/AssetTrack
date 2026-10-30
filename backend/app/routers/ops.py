from datetime import date, datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session, joinedload

from app.auth.jwt import get_current_user
from app.database import get_db
from app.models.models import CustodyLog, FixedAsset, MaintenanceLog, MaintenanceTask, User
from app.services import audit
from app.services.maintenance import (
    DUE_SOON_DAYS, WARRANTY_SOON_DAYS, available_quantity, next_due_after, return_status, task_status, warranty_status,
)

router = APIRouter(prefix="/api/ops", tags=["maintenance-custody"])


def _admin(user: User):
    if user.role != "Admin":
        raise HTTPException(status_code=403, detail="Admin only.")


def _f(v) -> float:
    return float(v) if v is not None else 0.0


def _iso(d) -> Optional[str]:
    return d.isoformat() if d else None


def _asset(db: Session, iid: int, asset_id: int) -> FixedAsset:
    a = db.query(FixedAsset).filter(FixedAsset.id == asset_id, FixedAsset.institution_id == iid).first()
    if not a:
        raise HTTPException(status_code=400, detail="Asset not found.")
    return a


def _is_disposed(a: FixedAsset, today: date) -> bool:
    return bool(a.disposal_date and a.disposal_date <= today)


# ── Maintenance ──────────────────────────────────────────────────────────────

class TaskIn(BaseModel):
    fixed_asset_id: int
    title: str
    frequency_days: Optional[int] = None
    next_due: date
    notes: Optional[str] = None


def _task_out(t: MaintenanceTask, today: date) -> dict:
    a = t.fixed_asset
    return dict(id=t.id, fixed_asset_id=t.fixed_asset_id, far_no=a.far_no, asset=a.description, title=t.title,
                frequency_days=t.frequency_days, next_due=_iso(t.next_due), last_done=_iso(t.last_done), notes=t.notes or "",
                status=task_status(t.next_due, today),
                days_to_due=(t.next_due - today).days if t.next_due else None)


def _check_task(d: TaskIn):
    if not d.title.strip():
        raise HTTPException(status_code=400, detail="Task title is required.")
    if d.frequency_days is not None and d.frequency_days <= 0:
        raise HTTPException(status_code=400, detail="Repeat interval must be at least 1 day (leave blank for a one-off task).")


@router.get("/maintenance")
def list_tasks(today: Optional[date] = Query(None), db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    _admin(user)
    today = today or date.today()
    rows = (db.query(MaintenanceTask).options(joinedload(MaintenanceTask.fixed_asset))
            .filter(MaintenanceTask.institution_id == user.institution_id).all())
    out = [_task_out(t, today) for t in rows]
    out.sort(key=lambda r: (r["next_due"] is None, r["next_due"] or ""))
    return out


@router.post("/maintenance", status_code=201)
def create_task(d: TaskIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    _admin(user)
    _check_task(d)
    a = _asset(db, user.institution_id, d.fixed_asset_id)
    t = MaintenanceTask(institution_id=user.institution_id, fixed_asset_id=a.id, title=d.title.strip(),
                        frequency_days=d.frequency_days, next_due=d.next_due, notes=d.notes)
    db.add(t); db.commit(); db.refresh(t)
    return _task_out(t, date.today())


@router.put("/maintenance/{task_id}")
def update_task(task_id: int, d: TaskIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    _admin(user)
    _check_task(d)
    t = db.query(MaintenanceTask).filter(MaintenanceTask.id == task_id, MaintenanceTask.institution_id == user.institution_id).first()
    if not t:
        raise HTTPException(status_code=404, detail="Task not found.")
    a = _asset(db, user.institution_id, d.fixed_asset_id)
    t.fixed_asset_id, t.title, t.frequency_days, t.next_due, t.notes = a.id, d.title.strip(), d.frequency_days, d.next_due, d.notes
    db.commit()
    return _task_out(t, date.today())


@router.delete("/maintenance/{task_id}", status_code=204)
def delete_task(task_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    _admin(user)
    t = db.query(MaintenanceTask).filter(MaintenanceTask.id == task_id, MaintenanceTask.institution_id == user.institution_id).first()
    if not t:
        raise HTTPException(status_code=404, detail="Task not found.")
    db.delete(t); db.commit()


class DoneIn(BaseModel):
    done_on: date
    done_by: str
    cost: float = 0
    notes: Optional[str] = None


@router.post("/maintenance/{task_id}/complete")
def complete_task(task_id: int, d: DoneIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    _admin(user)
    if not d.done_by.strip():
        raise HTTPException(status_code=400, detail="Name of the person who did the work is required.")
    if d.cost < 0:
        raise HTTPException(status_code=400, detail="Cost cannot be negative.")
    t = db.query(MaintenanceTask).filter(MaintenanceTask.id == task_id, MaintenanceTask.institution_id == user.institution_id).first()
    if not t:
        raise HTTPException(status_code=404, detail="Task not found.")
    if t.next_due is None:
        raise HTTPException(status_code=409, detail="This task is already completed.")
    if d.done_on > date.today():
        raise HTTPException(status_code=400, detail="Completion date cannot be in the future.")
    db.add(MaintenanceLog(institution_id=user.institution_id, task_id=t.id, done_on=d.done_on, done_by=d.done_by.strip(),
                          cost=d.cost, notes=d.notes, recorded_by=user.username))
    t.last_done = d.done_on
    t.next_due = next_due_after(d.done_on, t.frequency_days)
    audit.record(db, user, "Maintenance done", t.fixed_asset, {"task": t.title, "done_on": d.done_on, "done_by": d.done_by.strip(), "cost": d.cost})
    db.commit()
    return _task_out(t, date.today())


@router.get("/maintenance/{task_id}/log")
def task_log(task_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    _admin(user)
    t = db.query(MaintenanceTask).filter(MaintenanceTask.id == task_id, MaintenanceTask.institution_id == user.institution_id).first()
    if not t:
        raise HTTPException(status_code=404, detail="Task not found.")
    rows = db.query(MaintenanceLog).filter(MaintenanceLog.task_id == t.id).order_by(MaintenanceLog.done_on.desc(), MaintenanceLog.id.desc()).all()
    return [dict(id=r.id, done_on=_iso(r.done_on), done_by=r.done_by, cost=_f(r.cost), notes=r.notes or "", recorded_by=r.recorded_by or "") for r in rows]


# ── Warranty ─────────────────────────────────────────────────────────────────

@router.get("/warranties")
def warranties(today: Optional[date] = Query(None), days: int = Query(WARRANTY_SOON_DAYS, ge=1, le=730),
               db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """In-force assets whose warranty has expired or ends within `days`."""
    _admin(user)
    today = today or date.today()
    rows = db.query(FixedAsset).filter(FixedAsset.institution_id == user.institution_id, FixedAsset.warranty_expiry.isnot(None)).all()
    out = []
    for a in rows:
        if _is_disposed(a, today):
            continue
        st = warranty_status(a.warranty_expiry, today, days)
        if st in ("Expired", "Expiring soon"):
            out.append(dict(id=a.id, far_no=a.far_no, description=a.description, vendor=a.vendor or "", warranty_expiry=_iso(a.warranty_expiry),
                            status=st, days_left=(a.warranty_expiry - today).days))
    out.sort(key=lambda r: r["warranty_expiry"])
    return out


# ── Custody (check-out / check-in) ───────────────────────────────────────────

class CheckoutIn(BaseModel):
    fixed_asset_id: int
    quantity: float = 1
    issued_to: str
    due_back: Optional[date] = None
    condition_out: Optional[str] = None
    notes: Optional[str] = None


class CheckinIn(BaseModel):
    condition_in: Optional[str] = None
    notes: Optional[str] = None


def _open_qty(db: Session, asset_id: int) -> float:
    return _f(db.query(func.coalesce(func.sum(CustodyLog.quantity), 0)).filter(CustodyLog.fixed_asset_id == asset_id, CustodyLog.returned_at.is_(None)).scalar())


def _custody_out(c: CustodyLog, today: date) -> dict:
    a = c.fixed_asset
    return dict(id=c.id, fixed_asset_id=c.fixed_asset_id, far_no=a.far_no, asset=a.description, quantity=_f(c.quantity), issued_to=c.issued_to,
                issued_by=c.issued_by, issued_at=c.issued_at.isoformat() if c.issued_at else "", due_back=_iso(c.due_back),
                condition_out=c.condition_out or "", returned_at=c.returned_at.isoformat() if c.returned_at else None,
                returned_to=c.returned_to or "", condition_in=c.condition_in or "", notes=c.notes or "",
                status=return_status(c.due_back, c.returned_at is not None, today))


@router.get("/custody")
def custody(today: Optional[date] = Query(None), history: bool = Query(False), asset_id: Optional[int] = Query(None),
            db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    _admin(user)
    today = today or date.today()
    q = (db.query(CustodyLog).options(joinedload(CustodyLog.fixed_asset)).filter(CustodyLog.institution_id == user.institution_id))
    if asset_id:
        q = q.filter(CustodyLog.fixed_asset_id == asset_id)
    if not history:
        q = q.filter(CustodyLog.returned_at.is_(None))
    rows = q.order_by(CustodyLog.id.desc()).limit(500).all()
    return [_custody_out(c, today) for c in rows]


@router.post("/custody/checkout", status_code=201)
def checkout(d: CheckoutIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    _admin(user)
    today = date.today()
    if not d.issued_to.strip():
        raise HTTPException(status_code=400, detail="Name of the person it is issued to is required.")
    if d.quantity <= 0:
        raise HTTPException(status_code=400, detail="Quantity must be more than zero.")
    if d.due_back and d.due_back < today:
        raise HTTPException(status_code=400, detail="Due-back date cannot be in the past.")
    a = _asset(db, user.institution_id, d.fixed_asset_id)
    if _is_disposed(a, today):
        raise HTTPException(status_code=400, detail="This asset has been disposed and cannot be checked out.")
    if a.category.is_immovable:
        raise HTTPException(status_code=400, detail="Land and buildings cannot be checked out.")
    free = available_quantity(_f(a.quantity), _open_qty(db, a.id))
    if d.quantity > free:
        raise HTTPException(status_code=409, detail=f"Only {free:g} of {a.description} available to issue.")
    c = CustodyLog(institution_id=user.institution_id, fixed_asset_id=a.id, quantity=d.quantity, issued_to=d.issued_to.strip(),
                   issued_by=user.username, due_back=d.due_back, condition_out=d.condition_out, notes=d.notes)
    db.add(c); db.flush()
    audit.record(db, user, "Checked out", a, {"to": c.issued_to, "quantity": d.quantity, "due_back": d.due_back, "condition": d.condition_out})
    db.commit(); db.refresh(c)
    return _custody_out(c, today)


@router.post("/custody/{cid}/checkin")
def checkin(cid: int, d: CheckinIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    _admin(user)
    c = db.query(CustodyLog).filter(CustodyLog.id == cid, CustodyLog.institution_id == user.institution_id).first()
    if not c:
        raise HTTPException(status_code=404, detail="Record not found.")
    if c.returned_at is not None:
        raise HTTPException(status_code=409, detail="Already checked in.")
    c.returned_at = datetime.now(timezone.utc)
    c.returned_to = user.username
    c.condition_in = d.condition_in
    audit.record(db, user, "Checked in", c.fixed_asset, {"from": c.issued_to, "quantity": _f(c.quantity), "condition": d.condition_in})
    if d.notes:
        c.notes = ((c.notes + "\n") if c.notes else "") + d.notes
    db.commit()
    return _custody_out(c, date.today())


# ── Summary for the reminder badges ──────────────────────────────────────────

@router.get("/summary")
def summary(today: Optional[date] = Query(None), db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    _admin(user)
    today = today or date.today()
    iid = user.institution_id
    tasks = db.query(MaintenanceTask).filter(MaintenanceTask.institution_id == iid, MaintenanceTask.next_due.isnot(None)).all()
    statuses = [task_status(t.next_due, today) for t in tasks]
    warranty = [a for a in db.query(FixedAsset).filter(FixedAsset.institution_id == iid, FixedAsset.warranty_expiry.isnot(None)).all()
                if not _is_disposed(a, today) and warranty_status(a.warranty_expiry, today) == "Expiring soon"]
    out = db.query(CustodyLog).filter(CustodyLog.institution_id == iid, CustodyLog.returned_at.is_(None)).all()
    return dict(tasks_overdue=statuses.count("Overdue"), tasks_due_soon=statuses.count("Due soon"), warranties_expiring=len(warranty),
                custody_out=len(out), custody_overdue=sum(1 for c in out if c.due_back and c.due_back < today),
                due_soon_days=DUE_SOON_DAYS, warranty_soon_days=WARRANTY_SOON_DAYS)
