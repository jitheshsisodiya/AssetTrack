"""Depreciation engine — Companies Act 2013, Schedule II conventions.

Financial year runs 1 April to 31 March; `fy` is the calendar year in which it starts.
Depreciation is charged pro rata by days, from the capitalisation (put-to-use) date up to
and including the disposal date, and each year's charge is rounded to 2 decimals so that
closing figures of one year always equal the opening figures of the next.
"""
from dataclasses import dataclass
from datetime import date
from typing import Optional

METHODS = ("SLM", "WDV")


def fy_bounds(fy: int) -> tuple[date, date]:
    return date(fy, 4, 1), date(fy + 1, 3, 31)


def fy_of(d: date) -> int:
    return d.year if d.month >= 4 else d.year - 1


def fy_label(fy: int) -> str:
    return f"{fy}-{str(fy + 1)[-2:]}"


@dataclass
class DepAsset:
    cost: float
    cap_date: date
    method: str = "SLM"
    life: float = 0.0
    residual_pct: float = 5.0
    disposal_date: Optional[date] = None
    proceeds: float = 0.0


def residual_value(a: DepAsset) -> float:
    r = a.cost * a.residual_pct / 100.0
    if a.method == "WDV" and r < 1.0:
        r = min(1.0, a.cost)
    return r


def _days_in_use(a: DepAsset, fs: date, fe: date) -> int:
    start = max(a.cap_date, fs)
    end = min(a.disposal_date, fe) if a.disposal_date else fe
    return max(0, (end - start).days + 1)


def _charge(a: DepAsset, fs: date, fe: date, acc_so_far: float, until: Optional[date] = None) -> float:
    if not a.life or a.life <= 0 or a.cost <= 0:
        return 0.0
    days = _days_in_use(a, fs, min(fe, until) if until else fe)
    if days == 0:
        return 0.0
    fy_days = (fe - fs).days + 1
    resid = residual_value(a)
    depreciable = a.cost - resid
    if a.method == "WDV":
        rate = 1.0 - (resid / a.cost) ** (1.0 / a.life)
        dep = (a.cost - acc_so_far) * rate * days / fy_days
    else:
        dep = depreciable / a.life * days / fy_days
    dep = round(dep, 2)
    room = round(depreciable - acc_so_far, 2)
    return max(0.0, min(dep, room))


def accumulated_before(a: DepAsset, fs: date) -> float:
    acc, y = 0.0, fy_of(a.cap_date)
    while True:
        s, e = fy_bounds(y)
        if s >= fs:
            break
        acc = round(acc + _charge(a, s, e, acc), 2)
        y += 1
    return acc


def fy_figures(a: DepAsset, fy: int) -> dict:
    fs, fe = fy_bounds(fy)
    z = dict(opening_gross=0.0, additions=0.0, disposals=0.0, closing_gross=0.0,
             opening_acc=0.0, charge=0.0, acc_on_disposal=0.0, closing_acc=0.0,
             opening_net=0.0, closing_net=0.0, profit_loss_on_disposal=0.0,
             disposed_in_year=False)
    if a.cap_date > fe or (a.disposal_date and a.disposal_date < fs):
        return z
    cost = round(a.cost, 2)
    opening_gross = cost if a.cap_date < fs else 0.0
    additions = cost if fs <= a.cap_date <= fe else 0.0
    opening_acc = accumulated_before(a, fs)
    charge = _charge(a, fs, fe, opening_acc)
    disposed = bool(a.disposal_date and fs <= a.disposal_date <= fe)
    disposals = cost if disposed else 0.0
    acc_pre = round(opening_acc + charge, 2)
    acc_on_disposal = acc_pre if disposed else 0.0
    closing_gross = round(opening_gross + additions - disposals, 2)
    closing_acc = round(opening_acc + charge - acc_on_disposal, 2)
    z.update(
        opening_gross=opening_gross, additions=additions, disposals=disposals, closing_gross=closing_gross,
        opening_acc=opening_acc, charge=charge, acc_on_disposal=acc_on_disposal, closing_acc=closing_acc,
        opening_net=round(opening_gross - opening_acc, 2), closing_net=round(closing_gross - closing_acc, 2),
        profit_loss_on_disposal=round(a.proceeds - (cost - acc_pre), 2) if disposed else 0.0,
        disposed_in_year=disposed,
    )
    return z


def nbv_as_on(a: DepAsset, d: date) -> float:
    """Net book value at the end of day `d` (zero before capitalisation or after disposal)."""
    if a.cap_date > d or (a.disposal_date and a.disposal_date <= d):
        return 0.0
    acc, y = 0.0, fy_of(a.cap_date)
    while True:
        fs, fe = fy_bounds(y)
        if fs > d:
            break
        acc = round(acc + _charge(a, fs, fe, acc, until=d), 2)
        y += 1
    return round(round(a.cost, 2) - acc, 2)
