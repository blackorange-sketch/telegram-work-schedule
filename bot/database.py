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



async def get_work_groups(active_only: bool = True):
    async with _pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT id, slug, name, active, sort_order
            FROM work_groups
            WHERE ($1::boolean = FALSE OR active = TRUE)
            ORDER BY sort_order, name
            """,
            active_only,
        )
        return [dict(row) for row in rows]


async def get_work_group_stations(
    group_slug: str,
    active_only: bool = True,
):
    async with _pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT s.id, s.station_number, s.label, s.active
            FROM work_group_stations AS s
            JOIN work_groups AS g ON g.id = s.group_id
            WHERE g.slug = $1
              AND ($2::boolean = FALSE OR s.active = TRUE)
            ORDER BY s.station_number
            """,
            group_slug,
            active_only,
        )
        return [dict(row) for row in rows]



async def get_group_worker_days_off(group_slug, start_date, end_date):
    async with _pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT d.worker_id, d.work_date
            FROM group_worker_days_off AS d
            JOIN work_groups AS g ON g.id = d.group_id
            WHERE g.slug = $1
              AND d.work_date BETWEEN $2 AND $3
            ORDER BY d.work_date, d.worker_id
        """, group_slug, start_date, end_date)
        return [dict(row) for row in rows]


async def get_group_workers(group_slug: str, team_code: str | None = None):
    async with _pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT w.id, w.name, w.team_code, w.is_reserve,
                   w.reserve_number, w.active
            FROM group_workers AS w
            JOIN work_groups AS g ON g.id = w.group_id
            WHERE g.slug = $1
              AND w.active = TRUE
              AND ($2::text IS NULL OR w.team_code = $2)
            ORDER BY w.team_code, w.is_reserve DESC, w.id
        """, group_slug, team_code)
        return [dict(row) for row in rows]


async def add_group_worker(
    group_slug: str, name: str, team_code: str, is_reserve: bool = False
):
    team_code = team_code.strip().upper()
    if team_code not in ("A", "B", "C"):
        raise ValueError("Бригада має бути A, B або C")

    async with _pool.acquire() as conn:
        row = await conn.fetchrow("""
            INSERT INTO group_workers (group_id, name, team_code, is_reserve)
            SELECT id, $2, $3, $4
            FROM work_groups
            WHERE slug = $1 AND active = TRUE
            RETURNING id, name, team_code, is_reserve,
                      reserve_number, active
        """, group_slug, name, team_code, is_reserve)

        if row:
            return dict(row)

        exists = await conn.fetchval(
            "SELECT EXISTS(SELECT 1 FROM work_groups WHERE slug = $1)",
            group_slug,
        )
        if not exists:
            raise ValueError(f"Групу не знайдено: {group_slug}")
        raise ValueError(f"Група неактивна: {group_slug}")


async def update_group_worker(
    group_slug: str, worker_id: int, name: str,
    team_code: str, is_reserve: bool
):
    team_code = team_code.strip().upper()
    if team_code not in ("A", "B", "C"):
        raise ValueError("Бригада має бути A, B або C")

    async with _pool.acquire() as conn:
        row = await conn.fetchrow("""
            UPDATE group_workers AS w
            SET name = $3, team_code = $4, is_reserve = $5
            FROM work_groups AS g
            WHERE g.id = w.group_id
              AND g.slug = $1
              AND w.id = $2
              AND w.active = TRUE
            RETURNING w.id, w.name, w.team_code, w.is_reserve,
                      w.reserve_number, w.active
        """, group_slug, worker_id, name, team_code, is_reserve)
        return dict(row) if row else None


async def deactivate_group_worker(group_slug: str, worker_id: int):
    async with _pool.acquire() as conn:
        row = await conn.fetchrow("""
            UPDATE group_workers AS w
            SET active = FALSE
            FROM work_groups AS g
            WHERE g.id = w.group_id
              AND g.slug = $1
              AND w.id = $2
              AND w.active = TRUE
            RETURNING w.id, w.name, w.team_code, w.is_reserve,
                      w.reserve_number, w.active
        """, group_slug, worker_id)
        return dict(row) if row else None


async def set_group_worker_reserve(
    group_slug: str, worker_id: int, is_reserve: bool
):
    async with _pool.acquire() as conn:
        row = await conn.fetchrow("""
            UPDATE group_workers AS w
            SET is_reserve = $3
            FROM work_groups AS g
            WHERE g.id = w.group_id
              AND g.slug = $1
              AND w.id = $2
              AND w.active = TRUE
            RETURNING w.id, w.name, w.team_code, w.is_reserve,
                      w.reserve_number, w.active
        """, group_slug, worker_id, is_reserve)
        return dict(row) if row else None


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


async def get_rotation_settings():
    """Спільна ротація змін для всіх груп (або None, якщо не налаштована)."""
    async with _pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT start_week, start_shift_slot, updated_at "
            "FROM rotation_settings WHERE id = 1"
        )
        return dict(row) if row else None


