"""
Generic async repository pattern.
"""
from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from database.base import Base


class BaseRepository[ModelT: Base]:
    """Async repository with common CRUD operations."""

    def __init__(self, model: type[ModelT], session: AsyncSession) -> None:
        self.model = model
        self.session = session

    async def get(self, id: UUID) -> ModelT | None:
        """Tek bir kaydı ID ile getir."""
        return await self.session.get(self.model, id)

    async def list(
        self,
        skip: int = 0,
        limit: int = 100,
        order_by: Any | None = None,
    ) -> list[ModelT]:
        """Kayıtları sayfalı olarak listele."""
        stmt = select(self.model).offset(skip).limit(limit)
        if order_by is not None:
            stmt = stmt.order_by(order_by)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def count(self) -> int:
        """Toplam kayıt sayısını döndür."""
        stmt = select(func.count()).select_from(self.model)
        result = await self.session.execute(stmt)
        return result.scalar() or 0

    async def add(self, instance: ModelT) -> ModelT:
        """Yeni kayıt ekle."""
        self.session.add(instance)
        await self.session.flush()
        return instance

    async def delete(self, instance: ModelT) -> None:
        """Kaydı sil."""
        await self.session.delete(instance)
        await self.session.flush()
