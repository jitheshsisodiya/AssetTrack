"""Append-only audit trail for the fixed asset register. Callers commit."""
import json
from datetime import date, datetime
from decimal import Decimal

from app.models.models import FarAudit


def _plain(v):
    if isinstance(v, Decimal):
        return float(v)
    if isinstance(v, (date, datetime)):
        return v.isoformat()
    return v


def record(db, user, action, asset=None, details=None, far_no=None, description=None):
    db.add(FarAudit(
        institution_id=user.institution_id,
        fixed_asset_id=asset.id if asset is not None else None,
        far_no=far_no or (asset.far_no if asset is not None else None),
        description=description or (asset.description if asset is not None else None),
        action=action, username=user.username,
        details=json.dumps(details, default=_plain) if details else None,
    ))


def diff(asset, new: dict) -> dict:
    """{field: [old, new]} for every value that actually changes."""
    out = {}
    for k, v in new.items():
        old = getattr(asset, k, None)
        if _plain(old) == _plain(v) or (old in (None, "") and v in (None, "")):
            continue
        out[k] = [_plain(old), _plain(v)]
    return out