async def set_rotation_settings(start_week, start_shift_slot: int):
    if not 1 <= int(start_shift_slot) <= 3:
        raise ValueError("start_shift_slot має бути від 1 до 3")

    async with _pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO rotation_settings (id, start_week, start_shift_slot, updated_at)
            VALUES (1, $1, $2, NOW())
            ON CONFLICT (id) DO UPDATE SET
                start_week = EXCLUDED.start_week,
                start_shift_slot = EXCLUDED.start_shift_slot,
                updated_at = NOW()
            RETURNING start_week, start_shift_slot
            """,
            start_week, int(start_shift_slot),
        )
        return dict(row)


async def get_group_schedule_settings(group_slug):
    """Налаштування ротації для групи — тепер це спільна ротація всього складу."""
    async with _pool.acquire() as conn:
        exists = await conn.fetchval(
            "SELECT EXISTS(SELECT 1 FROM work_groups WHERE slug = $1)", group_slug
        )
    if not exists:
        return None

    rotation = await get_rotation_settings()
    return {
        "slug": group_slug,
        "start_week": rotation["start_week"] if rotation else None,
        "start_shift_slot": rotation["start_shift_slot"] if rotation else None,
        "global": True,
    }


async def set_group_schedule_settings(
    group_slug, start_week, start_shift_slot: int
):
    """Залишено для сумісності: змінює спільну ротацію для всіх груп."""
    async with _pool.acquire() as conn:
        exists = await conn.fetchval(
            "SELECT EXISTS(SELECT 1 FROM work_groups WHERE slug = $1)", group_slug
        )
    if not exists:
        raise ValueError(f"Групу не знайдено: {group_slug}")
    return await set_rotation_settings(start_week, start_shift_slot)


def team_slots_for_week(rotation, week_start):
    """Зміна кожної бригади на тижні week_start за спільною ротацією."""
    if not rotation or rotation.get("start_week") is None:
        return None
    weeks_diff = (week_start - rotation["start_week"]).days // 7
    phase = ((rotation["start_shift_slot"] - 1 - weeks_diff) % 3) + 1
    return dict(ROTATION_PHASES[phase])


ROTATION_PHASES = {
    3: {"C": 1, "A": 2, "B": 3},
    2: {"A": 1, "B": 2, "C": 3},
    1: {"B": 1, "C": 2, "A": 3},
}


async def get_group_shift_for_week(group_slug, week_start):
    settings = await get_group_schedule_settings(group_slug)

    if not settings:
        return None

    start_week = settings["start_week"]
    start_slot = settings["start_shift_slot"]

    if start_week is None or start_slot is None:
        return None

    weeks_diff = (week_start - start_week).days // 7
    return ((start_slot - 1 - weeks_diff) % 3) + 1


async def get_group_team_shift_slots(group_slug, week_start):
    phase = await get_group_shift_for_week(group_slug, week_start)
    if phase is None:
        return None

    rotations = {
        3: {"C": 1, "A": 2, "B": 3},
        2: {"A": 1, "B": 2, "C": 3},
        1: {"B": 1, "C": 2, "A": 3},
    }
    return rotations[phase]


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





async def get_group_schedule_assignments(week_id, group_slug):
    async with _pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT
                a.id,
                a.week_id,
                a.work_date,
                a.worker_id,
                w.name AS worker_name,
                s.station_number AS station,
                a.shift_slot AS shift,
                a.team_code
            FROM group_schedule_assignments AS a
            JOIN work_groups AS g ON g.id = a.group_id
            JOIN group_workers AS w
              ON w.id = a.worker_id
             AND w.group_id = a.group_id
             AND w.team_code = a.team_code
            JOIN work_group_stations AS s
              ON s.id = a.station_id
             AND s.group_id = a.group_id
            WHERE a.week_id = $1
              AND g.slug = $2
            ORDER BY a.work_date, a.shift_slot, s.station_number
        """, week_id, group_slug)
        return [dict(row) for row in rows]


