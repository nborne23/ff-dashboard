"""`Connection` — the D12 read-model for `/api/connections` (distinct from `api/connections.py`'s
lighter-weight `ConnectionStatus` response model used by the existing OAuth/cookie endpoints)."""

from datetime import datetime

from pydantic import BaseModel

from backend.gridiron.schemas.common import Platform


class ConnectionError(BaseModel):
    code: str
    message: str


class Connection(BaseModel):
    platform: Platform
    is_connected: bool
    display_name: str | None
    last_verified_at: datetime | None
    error: ConnectionError | None = None
