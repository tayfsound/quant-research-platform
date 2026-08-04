"""Auth repositories — Sprint 22-24."""
from sqlalchemy import Boolean, Column, DateTime, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID

from contracts.auth import APIKey, AuditLogEntry, Role, User
from database.base import Base


class UserModel(Base):
    __tablename__ = "users"
    id = Column(UUID(as_uuid=True), primary_key=True)
    username = Column(String(64), nullable=False, unique=True)
    password_hash = Column(String(128), nullable=False)
    role = Column(String(16), nullable=False)
    created_at = Column(DateTime, nullable=False)
    disabled = Column(Boolean, nullable=False, default=False)


class APIKeyModel(Base):
    __tablename__ = "api_keys"
    id = Column(UUID(as_uuid=True), primary_key=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    key_hash = Column(String(64), nullable=False, unique=True)
    label = Column(String(128), nullable=False, default="")
    created_at = Column(DateTime, nullable=False)
    revoked_at = Column(DateTime, nullable=True)


class AuditLogModel(Base):
    __tablename__ = "audit_log"
    id = Column(UUID(as_uuid=True), primary_key=True)
    timestamp = Column(DateTime, nullable=False)
    user_id = Column(UUID(as_uuid=True), nullable=True)
    username = Column(String(64), nullable=True)
    action = Column(String(64), nullable=False)
    resource = Column(String(255), nullable=False)
    allowed = Column(Boolean, nullable=False)
    detail = Column(String(500), nullable=False, default="")


class UserRepository:
    def __init__(self, session):
        self.session = session

    def create(self, user: User) -> User:
        row = UserModel(
            id=user.id,
            username=user.username,
            password_hash=user.password_hash,
            role=user.role.name,
            created_at=user.created_at,
            disabled=user.disabled,
        )
        self.session.add(row)
        self.session.commit()
        return user

    def get_by_username(self, username: str) -> UserModel | None:
        return self.session.query(UserModel).filter_by(username=username).first()

    def get_by_id(self, user_id) -> UserModel | None:
        return self.session.query(UserModel).filter_by(id=user_id).first()

    def count(self) -> int:
        return self.session.query(UserModel).count()


class APIKeyRepository:
    def __init__(self, session):
        self.session = session

    def create(self, api_key: APIKey) -> APIKey:
        row = APIKeyModel(
            id=api_key.id,
            user_id=api_key.user_id,
            key_hash=api_key.key_hash,
            label=api_key.label,
            created_at=api_key.created_at,
            revoked_at=api_key.revoked_at,
        )
        self.session.add(row)
        self.session.commit()
        return api_key

    def get_by_hash(self, key_hash: str) -> APIKeyModel | None:
        return (
            self.session.query(APIKeyModel)
            .filter_by(key_hash=key_hash, revoked_at=None)
            .first()
        )

    def revoke(self, api_key_id) -> None:
        from datetime import datetime
        self.session.query(APIKeyModel).filter_by(id=api_key_id).update(
            {"revoked_at": datetime.now()}
        )
        self.session.commit()


class AuditLogRepository:
    def __init__(self, session):
        self.session = session

    def record(self, entry: AuditLogEntry) -> None:
        row = AuditLogModel(
            id=entry.id,
            timestamp=entry.timestamp,
            user_id=entry.user_id,
            username=entry.username,
            action=entry.action,
            resource=entry.resource,
            allowed=entry.allowed,
            detail=entry.detail,
        )
        self.session.add(row)
        self.session.commit()

    def list_recent(self, limit: int = 100) -> list[AuditLogModel]:
        return (
            self.session.query(AuditLogModel)
            .order_by(AuditLogModel.timestamp.desc())
            .limit(limit)
            .all()
        )