async def get_group_schedule_reserves(week_id, group_slug):
    async with _pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT
                r.week_id,
                r.work_date,
                r.worker_id,
                w.name AS worker_name,
                r.team_code
            FROM group_schedule_reserves AS r
            JOIN work_groups AS g ON g.id = r.group_id
            JOIN group_workers AS w
              ON w.id = r.worker_id
             AND w.group_id = r.group_id
             AND w.team_code = r.team_code
            WHERE r.week_id = $1
              AND g.slug = $2
            ORDER BY r.work_date, r.team_code, r.worker_id
        """, week_id, group_slug)
        return [dict(row) for row in rows]


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


async def generate_group_schedule_assignments(
    week_id,
    week_start,
    group_slug,
):
    if week_start.weekday() != 0:
        raise ValueError("Початок тижня має бути понеділком")

    team_slots = await get_group_team_shift_slots(group_slug, week_start)
    if not team_slots:
        raise ValueError("Спочатку налаштуйте ротацію змін")

    async with _pool.acquire() as conn:
        async with conn.transaction():
            group = await conn.fetchrow("""
                SELECT id
                FROM work_groups
                WHERE slug = $1 AND active = TRUE
            """, group_slug)

            if not group:
                raise ValueError(
                    f"Активну групу не знайдено: {group_slug}"
                )

            group_id = group["id"]

            week = await conn.fetchrow("""
                SELECT id, week_start
                FROM schedule_weeks
                WHERE id = $1
            """, week_id)

            if not week or week["week_start"] != week_start:
                raise ValueError(
                    "week_id не відповідає вказаному week_start"
                )

            stations = await conn.fetch("""
                SELECT id, station_number
                FROM work_group_stations
                WHERE group_id = $1 AND active = TRUE
                ORDER BY station_number
            """, group_id)

            if not stations:
                raise ValueError(
                    f"У групі {group_slug} немає активних станцій"
                )

            workers = await conn.fetch("""
                SELECT id, team_code, is_reserve
                FROM group_workers
                WHERE group_id = $1 AND active = TRUE
                ORDER BY team_code, id
            """, group_id)

            if not workers:
                raise ValueError(
                    f"У групі {group_slug} немає активних працівників"
                )

            days_off_rows = await conn.fetch("""
                SELECT worker_id, work_date
                FROM group_worker_days_off
                WHERE group_id = $1
                  AND work_date BETWEEN $2 AND $3
            """, group_id, week_start, week_start + timedelta(days=4))

            days_off = {
                (row["worker_id"], row["work_date"])
                for row in days_off_rows
            }

            # Видаляємо тільки розклад цієї групи та цього тижня.
            await conn.execute("""
                DELETE FROM group_schedule_assignments
                WHERE group_id = $1 AND week_id = $2
            """, group_id, week_id)

            await conn.execute("""
                DELETE FROM group_schedule_reserves
                WHERE group_id = $1 AND week_id = $2
            """, group_id, week_id)

            station_ids = [row["id"] for row in stations]
            used_by_worker = {
                row["id"]: set() for row in workers
            }
            reserve_count = {
                row["id"]: 0 for row in workers
            }

            assignment_count = 0
            reserve_total = 0

            for team_code in ("A", "B", "C"):
                team_workers = [
                    row for row in workers
                    if row["team_code"].strip() == team_code
                ]
                shift_slot = team_slots[team_code]
                day_plans = []

                # Спочатку фіксуємо склад працівників і резерву на кожен день.
                for day_offset in range(5):
                    work_date = week_start + timedelta(days=day_offset)
                    eligible = [
                        row for row in team_workers
                        if (row["id"], work_date) not in days_off
                    ]

                    if not eligible:
                        continue

                    fixed_reserve = [
                        row for row in eligible if row["is_reserve"]
                    ]
                    ordinary = [
                        row for row in eligible if not row["is_reserve"]
                    ]

                    reserve_slots = max(
                        0, len(ordinary) - len(station_ids)
                    )
                    never_reserved = [
                        row for row in ordinary
                        if reserve_count[row["id"]] == 0
                    ]
                    previously_reserved = [
                        row for row in ordinary
                        if reserve_count[row["id"]] > 0
                    ]
                    random.shuffle(never_reserved)
                    random.shuffle(previously_reserved)

                    # Спершу ті, у кого далі цього тижня менше доступних днів:
                    # інакше працівник із вихідним у п'ятницю може лишитися
                    # без резерву, а хтось інший отримає його двічі.
                    def remaining_days(row):
                        return sum(
                            1 for later in range(day_offset + 1, 5)
                            if (
                                row["id"],
                                week_start + timedelta(days=later),
                            ) not in days_off
                        )

                    never_reserved.sort(key=remaining_days)
                    previously_reserved.sort(
                        key=lambda row: (
                            reserve_count[row["id"]],
                            remaining_days(row),
                        )
                    )

                    ordinary_reserves = (
                        never_reserved + previously_reserved
                    )[:reserve_slots]
                    reserve_workers = fixed_reserve + ordinary_reserves
                    ordinary_reserve_ids = {
                        row["id"] for row in ordinary_reserves
                    }
                    station_workers = [
                        row for row in ordinary
                        if row["id"] not in ordinary_reserve_ids
                    ]

                    day_plans.append({
                        "work_date": work_date,
                        "station_workers": station_workers,
                        "reserve_workers": reserve_workers,
                    })

                    for row in reserve_workers:
                        reserve_count[row["id"]] += 1

                # Пошук із поверненням назад: плануємо всі дні команди
                # разом, щоб не залишити п'ятницю без допустимого варіанта.
                def solve_week(day_index):
                    if day_index >= len(day_plans):
                        return True

                    plan = day_plans[day_index]
                    station_workers = plan["station_workers"]
                    candidate = {}

                    def assign_worker(worker_index, available_stations):
                        if worker_index >= len(station_workers):
                            plan["assignment"] = candidate.copy()
                            if solve_week(day_index + 1):
                                return True
                            plan.pop("assignment", None)
                            return False

                        worker = station_workers[worker_index]
                        worker_id = worker["id"]
                        choices = [
                            station_id
                            for station_id in available_stations
                            if station_id not in used_by_worker[worker_id]
                        ]
                        random.shuffle(choices)

                        for station_id in choices:
                            used_by_worker[worker_id].add(station_id)
                            candidate[worker_id] = station_id
                            remaining_stations = [
                                item for item in available_stations
                                if item != station_id
                            ]

                            if assign_worker(
                                worker_index + 1, remaining_stations
                            ):
                                return True

                            candidate.pop(worker_id, None)
                            used_by_worker[worker_id].remove(station_id)

                        return False

                    return assign_worker(0, station_ids[:])

                if not solve_week(0):
                    failed_date = (
                        day_plans[-1]["work_date"]
                        if day_plans else week_start
                    )
                    raise RuntimeError(
                        f"Не вдалося розподілити станції на весь тиждень "
                        f"для команди {team_code}; перевірено до {failed_date}"
                    )

                # Записуємо лише після успішного планування всіх днів команди.
                for plan in day_plans:
                    work_date = plan["work_date"]
                    assignment = plan["assignment"]
                    reserve_workers = plan["reserve_workers"]

                    assignment_rows = [
                        (
                            group_id,
                            team_code,
                            shift_slot,
                            week_id,
                            work_date,
                            worker_id,
                            station_id,
                        )
                        for worker_id, station_id in assignment.items()
                    ]

                    if assignment_rows:
                        await conn.executemany("""
                            INSERT INTO group_schedule_assignments (
                                group_id, team_code, shift_slot,
                                week_id, work_date, worker_id, station_id
                            )
                            VALUES ($1, $2, $3, $4, $5, $6, $7)
                        """, assignment_rows)

                    reserve_rows = [
                        (
                            group_id,
                            team_code,
                            week_id,
                            work_date,
                            row["id"],
                        )
                        for row in reserve_workers
                    ]

                    if reserve_rows:
                        await conn.executemany("""
                            INSERT INTO group_schedule_reserves (
                                group_id, team_code, week_id,
                                work_date, worker_id
                            )
                            VALUES ($1, $2, $3, $4, $5)
                        """, reserve_rows)

                    assignment_count += len(assignment_rows)
                    reserve_total += len(reserve_rows)

            return {
                "group": group_slug,
                "week_start": week_start.isoformat(),
                "assignments": assignment_count,
                "reserves": reserve_total,
            }


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


async def set_group_schedule_assignment(
    week_id: int,
    work_date,
    worker_id: int,
    station: int,
    shift_slot: int,
    group_slug: str,
):
    from datetime import date as date_type

    if shift_slot not in (1, 2, 3):
        raise ValueError("Некоректна зміна")

    if isinstance(work_date, str):
        work_date = date_type.fromisoformat(work_date)

    async with _pool.acquire() as conn:
        async with conn.transaction():
            group = await conn.fetchrow(
                "SELECT id FROM work_groups WHERE slug = $1 AND active = TRUE",
                group_slug,
            )
            if not group:
                raise ValueError("Групу не знайдено або вона неактивна")

            group_id = group["id"]

            week = await conn.fetchrow(
                "SELECT week_start FROM schedule_weeks WHERE id = $1",
                week_id,
            )
            if not week:
                raise ValueError("Тиждень не знайдено")

            week_start = week["week_start"]
            if not (week_start <= work_date <= week_start.fromordinal(
                week_start.toordinal() + 6
            )):
                raise ValueError("Дата не належить до вибраного тижня")

            worker = await conn.fetchrow(
                """
                SELECT id, team_code
                FROM group_workers
                WHERE id = $1 AND group_id = $2 AND active = TRUE
                """,
                worker_id, group_id,
            )
            if not worker:
                raise ValueError("Працівника не знайдено в цій групі")

            day_off = await conn.fetchval(
                """
                SELECT EXISTS(
                    SELECT 1 FROM group_worker_days_off
                    WHERE group_id = $1 AND worker_id = $2 AND work_date = $3
                )
                """,
                group_id, worker_id, work_date,
            )
            if day_off:
                raise ValueError("Працівник відсутній у цей день")

            station_row = await conn.fetchrow(
                """
                SELECT id
                FROM work_group_stations
                WHERE group_id = $1
                  AND station_number = $2
                  AND active = TRUE
                """,
                group_id, station,
            )
            if not station_row:
                raise ValueError("Станцію не знайдено в цій групі")

            team_code = worker["team_code"]

            rotation = await conn.fetchrow(
                """
                SELECT start_week, start_shift_slot
                FROM rotation_settings
                WHERE id = 1
                """
            )
            if (
                not rotation
                or rotation["start_week"] is None
                or rotation["start_shift_slot"] is None
            ):
                raise ValueError("Спочатку налаштуйте ротацію змін")

            weeks_diff = (week_start - rotation["start_week"]).days // 7
            phase = (
                (rotation["start_shift_slot"] - 1 - weeks_diff) % 3
            ) + 1

            rotations = {
                3: {"C": 1, "A": 2, "B": 3},
                2: {"A": 1, "B": 2, "C": 3},
                1: {"B": 1, "C": 2, "A": 3},
            }
            shift_slot = rotations[phase][team_code]

            current = await conn.fetchrow(
                """
                SELECT id, station_id
                FROM group_schedule_assignments
                WHERE group_id = $1 AND team_code = $2
                  AND week_id = $3 AND work_date = $4
                  AND worker_id = $5
                FOR UPDATE
                """,
                group_id, team_code, week_id, work_date, worker_id,
            )

            occupied = await conn.fetchrow(
                """
                SELECT id, worker_id, team_code, shift_slot, station_id
                FROM group_schedule_assignments
                WHERE group_id = $1 AND team_code = $2
                  AND week_id = $3 AND work_date = $4
                  AND station_id = $5
                FOR UPDATE
                """,
                group_id, team_code, week_id, work_date, station_row["id"],
            )



            if occupied and occupied["worker_id"] != worker_id:
                if current:
                    # Обмін станціями двох уже призначених працівників.
                    await conn.execute(
                        """
                        DELETE FROM group_schedule_assignments
                        WHERE id = ANY($1::bigint[])
                        """,
                        [current["id"], occupied["id"]],
                    )
                    await conn.executemany(
                        """
                        INSERT INTO group_schedule_assignments
                            (group_id, team_code, shift_slot, week_id,
                             work_date, worker_id, station_id)
                        VALUES ($1, $2, $3, $4, $5, $6, $7)
                        """,
                        [
                            (
                                group_id, team_code, shift_slot, week_id,
                                work_date, worker_id, station_row["id"],
                            ),
                            (
                                group_id, team_code, occupied["shift_slot"],
                                week_id, work_date, occupied["worker_id"],
                                current["station_id"],
                            ),
                        ],
                    )
                else:
                    # Попередній працівник переходить у резерв на цю дату.
                    await conn.execute(
                        """
                        INSERT INTO group_schedule_reserves
                            (group_id, team_code, week_id, work_date, worker_id)
                        VALUES ($1, $2, $3, $4, $5)
                        ON CONFLICT
                            (group_id, team_code, week_id, work_date, worker_id)
                        DO NOTHING
                        """,
                        group_id, occupied["team_code"], week_id,
                        work_date, occupied["worker_id"],
                    )
                    # Новий працівник займає вибрану станцію.
                    await conn.execute(
                        """
                        UPDATE group_schedule_assignments
                        SET worker_id = $1, shift_slot = $2
                        WHERE id = $3
                        """,
                        worker_id, shift_slot, occupied["id"],
                    )
            elif current:
                await conn.execute(
                    """
                    UPDATE group_schedule_assignments
                    SET station_id = $1, shift_slot = $2
                    WHERE id = $3
                    """,
                    station_row["id"], shift_slot, current["id"],
                )
            else:
                await conn.execute(
                    """
                    INSERT INTO group_schedule_assignments
                        (group_id, team_code, shift_slot, week_id,
                         work_date, worker_id, station_id)
                    VALUES ($1, $2, $3, $4, $5, $6, $7)
                    """,
                    group_id, team_code, shift_slot, week_id,
                    work_date, worker_id, station_row["id"],
                )

            # Прибрати з резерву працівника, якого призначили на станцію.
            await conn.execute(
                """
                DELETE FROM group_schedule_reserves
                WHERE group_id = $1 AND week_id = $2
                  AND work_date = $3 AND worker_id = $4
                """,
                group_id, week_id, work_date, worker_id,
            )

            row = await conn.fetchrow(
                """
                SELECT a.id, a.week_id, a.work_date, a.worker_id,
                       w.name AS worker_name,
                       s.station_number AS station,
                       a.shift_slot AS shift, a.team_code
                FROM group_schedule_assignments a
                JOIN group_workers w
                  ON w.id = a.worker_id AND w.group_id = a.group_id
                JOIN work_group_stations s
                  ON s.id = a.station_id AND s.group_id = a.group_id
                WHERE a.group_id = $1 AND a.week_id = $2
                  AND a.work_date = $3 AND a.worker_id = $4
                """,
                group_id, week_id, work_date, worker_id,
            )
            return dict(row) if row else None


async def delete_group_schedule_assignment(
    week_id: int,
    work_date,
    station: int,
    group_slug: str,
    worker_id: int,
):
    from datetime import date as date_type

    if isinstance(work_date, str):
        work_date = date_type.fromisoformat(work_date)

    async with _pool.acquire() as conn:
        # Знімаємо лише одного працівника: на станції в той самий день
        # можуть стояти працівники інших команд (змін).
        row = await conn.fetchrow(
            """
            DELETE FROM group_schedule_assignments a
            USING work_groups g, work_group_stations s
            WHERE a.group_id = g.id
              AND s.id = a.station_id
              AND s.group_id = a.group_id
              AND g.slug = $1
              AND a.week_id = $2
              AND a.work_date = $3
              AND s.station_number = $4
              AND a.worker_id = $5
            RETURNING a.id, a.week_id, a.work_date, a.worker_id,
                      s.station_number AS station,
                      a.shift_slot AS shift, a.team_code
            """,
            group_slug, week_id, work_date, station, worker_id,
        )
        return dict(row) if row else None


# ---------------------------------------------------------------------------
# Вихідні, резерв, очищення тижня й обіди для нової моделі груп (group_*).
# ---------------------------------------------------------------------------

async def _get_active_group_id(conn, group_slug):
    group_id = await conn.fetchval(
        "SELECT id FROM work_groups WHERE slug = $1 AND active = TRUE",
        group_slug,
    )
    if group_id is None:
        raise ValueError("Групу не знайдено або вона неактивна")
    return group_id


async def _get_group_worker(conn, group_id, worker_id):
    worker = await conn.fetchrow(
        """
        SELECT id, team_code
        FROM group_workers
        WHERE id = $1 AND group_id = $2 AND active = TRUE
        """,
        worker_id, group_id,
    )
    if worker is None:
        raise ValueError("Працівника не знайдено в цій групі")
    return worker


async def set_group_worker_day_off(group_slug, worker_id, work_date):
    async with _pool.acquire() as conn:
        async with conn.transaction():
            group_id = await _get_active_group_id(conn, group_slug)
            await _get_group_worker(conn, group_id, worker_id)

            row = await conn.fetchrow(
                """
                INSERT INTO group_worker_days_off (group_id, worker_id, work_date)
                VALUES ($1, $2, $3)
                ON CONFLICT (worker_id, work_date)
                DO UPDATE SET work_date = EXCLUDED.work_date
                RETURNING id, worker_id, work_date
                """,
                group_id, worker_id, work_date,
            )

            # Відсутній працівник не може бути ні на станції, ні в резерві.
            for table in ("group_schedule_assignments", "group_schedule_reserves"):
                await conn.execute(
                    f"""
                    DELETE FROM {table}
                    WHERE group_id = $1 AND worker_id = $2 AND work_date = $3
                    """,
                    group_id, worker_id, work_date,
                )

            return dict(row)


async def delete_group_worker_day_off(group_slug, worker_id, work_date):
    async with _pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            DELETE FROM group_worker_days_off d
            USING work_groups g
            WHERE g.id = d.group_id
              AND g.slug = $1
              AND d.worker_id = $2
              AND d.work_date = $3
            RETURNING d.id, d.worker_id, d.work_date
            """,
            group_slug, worker_id, work_date,
        )
        return dict(row) if row else None


