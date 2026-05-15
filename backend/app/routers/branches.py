from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.auth.jwt import get_current_user
from app.database import get_db
from app.models.models import Branch, User
from app.schemas.schemas import BranchBulkItem, BranchCreate, BranchOut, BranchUpdate

router = APIRouter(prefix="/api/branches", tags=["branches"])


def _require_admin(user: User):
    if user.role != "Admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin only.")


@router.get("", response_model=list[BranchOut])
def list_branches(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    return (
        db.query(Branch)
        .filter(Branch.institution_id == current_user.institution_id)
        .order_by(Branch.name)
        .all()
    )


@router.post("", response_model=BranchOut, status_code=status.HTTP_201_CREATED)
def create_branch(data: BranchCreate, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    _require_admin(current_user)
    iid = current_user.institution_id
    if db.query(Branch).filter(Branch.institution_id == iid, Branch.name == data.name).first():
        raise HTTPException(status_code=400, detail="Branch name already exists.")
    if db.query(Branch).filter(Branch.institution_id == iid, Branch.code == data.code.upper()).first():
        raise HTTPException(status_code=400, detail="Branch code already exists.")
    branch = Branch(institution_id=iid, name=data.name, code=data.code.upper(), is_active=data.is_active)
    db.add(branch)
    db.commit()
    db.refresh(branch)
    return branch


@router.put("/{branch_id}", response_model=BranchOut)
def update_branch(branch_id: int, data: BranchUpdate, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    _require_admin(current_user)
    iid = current_user.institution_id
    branch = db.query(Branch).filter(Branch.id == branch_id, Branch.institution_id == iid).first()
    if not branch:
        raise HTTPException(status_code=404, detail="Branch not found.")
    if data.name is not None:
        if db.query(Branch).filter(Branch.institution_id == iid, Branch.name == data.name, Branch.id != branch_id).first():
            raise HTTPException(status_code=400, detail="Branch name already exists.")
        branch.name = data.name
    if data.code is not None:
        code = data.code.upper()
        if db.query(Branch).filter(Branch.institution_id == iid, Branch.code == code, Branch.id != branch_id).first():
            raise HTTPException(status_code=400, detail="Branch code already exists.")
        branch.code = code
    if data.is_active is not None:
        branch.is_active = data.is_active
    db.commit()
    db.refresh(branch)
    return branch


@router.delete("/{branch_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_branch(branch_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    _require_admin(current_user)
    iid = current_user.institution_id
    branch = db.query(Branch).filter(Branch.id == branch_id, Branch.institution_id == iid).first()
    if not branch:
        raise HTTPException(status_code=404, detail="Branch not found.")
    db.delete(branch)
    db.commit()


@router.post("/bulk")
def bulk_create_branches(items: list[BranchBulkItem], db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    _require_admin(current_user)
    iid = current_user.institution_id
    created = skipped = 0
    for item in items:
        name = item.name.strip()
        code = item.code.strip().upper()
        if not name or not code:
            skipped += 1
            continue
        if db.query(Branch).filter(Branch.institution_id == iid, Branch.code == code).first():
            skipped += 1
            continue
        db.add(Branch(institution_id=iid, name=name, code=code, is_active=item.is_active))
        created += 1
    db.commit()
    return {"created": created, "skipped": skipped}
