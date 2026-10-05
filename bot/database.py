import os
import asyncpg


DATABASE_URL = os.getenv("DATABASE_URL")

_pool = None


async def init_db():
    global _pool

    if not DATABASE_URL:
        raise RuntimeError("DATABASE_URL не знайдено")

    _pool = await asyncpg.create_pool(DATABASE_URL)

    async with _pool.acquire() as conn:
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS workers (
                id SERIAL PRIMARY KEY,
                name TEXT NOT NULL DEFAULT '',
                is_reserve BOOLEAN NOT NULL DEFAULT FALSE,
                reserve_number INTEGER
            )
        """)

        count = await conn.fetchval(
            "SELECT COUNT(*) FROM workers"
        )

        if count == 0:
            await conn.executemany(
                """
                INSERT INTO workers (name)
                VALUES ($1)
                """,
                [("",) for _ in range(12)]
            )


async def get_workers():
    async with _pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT
                id,
                name,
                is_reserve,
                reserve_number
            FROM workers
            ORDER BY id
        """)

        return [dict(row) for row in rows]


async def update_worker(
    worker_id: int,
    name: str,
):
    async with _pool.acquire() as conn:
        await conn.execute(
            """
            UPDATE workers
            SET name = $1
            WHERE id = $2
            """,
            name,
            worker_id,
        )