async def set_group_schedule_reserve(week_id, work_date, worker_id, group_slug):
    async with _pool.acquire() as conn:
        async with conn.transaction():
            group_id = await _get_active_group_id(conn, group_slug)
            worker = await _get_group_worker(conn, group_id, worker_id)

            day_off = await conn.fetchval(
                """
                SELECT EXISTS(
                    SELECT 1 FROM group_worker_days_off
                    WHERE group_id = $1 AND worker_id = $2 AND work_date = $3
                )
                """,
                group_id, worker_id, work_date,
            )
            if day_off:
                raise ValueError("Працівник відсутній у цей день")

            # Працівник у резерві не стоїть на станції цього дня.
            await conn.execute(
                """
                DELETE FROM group_schedule_assignments
                WHERE group_id = $1 AND week_id = $2
                  AND work_date = $3 AND worker_id = $4
                """,
                group_id, week_id, work_date, worker_id,
            )
            await conn.execute(
                """
                INSERT INTO group_schedule_reserves
                    (group_id, team_code, week_id, work_date, worker_id)
                VALUES ($1, $2, $3, $4, $5)
                ON CONFLICT (group_id, team_code, week_id, work_date, worker_id)
                DO NOTHING
                """,
                group_id, worker["team_code"], week_id, work_date, worker_id,
            )


