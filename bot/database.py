import os
import asyncpg
import random
from datetime import timedelta


DATABASE_URL = os.getenv("DATABASE_URL")

_pool = None

EXOTEC_GROUPS = {
    "exotec_1": range(1, 15),
    "exotec_2": range(15, 25),
    "exotec_3": range(25, 35),
}

def get_group_tables(group):
    if group not in EXOTEC_GROUPS:
        raise ValueError(f"Невідома група Exotec: {group}")

    return {
        "workers": f"workers_{group}",
        "worker_days_off": f"worker_days_off_{group}",
        "schedule_assignments": f"schedule_assignments_{group}",
        "schedule_reserves": f"schedule_reserves_{group}",
        "lunch_settings": f"lunch_settings_{group}",
    }


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
            CREATE INDEX IF NOT EXISTS idx_schedule_assignments_date_worker
            ON schedule_assignments (work_date, worker_id)
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
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS worker_days_off (
                id SERIAL PRIMARY KEY,
                worker_id INTEGER NOT NULL REFERENCES workers(id) ON DELETE CASCADE,
                work_date DATE NOT NULL,
                UNIQUE (worker_id, work_date)
            )
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_worker_days_off_work_date_worker
            ON worker_days_off (work_date, worker_id)
        """)

        await conn.execute("""
            CREATE TABLE IF NOT EXISTS schedule_reserves (
                id SERIAL PRIMARY KEY,
                week_id INTEGER NOT NULL REFERENCES schedule_weeks(id) ON DELETE CASCADE,
                work_date DATE NOT NULL,
                worker_id INTEGER NOT NULL REFERENCES workers(id),
                UNIQUE (week_id, work_date, worker_id)
            )
        """)

        await conn.execute("""
            CREATE TABLE IF NOT EXISTS lunch_settings (
                id SERIAL PRIMARY KEY,
                week_id INTEGER NOT NULL REFERENCES schedule_weeks(id) ON DELETE CASCADE,
                shift INTEGER NOT NULL CHECK (shift BETWEEN 1 AND 3),
                pair_number INTEGER NOT NULL CHECK (pair_number BETWEEN 1 AND 5),
                worker1_id INTEGER REFERENCES workers(id),
                worker2_id INTEGER REFERENCES workers(id),
                start_time TIME NOT NULL,
                UNIQUE (week_id, shift, pair_number)
            )
        """)









        for group in EXOTEC_GROUPS:
            tables = get_group_tables(group)
            workers_table = tables["workers"]
            days_off_table = tables["worker_days_off"]
            assignments_table = tables["schedule_assignments"]
            reserves_table = tables["schedule_reserves"]
            lunch_table = tables["lunch_settings"]
            station_start = min(EXOTEC_GROUPS[group])
            station_end = max(EXOTEC_GROUPS[group])

            await conn.execute(f"""
                CREATE TABLE IF NOT EXISTS {workers_table} (
                    id SERIAL PRIMARY KEY,
                    name TEXT NOT NULL DEFAULT '',
                    is_reserve BOOLEAN NOT NULL DEFAULT FALSE,
                    reserve_number INTEGER,
                    active BOOLEAN NOT NULL DEFAULT TRUE
                )
            """)

            await conn.execute(f"""
                CREATE TABLE IF NOT EXISTS {days_off_table} (
                    id SERIAL PRIMARY KEY,
                    worker_id INTEGER NOT NULL REFERENCES {workers_table}(id) ON DELETE CASCADE,
                    work_date DATE NOT NULL,
                    UNIQUE (worker_id, work_date)
                )
            """)

            await conn.execute(f"""
                CREATE INDEX IF NOT EXISTS idx_{days_off_table}_work_date_worker
                ON {days_off_table} (work_date, worker_id)
            """)

            await conn.execute(f"""
                CREATE TABLE IF NOT EXISTS {assignments_table} (
                    id SERIAL PRIMARY KEY,
                    shift INTEGER NOT NULL CHECK (shift BETWEEN 1 AND 3),
                    week_id INTEGER NOT NULL REFERENCES schedule_weeks(id) ON DELETE CASCADE,
                    work_date DATE NOT NULL,
                    worker_id INTEGER NOT NULL REFERENCES {workers_table}(id),
                    station INTEGER NOT NULL CHECK (station BETWEEN {station_start} AND {station_end}),
                    UNIQUE (week_id, work_date, worker_id),
                    UNIQUE (week_id, work_date, station)
                )
            """)

            await conn.execute(f"""
                CREATE INDEX IF NOT EXISTS idx_{assignments_table}_date_worker
                ON {assignments_table} (work_date, worker_id)
            """)

            await conn.execute(f"""
                CREATE TABLE IF NOT EXISTS {reserves_table} (
                    id SERIAL PRIMARY KEY,
                    week_id INTEGER NOT NULL REFERENCES schedule_weeks(id) ON DELETE CASCADE,
                    work_date DATE NOT NULL,
                    worker_id INTEGER NOT NULL REFERENCES {workers_table}(id),
                    UNIQUE (week_id, work_date, worker_id)
                )
            """)

            await conn.execute(f"""
                CREATE TABLE IF NOT EXISTS {lunch_table} (
                    id SERIAL PRIMARY KEY,
                    week_id INTEGER NOT NULL REFERENCES schedule_weeks(id) ON DELETE CASCADE,
                    shift INTEGER NOT NULL CHECK (shift BETWEEN 1 AND 3),
                    pair_number INTEGER NOT NULL CHECK (pair_number BETWEEN 1 AND 5),
                    worker1_id INTEGER REFERENCES {workers_table}(id),
                    worker2_id INTEGER REFERENCES {workers_table}(id),
                    start_time TIME NOT NULL,
                    UNIQUE (week_id, shift, pair_number)
                )
            """)



async def get_workers(group="exotec_2"):
    tables = get_group_tables(group)

    async with _pool.acquire() as conn:
        rows = await conn.fetch(f"""
            SELECT
                id,
                name,
                is_reserve,
                reserve_number,
                active
            FROM {tables["workers"]}
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


