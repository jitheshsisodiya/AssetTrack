import shutil
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import case, func
from sqlalchemy.orm import Session

from app.auth.jwt import create_access_token, get_current_user, hash_password, username_taken, verify_password
from app.config import UPLOAD_ROOT
from app.database import get_db
from app.models.models import Asset, AssetClassCount, Class, EditLog, Institution, User

INDUSTRY_TEMPLATES: dict[str, list[str]] = {
    "Retail":        ["Showroom Floor", "Storage Room", "Billing Counter", "Trial Room", "Manager Office"],
    "Manufacturing": ["Production Floor", "Assembly Line", "Quality Control", "Warehouse", "Admin Office"],
    "SaaS/Tech":     ["Engineering", "Server Room", "Conference Room", "Reception", "HR"],
    "Healthcare":    ["Ward", "OPD", "Pharmacy", "Lab", "Admin"],
    "School":        ["Classroom", "Lab", "Library", "Staff Room", "Principal Office"],
}
from app.schemas.schemas import InstitutionRegister, LoginRequest, TokenResponse

router = APIRouter(prefix="/auth", tags=["auth"])


def _require_superadmin(user: User):
    if user.role != "SuperAdmin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="SuperAdmin only.")


@router.post("/login", response_model=TokenResponse)
def login(data: LoginRequest, db: Session = Depends(get_db)):
    user = (
        db.query(User)
        .filter(User.username == data.username)
        .order_by(case({"SuperAdmin": 0}, value=User.role, else_=1))
        .first()
    )
    if not user or not verify_password(data.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid username or password.")
    institution = db.get(Institution, user.institution_id)
    if institution and not institution.is_active and user.role != "SuperAdmin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="This institution has been disabled. Contact support.")
    user.last_login = datetime.now(timezone.utc)
    db.commit()
    branch_ids   = [b.id   for b in user.branches]
    branch_names = [b.name for b in user.branches]
    token = create_access_token({
        "sub":            user.username,
        "role":           user.role,
        "institution_id": user.institution_id,
        "branch_ids":     branch_ids,
    })
    return TokenResponse(
        access_token=token,
        username=user.username,
        role=user.role,
        institution_name=institution.name if institution else "",
        group_label=institution.group_label if institution else "Class",
        branch_ids=branch_ids,
        branch_names=branch_names,
    )


@router.get("/institutions/count")
def institution_count(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    return {"count": db.query(Institution).filter(Institution.name != "System").count()}


@router.get("/overview")
def overview(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    _require_superadmin(current_user)
    institutions = db.query(Institution).filter(Institution.name != "System").order_by(Institution.id).all()
    now = datetime.now(timezone.utc)
    cutoff_24h = now - timedelta(hours=24)
    result = []
    for inst in institutions:
        total_qty = (
            db.query(func.sum(AssetClassCount.count))
            .join(Asset, AssetClassCount.asset_id == Asset.id)
            .filter(Asset.institution_id == inst.id)
            .scalar() or 0
        )
        last_active = (
            db.query(func.max(User.last_login))
            .filter(User.institution_id == inst.id)
            .scalar()
        )
        active_users_today = (
            db.query(User)
            .filter(User.institution_id == inst.id, User.last_login >= cutoff_24h)
            .count()
        )
        result.append({
            "id":          inst.id,
            "name":        inst.name,
            "is_active":   inst.is_active,
            "users":       db.query(User).filter(User.institution_id == inst.id).count(),
            "classes":     db.query(Class).filter(Class.institution_id == inst.id).count(),
            "line_items":  db.query(Asset).filter(Asset.institution_id == inst.id).count(),
            "total_qty":   float(total_qty),
            "active_users_today": active_users_today,
            "last_active": last_active.isoformat() if last_active else None,
            "created_at":  inst.created_at.strftime("%d/%m/%Y") if inst.created_at else "",
        })
    return result


@router.get("/activity")
def activity(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    _require_superadmin(current_user)
    system_inst = db.query(Institution).filter(Institution.name == "System").first()
    system_id   = system_inst.id if system_inst else -1

    logins = (
        db.query(User, Institution)
        .join(Institution, User.institution_id == Institution.id)
        .filter(User.institution_id != system_id, User.last_login.isnot(None))
        .order_by(User.last_login.desc())
        .limit(20)
        .all()
    )
    edits = (
        db.query(EditLog, Institution)
        .join(Institution, EditLog.institution_id == Institution.id)
        .order_by(EditLog.created_at.desc())
        .limit(20)
        .all()
    )
    return {
        "logins": [
            {
                "username":    u.username,
                "institution": inst.name,
                "last_login":  u.last_login.isoformat(),
            }
            for u, inst in logins
        ],
        "edits": [
            {
                "username":    e.username,
                "institution": inst.name,
                "item_name":   e.item_name,
                "class_name":  e.class_name,
                "qty":         float(e.qty) if e.qty else 0,
                "timestamp":   e.created_at.isoformat() if e.created_at else "",
            }
            for e, inst in edits
        ],
    }


@router.patch("/institution/{inst_id}/toggle")
def toggle_institution(inst_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    _require_superadmin(current_user)
    inst = db.get(Institution, inst_id)
    if not inst or inst.name == "System":
        raise HTTPException(status_code=404, detail="Institution not found.")
    inst.is_active = not inst.is_active
    db.commit()
    return {"id": inst_id, "is_active": inst.is_active}


@router.delete("/institution/{inst_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_institution(inst_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    _require_superadmin(current_user)
    inst = db.get(Institution, inst_id)
    if not inst or inst.name == "System":
        raise HTTPException(status_code=404, detail="Institution not found.")
    db.delete(inst)
    db.commit()
    shutil.rmtree(UPLOAD_ROOT / str(inst_id), ignore_errors=True)


class ResetPasswordBody(BaseModel):
    new_password: str


@router.post("/institution/{inst_id}/reset-password")
def reset_password(inst_id: int, body: ResetPasswordBody, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    _require_superadmin(current_user)
    admin = db.query(User).filter(User.institution_id == inst_id, User.role == "Admin").first()
    if not admin:
        raise HTTPException(status_code=404, detail="No Admin user found for this institution.")
    if not body.new_password:
        raise HTTPException(status_code=400, detail="New password is required.")
    admin.password_hash = hash_password(body.new_password)
    db.commit()
    return {"success": True, "username": admin.username}


@router.get("/institution/{inst_id}/users")
def list_institution_users(inst_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    _require_superadmin(current_user)
    users = db.query(User).filter(User.institution_id == inst_id).all()
    return [{"id": u.id, "username": u.username, "role": u.role, "last_login": u.last_login.isoformat() if u.last_login else None} for u in users]


class AddAdminBody(BaseModel):
    username: str
    password: str


@router.post("/institution/{inst_id}/admin", status_code=status.HTTP_201_CREATED)
def add_admin(inst_id: int, body: AddAdminBody, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    _require_superadmin(current_user)
    if not body.username.strip() or not body.password:
        raise HTTPException(status_code=400, detail="Username and password are required.")
    inst = db.get(Institution, inst_id)
    if not inst:
        raise HTTPException(status_code=404, detail="Institution not found.")
    if username_taken(db, body.username):
        raise HTTPException(status_code=409, detail="That username is already taken.")
    user = User(institution_id=inst_id, username=body.username.strip(), password_hash=hash_password(body.password), role="Admin")
    db.add(user)
    db.commit()
    return {"success": True, "username": user.username}


@router.delete("/user/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_user(user_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    _require_superadmin(current_user)
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")
    if user.role == "SuperAdmin":
        raise HTTPException(status_code=400, detail="Cannot delete SuperAdmin.")
    db.delete(user)
    db.commit()


@router.post("/register", status_code=status.HTTP_201_CREATED)
def register(data: InstitutionRegister, db: Session = Depends(get_db)):
    name     = data.institution_name.strip()
    username = data.username.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Institution name is required.")
    if not username or not data.password:
        raise HTTPException(status_code=400, detail="Admin username and password are required.")

    if username_taken(db, username):
        raise HTTPException(status_code=409, detail="That username is already taken. Please choose another.")

    institution = Institution(
        name=name,
        industry=data.industry.strip() or "Other",
        group_label=data.group_label.strip() or "Class",
    )
    db.add(institution)
    db.flush()

    admin = User(
        institution_id=institution.id,
        username=username,
        password_hash=hash_password(data.password),
        role="Admin",
    )
    db.add(admin)

    for i, cat in enumerate(INDUSTRY_TEMPLATES.get(institution.industry, []), start=1):
        db.add(Class(institution_id=institution.id, class_name=cat, display_order=i))

    db.commit()
    return {"success": True, "institution_name": name, "username": username}