async def delete_group_schedule_reserve(week_id, work_date, worker_id, group_slug):
    async with _pool.acquire() as conn:
        result = await conn.execute(
            """
            DELETE FROM group_schedule_reserves r
            USING work_groups g
            WHERE g.id = r.group_id
              AND g.slug = $1
              AND r.week_id = $2
              AND r.work_date = $3
              AND r.worker_id = $4
            """,
            group_slug, week_id, work_date, worker_id,
        )
        return result != "DELETE 0"


async def clear_group_schedule_week(week_id, group_slug):
    async with _pool.acquire() as conn:
        async with conn.transaction():
            group_id = await _get_active_group_id(conn, group_slug)
            assignments = await conn.execute(
                """
                DELETE FROM group_schedule_assignments
                WHERE group_id = $1 AND week_id = $2
                """,
                group_id, week_id,
            )
            reserves = await conn.execute(
                """
                DELETE FROM group_schedule_reserves
                WHERE group_id = $1 AND week_id = $2
                """,
                group_id, week_id,
            )
            return {
                "assignments": int(assignments.split()[-1]),
                "reserves": int(reserves.split()[-1]),
            }


DEFAULT_LUNCH_START_TIMES = {1: "10:00", 2: "18:00", 3: "02:00"}
LUNCH_INTERVAL_MINUTES = 30


