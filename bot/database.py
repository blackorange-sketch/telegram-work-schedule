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
        await conn.execute("ALTER TABLE workers ADD COLUMN IF NOT EXISTS active BOOLEAN NOT NULL DEFAULT TRUE")

        count = await conn.fetchval(
            "SELECT COUNT(*) FROM workers"
        )



async def get_workers():
    async with _pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT
                id,
                name,
                is_reserve,
                reserve_number,
                active
            FROM workers
            WHERE active = TRUE
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

async def add_worker(name: str):
    async with _pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO workers (name)
            VALUES ($1)
            RETURNING id, name, active, is_reserve, reserve_number
            """,
            name,
        )
        return dict(row)

async def deactivate_worker(worker_id: int):
    async with _pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            UPDATE workers
            SET active = FALSE
            WHERE id = $1
            RETURNING id, name, active, is_reserve, reserve_number
            """,
            worker_id,
        )
        return dict(row) if row else None

async def set_worker_reserve(worker_id: int, is_reserve: bool):
    async with _pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            UPDATE workers
            SET is_reserve = $1
            WHERE id = $2
            RETURNING id, name, active, is_reserve, reserve_number
            """,
            is_reserve,
            worker_id,
        )
    return dict(row) if row else None
