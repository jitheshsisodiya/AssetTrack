from sqlalchemy import (
    Column, Integer, String, Boolean, Numeric, DateTime,
    ForeignKey, Table, UniqueConstraint, func,
)
from sqlalchemy.orm import relationship
from app.database import Base

# Many-to-many: users ↔ branches
user_branches = Table(
    "user_branches",
    Base.metadata,
    Column("user_id",   Integer, ForeignKey("users.id",    ondelete="CASCADE"), primary_key=True),
    Column("branch_id", Integer, ForeignKey("branches.id", ondelete="CASCADE"), primary_key=True),
)


class Institution(Base):
    __tablename__ = "institutions"
    id         = Column(Integer, primary_key=True, index=True)
    name       = Column(String(200), nullable=False)
    is_active  = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class Branch(Base):
    __tablename__ = "branches"
    id             = Column(Integer, primary_key=True, index=True)
    institution_id = Column(Integer, ForeignKey("institutions.id", ondelete="CASCADE"), nullable=False)
    name           = Column(String(200), nullable=False)
    code           = Column(String(50),  nullable=False)
    is_active      = Column(Boolean, nullable=False, default=True)
    created_at     = Column(DateTime(timezone=True), server_default=func.now())
    users          = relationship("User",  secondary=user_branches, back_populates="branches")
    classes        = relationship("Class", back_populates="branch")
    __table_args__ = (
        UniqueConstraint("institution_id", "name", name="uq_branches_inst_name"),
        UniqueConstraint("institution_id", "code", name="uq_branches_inst_code"),
    )


class User(Base):
    __tablename__ = "users"
    id             = Column(Integer, primary_key=True, index=True)
    institution_id = Column(Integer, ForeignKey("institutions.id", ondelete="CASCADE"), nullable=False)
    username       = Column(String(100), nullable=False, index=True)
    password_hash  = Column(String(255), nullable=False)
    role           = Column(String(50),  nullable=False)
    last_login     = Column(DateTime(timezone=True), nullable=True)
    branches       = relationship("Branch", secondary=user_branches, back_populates="users")
    __table_args__ = (
        UniqueConstraint("institution_id", "username", name="uq_users_inst_username"),
    )


class Asset(Base):
    __tablename__ = "assets"
    id             = Column(Integer, primary_key=True, index=True)
    institution_id = Column(Integer, ForeignKey("institutions.id", ondelete="CASCADE"), nullable=False)
    item_name      = Column(String(255), nullable=False)
    sl_no          = Column(Integer)
    asset_code     = Column(String(100), nullable=False, index=True)
    counts         = relationship("AssetClassCount", back_populates="asset", cascade="all, delete-orphan")
    __table_args__ = (
        UniqueConstraint("institution_id", "asset_code", name="uq_assets_inst_code"),
    )


class Class(Base):
    __tablename__ = "classes"
    id                = Column(Integer, primary_key=True, index=True)
    institution_id    = Column(Integer, ForeignKey("institutions.id", ondelete="CASCADE"), nullable=False)
    class_name        = Column(String(100), nullable=False, index=True)
    assigned_to       = Column(String(100))
    locked            = Column(Boolean, default=False)
    locked_by         = Column(String(100))
    lock_timestamp    = Column(String(100))
    sticker_locked    = Column(Boolean, default=False)
    sticker_locked_by = Column(String(100))
    sticker_timestamp = Column(String(100))
    display_order     = Column(Integer, default=0)
    branch_id         = Column(Integer, ForeignKey("branches.id"), nullable=True)
    branch            = relationship("Branch", back_populates="classes")
    counts            = relationship("AssetClassCount", back_populates="cls", cascade="all, delete-orphan")
    __table_args__ = (
        UniqueConstraint("institution_id", "class_name", name="uq_classes_inst_name"),
    )


class AssetClassCount(Base):
    __tablename__ = "asset_class_counts"
    id       = Column(Integer, primary_key=True, index=True)
    asset_id = Column(Integer, ForeignKey("assets.id",  ondelete="CASCADE"), nullable=False)
    class_id = Column(Integer, ForeignKey("classes.id", ondelete="CASCADE"), nullable=False)
    count    = Column(Numeric(10, 2), default=0)
    asset    = relationship("Asset", back_populates="counts")
    cls      = relationship("Class", back_populates="counts")
    __table_args__ = (UniqueConstraint("asset_id", "class_id"),)


class EditLog(Base):
    __tablename__ = "edit_log"
    id             = Column(Integer, primary_key=True, index=True)
    institution_id = Column(Integer, ForeignKey("institutions.id", ondelete="CASCADE"), nullable=False)
    username       = Column(String(100), nullable=False)
    item_name      = Column(String(255))
    asset_code     = Column(String(100))
    class_name     = Column(String(100))
    qty            = Column(Numeric(10, 2))
    created_at     = Column(DateTime(timezone=True), server_default=func.now())


class Barcode(Base):
    __tablename__ = "barcodes"
    id             = Column(Integer, primary_key=True, index=True)
    institution_id = Column(Integer, ForeignKey("institutions.id", ondelete="CASCADE"), nullable=False)
    sl_no          = Column(Integer)
    code_text      = Column(String(255))
    item_name      = Column(String(255))
    class_name     = Column(String(100))
    remarks        = Column(String(255), default="")


class Stickering(Base):
    __tablename__ = "stickering"
    id             = Column(Integer, primary_key=True, index=True)
    institution_id = Column(Integer, ForeignKey("institutions.id", ondelete="CASCADE"), nullable=False)
    sl_no          = Column(Integer)
    bar_code       = Column(String(255))
    item_name      = Column(String(255))
    class_name     = Column(String(100))
    remarks        = Column(String(255), default="")
    __table_args__ = (
        UniqueConstraint("institution_id", "bar_code", name="uq_stickering_inst_barcode"),
    )


class AppState(Base):
    # Key pattern: "lastModified_{institution_id}" — no institution_id column needed
    __tablename__ = "app_state"
    key   = Column(String(100), primary_key=True)
    value = Column(String)
