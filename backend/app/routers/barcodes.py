import time
from typing import List, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.auth.jwt import get_current_user
from app.database import get_db
from app.models.models import AppState, Asset, Barcode, Class, Stickering, User
from app.schemas.schemas import BarcodeItem, CancelBarCodesRequest

router = APIRouter(prefix="/api/barcodes", tags=["barcodes"])


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
def get_barcodes(branch_id: Optional[int] = Query(None), db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    iid         = current_user.institution_id
    class_names = _branch_class_names(db, current_user, branch_id)
    q = db.query(Barcode).filter(Barcode.institution_id == iid).order_by(Barcode.sl_no)
    if class_names is not None:
        q = q.filter(Barcode.class_name.in_(class_names)) if class_names else q.filter(False)
    return [{"slNo": r.sl_no, "barCode": r.code_text or "", "itemName": r.item_name or "", "className": r.class_name or "", "remarks": r.remarks or ""} for r in q.all()]


@router.post("/save")
def save_barcodes(barcodes: List[BarcodeItem], db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    iid      = current_user.institution_id
    item_map = {a.asset_code: a.item_name for a in db.query(Asset).filter(Asset.institution_id == iid).all()}
    db.query(Barcode).filter(Barcode.institution_id == iid).delete()
    db.flush()
    for i, bc in enumerate(barcodes):
        parts      = bc.codeText.split("/")
        asset_code = parts[1] if len(parts) >= 2 else ""
        db.add(Barcode(institution_id=iid, sl_no=i+1, code_text=bc.codeText, item_name=item_map.get(asset_code, ""), class_name=bc.className, remarks=""))
    db.commit(); _touch(db, iid)
    return {"success": True, "count": len(barcodes)}


@router.post("/cancel")
def cancel_barcodes(data: CancelBarCodesRequest, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    iid       = current_user.institution_id
    sl_ints   = [int(s) for s in data.slNos if str(s).isdigit()]
    to_cancel = db.query(Barcode).filter(Barcode.institution_id == iid, Barcode.sl_no.in_(sl_ints)).all()
    if not to_cancel:
        return {"success": True, "count": 0}
    next_sl = db.query(func.count(Stickering.id)).filter(Stickering.institution_id == iid).scalar() or 0
    for bc in to_cancel:
        bc_upper = (bc.code_text or "").upper()
        existing = db.query(Stickering).filter(Stickering.institution_id == iid, func.upper(Stickering.bar_code) == bc_upper).first()
        if existing:
            existing.remarks = "Cancelled"
        else:
            next_sl += 1
            db.add(Stickering(institution_id=iid, sl_no=next_sl, bar_code=bc_upper, item_name=bc.item_name or "", class_name=bc.class_name or "", remarks="Cancelled"))
    db.commit(); _touch(db, iid)
    return {"success": True, "count": len(to_cancel)}