async def set_worker_day_off(worker_id, work_date, group="exotec_2"):
    tables = get_group_tables(group)

    async with _pool.acquire() as conn:
        row = await conn.fetchrow(f"""
            INSERT INTO {tables["worker_days_off"]} (worker_id, work_date)
            VALUES ($1, $2)
            ON CONFLICT (worker_id, work_date)
            DO UPDATE SET work_date = EXCLUDED.work_date
            RETURNING id, worker_id, work_date
        """, worker_id, work_date)

        await conn.execute(f"""
            DELETE FROM {tables["schedule_assignments"]}
            WHERE worker_id = $1
              AND work_date = $2
        """, worker_id, work_date)

        return dict(row) if row else None


async def delete_worker_day_off(worker_id, work_date, group="exotec_2"):
    tables = get_group_tables(group)

    async with _pool.acquire() as conn:
        row = await conn.fetchrow(f"""
            DELETE FROM {tables["worker_days_off"]}
            WHERE worker_id = $1
              AND work_date = $2
            RETURNING id, worker_id, work_date
        """, worker_id, work_date)

        return dict(row) if row else None


async def get_worker_days_off(start_date, end_date, group="exotec_2"):
    tables = get_group_tables(group)

    async with _pool.acquire() as conn:
        rows = await conn.fetch(f"""
            SELECT worker_id, work_date
            FROM {tables["worker_days_off"]}
            WHERE work_date BETWEEN $1 AND $2
            ORDER BY work_date, worker_id
        """, start_date, end_date)

        return [dict(row) for row in rows]


async def create_schedule_days(week_id, week_start):
    async with _pool.acquire() as conn:
        rows = await conn.fetch("""
            INSERT INTO schedule_days (
                week_id,
                work_date
            )
            SELECT
                $1,
                $2::date + day_offset::integer
            FROM generate_series(0, 6) AS day_offset
            ON CONFLICT (week_id, work_date) DO NOTHING
            RETURNING id, week_id, work_date, is_working_day, default_shift
        """, week_id, week_start)

        return [dict(row) for row in rows]

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





async def get_schedule_assignments(week_id, group="exotec_2"):
    tables = get_group_tables(group)

    async with _pool.acquire() as conn:
        rows = await conn.fetch(f"""
            SELECT
                sa.id,
                sa.week_id,
                sa.work_date,
                sa.worker_id,
                w.name AS worker_name,
                sa.station,
                sa.shift
            FROM {tables["schedule_assignments"]} sa
            JOIN {tables["workers"]} w ON w.id = sa.worker_id
            WHERE sa.week_id = $1
            ORDER BY sa.work_date, sa.station
        """, week_id)

        return [dict(row) for row in rows]


