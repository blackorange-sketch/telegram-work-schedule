import os
import asyncpg
import random
from datetime import timedelta


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
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS schedule_days (
                id SERIAL PRIMARY KEY,
                week_id INTEGER NOT NULL REFERENCES schedule_weeks(id) ON DELETE CASCADE,
                work_date DATE NOT NULL,
                is_working_day BOOLEAN NOT NULL DEFAULT TRUE,
                default_shift INTEGER CHECK (default_shift BETWEEN 1 AND 3),
                UNIQUE (week_id, work_date)
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

async def get_or_create_schedule_week(week_start):
    async with _pool.acquire() as conn:
        row = await conn.fetchrow("""
            SELECT id, week_start, generated_at
            FROM schedule_weeks
            WHERE week_start = $1
        """, week_start)

        if row:
            return dict(row)

        row = await conn.fetchrow("""
            INSERT INTO schedule_weeks (week_start)
            VALUES ($1)
            RETURNING id, week_start, generated_at
        """, week_start)

        return dict(row)


async def create_schedule_days(week_id, week_start):
    async with _pool.acquire() as conn:
        rows = []

        for day_offset in range(7):
            work_date = week_start + timedelta(days=day_offset)
            row = await conn.fetchrow("""
                INSERT INTO schedule_days (week_id, work_date)
                VALUES ($1, $2)
                ON CONFLICT (week_id, work_date) DO NOTHING
                RETURNING id, week_id, work_date, is_working_day, default_shift
            """, week_id, work_date)

            if row:
                rows.append(dict(row))

        return rows

async def update_schedule_day(week_id, work_date, is_working_day, default_shift):
    async with _pool.acquire() as conn:
        row = await conn.fetchrow("""
            UPDATE schedule_days
            SET is_working_day = $1,
                default_shift = $2
            WHERE week_id = $3 AND work_date = $4
            RETURNING id, week_id, work_date, is_working_day, default_shift
        """, is_working_day, default_shift, week_id, work_date)

        return dict(row) if row else None





async def get_schedule_assignments(week_id):
    async with _pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT
                sa.id,
                sa.week_id,
                sa.work_date,
                sa.worker_id,
                w.name AS worker_name,
                sa.station,
                sa.shift
            FROM schedule_assignments sa
            JOIN workers w ON w.id = sa.worker_id
            WHERE sa.week_id = $1
            ORDER BY sa.work_date, sa.station
        """, week_id)

        return [dict(row) for row in rows]


async def generate_schedule_assignments(week_id, week_start, shift):
    async with _pool.acquire() as conn:
        existing = await conn.fetchval("""
            SELECT COUNT(*)
            FROM schedule_assignments
            WHERE week_id = $1
        """, week_id)

        if existing:
            return False

        rows = await conn.fetch("""
            SELECT id
            FROM workers
            WHERE active = TRUE
              AND is_reserve = FALSE
            ORDER BY id
            LIMIT 10
        """)

        worker_ids = [row["id"] for row in rows]

        if not worker_ids:
            return False

        stations = list(range(15, 25))
        used_by_worker = {worker_id: set() for worker_id in worker_ids}

        for day_offset in range(5):
            work_date = week_start + timedelta(days=day_offset)

            assignment = None

            for _ in range(1000):
                available_workers = worker_ids[:]
                random.shuffle(available_workers)

                available_stations = stations[:]
                random.shuffle(available_stations)

                candidate = {}
                valid = True

                for worker_id in available_workers:
                    choices = [
                        station
                        for station in available_stations
                        if station not in used_by_worker[worker_id]
                    ]

                    if not choices:
                        valid = False
                        break

                    station = random.choice(choices)
                    candidate[worker_id] = station
                    available_stations.remove(station)

                if valid:
                    assignment = candidate
                    break

            if assignment is None:
                raise RuntimeError(
                    f"Не вдалося розподілити станції на {work_date}"
                )

            for worker_id, station in assignment.items():
                await conn.execute("""
                    INSERT INTO schedule_assignments (
                        shift,
                        week_id,
                        work_date,
                        worker_id,
                        station
                    )
                    VALUES ($1, $2, $3, $4, $5)
                """, shift, week_id, work_date, worker_id, station)

                used_by_worker[worker_id].add(station)

        return True


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

async def set_schedule_assignment(
    week_id: int,
    work_date,
    worker_id: int,
    station: int,
    shift: int,
):
    async with _pool.acquire() as conn:
        async with conn.transaction():
            current_station = await conn.fetchrow("""
                SELECT id, worker_id, station, shift
                FROM schedule_assignments
                WHERE week_id = $1
                  AND work_date = $2
                  AND worker_id = $3
            """, week_id, work_date, worker_id)

            station_assignment = await conn.fetchrow("""
                SELECT id, worker_id, station, shift
                FROM schedule_assignments
                WHERE week_id = $1
                  AND work_date = $2
                  AND station = $3
            """, week_id, work_date, station)

            if station_assignment and station_assignment["worker_id"] != worker_id:
                if current_station:
                    await conn.execute("""
                        UPDATE schedule_assignments
                        SET worker_id = CASE
                            WHEN id = $1 THEN $3
                            WHEN id = $2 THEN $4
                        END
                        WHERE id IN ($1, $2)
                    """,
                        station_assignment["id"],
                        current_station["id"],
                        worker_id,
                        station_assignment["worker_id"],
                    )
                else:
                    await conn.execute("""
                        UPDATE schedule_assignments
                        SET worker_id = $1
                        WHERE id = $2
                    """, worker_id, station_assignment["id"])

            elif current_station:
                await conn.execute("""
                    UPDATE schedule_assignments
                    SET station = $1,
                        shift = $2
                    WHERE id = $3
                """, station, shift, current_station["id"])

            else:
                await conn.execute("""
                    INSERT INTO schedule_assignments (
                        shift,
                        week_id,
                        work_date,
                        worker_id,
                        station
                    )
                    VALUES ($1, $2, $3, $4, $5)
                """, shift, week_id, work_date, worker_id, station)

            row = await conn.fetchrow("""
                SELECT
                    sa.id,
                    sa.week_id,
                    sa.work_date,
                    sa.worker_id,
                    w.name AS worker_name,
                    sa.station,
                    sa.shift
                FROM schedule_assignments sa
                JOIN workers w ON w.id = sa.worker_id
                WHERE sa.week_id = $1
                  AND sa.work_date = $2
                  AND sa.worker_id = $3
            """, week_id, work_date, worker_id)

            return dict(row) if row else None


async def delete_schedule_assignment(
    week_id: int,
    work_date,
    station: int,
):
    async with _pool.acquire() as conn:
        row = await conn.fetchrow("""
            DELETE FROM schedule_assignments
            WHERE week_id = $1
              AND work_date = $2
              AND station = $3
            RETURNING id, week_id, work_date, worker_id, station, shift
        """, week_id, work_date, station)

        return dict(row) if row else None
