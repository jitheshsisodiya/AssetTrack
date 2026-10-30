"""Rules for maintenance due dates, warranty status and custody availability."""
from datetime import date, timedelta
from typing import Optional

DUE_SOON_DAYS = 30
WARRANTY_SOON_DAYS = 60


def task_status(next_due: Optional[date], today: date, soon_days: int = DUE_SOON_DAYS) -> str:
    if next_due is None:
        return "Completed"
    if next_due < today:
        return "Overdue"
    if next_due <= today + timedelta(days=soon_days):
        return "Due soon"
    return "Scheduled"


def next_due_after(done_on: date, frequency_days: Optional[int]) -> Optional[date]:
    """Recurring tasks fall due again `frequency_days` after the date they were actually done."""
    if not frequency_days or frequency_days <= 0:
        return None
    return done_on + timedelta(days=frequency_days)


def warranty_status(expiry: Optional[date], today: date, soon_days: int = WARRANTY_SOON_DAYS) -> str:
    if expiry is None:
        return "None"
    if expiry < today:
        return "Expired"
    if expiry <= today + timedelta(days=soon_days):
        return "Expiring soon"
    return "In warranty"


def available_quantity(total: float, out_open: float) -> float:
    return round(total - out_open, 2)


def return_status(due_back: Optional[date], returned: bool, today: date) -> str:
    if returned:
        return "Returned"
    if due_back is not None and due_back < today:
        return "Overdue"
    return "Out"
