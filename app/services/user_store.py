import uuid
from datetime import datetime
from typing import List, Optional

from sqlalchemy import select

from app.database import AsyncSessionLocal
from app.orm_models import UserRow


class UserStore:
    @staticmethod
    async def get_by_email(email: str) -> Optional[UserRow]:
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(UserRow).where(UserRow.email == email.lower())
            )
            return result.scalar_one_or_none()

    @staticmethod
    async def get_by_id(user_id: str) -> Optional[UserRow]:
        async with AsyncSessionLocal() as session:
            return await session.get(UserRow, user_id)

    @staticmethod
    async def create(email: str, name: str, hashed_password: str, role: str) -> UserRow:
        async with AsyncSessionLocal() as session:
            row = UserRow(
                id=str(uuid.uuid4()),
                email=email.lower(),
                name=name,
                hashed_password=hashed_password,
                role=role,
                is_active=True,
                created_at=datetime.utcnow(),
            )
            session.add(row)
            await session.commit()
            await session.refresh(row)
            return row

    @staticmethod
    async def list_all() -> List[UserRow]:
        async with AsyncSessionLocal() as session:
            result = await session.execute(select(UserRow))
            return list(result.scalars().all())

    @staticmethod
    async def count() -> int:
        async with AsyncSessionLocal() as session:
            result = await session.execute(select(UserRow))
            return len(result.scalars().all())

    @staticmethod
    async def set_active(user_id: str, active: bool) -> Optional[UserRow]:
        from sqlalchemy import update
        async with AsyncSessionLocal() as session:
            await session.execute(
                update(UserRow).where(UserRow.id == user_id).values(is_active=active)
            )
            await session.commit()
            return await session.get(UserRow, user_id)

    @staticmethod
    async def delete(user_id: str) -> bool:
        from sqlalchemy import delete as sql_delete
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                sql_delete(UserRow).where(UserRow.id == user_id)
            )
            await session.commit()
            return result.rowcount > 0
