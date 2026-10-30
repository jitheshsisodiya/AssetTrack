import base64
import ipaddress
import socket

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.auth.jwt import get_current_user
from app.models.models import User

router = APIRouter(prefix="/api/print", tags=["print"])

MAX_BYTES = 2_000_000
ALLOWED_PORT = 9100


class RawPrint(BaseModel):
    host: str
    port: int = ALLOWED_PORT
    data: str


@router.post("/raw")
def raw_print(body: RawPrint, current_user: User = Depends(get_current_user)):
    if body.port != ALLOWED_PORT:
        raise HTTPException(status_code=400, detail=f"Only port {ALLOWED_PORT} is allowed.")
    try:
        payload = base64.b64decode(body.data, validate=True)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid print data.")
    if not payload or len(payload) > MAX_BYTES:
        raise HTTPException(status_code=400, detail="Print data is empty or too large.")
    try:
        ip = ipaddress.ip_address(socket.gethostbyname(body.host.strip()))
    except Exception:
        raise HTTPException(status_code=400, detail="Printer address not found.")
    if ip.is_link_local or not (ip.is_private or ip.is_loopback):
        raise HTTPException(status_code=400, detail="Only printers on a private network address are allowed.")
    try:
        with socket.create_connection((str(ip), ALLOWED_PORT), timeout=5) as s:
            s.sendall(payload)
    except OSError as e:
        raise HTTPException(status_code=502, detail=f"Could not reach the printer at {ip}:{ALLOWED_PORT} ({e.strerror or e}).")
    return {"success": True, "bytes": len(payload)}