async def get_group_lunch(week_id, week_start, group_slug):
    """Обіди групи на тиждень: час початку змін, зміна кожної бригади
    цього тижня та склад обідніх груп кожної бригади."""
    team_slots = await get_group_team_shift_slots(group_slug, week_start)

    async with _pool.acquire() as conn:
        group_id = await _get_active_group_id(conn, group_slug)

        start_rows = await conn.fetch(
            """
            SELECT shift_slot, start_time
            FROM group_lunch_start_times
            WHERE group_id = $1
            """,
            group_id,
        )
        start_times = dict(DEFAULT_LUNCH_START_TIMES)
        for row in start_rows:
            start_times[row["shift_slot"]] = row["start_time"].strftime("%H:%M")

        rows = await conn.fetch(
            """
            SELECT m.team_code, m.pair_number, m.worker_id, w.name AS worker_name
            FROM group_lunch_members m
            JOIN group_workers w
              ON w.id = m.worker_id AND w.group_id = m.group_id
            WHERE m.group_id = $1 AND m.week_id = $2 AND w.active = TRUE
            ORDER BY m.team_code, m.pair_number, m.id
            """,
            group_id, week_id,
        )

    teams = {"A": [], "B": [], "C": []}
    for row in rows:
        team = row["team_code"].strip()
        pairs = teams[team]
        while len(pairs) < row["pair_number"]:
            pairs.append([])
        pairs[row["pair_number"] - 1].append(
            {"id": row["worker_id"], "name": row["worker_name"]}
        )
    # Порожні проміжні групи (якщо когось деактивували) прибираємо.
    teams = {team: [p for p in pairs if p] for team, pairs in teams.items()}

    return {
        "start_times": {str(k): v for k, v in sorted(start_times.items())},
        "interval_minutes": LUNCH_INTERVAL_MINUTES,
        "team_slots": team_slots,
        "teams": teams,
    }


