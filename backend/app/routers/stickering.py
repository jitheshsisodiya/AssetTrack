import time
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.auth.jwt import get_current_user
from app.database import get_db
from app.models.models import AppState, Class, Stickering, User
from app.schemas.schemas import AddStickeringRowRequest, UpdateRemarksRequest

router = APIRouter(prefix="/api/stickering", tags=["stickering"])


def _touch(db: Session, institution_id: int) -> None:
    key = f"lastModified_{institution_id}"
    ts  = str(int(time.time() * 1000))
    state = db.query(AppState).filter(AppState.key == key).first()
    if state:
        state.value = ts
    else:
        db.add(AppState(key=key, value=ts))
    db.commit()


def _branch_class_names(db: Session, user: User, branch_id_param: Optional[int]) -> Optional[list]:
    iid  = user.institution_id
    bids = [branch_id_param] if (user.role == "Admin" and branch_id_param) else (None if user.role == "Admin" else ([b.id for b in user.branches] or None))
    if bids is None:
        return None
    return [c.class_name for c in db.query(Class).filter(Class.institution_id == iid, Class.branch_id.in_(bids)).all()]


@router.get("")
def get_stickering(filterClass: Optional[str] = "", branch_id: Optional[int] = Query(None), db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    iid         = current_user.institution_id
    class_names = _branch_class_names(db, current_user, branch_id)
    q = db.query(Stickering).filter(Stickering.institution_id == iid)
    if filterClass:
        q = q.filter(Stickering.class_name == filterClass)
    elif class_names is not None:
        q = q.filter(Stickering.class_name.in_(class_names)) if class_names else q.filter(False)
    return [{"slNo": r.sl_no, "barCode": r.bar_code or "", "itemName": r.item_name or "", "className": r.class_name or "", "remarks": r.remarks or ""} for r in q.order_by(Stickering.sl_no).all()]


@router.post("/remarks")
def update_remarks(data: UpdateRemarksRequest, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    iid     = current_user.institution_id
    sl_ints = [int(s) for s in data.slNos if str(s).isdigit()]
    for r in db.query(Stickering).filter(Stickering.institution_id == iid, Stickering.sl_no.in_(sl_ints)).all():
        r.remarks = data.remark
    db.commit(); _touch(db, iid)
    return {"success": True}


@router.post("/add")
def add_row(entry: AddStickeringRowRequest, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    iid      = current_user.institution_id
    bc_upper = entry.barCode.upper()
    existing = db.query(Stickering).filter(Stickering.institution_id == iid, func.upper(Stickering.bar_code) == bc_upper).first()
    if existing:
        return {"duplicate": True}
    next_sl = (db.query(func.count(Stickering.id)).filter(Stickering.institution_id == iid).scalar() or 0) + 1
    db.add(Stickering(institution_id=iid, sl_no=next_sl, bar_code=bc_upper, item_name=entry.itemName, class_name=entry.className, remarks="New Added"))
    db.commit(); _touch(db, iid)
    return {"success": True}
