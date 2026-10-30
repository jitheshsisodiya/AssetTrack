from pydantic import BaseModel
from typing import Any, List, Optional


class LoginRequest(BaseModel):
    username: str
    password: str


class InstitutionRegister(BaseModel):
    institution_name: str
    username:         str
    password:         str
    industry:         str = "Other"
    group_label:      str = "Class"


class TokenResponse(BaseModel):
    access_token:     str
    token_type:       str = "bearer"
    username:         str
    role:             str
    institution_name: str = ""
    group_label:      str = "Class"
    branch_ids:       List[int] = []
    branch_names:     List[str] = []


class SubmitEntryRequest(BaseModel):
    username:  str
    itemName:  str
    assetCode: str
    className: str
    qty:       float


class LockClassRequest(BaseModel):
    className: str
    lockedBy:  str
    timestamp: str


class UnlockClassRequest(BaseModel):
    className: str


class BarcodeItem(BaseModel):
    codeText:  str
    className: str


class UpdateRemarksRequest(BaseModel):
    slNos:  List[Any]
    remark: str


class AddStickeringRowRequest(BaseModel):
    barCode:   str
    itemName:  str
    className: str


class CancelBarCodesRequest(BaseModel):
    slNos: List[Any]


# ── Bulk upload schemas ───────────────────────────────────────────────────────

class BranchBulkItem(BaseModel):
    name:      str
    code:      str
    is_active: bool = True


class ClassBulkItem(BaseModel):
    class_name:  str
    branch_code: Optional[str] = None


class UserBulkItem(BaseModel):
    username:     str
    password:     str
    role:         str = "Editor"
    branch_codes: Optional[str] = None


# ── Branch schemas ────────────────────────────────────────────────────────────

class BranchCreate(BaseModel):
    name:      str
    code:      str
    is_active: bool = True


class BranchUpdate(BaseModel):
    name:      Optional[str]  = None
    code:      Optional[str]  = None
    is_active: Optional[bool] = None


class BranchOut(BaseModel):
    id:        int
    name:      str
    code:      str
    is_active: bool

    class Config:
        from_attributes = True


# ── User schemas ──────────────────────────────────────────────────────────────

class UserCreate(BaseModel):
    username:   str
    password:   str
    role:       str = "Editor"
    branch_ids: List[int] = []


class UserUpdate(BaseModel):
    password:   Optional[str]       = None
    role:       Optional[str]       = None
    branch_ids: Optional[List[int]] = None


class UserOut(BaseModel):
    id:           int
    username:     str
    role:         str
    branch_ids:   List[int] = []
    branch_names: List[str] = []

    class Config:
        from_attributes = True