async def set_group_lunch_team(week_id, group_slug, team_code, pairs):
    """Повністю замінює обідні групи бригади на тиждень.
    pairs — список груп, кожна група — список id працівників."""
    team_code = str(team_code).strip().upper()
    if team_code not in ("A", "B", "C"):
        raise ValueError("Бригада має бути A, B або C")

    cleaned = []
    seen = set()
    for pair in pairs:
        ids = [int(worker_id) for worker_id in pair]
        if not ids:
            continue
        for worker_id in ids:
            if worker_id in seen:
                raise ValueError("Працівник може бути лише в одній обідній групі")
            seen.add(worker_id)
        cleaned.append(ids)

    async with _pool.acquire() as conn:
        async with conn.transaction():
            group_id = await _get_active_group_id(conn, group_slug)

            for worker_id in seen:
                worker = await _get_group_worker(conn, group_id, worker_id)
                if worker["team_code"].strip() != team_code:
                    raise ValueError("Працівник не належить до цієї бригади")

            await conn.execute(
                """
                DELETE FROM group_lunch_members
                WHERE group_id = $1 AND week_id = $2 AND team_code = $3
                """,
                group_id, week_id, team_code,
            )
            await conn.executemany(
                """
                INSERT INTO group_lunch_members
                    (group_id, team_code, week_id, pair_number, worker_id)
                VALUES ($1, $2, $3, $4, $5)
                """,
                [
                    (group_id, team_code, week_id, number, worker_id)
                    for number, ids in enumerate(cleaned, start=1)
                    for worker_id in ids
                ],
            )

    return {"team_code": team_code, "pairs": len(cleaned), "workers": len(seen)}


async def set_group_lunch_start_times(group_slug, start_times):
    """start_times — словник {слот: "HH:MM"} для слотів 1..3."""
    from datetime import time as time_type

    parsed = {}
    for slot, value in start_times.items():
        slot = int(slot)
        if slot not in (1, 2, 3):
            raise ValueError("Некоректна зміна")
        try:
            parsed[slot] = time_type.fromisoformat(str(value))
        except ValueError:
            raise ValueError("Некоректний час обіду")

    async with _pool.acquire() as conn:
        async with conn.transaction():
            group_id = await _get_active_group_id(conn, group_slug)
            await conn.executemany(
                """
                INSERT INTO group_lunch_start_times (group_id, shift_slot, start_time)
                VALUES ($1, $2, $3)
                ON CONFLICT (group_id, shift_slot)
                DO UPDATE SET start_time = EXCLUDED.start_time
                """,
                [(group_id, slot, value) for slot, value in sorted(parsed.items())],
            )

    return {str(slot): value.strftime("%H:%M") for slot, value in sorted(parsed.items())}


# ---------------------------------------------------------------------------
# Керування групами (лише super admin): назва, активність, станції.
# ---------------------------------------------------------------------------

MAX_GROUP_STATIONS = 200


def parse_station_numbers(text):
    """«15-24» або «1-10, 12, 14» -> відсортований список унікальних номерів."""
    numbers = set()
    for part in str(text).replace(";", ",").split(","):
        part = part.strip().replace("–", "-").replace("—", "-")
        if not part:
            continue
        if "-" in part:
            first, _, last = part.partition("-")
            try:
                first, last = int(first), int(last)
            except ValueError:
                raise ValueError(f"Некоректний діапазон станцій: «{part}»")
            if first > last:
                first, last = last, first
            if last - first + 1 > MAX_GROUP_STATIONS:
                raise ValueError(f"Забагато станцій у діапазоні «{part}»")
            numbers.update(range(first, last + 1))
        else:
            try:
                numbers.add(int(part))
            except ValueError:
                raise ValueError(f"Некоректний номер станції: «{part}»")

    if not numbers:
        raise ValueError("Вкажіть хоча б одну станцію")
    if min(numbers) < 1 or max(numbers) > 9999:
        raise ValueError("Номери станцій мають бути від 1 до 9999")
    if len(numbers) > MAX_GROUP_STATIONS:
        raise ValueError(f"Не більше {MAX_GROUP_STATIONS} станцій у групі")
    return sorted(numbers)