async def get_schedule_reserves(week_id, group="exotec_2"):
    tables = get_group_tables(group)

    async with _pool.acquire() as conn:
        rows = await conn.fetch(f"""
            SELECT
                sr.work_date,
                sr.worker_id,
                w.name AS worker_name
            FROM {tables["schedule_reserves"]} sr
            JOIN {tables["workers"]} w ON w.id = sr.worker_id
            WHERE sr.week_id = $1
            ORDER BY sr.work_date, sr.worker_id
        """, week_id)

        return [dict(row) for row in rows]


async def generate_schedule_assignments(
    week_id,
    week_start,
    shift,
    group="exotec_2",
):
    tables = get_group_tables(group)
    station_count = len(EXOTEC_GROUPS[group])

    async with _pool.acquire() as conn:
        existing = await conn.fetchval(f"""
            SELECT 1
            FROM {tables["schedule_assignments"]}
            WHERE week_id = $1
            LIMIT 1
        """, week_id)

        if existing:
            return False

        rows = await conn.fetch(f"""
            SELECT id, is_reserve
            FROM {tables["workers"]}
            WHERE active = TRUE
            ORDER BY id
        """)

        worker_ids = [row["id"] for row in rows]
        fixed_reserve_workers = {
            row["id"] for row in rows
            if row["is_reserve"]
        }

        if not worker_ids:
            return False

        days_off_rows = await conn.fetch(f"""
            SELECT worker_id, work_date
            FROM {tables["worker_days_off"]}
            WHERE work_date BETWEEN $1 AND $2
        """, week_start, week_start + timedelta(days=4))

        days_off = {
            (row["worker_id"], row["work_date"])
            for row in days_off_rows
        }

        stations = list(EXOTEC_GROUPS[group])
        used_by_worker = {
            worker_id: set()
            for worker_id in worker_ids
        }
        reserve_count = {
            worker_id: 0
            for worker_id in worker_ids
        }

        for day_offset in range(5):
            work_date = week_start + timedelta(days=day_offset)

            eligible_workers = [
                worker_id
                for worker_id in worker_ids
                if (worker_id, work_date) not in days_off
            ]

            if not eligible_workers:
                continue

            reserve_slots = max(
                0,
                len(eligible_workers) - station_count,
            )

            fixed_reserve = [
                worker_id
                for worker_id in eligible_workers
                if worker_id in fixed_reserve_workers
            ]

            random_reserve = [
                worker_id
                for worker_id in eligible_workers
                if worker_id not in fixed_reserve_workers
                and reserve_count[worker_id] == 0
            ]

            random.shuffle(fixed_reserve)
            random.shuffle(random_reserve)

            reserve_workers = (
                fixed_reserve + random_reserve
            )[:reserve_slots]

            station_workers = [
                worker_id
                for worker_id in eligible_workers
                if worker_id not in reserve_workers
            ]

            assignment = None

            for _ in range(1000):
                available_workers = station_workers[:]
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

            assignment_rows = [
                (
                    shift,
                    week_id,
                    work_date,
                    worker_id,
                    station,
                )
                for worker_id, station in assignment.items()
            ]

            if assignment_rows:
                await conn.executemany(
                    f"""
                    INSERT INTO {tables["schedule_assignments"]} (
                        shift,
                        week_id,
                        work_date,
                        worker_id,
                        station
                    )
                    VALUES ($1, $2, $3, $4, $5)
                    """,
                    assignment_rows,
                )

            for worker_id, station in assignment.items():
                used_by_worker[worker_id].add(station)

            reserve_rows = [
                (
                    week_id,
                    work_date,
                    worker_id,
                )
                for worker_id in reserve_workers
            ]

            if reserve_rows:
                await conn.executemany(
                    f"""
                    INSERT INTO {tables["schedule_reserves"]} (
                        week_id,
                        work_date,
                        worker_id
                    )
                    VALUES ($1, $2, $3)
                    """,
                    reserve_rows,
                )

            for worker_id in reserve_workers:
                reserve_count[worker_id] += 1

        return True


async def update_worker(
    worker_id: int,
    name: str,
    group="exotec_2",
):
    tables = get_group_tables(group)

    async with _pool.acquire() as conn:
        row = await conn.fetchrow(
            f"""
            UPDATE {tables["workers"]}
            SET name = $1
            WHERE id = $2
            RETURNING id, name, active, is_reserve, reserve_number
            """,
            name,
            worker_id,
        )

        return dict(row) if row else None


