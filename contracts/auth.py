"""Auth contracts — Sprint 22-24. Kullanıcı/Rol/API Key/Audit Log.

Workspace (roadmap's "Kullanıcı/Rol/Workspace/Permission") deliberately not
modeled: this system has no multi-tenant concept anywhere else (single
global dashboard/DB), so a Workspace entity would be invented from nothing
rather than extending something real — logged as a known gap instead of
forced in.
"""
from datetime import datetime
from enum import IntEnum
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class Role(IntEnum):
    """Ordered so `current_role >= min_role` is a valid permission check."""
    VIEWER = 0
    OPERATOR = 1
    ADMIN = 2

    @classmethod
    def from_str(cls, value: str) -> "Role":
        return cls[value.upper()]


class User(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    username: str
    password_hash: str
    role: Role = Role.VIEWER
    created_at: datetime = Field(default_factory=datetime.now)
    disabled: bool = False


class APIKey(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    user_id: UUID
    key_hash: str
    label: str = ""
    created_at: datetime = Field(default_factory=datetime.now)
    revoked_at: datetime | None = None


class AuditLogEntry(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    timestamp: datetime = Field(default_factory=datetime.now)
    user_id: UUID | None = None
    username: str | None = None
    action: str
    resource: str
    allowed: bool
    detail: str = ""
