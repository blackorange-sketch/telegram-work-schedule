import asyncio
import os
from datetime import date, timedelta

import asyncpg
import bot.database as db

WEEK_START = date(2026, 10, 5)
RUNS = 30

# Назва, кількість звичайних працівників, відсутності (номер працівника, день 0-4)
SCENARIOS = [
    ("zz_test_fair_rotation_20261009", 7, []),
    ("zz_test_fair_days_off_20261009", 7, [(1, 0), (2, 2), (3, 4)]),
]


async def run_scenario(pool, slug, workers_total, absences):
    created = False
    try:
        async with pool.acquire() as conn:
            exists = await conn.fetchval(
                "SELECT EXISTS(SELECT 1 FROM work_groups WHERE slug=$1)", slug
            )
            if exists:
                raise RuntimeError(f"Група {slug} вже існує; зупинка без змін.")
            group_id = await conn.fetchval(
                """
                INSERT INTO work_groups (slug, name, sort_order)
                VALUES ($1, 'Temporary reserve fairness test', 999)
                RETURNING id
                """,
                slug,
            )
            created = True
            for station in range(1, 6):
                await conn.execute(
                    """
                    INSERT INTO work_group_stations (group_id, station_number, active)
                    VALUES ($1, $2, TRUE)
                    """,
                    group_id,
                    station,
                )
            ids = []
            for number in range(1, workers_total + 1):
                ids.append(
                    await conn.fetchval(
                        """
                        INSERT INTO group_workers
                            (group_id, team_code, name, is_reserve)
                        VALUES ($1, 'A', $2, FALSE)
                        RETURNING id
                        """,
                        group_id,
                        f"Fair worker {number}",
                    )
                )
            for number, day in absences:
                await conn.execute(
                    """
                    INSERT INTO group_worker_days_off (group_id, worker_id, work_date)
                    VALUES ($1, $2, $3)
                    """,
                    group_id,
                    ids[number - 1],
                    WEEK_START + timedelta(days=day),
                )

        await db.set_group_schedule_settings(slug, WEEK_START, 3)
        week_id = (await db.get_or_create_schedule_week(WEEK_START))["id"]

        unfair = []
        for run in range(1, RUNS + 1):
            # Генератор сам очищає попередній результат цієї групи й тижня.
            await db.generate_group_schedule_assignments(week_id, WEEK_START, slug)
            async with pool.acquire() as conn:
                rows = await conn.fetch(
                    """
                    SELECT w.id, COUNT(r.worker_id) AS days
                    FROM group_workers w
                    LEFT JOIN group_schedule_reserves r
                      ON r.worker_id = w.id AND r.group_id = w.group_id
                     AND r.week_id = $2
                    WHERE w.group_id = $1
                    GROUP BY w.id ORDER BY w.id
                    """,
                    group_id,
                    week_id,
                )
            counts = [r["days"] for r in rows]
            if max(counts) - min(counts) > 1:
                unfair.append((run, counts))

        print(f"{slug}: нерівних запусків {len(unfair)}/{RUNS}")
        for run, counts in unfair[:3]:
            print(f"  запуск {run}: {counts}")
        return len(unfair)
    finally:
        if created:
            async with pool.acquire() as conn:
                await conn.execute("DELETE FROM work_groups WHERE slug=$1", slug)
            print(f"  Тимчасову групу {slug} видалено")


async def main():
    database_url = os.environ.get("DATABASE_URL", "")
    if "telegram_schedule_test" not in database_url:
        raise RuntimeError(
            "Зупинка: DATABASE_URL має вказувати на telegram_schedule_test"
        )
    pool = await asyncpg.create_pool(database_url)
    db._pool = pool
    try:
        total = 0
        for slug, workers_total, absences in SCENARIOS:
            total += await run_scenario(pool, slug, workers_total, absences)
        if total:
            raise RuntimeError(f"Нерівний розподіл резерву: {total} запусків")
        print("ТЕСТ РІВНОМІРНОСТІ РЕЗЕРВУ ПРОЙДЕНО")
    finally:
        await pool.close()
        db._pool = None


asyncio.run(main())
