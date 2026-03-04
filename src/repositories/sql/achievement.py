from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.db.models.steam.achievements import SteamAchievement


class SteamAchievementRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def batch_upsert(self, rows: list[dict]) -> None:
        """Insert or update achievements based on the (username, game, title) unique constraint.

        On conflict the mutable columns are updated in-place.
        Processes in chunks to avoid exceeding database parameter limits.
        """
        if not rows:
            return

        chunk_size = 500
        for i in range(0, len(rows), chunk_size):
            chunk = rows[i : i + chunk_size]
            stmt = pg_insert(SteamAchievement).values(chunk)
            stmt = stmt.on_conflict_do_update(
                constraint='uq_user_game_title',
                set_={
                    'description': stmt.excluded.description,
                    'unlock_time': stmt.excluded.unlock_time,
                    'current_progress': stmt.excluded.current_progress,
                    'total_progress': stmt.excluded.total_progress,
                    'language': stmt.excluded.language,
                    'url': stmt.excluded.url,
                },
            )
            await self.session.execute(stmt)

        await self.session.commit()

    async def get_by_username(self, username: str) -> list[SteamAchievement]:
        result = await self.session.scalars(
            select(SteamAchievement)
            .where(SteamAchievement.username == username)
            .order_by(SteamAchievement.game, SteamAchievement.title)
        )
        return list(result.all())
