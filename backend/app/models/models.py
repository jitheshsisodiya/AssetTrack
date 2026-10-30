from sqlalchemy import (
    Column, Integer, String, Boolean, Numeric, DateTime, Date, Text,
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
    id          = Column(Integer, primary_key=True, index=True)
    name        = Column(String(200), nullable=False)
    is_active   = Column(Boolean,     nullable=False, default=True)
    industry    = Column(String(50),  nullable=False, default="Other")
    group_label = Column(String(50),  nullable=False, default="Class")
    created_at  = Column(DateTime(timezone=True), server_default=func.now())


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


class AssetCategory(Base):
    __tablename__ = "asset_categories"
    id                 = Column(Integer, primary_key=True, index=True)
    institution_id     = Column(Integer, ForeignKey("institutions.id", ondelete="CASCADE"), nullable=False)
    name               = Column(String(100), nullable=False)
    schedule_iii_class = Column(String(60),  nullable=False)
    schedule_ii_life   = Column(Numeric(5, 2), nullable=True)
    default_method     = Column(String(10),  nullable=False, default="SLM")
    residual_pct       = Column(Numeric(5, 2), nullable=False, default=5)
    is_intangible      = Column(Boolean, nullable=False, default=False)
    is_immovable       = Column(Boolean, nullable=False, default=False)
    __table_args__ = (UniqueConstraint("institution_id", "name", name="uq_asset_categories_inst_name"),)


class FixedAsset(Base):
    __tablename__ = "fixed_assets"
    id                    = Column(Integer, primary_key=True, index=True)
    institution_id        = Column(Integer, ForeignKey("institutions.id", ondelete="CASCADE"), nullable=False)
    far_no                = Column(String(30),  nullable=False)
    description           = Column(String(255), nullable=False)
    category_id           = Column(Integer, ForeignKey("asset_categories.id"), nullable=False)
    asset_id              = Column(Integer, ForeignKey("assets.id",  ondelete="SET NULL"), nullable=True)
    class_id              = Column(Integer, ForeignKey("classes.id", ondelete="SET NULL"), nullable=True)
    parent_id             = Column(Integer, ForeignKey("fixed_assets.id", ondelete="CASCADE"), nullable=True)
    quantity              = Column(Numeric(10, 2), nullable=False, default=1)
    cost                  = Column(Numeric(14, 2), nullable=False)
    purchase_date         = Column(Date, nullable=False)
    put_to_use_date       = Column(Date, nullable=True)
    vendor                = Column(String(200))
    invoice_no            = Column(String(100))
    serial_no             = Column(String(100))
    method                = Column(String(10), nullable=False, default="SLM")
    useful_life_years     = Column(Numeric(5, 2), nullable=False, default=0)
    residual_pct          = Column(Numeric(5, 2), nullable=False, default=5)
    policy_note           = Column(Text)
    disposal_date         = Column(Date, nullable=True)
    disposal_proceeds     = Column(Numeric(14, 2), nullable=False, default=0)
    title_in_company_name = Column(Boolean, nullable=True)
    title_holder          = Column(String(200))
    title_holder_related  = Column(Boolean, nullable=True)
    title_held_since      = Column(Date, nullable=True)
    title_reason          = Column(Text)
    warranty_expiry       = Column(Date, nullable=True)
    created_at            = Column(DateTime(timezone=True), server_default=func.now())
    category              = relationship("AssetCategory")
    __table_args__ = (UniqueConstraint("institution_id", "far_no", name="uq_fixed_assets_inst_farno"),)


class Revaluation(Base):
    __tablename__ = "revaluations"
    id                    = Column(Integer, primary_key=True, index=True)
    institution_id        = Column(Integer, ForeignKey("institutions.id", ondelete="CASCADE"), nullable=False)
    fixed_asset_id        = Column(Integer, ForeignKey("fixed_assets.id", ondelete="CASCADE"), nullable=False)
    reval_date            = Column(Date, nullable=False)
    valuer_name           = Column(String(200))
    valuer_reg_no         = Column(String(100))
    prior_net_carrying    = Column(Numeric(14, 2), nullable=False)
    revalued_net_carrying = Column(Numeric(14, 2), nullable=False)
    notes                 = Column(Text)
    fixed_asset           = relationship("FixedAsset")


class VerificationRun(Base):
    __tablename__ = "verification_runs"
    id             = Column(Integer, primary_key=True, index=True)
    institution_id = Column(Integer, ForeignKey("institutions.id", ondelete="CASCADE"), nullable=False)
    as_on          = Column(Date, nullable=False)
    verified_by    = Column(String(200), nullable=False)
    status         = Column(String(40), nullable=False, default="Open")
    remarks        = Column(Text)
    snapshot       = Column(Text, nullable=False)
    created_at     = Column(DateTime(timezone=True), server_default=func.now())


class MaintenanceTask(Base):
    __tablename__ = "maintenance_tasks"
    id             = Column(Integer, primary_key=True, index=True)
    institution_id = Column(Integer, ForeignKey("institutions.id", ondelete="CASCADE"), nullable=False)
    fixed_asset_id = Column(Integer, ForeignKey("fixed_assets.id", ondelete="CASCADE"), nullable=False)
    title          = Column(String(200), nullable=False)
    frequency_days = Column(Integer, nullable=True)
    next_due       = Column(Date, nullable=True)
    last_done      = Column(Date, nullable=True)
    notes          = Column(Text)
    fixed_asset    = relationship("FixedAsset")


class MaintenanceLog(Base):
    __tablename__ = "maintenance_log"
    id             = Column(Integer, primary_key=True, index=True)
    institution_id = Column(Integer, ForeignKey("institutions.id", ondelete="CASCADE"), nullable=False)
    task_id        = Column(Integer, ForeignKey("maintenance_tasks.id", ondelete="CASCADE"), nullable=False)
    done_on        = Column(Date, nullable=False)
    done_by        = Column(String(200), nullable=False)
    cost           = Column(Numeric(14, 2), nullable=False, default=0)
    notes          = Column(Text)
    recorded_by    = Column(String(100))
    created_at     = Column(DateTime(timezone=True), server_default=func.now())


class CustodyLog(Base):
    __tablename__ = "custody_log"
    id             = Column(Integer, primary_key=True, index=True)
    institution_id = Column(Integer, ForeignKey("institutions.id", ondelete="CASCADE"), nullable=False)
    fixed_asset_id = Column(Integer, ForeignKey("fixed_assets.id", ondelete="CASCADE"), nullable=False)
    quantity       = Column(Numeric(10, 2), nullable=False, default=1)
    issued_to      = Column(String(200), nullable=False)
    issued_by      = Column(String(100), nullable=False)
    issued_at      = Column(DateTime(timezone=True), server_default=func.now())
    due_back       = Column(Date, nullable=True)
    condition_out  = Column(String(200))
    returned_at    = Column(DateTime(timezone=True), nullable=True)
    returned_to    = Column(String(100))
    condition_in   = Column(String(200))
    notes          = Column(Text)
    fixed_asset    = relationship("FixedAsset")


class FarAudit(Base):
    """Append-only record of changes to the fixed asset register. No foreign key to the asset, so it survives deletion."""
    __tablename__ = "far_audit"
    id             = Column(Integer, primary_key=True, index=True)
    institution_id = Column(Integer, ForeignKey("institutions.id", ondelete="CASCADE"), nullable=False)
    fixed_asset_id = Column(Integer, nullable=True)
    far_no         = Column(String(30))
    description    = Column(String(255))
    action         = Column(String(60), nullable=False)
    username       = Column(String(100), nullable=False)
    details        = Column(Text)
    created_at     = Column(DateTime(timezone=True), server_default=func.now())


class AssetFile(Base):
    __tablename__ = "asset_files"
    id             = Column(Integer, primary_key=True, index=True)
    institution_id = Column(Integer, ForeignKey("institutions.id", ondelete="CASCADE"), nullable=False)
    fixed_asset_id = Column(Integer, ForeignKey("fixed_assets.id", ondelete="CASCADE"), nullable=False)
    filename       = Column(String(255), nullable=False)
    content_type   = Column(String(100), nullable=False)
    size           = Column(Integer, nullable=False)
    stored_name    = Column(String(100), nullable=False)
    uploaded_by    = Column(String(100), nullable=False)
    created_at     = Column(DateTime(timezone=True), server_default=func.now())
