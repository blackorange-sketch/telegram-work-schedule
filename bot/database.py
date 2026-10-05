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
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS schedule_settings (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                start_week DATE NOT NULL,
                start_shift INTEGER NOT NULL CHECK (start_shift IN (1, 2, 3))
            )
        """)

        await conn.execute("""
            CREATE TABLE IF NOT EXISTS schedule_weeks (
                id SERIAL PRIMARY KEY,
                week_start DATE NOT NULL UNIQUE,
                generated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """)

        await conn.execute("""
            CREATE TABLE IF NOT EXISTS schedule_assignments (
                id SERIAL PRIMARY KEY,
                shift INTEGER NOT NULL CHECK (shift BETWEEN 1 AND 3),
                week_id INTEGER NOT NULL REFERENCES schedule_weeks(id) ON DELETE CASCADE,
                work_date DATE NOT NULL,
                worker_id INTEGER NOT NULL REFERENCES workers(id),
                station INTEGER NOT NULL CHECK (station BETWEEN 15 AND 24),
                UNIQUE (week_id, work_date, worker_id),
                UNIQUE (week_id, work_date, station)
            )
        """)




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

async def get_schedule_settings():
    async with _pool.acquire() as conn:
        row = await conn.fetchrow("""
            SELECT id, start_week, start_shift
            FROM schedule_settings
            WHERE id = 1
        """)
        return dict(row) if row else None


async def set_schedule_settings(start_week, start_shift: int):
    async with _pool.acquire() as conn:
        row = await conn.fetchrow("""
            INSERT INTO schedule_settings (id, start_week, start_shift)
            VALUES (1, $1, $2)
            ON CONFLICT (id) DO UPDATE SET
                start_week = EXCLUDED.start_week,
                start_shift = EXCLUDED.start_shift
            RETURNING id, start_week, start_shift
        """, start_week, start_shift)
        return dict(row)


async def get_shift_for_week(week_start):
    async with _pool.acquire() as conn:
        row = await conn.fetchrow("""
            SELECT start_week, start_shift
            FROM schedule_settings
            WHERE id = 1
        """)

        if not row:
            return None

        weeks_diff = (week_start - row["start_week"]).days // 7
        return ((row["start_shift"] - 1 - weeks_diff) % 3) + 1



async def update_worker(
    worker_id: int,
    name: str,
):
    async with _pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            UPDATE workers
            SET name = $1
            WHERE id = $2
            RETURNING id, name, active, is_reserve, reserve_number
            """,
            name,
            worker_id,
        )
        return dict(row) if row else None

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