async def add_worker(name: str, group="exotec_2"):
    tables = get_group_tables(group)

    async with _pool.acquire() as conn:
        row = await conn.fetchrow(
            f"""
            INSERT INTO {tables["workers"]} (name)
            VALUES ($1)
            RETURNING id, name, active, is_reserve, reserve_number
            """,
            name,
        )

        return dict(row)


async def deactivate_worker(
    worker_id: int,
    group="exotec_2",
):
    tables = get_group_tables(group)

    async with _pool.acquire() as conn:
        row = await conn.fetchrow(
            f"""
            UPDATE {tables["workers"]}
            SET active = FALSE
            WHERE id = $1
            RETURNING id, name, active, is_reserve, reserve_number
            """,
            worker_id,
        )

        return dict(row) if row else None


async def set_worker_reserve(
    worker_id: int,
    is_reserve: bool,
    group="exotec_2",
):
    tables = get_group_tables(group)

    async with _pool.acquire() as conn:
        row = await conn.fetchrow(
            f"""
            UPDATE {tables["workers"]}
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
    group="exotec_2",
):
    tables = get_group_tables(group)
    worker_id = int(worker_id)

    if station not in EXOTEC_GROUPS[group]:
        raise ValueError(f"Станція {station} не належить групі {group}")

    async with _pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute(
                f"""
                DELETE FROM {tables["schedule_reserves"]}
                WHERE week_id = $1
                  AND work_date = $2
                  AND worker_id = $3
                """,
                week_id,
                work_date,
                worker_id,
            )

            current_station = await conn.fetchrow(
                f"""
                SELECT id, worker_id, station, shift
                FROM {tables["schedule_assignments"]}
                WHERE week_id = $1
                  AND work_date = $2
                  AND worker_id = $3
                """,
                week_id,
                work_date,
                worker_id,
            )

            station_assignment = await conn.fetchrow(
                f"""
                SELECT id, worker_id, station, shift
                FROM {tables["schedule_assignments"]}
                WHERE week_id = $1
                  AND work_date = $2
                  AND station = $3
                """,
                week_id,
                work_date,
                station,
            )

            if station_assignment and station_assignment["worker_id"] != worker_id:
                if current_station:
                    old_worker_id = station_assignment["worker_id"]
                    current_shift = current_station["shift"]
                    current_station_number = current_station["station"]
                    selected_shift = station_assignment["shift"]
                    selected_station_number = station_assignment["station"]

                    await conn.execute(
                        f"""
                        DELETE FROM {tables["schedule_assignments"]}
                        WHERE id IN ($1, $2)
                        """,
                        station_assignment["id"],
                        current_station["id"],
                    )

                    await conn.execute(
                        f"""
                        INSERT INTO {tables["schedule_assignments"]} (
                            shift,
                            week_id,
                            work_date,
                            worker_id,
                            station
                        )
                        VALUES ($1, $2, $3, $4, $5)
                        """,
                        selected_shift,
                        week_id,
                        work_date,
                        worker_id,
                        selected_station_number,
                    )

                    await conn.execute(
                        f"""
                        INSERT INTO {tables["schedule_assignments"]} (
                            shift,
                            week_id,
                            work_date,
                            worker_id,
                            station
                        )
                        VALUES ($1, $2, $3, $4, $5)
                        """,
                        current_shift,
                        week_id,
                        work_date,
                        old_worker_id,
                        current_station_number,
                    )

                else:
                    await conn.execute(
                        f"""
                        UPDATE {tables["schedule_assignments"]}
                        SET worker_id = $1
                        WHERE id = $2
                        """,
                        worker_id,
                        station_assignment["id"],
                    )

            elif current_station:
                await conn.execute(
                    f"""
                    UPDATE {tables["schedule_assignments"]}
                    SET station = $1,
                        shift = $2
                    WHERE id = $3
                    """,
                    station,
                    shift,
                    current_station["id"],
                )

            else:
                await conn.execute(
                    f"""
                    INSERT INTO {tables["schedule_assignments"]} (
                        shift,
                        week_id,
                        work_date,
                        worker_id,
                        station
                    )
                    VALUES ($1, $2, $3, $4, $5)
                    """,
                    shift,
                    week_id,
                    work_date,
                    worker_id,
                    station,
                )

            row = await conn.fetchrow(
                f"""
                SELECT
                    sa.id,
                    sa.week_id,
                    sa.work_date,
                    sa.worker_id,
                    w.name AS worker_name,
                    sa.station,
                    sa.shift
                FROM {tables["schedule_assignments"]} sa
                JOIN {tables["workers"]} w ON w.id = sa.worker_id
                WHERE sa.week_id = $1
                  AND sa.work_date = $2
                  AND sa.worker_id = $3
                """,
                week_id,
                work_date,
                worker_id,
            )

            return dict(row) if row else None


async def set_schedule_reserve(
    week_id: int,
    work_date,
    worker_id: int,
    group="exotec_2",
):
    tables = get_group_tables(group)

    async with _pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute(
                f"""
                DELETE FROM {tables["schedule_assignments"]}
                WHERE week_id = $1
                  AND work_date = $2
                  AND worker_id = $3
                """,
                week_id,
                work_date,
                worker_id,
            )

            await conn.execute(
                f"""
                INSERT INTO {tables["schedule_reserves"]} (
                    week_id,
                    work_date,
                    worker_id
                )
                VALUES ($1, $2, $3)
                ON CONFLICT (week_id, work_date, worker_id)
                DO NOTHING
                """,
                week_id,
                work_date,
                worker_id,
            )


async def delete_schedule_reserve(
    week_id: int,
    work_date,
    worker_id: int,
    group="exotec_2",
):
    tables = get_group_tables(group)

    async with _pool.acquire() as conn:
        await conn.execute(
            f"""
            DELETE FROM {tables["schedule_reserves"]}
            WHERE week_id = $1
              AND work_date = $2
              AND worker_id = $3
            """,
            week_id,
            work_date,
            worker_id,
        )


async def delete_schedule_assignments_for_week(
    week_id: int,
    group="exotec_2",
):
    tables = get_group_tables(group)

    async with _pool.acquire() as conn:
        result = await conn.execute(
            f"""
            DELETE FROM {tables["schedule_assignments"]}
            WHERE week_id = $1
            """,
            week_id,
        )

        await conn.execute(
            f"""
            DELETE FROM {tables["schedule_reserves"]}
            WHERE week_id = $1
            """,
            week_id,
        )

        return result


async def delete_schedule_assignment(
    week_id: int,
    work_date,
    station: int,
    group="exotec_2",
):
    tables = get_group_tables(group)

    async with _pool.acquire() as conn:
        row = await conn.fetchrow(
            f"""
            DELETE FROM {tables["schedule_assignments"]}
            WHERE week_id = $1
              AND work_date = $2
              AND station = $3
            RETURNING id, week_id, work_date, worker_id, station, shift
            """,
            week_id,
            work_date,
            station,
        )

        return dict(row) if row else None

async def get_lunch_settings(
    week_id: int,
    group="exotec_2",
):
    tables = get_group_tables(group)

    async with _pool.acquire() as conn:
        rows = await conn.fetch(
            f"""
            SELECT
                ls.id,
                ls.week_id,
                ls.shift,
                ls.pair_number,
                ls.worker1_id,
                w1.name AS worker1_name,
                ls.worker2_id,
                w2.name AS worker2_name,
                ls.start_time
            FROM {tables["lunch_settings"]} ls
            LEFT JOIN {tables["workers"]} w1 ON w1.id = ls.worker1_id
            LEFT JOIN {tables["workers"]} w2 ON w2.id = ls.worker2_id
            WHERE ls.week_id = $1
            ORDER BY ls.shift, ls.pair_number
            """,
            week_id,
        )

        return [dict(row) for row in rows]


async def set_lunch_setting(
    week_id: int,
    shift: int,
    pair_number: int,
    worker1_id: int | None,
    worker2_id: int | None,
    start_time,
    group="exotec_2",
):
    tables = get_group_tables(group)

    async with _pool.acquire() as conn:
        row = await conn.fetchrow(
            f"""
            INSERT INTO {tables["lunch_settings"]} (
                week_id,
                shift,
                pair_number,
                worker1_id,
                worker2_id,
                start_time
            )
            VALUES ($1, $2, $3, $4, $5, $6)
            ON CONFLICT (week_id, shift, pair_number)
            DO UPDATE SET
                worker1_id = EXCLUDED.worker1_id,
                worker2_id = EXCLUDED.worker2_id,
                start_time = EXCLUDED.start_time
            RETURNING
                id,
                week_id,
                shift,
                pair_number,
                worker1_id,
                worker2_id,
                start_time
            """,
            week_id,
            shift,
            pair_number,
            worker1_id,
            worker2_id,
            start_time,
        )

        return dict(row) if row else None
