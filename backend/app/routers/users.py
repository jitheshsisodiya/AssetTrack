from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.auth.jwt import get_current_user, hash_password, username_taken
from app.database import get_db
from app.models.models import Branch, User
from app.schemas.schemas import UserBulkItem, UserCreate, UserOut, UserUpdate

router = APIRouter(prefix="/api/users", tags=["users"])


def _require_admin(user: User):
    if user.role != "Admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin only.")


def _to_out(u: User) -> UserOut:
    return UserOut(
        id=u.id,
        username=u.username,
        role=u.role,
        branch_ids=[b.id for b in u.branches],
        branch_names=[b.name for b in u.branches],
    )


def _set_branches(db: Session, user: User, branch_ids: list[int]):
    branches = db.query(Branch).filter(
        Branch.id.in_(branch_ids), Branch.institution_id == user.institution_id
    ).all()
    if len(branches) != len(branch_ids):
        raise HTTPException(status_code=400, detail="One or more branch IDs not found.")
    user.branches = branches


@router.get("", response_model=list[UserOut])
def list_users(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    _require_admin(current_user)
    return [
        _to_out(u)
        for u in db.query(User).filter(User.institution_id == current_user.institution_id).order_by(User.username).all()
    ]


@router.post("", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def create_user(data: UserCreate, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    _require_admin(current_user)
    iid = current_user.institution_id
    if username_taken(db, data.username):
        raise HTTPException(status_code=400, detail="Username already exists.")
    user = User(institution_id=iid, username=data.username, password_hash=hash_password(data.password), role=data.role)
    db.add(user)
    db.flush()
    if data.branch_ids:
        _set_branches(db, user, data.branch_ids)
    db.commit()
    db.refresh(user)
    return _to_out(user)


@router.put("/{user_id}", response_model=UserOut)
def update_user(user_id: int, data: UserUpdate, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    _require_admin(current_user)
    user = db.query(User).filter(User.id == user_id, User.institution_id == current_user.institution_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")
    if data.password is not None:
        user.password_hash = hash_password(data.password)
    if data.role is not None:
        user.role = data.role
    if data.branch_ids is not None:
        _set_branches(db, user, data.branch_ids)
    db.commit()
    db.refresh(user)
    return _to_out(user)


@router.post("/bulk")
def bulk_create_users(items: list[UserBulkItem], db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    _require_admin(current_user)
    iid = current_user.institution_id
    branch_map = {b.code.upper(): b for b in db.query(Branch).filter(Branch.institution_id == iid).all()}
    created = skipped = 0
    for item in items:
        username = item.username.strip()
        if not username or not item.password:
            skipped += 1; continue
        if username_taken(db, username):
            skipped += 1; continue
        user = User(institution_id=iid, username=username, password_hash=hash_password(item.password), role=item.role or "Editor")
        db.add(user)
        db.flush()
        if item.branch_codes:
            codes = [c.strip().upper() for c in item.branch_codes.split(",") if c.strip()]
            user.branches = [branch_map[c] for c in codes if c in branch_map]
        created += 1
    db.commit()
    return {"created": created, "skipped": skipped}


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_user(user_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    _require_admin(current_user)
    if user_id == current_user.id:
        raise HTTPException(status_code=400, detail="Cannot delete yourself.")
    user = db.query(User).filter(User.id == user_id, User.institution_id == current_user.institution_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")
    db.delete(user)
    db.commit()
