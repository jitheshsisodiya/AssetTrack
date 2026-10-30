import base64
import json
import os
import re
import uuid
from collections import defaultdict
from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session, joinedload

from app.auth.jwt import get_current_user
from app.database import get_db
from app.models.models import (
    Asset, AssetCategory, AssetClassCount, AssetFile, Class, CustodyLog, FarAudit, FixedAsset, Revaluation, User, VerificationRun,
)
from app.config import UPLOAD_ROOT
from app.services import audit
from app.services.depreciation import METHODS, DepAsset, fy_bounds, fy_figures, fy_label, fy_of, nbv_as_on

router = APIRouter(prefix="/api/far", tags=["fixed-assets"])

# Schedule II (Part C) useful lives as commonly applied — editable per company, confirm with your accountant.
# (name, Schedule III class, life in years or None, intangible, immovable)
DEFAULT_CATEGORIES = [
    ("Freehold Land",                 "Land",                       0,    False, True),
    ("Buildings - RCC frame",         "Buildings",                  60,   False, True),
    ("Buildings - other than RCC",    "Buildings",                  30,   False, True),
    ("Plant and Machinery",           "Plant and Equipment",        15,   False, False),
    ("Electrical Installations",      "Plant and Equipment",        10,   False, False),
    ("Furniture and Fittings",        "Furniture and Fixtures",     10,   False, False),
    ("Office Equipment",              "Office Equipment",           5,    False, False),
    ("Computers - desktops/laptops",  "Computers and IT Equipment", 3,    False, False),
    ("Servers and Networks",          "Computers and IT Equipment", 6,    False, False),
    ("Motor Cars",                    "Vehicles",                   8,    False, False),
    ("Two-wheelers",                  "Vehicles",                   10,   False, False),
    ("Computer Software",             "Intangible Assets",          None, True,  False),
]
CLASS_ORDER = ["Land", "Buildings", "Plant and Equipment", "Furniture and Fixtures", "Office Equipment",
               "Computers and IT Equipment", "Vehicles"]


def _admin(user: User):
    if user.role != "Admin":
        raise HTTPException(status_code=403, detail="Admin only.")


def _f(v) -> float:
    return float(v) if v is not None else 0.0


def _default_fy() -> int:
    return fy_of(date.today())


def _cap_date(a: FixedAsset) -> date:
    return a.put_to_use_date or a.purchase_date


def _dep(a: FixedAsset) -> DepAsset:
    return DepAsset(cost=_f(a.cost), cap_date=_cap_date(a), method=a.method, life=_f(a.useful_life_years),
                    residual_pct=_f(a.residual_pct), disposal_date=a.disposal_date, proceeds=_f(a.disposal_proceeds))


def _seed_categories(db: Session, iid: int):
    if db.query(AssetCategory).filter(AssetCategory.institution_id == iid).count():
        return
    for name, cls, life, intang, immov in DEFAULT_CATEGORIES:
        db.add(AssetCategory(institution_id=iid, name=name, schedule_iii_class=cls, schedule_ii_life=life,
                             default_method="SLM", residual_pct=0 if life == 0 else 5,
                             is_intangible=intang, is_immovable=immov))
    db.commit()


def _cat_out(c: AssetCategory) -> dict:
    return dict(id=c.id, name=c.name, schedule_iii_class=c.schedule_iii_class,
                schedule_ii_life=None if c.schedule_ii_life is None else _f(c.schedule_ii_life),
                default_method=c.default_method, residual_pct=_f(c.residual_pct),
                is_intangible=c.is_intangible, is_immovable=c.is_immovable)


# ── Categories ───────────────────────────────────────────────────────────────

class CategoryIn(BaseModel):
    name: str
    schedule_iii_class: str
    schedule_ii_life: Optional[float] = None
    default_method: str = "SLM"
    residual_pct: float = 5
    is_intangible: bool = False
    is_immovable: bool = False


def _check_category(d: CategoryIn):
    if not d.name.strip() or not d.schedule_iii_class.strip():
        raise HTTPException(status_code=400, detail="Name and class are required.")
    if d.default_method not in METHODS:
        raise HTTPException(status_code=400, detail="Method must be SLM or WDV.")
    if d.residual_pct < 0 or d.residual_pct >= 100:
        raise HTTPException(status_code=400, detail="Residual % must be between 0 and 100.")
    if d.schedule_ii_life is not None and d.schedule_ii_life < 0:
        raise HTTPException(status_code=400, detail="Useful life cannot be negative.")


