import time
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.auth.jwt import get_current_user
from app.database import get_db
from app.models.models import AppState, Branch, Class, User
from app.schemas.schemas import ClassBulkItem, LockClassRequest, UnlockClassRequest

from pydantic import BaseModel as _BM

class _CreateClassReq(_BM):
    className: str
    branchId: Optional[int] = None

router = APIRouter(prefix="/api/classes", tags=["classes"])


def _touch(db: Session, institution_id: int) -> None:
    key = f"lastModified_{institution_id}"
    ts = str(int(time.time() * 1000))
    state = db.query(AppState).filter(AppState.key == key).first()
    if state:
        state.value = ts
    else:
        db.add(AppState(key=key, value=ts))
    db.commit()


def _get_class_or_404(db: Session, class_name: str, institution_id: int) -> Class:
    cls = db.query(Class).filter(Class.class_name == class_name, Class.institution_id == institution_id).first()
    if not cls:
        raise HTTPException(status_code=404, detail="Class not found.")
    return cls


def _effective_branch_ids(user: User, branch_id_param: Optional[int]) -> Optional[list]:
    if user.role == "Admin":
        return [branch_id_param] if branch_id_param else None
    ids = [b.id for b in user.branches]
    return ids if ids else None


@router.get("")
def get_classes(branch_id: Optional[int] = Query(None), db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    iid = current_user.institution_id
    bids = _effective_branch_ids(current_user, branch_id)
    q = db.query(Class).filter(Class.institution_id == iid).order_by(Class.display_order, Class.class_name)
    if bids is not None:
        q = q.filter(Class.branch_id.in_(bids))
    rows = q.all()
    branch_map = {b.id: b.name for b in db.query(Branch).filter(Branch.institution_id == iid).all()}
    return [
        {
            "className":        r.class_name,
            "assignedTo":       r.assigned_to or "",
            "locked":           bool(r.locked),
            "lockedBy":         r.locked_by or "",
            "timestamp":        r.lock_timestamp or "",
            "stickerLocked":    bool(r.sticker_locked),
            "stickerLockedBy":  r.sticker_locked_by or "",
            "stickerTimestamp": r.sticker_timestamp or "",
            "branchId":         r.branch_id,
            "branchName":       branch_map.get(r.branch_id, "") if r.branch_id else "",
        }
        for r in rows
    ]


@router.post("/bulk")
def bulk_create_classes(items: list[ClassBulkItem], db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    if current_user.role != "Admin":
        raise HTTPException(status_code=403, detail="Admin only.")
    iid = current_user.institution_id
    branch_map = {b.code.upper(): b.id for b in db.query(Branch).filter(Branch.institution_id == iid).all()}
    created = skipped = 0
    max_order = db.query(Class).filter(Class.institution_id == iid).count()
    for item in items:
        name = item.class_name.strip()
        if not name or db.query(Class).filter(Class.institution_id == iid, Class.class_name == name).first():
            skipped += 1; continue
        branch_id = branch_map.get(item.branch_code.strip().upper()) if item.branch_code else None
        db.add(Class(institution_id=iid, class_name=name, branch_id=branch_id, display_order=max_order))
        max_order += 1; created += 1
    db.commit()
    return {"created": created, "skipped": skipped}


@router.post("/create")
def create_class(data: _CreateClassReq, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    if current_user.role != "Admin":
        raise HTTPException(status_code=403, detail="Admin only.")
    iid = current_user.institution_id
    class_name = data.className.strip()
    if not class_name:
        raise HTTPException(status_code=400, detail="className is required.")
    if db.query(Class).filter(Class.institution_id == iid, Class.class_name == class_name).first():
        raise HTTPException(status_code=400, detail="Class already exists.")
    if data.branchId and not db.query(Branch).filter(Branch.id == data.branchId, Branch.institution_id == iid).first():
        raise HTTPException(status_code=400, detail="Branch not found.")
    max_order = db.query(Class).filter(Class.institution_id == iid).count()
    db.add(Class(institution_id=iid, class_name=class_name, branch_id=data.branchId, display_order=max_order))
    db.commit()
    _touch(db, iid)
    return {"success": True, "className": class_name}


@router.post("/assign")
def assign_class(data: dict, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    if current_user.role != "Admin":
        raise HTTPException(status_code=403, detail="Admin only.")
    cls = _get_class_or_404(db, (data.get("className") or "").strip(), current_user.institution_id)
    cls.assigned_to = (data.get("assignedTo") or "").strip() or None
    db.commit()
    _touch(db, current_user.institution_id)
    return {"success": True}


@router.delete("/delete")
def delete_class(className: str = Query(...), db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    if current_user.role != "Admin":
        raise HTTPException(status_code=403, detail="Admin only.")
    cls = _get_class_or_404(db, className.strip(), current_user.institution_id)
    db.delete(cls)
    db.commit()
    _touch(db, current_user.institution_id)
    return {"success": True}


@router.post("/lock")
def lock_class(data: LockClassRequest, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    cls = _get_class_or_404(db, data.className, current_user.institution_id)
    cls.locked = True; cls.locked_by = data.lockedBy; cls.lock_timestamp = data.timestamp
    db.commit(); _touch(db, current_user.institution_id)
    return {"success": True}


@router.post("/unlock")
def unlock_class(data: UnlockClassRequest, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    cls = _get_class_or_404(db, data.className, current_user.institution_id)
    cls.locked = False; cls.locked_by = None; cls.lock_timestamp = None
    db.commit(); _touch(db, current_user.institution_id)
    return {"success": True}


@router.post("/lock-sticker")
def lock_sticker(data: LockClassRequest, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    cls = _get_class_or_404(db, data.className, current_user.institution_id)
    cls.sticker_locked = True; cls.sticker_locked_by = data.lockedBy; cls.sticker_timestamp = data.timestamp
    db.commit(); _touch(db, current_user.institution_id)
    return {"success": True}


@router.post("/unlock-sticker")
def unlock_sticker(data: UnlockClassRequest, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    cls = _get_class_or_404(db, data.className, current_user.institution_id)
    cls.sticker_locked = False; cls.sticker_locked_by = None; cls.sticker_timestamp = None
    db.commit(); _touch(db, current_user.institution_id)
    return {"success": True}
