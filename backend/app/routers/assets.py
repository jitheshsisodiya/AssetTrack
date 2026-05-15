import time
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session, joinedload

from pydantic import BaseModel as _BM

from app.auth.jwt import get_current_user
from app.database import get_db
from app.models.models import AppState, Asset, AssetClassCount, Class, EditLog, User
from app.schemas.schemas import SubmitEntryRequest


class _AssetIn(_BM):
    item_name:  str
    asset_code: str
    sl_no:      Optional[int] = None


class _AssetBulkItem(_BM):
    item_name:  str
    asset_code: str
    sl_no:      Optional[int] = None

router = APIRouter(prefix="/api", tags=["assets"])


def _touch(db: Session, institution_id: int) -> None:
    key = f"lastModified_{institution_id}"
    ts = str(int(time.time() * 1000))
    state = db.query(AppState).filter(AppState.key == key).first()
    if state:
        state.value = ts
    else:
        db.add(AppState(key=key, value=ts))
    db.commit()


def _effective_branch_ids(user: User, branch_id_param: Optional[int]) -> Optional[list]:
    if user.role == "Admin":
        return [branch_id_param] if branch_id_param else None
    ids = [b.id for b in user.branches]
    return ids if ids else None


@router.get("/data")
def get_data(branch_id: Optional[int] = Query(None), db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    iid  = current_user.institution_id
    bids = _effective_branch_ids(current_user, branch_id)
    q = db.query(Class).filter(Class.institution_id == iid).order_by(Class.display_order, Class.class_name)
    if bids is not None:
        q = q.filter(Class.branch_id.in_(bids))
    classes = q.all()
    assets  = db.query(Asset).filter(Asset.institution_id == iid).options(joinedload(Asset.counts)).order_by(Asset.sl_no).all()
    class_headers   = [c.class_name for c in classes]
    class_id_to_idx = {c.id: i for i, c in enumerate(classes)}
    rows = []
    for asset in assets:
        counts = [0] * len(classes)
        for acc in asset.counts:
            idx = class_id_to_idx.get(acc.class_id)
            if idx is not None:
                counts[idx] = float(acc.count) if acc.count is not None else 0
        rows.append({"slNo": asset.sl_no, "itemName": asset.item_name, "assetCode": asset.asset_code, "classCounts": counts})
    return {"classHeaders": class_headers, "rows": rows}


@router.post("/submit")
def submit_entry(data: SubmitEntryRequest, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    iid = current_user.institution_id
    cls = db.query(Class).filter(Class.class_name == data.className, Class.institution_id == iid).first()
    if not cls:
        raise HTTPException(status_code=404, detail=f'"{data.className}" not found.')
    user_branch_ids = [b.id for b in current_user.branches]
    if current_user.role != "Admin" and user_branch_ids and cls.branch_id not in user_branch_ids:
        raise HTTPException(status_code=403, detail="Cannot submit to a class outside your branch.")
    asset = db.query(Asset).filter(Asset.asset_code == data.assetCode, Asset.institution_id == iid).first()
    if not asset:
        raise HTTPException(status_code=404, detail=f'Asset code "{data.assetCode}" not found.')
    acc = db.query(AssetClassCount).filter(AssetClassCount.asset_id == asset.id, AssetClassCount.class_id == cls.id).first()
    if acc:
        acc.count = float(acc.count or 0) + data.qty
    else:
        db.add(AssetClassCount(asset_id=asset.id, class_id=cls.id, count=data.qty))
    db.add(EditLog(institution_id=iid, username=data.username, item_name=data.itemName, asset_code=data.assetCode, class_name=data.className, qty=data.qty))
    db.commit(); _touch(db, iid)
    return {"success": True, "message": "Entry saved successfully."}


@router.get("/log")
def get_log(branch_id: Optional[int] = Query(None), db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    iid  = current_user.institution_id
    bids = _effective_branch_ids(current_user, branch_id)
    q = db.query(EditLog).filter(EditLog.institution_id == iid).order_by(EditLog.id)
    if bids is not None:
        class_names = [c.class_name for c in db.query(Class).filter(Class.institution_id == iid, Class.branch_id.in_(bids)).all()]
        if class_names:
            q = q.filter(EditLog.class_name.in_(class_names))
        else:
            return []
    return [
        {"User Name": r.username, "Item Name": r.item_name, "Asset Classification Code": r.asset_code,
         "Class Name": r.class_name, "Qty": float(r.qty) if r.qty is not None else 0,
         "Timestamp": r.created_at.strftime("%d/%m/%Y, %I:%M:%S %p") if r.created_at else ""}
        for r in q.all()
    ]


@router.get("/last-modified")
def get_last_modified(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    key   = f"lastModified_{current_user.institution_id}"
    state = db.query(AppState).filter(AppState.key == key).first()
    return {"ts": state.value if state else "0"}


@router.get("/assets/list")
def list_assets(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    if current_user.role != "Admin":
        raise HTTPException(status_code=403, detail="Admin only.")
    rows = db.query(Asset).filter(Asset.institution_id == current_user.institution_id).order_by(Asset.sl_no).all()
    return [{"id": a.id, "slNo": a.sl_no, "itemName": a.item_name, "assetCode": a.asset_code} for a in rows]


@router.post("/assets")
def create_asset(data: _AssetIn, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    if current_user.role != "Admin":
        raise HTTPException(status_code=403, detail="Admin only.")
    iid = current_user.institution_id
    if db.query(Asset).filter(Asset.institution_id == iid, Asset.asset_code == data.asset_code.strip()).first():
        raise HTTPException(status_code=400, detail="Asset code already exists.")
    max_sl = (db.query(Asset).filter(Asset.institution_id == iid).count() or 0) + 1
    asset  = Asset(institution_id=iid, item_name=data.item_name.strip(), asset_code=data.asset_code.strip(), sl_no=data.sl_no or max_sl)
    db.add(asset); db.commit(); db.refresh(asset); _touch(db, iid)
    return {"id": asset.id, "slNo": asset.sl_no, "itemName": asset.item_name, "assetCode": asset.asset_code}


@router.put("/assets/{asset_id}")
def update_asset(asset_id: int, data: _AssetIn, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    if current_user.role != "Admin":
        raise HTTPException(status_code=403, detail="Admin only.")
    iid   = current_user.institution_id
    asset = db.query(Asset).filter(Asset.id == asset_id, Asset.institution_id == iid).first()
    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found.")
    if db.query(Asset).filter(Asset.institution_id == iid, Asset.asset_code == data.asset_code.strip(), Asset.id != asset_id).first():
        raise HTTPException(status_code=400, detail="Asset code already exists.")
    asset.item_name = data.item_name.strip(); asset.asset_code = data.asset_code.strip()
    if data.sl_no is not None:
        asset.sl_no = data.sl_no
    db.commit(); _touch(db, iid)
    return {"success": True}


@router.delete("/assets/{asset_id}")
def delete_asset(asset_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    if current_user.role != "Admin":
        raise HTTPException(status_code=403, detail="Admin only.")
    iid   = current_user.institution_id
    asset = db.query(Asset).filter(Asset.id == asset_id, Asset.institution_id == iid).first()
    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found.")
    db.delete(asset); db.commit(); _touch(db, iid)
    return {"success": True}


@router.post("/assets/bulk")
def bulk_create_assets(items: list[_AssetBulkItem], db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    if current_user.role != "Admin":
        raise HTTPException(status_code=403, detail="Admin only.")
    iid = current_user.institution_id
    created = skipped = 0
    next_sl = (db.query(Asset).filter(Asset.institution_id == iid).count() or 0) + 1
    for item in items:
        name = item.item_name.strip(); code = item.asset_code.strip()
        if not name or not code or db.query(Asset).filter(Asset.institution_id == iid, Asset.asset_code == code).first():
            skipped += 1; continue
        db.add(Asset(institution_id=iid, item_name=name, asset_code=code, sl_no=item.sl_no or next_sl))
        next_sl += 1; created += 1
    db.commit()
    if created:
        _touch(db, iid)
    return {"created": created, "skipped": skipped}