@router.get("/categories")
def list_categories(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    _admin(user)
    _seed_categories(db, user.institution_id)
    rows = db.query(AssetCategory).filter(AssetCategory.institution_id == user.institution_id).order_by(AssetCategory.id).all()
    return [_cat_out(c) for c in rows]


@router.post("/categories", status_code=201)
def create_category(d: CategoryIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    _admin(user)
    _check_category(d)
    if db.query(AssetCategory).filter(AssetCategory.institution_id == user.institution_id, func.lower(AssetCategory.name) == d.name.strip().lower()).first():
        raise HTTPException(status_code=409, detail="A category with this name already exists.")
    c = AssetCategory(institution_id=user.institution_id, name=d.name.strip(), schedule_iii_class=d.schedule_iii_class.strip(),
                      schedule_ii_life=d.schedule_ii_life, default_method=d.default_method, residual_pct=d.residual_pct,
                      is_intangible=d.is_intangible, is_immovable=d.is_immovable)
    db.add(c); db.flush()
    audit.record(db, user, "Category created", description=c.name, details={"life": d.schedule_ii_life, "method": d.default_method, "residual_pct": d.residual_pct})
    db.commit(); db.refresh(c)
    return _cat_out(c)


@router.put("/categories/{cat_id}")
def update_category(cat_id: int, d: CategoryIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    _admin(user)
    _check_category(d)
    c = db.query(AssetCategory).filter(AssetCategory.id == cat_id, AssetCategory.institution_id == user.institution_id).first()
    if not c:
        raise HTTPException(status_code=404, detail="Category not found.")
    c.name, c.schedule_iii_class = d.name.strip(), d.schedule_iii_class.strip()
    c.schedule_ii_life, c.default_method, c.residual_pct = d.schedule_ii_life, d.default_method, d.residual_pct
    c.is_intangible, c.is_immovable = d.is_intangible, d.is_immovable
    audit.record(db, user, "Category updated", description=c.name, details={"life": d.schedule_ii_life, "method": d.default_method, "residual_pct": d.residual_pct})
    db.commit()
    return _cat_out(c)


@router.delete("/categories/{cat_id}", status_code=204)
def delete_category(cat_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    _admin(user)
    c = db.query(AssetCategory).filter(AssetCategory.id == cat_id, AssetCategory.institution_id == user.institution_id).first()
    if not c:
        raise HTTPException(status_code=404, detail="Category not found.")
    if db.query(FixedAsset).filter(FixedAsset.category_id == cat_id).count():
        raise HTTPException(status_code=409, detail="This category is used by assets in the register.")
    audit.record(db, user, "Category deleted", description=c.name)
    db.delete(c); db.commit()


# ── Assets ───────────────────────────────────────────────────────────────────

class AssetIn(BaseModel):
    description: str
    category_id: int
    cost: float
    purchase_date: date
    put_to_use_date: Optional[date] = None
    far_no: Optional[str] = None
    asset_id: Optional[int] = None
    class_id: Optional[int] = None
    parent_id: Optional[int] = None
    quantity: float = 1
    vendor: Optional[str] = None
    invoice_no: Optional[str] = None
    serial_no: Optional[str] = None
    method: Optional[str] = None
    useful_life_years: Optional[float] = None
    residual_pct: Optional[float] = None
    policy_note: Optional[str] = None
    disposal_date: Optional[date] = None
    disposal_proceeds: float = 0
    title_in_company_name: Optional[bool] = None
    title_holder: Optional[str] = None
    title_holder_related: Optional[bool] = None
    title_held_since: Optional[date] = None
    title_reason: Optional[str] = None
    warranty_expiry: Optional[date] = None


def _next_far_no(db: Session, iid: int) -> str:
    top = 0
    for (n,) in db.query(FixedAsset.far_no).filter(FixedAsset.institution_id == iid, FixedAsset.far_no.like("FA-%")).all():
        tail = n[3:]
        if tail.isdigit():
            top = max(top, int(tail))
    return f"FA-{top + 1:05d}"


def _resolve(d: AssetIn, cat: AssetCategory) -> dict:
    """Apply category defaults and enforce the Schedule II rules; returns the column values."""
    if d.cost < 0:
        raise HTTPException(status_code=400, detail="Cost cannot be negative.")
    if d.quantity <= 0:
        raise HTTPException(status_code=400, detail="Quantity must be more than zero.")
    if not d.description.strip():
        raise HTTPException(status_code=400, detail="Description is required.")
    method = d.method or cat.default_method
    if method not in METHODS:
        raise HTTPException(status_code=400, detail="Method must be SLM or WDV.")
    life = d.useful_life_years if d.useful_life_years is not None else (_f(cat.schedule_ii_life) if cat.schedule_ii_life is not None else None)
    if life is None or life < 0:
        raise HTTPException(status_code=400, detail="Useful life (years) is required for this category.")
    resid = d.residual_pct if d.residual_pct is not None else _f(cat.residual_pct)
    if resid < 0 or resid >= 100:
        raise HTTPException(status_code=400, detail="Residual % must be between 0 and 100.")
    cap = d.put_to_use_date or d.purchase_date
    if d.put_to_use_date and d.put_to_use_date < d.purchase_date:
        raise HTTPException(status_code=400, detail="Put-to-use date cannot be before the purchase date.")
    if d.disposal_date and d.disposal_date < cap:
        raise HTTPException(status_code=400, detail="Disposal date cannot be before the put-to-use date.")
    if d.disposal_proceeds < 0:
        raise HTTPException(status_code=400, detail="Disposal proceeds cannot be negative.")
    departs = (cat.schedule_ii_life is not None and abs(life - _f(cat.schedule_ii_life)) > 1e-9) or resid > 5
    if departs and not (d.policy_note or "").strip():
        raise HTTPException(status_code=400, detail="Useful life or residual value differs from Schedule II. Please record the reason in the policy note.")
    return dict(method=method, useful_life_years=life, residual_pct=resid)


def _check_links(db: Session, iid: int, d: AssetIn, self_id: Optional[int] = None):
    cat = db.query(AssetCategory).filter(AssetCategory.id == d.category_id, AssetCategory.institution_id == iid).first()
    if not cat:
        raise HTTPException(status_code=400, detail="Category not found.")
    if d.asset_id and not db.query(Asset).filter(Asset.id == d.asset_id, Asset.institution_id == iid).first():
        raise HTTPException(status_code=400, detail="Linked item not found.")
    if d.class_id and not db.query(Class).filter(Class.id == d.class_id, Class.institution_id == iid).first():
        raise HTTPException(status_code=400, detail="Location not found.")
    if d.parent_id:
        parent = db.query(FixedAsset).filter(FixedAsset.id == d.parent_id, FixedAsset.institution_id == iid).first()
        if not parent or parent.parent_id is not None or parent.id == self_id:
            raise HTTPException(status_code=400, detail="Parent must be a main asset (components cannot have components).")
    return cat


def _asset_out(a: FixedAsset, fy: int, names: dict) -> dict:
    fig = fy_figures(_dep(a), fy)
    cat = a.category
    return dict(
        id=a.id, far_no=a.far_no, description=a.description, category_id=a.category_id, category=cat.name,
        schedule_iii_class=cat.schedule_iii_class, is_intangible=cat.is_intangible, is_immovable=cat.is_immovable,
        asset_id=a.asset_id, item=names["assets"].get(a.asset_id, ""), class_id=a.class_id, location=names["classes"].get(a.class_id, ""),
        parent_id=a.parent_id, quantity=_f(a.quantity), cost=_f(a.cost),
        purchase_date=a.purchase_date.isoformat(), put_to_use_date=a.put_to_use_date.isoformat() if a.put_to_use_date else None,
        vendor=a.vendor or "", invoice_no=a.invoice_no or "", serial_no=a.serial_no or "", method=a.method,
        useful_life_years=_f(a.useful_life_years), residual_pct=_f(a.residual_pct), policy_note=a.policy_note or "",
        disposal_date=a.disposal_date.isoformat() if a.disposal_date else None, disposal_proceeds=_f(a.disposal_proceeds),
        title_in_company_name=a.title_in_company_name, title_holder=a.title_holder or "", title_holder_related=a.title_holder_related,
        title_held_since=a.title_held_since.isoformat() if a.title_held_since else None, title_reason=a.title_reason or "",
        warranty_expiry=a.warranty_expiry.isoformat() if a.warranty_expiry else None,
        status="Disposed" if a.disposal_date and a.disposal_date <= fy_bounds(fy)[1] else "Active", **fig,
    )


def _names(db: Session, iid: int) -> dict:
    return dict(
        assets={i: n for i, n in db.query(Asset.id, Asset.item_name).filter(Asset.institution_id == iid).all()},
        classes={i: n for i, n in db.query(Class.id, Class.class_name).filter(Class.institution_id == iid).all()},
    )


@router.get("/lookups")
def lookups(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    _admin(user)
    iid = user.institution_id
    _seed_categories(db, iid)
    return dict(
        categories=[_cat_out(c) for c in db.query(AssetCategory).filter(AssetCategory.institution_id == iid).order_by(AssetCategory.id).all()],
        items=[dict(id=i, name=n, code=c) for i, n, c in db.query(Asset.id, Asset.item_name, Asset.asset_code).filter(Asset.institution_id == iid).order_by(Asset.sl_no).all()],
        locations=[dict(id=i, name=n) for i, n in db.query(Class.id, Class.class_name).filter(Class.institution_id == iid).order_by(Class.display_order, Class.class_name).all()],
    )


def _all_assets(db: Session, iid: int):
    return db.query(FixedAsset).options(joinedload(FixedAsset.category)).filter(FixedAsset.institution_id == iid).order_by(FixedAsset.far_no).all()


@router.get("/assets")
def list_assets(fy: Optional[int] = Query(None), db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    _admin(user)
    fy = fy or _default_fy()
    names = _names(db, user.institution_id)
    return dict(fy=fy, fy_label=fy_label(fy), assets=[_asset_out(a, fy, names) for a in _all_assets(db, user.institution_id)])


def _columns(d: AssetIn, resolved: dict) -> dict:
    return dict(
        description=d.description.strip(), category_id=d.category_id, asset_id=d.asset_id, class_id=d.class_id, parent_id=d.parent_id,
        quantity=d.quantity, cost=d.cost, purchase_date=d.purchase_date, put_to_use_date=d.put_to_use_date,
        vendor=d.vendor, invoice_no=d.invoice_no, serial_no=d.serial_no, policy_note=(d.policy_note or "").strip() or None,
        disposal_date=d.disposal_date, disposal_proceeds=d.disposal_proceeds,
        title_in_company_name=d.title_in_company_name, title_holder=d.title_holder, title_holder_related=d.title_holder_related,
        title_held_since=d.title_held_since, title_reason=d.title_reason, warranty_expiry=d.warranty_expiry, **resolved,
    )


@router.post("/assets", status_code=201)
def create_asset(d: AssetIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    _admin(user)
    iid = user.institution_id
    cat = _check_links(db, iid, d)
    far_no = (d.far_no or "").strip() or _next_far_no(db, iid)
    if db.query(FixedAsset).filter(FixedAsset.institution_id == iid, FixedAsset.far_no == far_no).first():
        raise HTTPException(status_code=409, detail=f"Register number {far_no} already exists.")
    a = FixedAsset(institution_id=iid, far_no=far_no, **_columns(d, _resolve(d, cat)))
    db.add(a); db.flush()
    audit.record(db, user, "Created", a, {"category": cat.name, "cost": d.cost, "quantity": d.quantity, "purchase_date": d.purchase_date, "put_to_use_date": d.put_to_use_date})
    db.commit(); db.refresh(a)
    return _asset_out(a, _default_fy(), _names(db, iid))


@router.put("/assets/{asset_id}")
def update_asset(asset_id: int, d: AssetIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    _admin(user)
    iid = user.institution_id
    a = db.query(FixedAsset).filter(FixedAsset.id == asset_id, FixedAsset.institution_id == iid).first()
    if not a:
        raise HTTPException(status_code=404, detail="Asset not found.")
    cat = _check_links(db, iid, d, self_id=a.id)
    if d.parent_id and db.query(FixedAsset).filter(FixedAsset.parent_id == a.id).count():
        raise HTTPException(status_code=400, detail="This asset has components, so it cannot itself become a component.")
    if d.disposal_date and db.query(CustodyLog).filter(CustodyLog.fixed_asset_id == a.id, CustodyLog.returned_at.is_(None)).count():
        raise HTTPException(status_code=400, detail="This asset is currently checked out. Check it in before recording a disposal.")
    far_no = (d.far_no or "").strip() or a.far_no
    if far_no != a.far_no and db.query(FixedAsset).filter(FixedAsset.institution_id == iid, FixedAsset.far_no == far_no).first():
        raise HTTPException(status_code=409, detail=f"Register number {far_no} already exists.")
    cols = _columns(d, _resolve(d, cat)); cols["far_no"] = far_no
    changes = audit.diff(a, cols)
    if "category_id" in changes:
        cn = {c.id: c.name for c in db.query(AssetCategory).filter(AssetCategory.institution_id == iid).all()}
        changes["category"] = [cn.get(changes["category_id"][0]), cn.get(changes["category_id"][1])]
        del changes["category_id"]
    for k, v in cols.items():
        setattr(a, k, v)
    if changes:
        audit.record(db, user, "Disposed" if (changes.get("disposal_date") or [None, None])[1] else "Updated", a, changes)
    db.commit(); db.refresh(a)
    return _asset_out(a, _default_fy(), _names(db, iid))


@router.delete("/assets/{asset_id}", status_code=204)
def delete_asset(asset_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    _admin(user)
    a = db.query(FixedAsset).filter(FixedAsset.id == asset_id, FixedAsset.institution_id == user.institution_id).first()
    if not a:
        raise HTTPException(status_code=404, detail="Asset not found.")
    _remove_files(db, a.id, user.institution_id)
    audit.record(db, user, "Deleted", a, {"cost": _f(a.cost), "category": a.category.name, "put_to_use_date": a.put_to_use_date or a.purchase_date})
    db.delete(a); db.commit()


class BulkRow(BaseModel):
    description: str
    category: str
    cost: float
    purchase_date: date
    put_to_use_date: Optional[date] = None
    quantity: float = 1
    location: Optional[str] = None
    asset_code: Optional[str] = None
    vendor: Optional[str] = None
    invoice_no: Optional[str] = None
    serial_no: Optional[str] = None
    method: Optional[str] = None
    useful_life_years: Optional[float] = None
    residual_pct: Optional[float] = None
    policy_note: Optional[str] = None


@router.post("/assets/bulk")
def bulk_assets(rows: list[BulkRow], db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    _admin(user)
    iid = user.institution_id
    _seed_categories(db, iid)
    cats = {c.name.lower(): c for c in db.query(AssetCategory).filter(AssetCategory.institution_id == iid).all()}
    locs = {n.lower(): i for i, n in db.query(Class.id, Class.class_name).filter(Class.institution_id == iid).all()}
    items = {c.lower(): i for i, c in db.query(Asset.id, Asset.asset_code).filter(Asset.institution_id == iid).all()}
    created, errors = 0, []
    for n, r in enumerate(rows, start=1):
        try:
            cat = cats.get(r.category.strip().lower())
            if not cat:
                raise HTTPException(status_code=400, detail=f'Category "{r.category}" does not exist.')
            loc = locs.get(r.location.strip().lower()) if r.location and r.location.strip() else None
            if r.location and r.location.strip() and loc is None:
                raise HTTPException(status_code=400, detail=f'Location "{r.location}" does not exist.')
            item = items.get(r.asset_code.strip().lower()) if r.asset_code and r.asset_code.strip() else None
            if r.asset_code and r.asset_code.strip() and item is None:
                raise HTTPException(status_code=400, detail=f'Item code "{r.asset_code}" does not exist.')
            d = AssetIn(description=r.description, category_id=cat.id, cost=r.cost, purchase_date=r.purchase_date,
                        put_to_use_date=r.put_to_use_date, asset_id=item, class_id=loc, quantity=r.quantity, vendor=r.vendor,
                        invoice_no=r.invoice_no, serial_no=r.serial_no, method=r.method, useful_life_years=r.useful_life_years,
                        residual_pct=r.residual_pct, policy_note=r.policy_note)
            resolved = _resolve(d, cat)
            row = FixedAsset(institution_id=iid, far_no=_next_far_no(db, iid), **_columns(d, resolved))
            db.add(row)
            db.flush()
            audit.record(db, user, "Created (import)", row, {"category": cat.name, "cost": r.cost})
            created += 1
        except HTTPException as e:
            errors.append(dict(row=n, message=e.detail))
    db.commit()
    return dict(created=created, errors=errors)


# ── Reports ──────────────────────────────────────────────────────────────────

FIG_KEYS = ["opening_gross", "additions", "disposals", "closing_gross", "opening_acc", "charge", "acc_on_disposal",
            "closing_acc", "opening_net", "closing_net"]


@router.get("/reports/movement")
def movement(fy: Optional[int] = Query(None), db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Schedule III style reconciliation of gross block, accumulated depreciation and net block, by class."""
    _admin(user)
    fy = fy or _default_fy()
    groups: dict = {}
    pl_total = 0.0
    for a in _all_assets(db, user.institution_id):
        f = fy_figures(_dep(a), fy)
        cls = a.category.schedule_iii_class
        g = groups.setdefault(cls, dict(schedule_iii_class=cls, intangible=a.category.is_intangible, count=0, **{k: 0.0 for k in FIG_KEYS}))
        for k in FIG_KEYS:
            g[k] = round(g[k] + f[k], 2)
        if any(f[k] for k in FIG_KEYS):
            g["count"] += 1
        pl_total = round(pl_total + f["profit_loss_on_disposal"], 2)
    ordered = sorted(groups.values(), key=lambda g: (g["intangible"], CLASS_ORDER.index(g["schedule_iii_class"]) if g["schedule_iii_class"] in CLASS_ORDER else 99, g["schedule_iii_class"]))

    def total(rows):
        return {k: round(sum(r[k] for r in rows), 2) for k in FIG_KEYS}

    ppe = [g for g in ordered if not g["intangible"]]
    intang = [g for g in ordered if g["intangible"]]
    return dict(fy=fy, fy_label=fy_label(fy), ppe=ppe, intangible=intang, ppe_total=total(ppe), intangible_total=total(intang),
                profit_loss_on_disposal=pl_total)


def _book_lines(db: Session, iid: int, as_on: date):
    """Book quantity per (item, location) from the register, as on a date."""
    book: dict = defaultdict(lambda: dict(qty=0.0, cost=0.0, nbv=0.0))
    unlinked = []
    for a in _all_assets(db, iid):
        if a.parent_id is not None or a.cost is None:
            continue
        if _cap_date(a) > as_on or (a.disposal_date and a.disposal_date <= as_on):
            continue
        if a.category.is_immovable or a.category.is_intangible:
            continue
        if a.asset_id is None or a.class_id is None:
            unlinked.append(dict(far_no=a.far_no, description=a.description, cost=_f(a.cost)))
            continue
        b = book[(a.asset_id, a.class_id)]
        b["qty"] += _f(a.quantity)
        b["cost"] += _f(a.cost)
        b["nbv"] += nbv_as_on(_dep(a), as_on)
    return book, unlinked


def _verification(db: Session, iid: int, as_on: date) -> dict:
    book, unlinked = _book_lines(db, iid, as_on)
    physical = {(ai, ci): _f(q) for ai, ci, q in db.query(AssetClassCount.asset_id, AssetClassCount.class_id, func.sum(AssetClassCount.count))
                .join(Asset, Asset.id == AssetClassCount.asset_id).filter(Asset.institution_id == iid).group_by(AssetClassCount.asset_id, AssetClassCount.class_id).all()}
    items = {i: (n, c) for i, n, c in db.query(Asset.id, Asset.item_name, Asset.asset_code).filter(Asset.institution_id == iid).all()}
    classes = {c.id: c for c in db.query(Class).filter(Class.institution_id == iid).all()}
    lines, sums = [], dict(matched=0, shortages=0, excesses=0, short_qty=0.0, excess_qty=0.0, short_value=0.0, short_nbv=0.0, book_qty=0.0, physical_qty=0.0)
    for key in sorted(set(book) | {k for k, v in physical.items() if v}, key=lambda k: (classes[k[1]].class_name if k[1] in classes else "", items.get(k[0], ("", ""))[0])):
        ai, ci = key
        b, p = book.get(key, dict(qty=0.0, cost=0.0, nbv=0.0)), physical.get(key, 0.0)
        diff = round(p - b["qty"], 2)
        status = "Match" if diff == 0 else ("Shortage" if diff < 0 else ("Excess - not in books" if b["qty"] == 0 else "Excess"))
        unit_cost = b["cost"] / b["qty"] if b["qty"] else 0.0
        short_value = round(-diff * unit_cost, 2) if diff < 0 else 0.0
        short_nbv = round(-diff * (b["nbv"] / b["qty"]), 2) if diff < 0 and b["qty"] else 0.0
        c = classes.get(ci)
        lines.append(dict(item=items.get(ai, ("", ""))[0], item_code=items.get(ai, ("", ""))[1], location=c.class_name if c else "",
                          count_submitted=bool(c and c.locked), book_qty=round(b["qty"], 2), physical_qty=round(p, 2), difference=diff,
                          status=status, book_cost=round(b["cost"], 2), book_nbv=round(b["nbv"], 2), shortage_value=short_value, shortage_nbv=short_nbv))
        sums["book_qty"] += b["qty"]; sums["physical_qty"] += p
        if diff == 0: sums["matched"] += 1
        elif diff < 0: sums["shortages"] += 1; sums["short_qty"] += -diff; sums["short_value"] += short_value; sums["short_nbv"] += short_nbv
        else: sums["excesses"] += 1; sums["excess_qty"] += diff
    unsubmitted = sorted({l["location"] for l in lines if not l["count_submitted"]})
    return dict(as_on=as_on.isoformat(), lines=lines, unlinked=unlinked, locations_not_submitted=unsubmitted,
                summary={k: round(v, 2) for k, v in sums.items()})


@router.get("/reports/verification")
def verification_report(as_on: Optional[date] = Query(None), db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    _admin(user)
    return _verification(db, user.institution_id, as_on or date.today())


class RunIn(BaseModel):
    verified_by: str
    status: str = "Open"
    remarks: Optional[str] = None
    as_on: Optional[date] = None


STATUSES = ("Open", "Under investigation", "Adjusted in books")


@router.post("/verification", status_code=201)
def save_verification(d: RunIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    _admin(user)
    if not d.verified_by.strip():
        raise HTTPException(status_code=400, detail="Name of the person who verified is required.")
    if d.status not in STATUSES:
        raise HTTPException(status_code=400, detail="Invalid status.")
    snap = _verification(db, user.institution_id, d.as_on or date.today())
    run = VerificationRun(institution_id=user.institution_id, as_on=date.fromisoformat(snap["as_on"]), verified_by=d.verified_by.strip(),
                          status=d.status, remarks=d.remarks, snapshot=json.dumps(snap))
    db.add(run)
    audit.record(db, user, "Verification recorded", description="As on " + snap["as_on"], details={"verified_by": run.verified_by, "status": run.status, "shortages": snap["summary"]["shortages"], "excesses": snap["summary"]["excesses"]})
    db.commit(); db.refresh(run)
    return dict(id=run.id, as_on=snap["as_on"], status=run.status)


def _run_out(r: VerificationRun, full=False) -> dict:
    snap = json.loads(r.snapshot)
    out = dict(id=r.id, as_on=r.as_on.isoformat(), verified_by=r.verified_by, status=r.status, remarks=r.remarks or "",
               created_at=r.created_at.isoformat() if r.created_at else "", summary=snap["summary"])
    if full:
        out["snapshot"] = snap
    return out


@router.get("/verification")
def list_verifications(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    _admin(user)
    rows = db.query(VerificationRun).filter(VerificationRun.institution_id == user.institution_id).order_by(VerificationRun.id.desc()).all()
    return [_run_out(r) for r in rows]


@router.get("/verification/{run_id}")
def get_verification(run_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    _admin(user)
    r = db.query(VerificationRun).filter(VerificationRun.id == run_id, VerificationRun.institution_id == user.institution_id).first()
    if not r:
        raise HTTPException(status_code=404, detail="Verification record not found.")
    return _run_out(r, full=True)


class RunStatusIn(BaseModel):
    status: str
    remarks: Optional[str] = None


@router.put("/verification/{run_id}")
def update_verification(run_id: int, d: RunStatusIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    _admin(user)
    r = db.query(VerificationRun).filter(VerificationRun.id == run_id, VerificationRun.institution_id == user.institution_id).first()
    if not r:
        raise HTTPException(status_code=404, detail="Verification record not found.")
    if d.status not in STATUSES:
        raise HTTPException(status_code=400, detail="Invalid status.")
    audit.record(db, user, "Verification status changed", description="As on " + r.as_on.isoformat(), details={"status": [r.status, d.status]})
    r.status = d.status
    if d.remarks is not None:
        r.remarks = d.remarks
    db.commit()
    return _run_out(r)


@router.get("/reports/titledeeds")
def title_deeds(fy: Optional[int] = Query(None), db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    _admin(user)
    fy = fy or _default_fy()
    names = _names(db, user.institution_id)
    rows = []
    for a in _all_assets(db, user.institution_id):
        if not a.category.is_immovable or a.parent_id is not None:
            continue
        o = _asset_out(a, fy, names)
        if o["status"] == "Disposed":
            continue
        o["needs_attention"] = o["title_in_company_name"] is not True
        rows.append(o)
    return dict(fy=fy, fy_label=fy_label(fy), rows=rows, attention=sum(1 for r in rows if r["needs_attention"]))


# ── Revaluations ─────────────────────────────────────────────────────────────

class RevalIn(BaseModel):
    fixed_asset_id: int
    reval_date: date
    valuer_name: str
    valuer_reg_no: Optional[str] = None
    prior_net_carrying: float
    revalued_net_carrying: float
    notes: Optional[str] = None


@router.post("/revaluations", status_code=201)
def create_revaluation(d: RevalIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    _admin(user)
    iid = user.institution_id
    fa = db.query(FixedAsset).filter(FixedAsset.id == d.fixed_asset_id, FixedAsset.institution_id == iid).first()
    if not fa:
        raise HTTPException(status_code=400, detail="Asset not found.")
    if d.prior_net_carrying < 0 or d.revalued_net_carrying < 0:
        raise HTTPException(status_code=400, detail="Carrying amounts cannot be negative.")
    r = Revaluation(institution_id=iid, **d.model_dump())
    db.add(r)
    audit.record(db, user, "Revaluation recorded", fa, {"date": d.reval_date, "valuer": d.valuer_name, "registration_no": d.valuer_reg_no, "before": d.prior_net_carrying, "after": d.revalued_net_carrying})
    db.commit(); db.refresh(r)
    return dict(id=r.id)


@router.delete("/revaluations/{rid}", status_code=204)
def delete_revaluation(rid: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    _admin(user)
    r = db.query(Revaluation).filter(Revaluation.id == rid, Revaluation.institution_id == user.institution_id).first()
    if not r:
        raise HTTPException(status_code=404, detail="Revaluation not found.")
    audit.record(db, user, "Revaluation deleted", r.fixed_asset, {"date": r.reval_date, "before": _f(r.prior_net_carrying), "after": _f(r.revalued_net_carrying)})
    db.delete(r); db.commit()


@router.get("/reports/revaluations")
def revaluation_report(fy: Optional[int] = Query(None), db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Revaluations in the year, plus the CARO 3(i)(d) test: change of 10% or more in a class's aggregate net carrying value."""
    _admin(user)
    iid = user.institution_id
    fy = fy or _default_fy()
    fs, fe = fy_bounds(fy)
    class_open: dict = defaultdict(float)
    for a in _all_assets(db, iid):
        f = fy_figures(_dep(a), fy)
        class_open[a.category.schedule_iii_class] += f["opening_net"] + f["additions"]
    revs = db.query(Revaluation).filter(Revaluation.institution_id == iid, Revaluation.reval_date >= fs, Revaluation.reval_date <= fe).order_by(Revaluation.reval_date).all()
    rows, per_class = [], defaultdict(float)
    for r in revs:
        a = r.fixed_asset
        change = round(_f(r.revalued_net_carrying) - _f(r.prior_net_carrying), 2)
        per_class[a.category.schedule_iii_class] += change
        rows.append(dict(id=r.id, far_no=a.far_no, description=a.description, schedule_iii_class=a.category.schedule_iii_class,
                         reval_date=r.reval_date.isoformat(), valuer_name=r.valuer_name or "", valuer_reg_no=r.valuer_reg_no or "",
                         prior_net_carrying=_f(r.prior_net_carrying), revalued_net_carrying=_f(r.revalued_net_carrying), change=change, notes=r.notes or ""))
    tests = []
    for cls, change in per_class.items():
        base = class_open.get(cls, 0.0)
        pct = round(change / base * 100, 2) if base else None
        tests.append(dict(schedule_iii_class=cls, net_change=round(change, 2), class_net_carrying_value=round(base, 2), change_pct=pct,
                          report_in_caro=bool(pct is not None and abs(pct) >= 10)))
    return dict(fy=fy, fy_label=fy_label(fy), rows=rows, tests=tests, valuer_missing=sum(1 for r in rows if not r["valuer_reg_no"]))


# ── Audit trail ──────────────────────────────────────────────────────────────

@router.get("/audit")
def audit_trail(asset_id: Optional[int] = Query(None), limit: int = Query(300, ge=1, le=1000),
                db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    _admin(user)
    q = db.query(FarAudit).filter(FarAudit.institution_id == user.institution_id)
    if asset_id:
        q = q.filter(FarAudit.fixed_asset_id == asset_id)
    rows = q.order_by(FarAudit.id.desc()).limit(limit).all()
    return [dict(id=r.id, at=r.created_at.isoformat() if r.created_at else "", username=r.username, action=r.action, fixed_asset_id=r.fixed_asset_id,
                 far_no=r.far_no or "", description=r.description or "", details=json.loads(r.details) if r.details else None) for r in rows]


# ── Photos and documents ─────────────────────────────────────────────────────

MAX_FILE_BYTES = 5 * 1024 * 1024
MAX_FILES_PER_ASSET = 10


class FileIn(BaseModel):
    filename: str
    data: str


def _sniff(data: bytes):
    if data[:3] == b"\xff\xd8\xff":
        return "image/jpeg", ".jpg"
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png", ".png"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp", ".webp"
    if data[:4] == b"%PDF":
        return "application/pdf", ".pdf"
    return None, None


def _file_out(f: AssetFile) -> dict:
    return dict(id=f.id, filename=f.filename, content_type=f.content_type, size=f.size, uploaded_by=f.uploaded_by,
                created_at=f.created_at.isoformat() if f.created_at else "", is_image=f.content_type.startswith("image/"))


def _remove_files(db: Session, asset_id: int, iid: int):
    for f in db.query(AssetFile).filter(AssetFile.fixed_asset_id == asset_id, AssetFile.institution_id == iid).all():
        try:
            (UPLOAD_ROOT / str(iid) / f.stored_name).unlink()
        except OSError:
            pass


@router.get("/assets/{asset_id}/files")
def list_files(asset_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    _admin(user)
    rows = db.query(AssetFile).filter(AssetFile.fixed_asset_id == asset_id, AssetFile.institution_id == user.institution_id).order_by(AssetFile.id).all()
    return [_file_out(f) for f in rows]


@router.post("/assets/{asset_id}/files", status_code=201)
def upload_file(asset_id: int, d: FileIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    _admin(user)
    iid = user.institution_id
    a = db.query(FixedAsset).filter(FixedAsset.id == asset_id, FixedAsset.institution_id == iid).first()
    if not a:
        raise HTTPException(status_code=404, detail="Asset not found.")
    if len(d.data) > MAX_FILE_BYTES * 4 // 3 + 16:
        raise HTTPException(status_code=413, detail="File is larger than 5 MB.")
    try:
        raw = base64.b64decode(d.data, validate=True)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid file data.")
    if not raw or len(raw) > MAX_FILE_BYTES:
        raise HTTPException(status_code=413 if raw else 400, detail="File is empty." if not raw else "File is larger than 5 MB.")
    ctype, ext = _sniff(raw)
    if not ctype:
        raise HTTPException(status_code=400, detail="Only JPG, PNG, WEBP and PDF files are accepted.")
    if db.query(AssetFile).filter(AssetFile.fixed_asset_id == asset_id).count() >= MAX_FILES_PER_ASSET:
        raise HTTPException(status_code=409, detail=f"An asset can have at most {MAX_FILES_PER_ASSET} files.")
    folder = UPLOAD_ROOT / str(iid)
    folder.mkdir(parents=True, exist_ok=True)
    stored = uuid.uuid4().hex + ext
    (folder / stored).write_bytes(raw)
    name = re.sub(r"[^\w.\- ]", "_", os.path.basename(d.filename or "file"))[:200] or "file"
    f = AssetFile(institution_id=iid, fixed_asset_id=asset_id, filename=name, content_type=ctype, size=len(raw), stored_name=stored, uploaded_by=user.username)
    db.add(f)
    audit.record(db, user, "File added", a, {"filename": name, "size": len(raw)})
    db.commit(); db.refresh(f)
    return _file_out(f)


@router.get("/files/{file_id}")
def get_file(file_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    _admin(user)
    f = db.query(AssetFile).filter(AssetFile.id == file_id, AssetFile.institution_id == user.institution_id).first()
    path = UPLOAD_ROOT / str(user.institution_id) / f.stored_name if f else None
    if not f or not path.is_file():
        raise HTTPException(status_code=404, detail="File not found.")
    safe = re.sub(r"[^\w.\-]", "_", f.filename)
    return FileResponse(path, media_type=f.content_type, headers={"Content-Disposition": f'inline; filename="{safe}"', "X-Content-Type-Options": "nosniff", "Cache-Control": "private, no-store"})


@router.delete("/files/{file_id}", status_code=204)
def delete_file(file_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    _admin(user)
    f = db.query(AssetFile).filter(AssetFile.id == file_id, AssetFile.institution_id == user.institution_id).first()
    if not f:
        raise HTTPException(status_code=404, detail="File not found.")
    try:
        (UPLOAD_ROOT / str(user.institution_id) / f.stored_name).unlink()
    except OSError:
        pass
    audit.record(db, user, "File removed", db.get(FixedAsset, f.fixed_asset_id), {"filename": f.filename})
    db.delete(f); db.commit()