def format_station_ranges(numbers):
    """[15,16,17,20] -> «15-17, 20»."""
    numbers = sorted(numbers)
    parts = []
    start = prev = None
    for number in numbers:
        if start is None:
            start = prev = number
        elif number == prev + 1:
            prev = number
        else:
            parts.append(f"{start}-{prev}" if prev > start else str(start))
            start = prev = number
    if start is not None:
        parts.append(f"{start}-{prev}" if prev > start else str(start))
    return ", ".join(parts)


async def get_work_groups_admin():
    async with _pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT g.id, g.slug, g.name, g.active, g.sort_order,
                   COALESCE(
                       array_agg(s.station_number ORDER BY s.station_number)
                       FILTER (WHERE s.active),
                       '{}'
                   ) AS stations,
                   (SELECT COUNT(*) FROM group_workers w
                    WHERE w.group_id = g.id AND w.active) AS workers
            FROM work_groups g
            LEFT JOIN work_group_stations s ON s.group_id = g.id
            GROUP BY g.id
            ORDER BY g.sort_order, g.name
            """
        )
    result = []
    for row in rows:
        item = dict(row)
        item["stations"] = list(item["stations"])
        item["stations_text"] = format_station_ranges(item["stations"])
        result.append(item)
    return result


def _clean_group_name(name):
    name = " ".join(str(name or "").split())
    if not name:
        raise ValueError("Вкажіть назву групи")
    if len(name) > 60:
        raise ValueError("Назва групи задовга (до 60 символів)")
    return name


async def _sync_group_stations(conn, group_id, numbers):
    # Станції, на які вже є призначення, не видаляємо, а вимикаємо:
    # історія розкладу лишається цілою.
    await conn.execute(
        """
        UPDATE work_group_stations
        SET active = (station_number = ANY($2::int[]))
        WHERE group_id = $1
        """,
        group_id, numbers,
    )
    await conn.execute(
        """
        INSERT INTO work_group_stations (group_id, station_number, label, active)
        SELECT $1, n, n::text, TRUE
        FROM unnest($2::int[]) AS n
        ON CONFLICT (group_id, station_number) DO UPDATE SET active = TRUE
        """,
        group_id, numbers,
    )


async def create_work_group(name, stations_text):
    import re

    name = _clean_group_name(name)
    numbers = parse_station_numbers(stations_text)

    base = re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_") or "group"
    if not re.match(r"^[a-z0-9]", base):
        base = "group_" + base

    async with _pool.acquire() as conn:
        async with conn.transaction():
            exists = await conn.fetchval(
                "SELECT EXISTS(SELECT 1 FROM work_groups WHERE lower(name) = lower($1))",
                name,
            )
            if exists:
                raise ValueError("Група з такою назвою вже існує")

            slug = base
            suffix = 2
            while await conn.fetchval(
                "SELECT EXISTS(SELECT 1 FROM work_groups WHERE slug = $1)", slug
            ):
                slug = f"{base}_{suffix}"
                suffix += 1

            sort_order = await conn.fetchval(
                "SELECT COALESCE(MAX(sort_order), 0) + 1 FROM work_groups"
            )
            group_id = await conn.fetchval(
                """
                INSERT INTO work_groups (slug, name, sort_order)
                VALUES ($1, $2, $3)
                RETURNING id
                """,
                slug, name, sort_order,
            )
            await conn.execute(
                """
                INSERT INTO group_schedule_settings (group_id)
                VALUES ($1)
                ON CONFLICT (group_id) DO NOTHING
                """,
                group_id,
            )
            await _sync_group_stations(conn, group_id, numbers)

    return {"slug": slug, "name": name, "stations": numbers}


async def update_work_group(slug, name=None, stations_text=None, active=None):
    numbers = parse_station_numbers(stations_text) if stations_text is not None else None
    if name is not None:
        name = _clean_group_name(name)

    async with _pool.acquire() as conn:
        async with conn.transaction():
            group_id = await conn.fetchval(
                "SELECT id FROM work_groups WHERE slug = $1", slug
            )
            if group_id is None:
                raise ValueError("Групу не знайдено")

            if name is not None:
                taken = await conn.fetchval(
                    """
                    SELECT EXISTS(
                        SELECT 1 FROM work_groups
                        WHERE lower(name) = lower($1) AND id <> $2
                    )
                    """,
                    name, group_id,
                )
                if taken:
                    raise ValueError("Група з такою назвою вже існує")
                await conn.execute(
                    "UPDATE work_groups SET name = $2 WHERE id = $1", group_id, name
                )

            if active is not None:
                if not active:
                    others = await conn.fetchval(
                        "SELECT COUNT(*) FROM work_groups WHERE active AND id <> $1",
                        group_id,
                    )
                    if others == 0:
                        raise ValueError("Не можна вимкнути останню активну групу")
                await conn.execute(
                    "UPDATE work_groups SET active = $2 WHERE id = $1",
                    group_id, bool(active),
                )

            if numbers is not None:
                await _sync_group_stations(conn, group_id, numbers)

    return {"slug": slug}
