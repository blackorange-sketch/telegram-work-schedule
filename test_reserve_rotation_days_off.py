import asyncio
import os
from datetime import date, timedelta

import asyncpg
import bot.database as db


SLUG = "zz_test_rotation_off_20261009"
WEEK_START = date(2026, 10, 5)


async def main():
    database_url = os.environ.get("DATABASE_URL", "")
    if "telegram_schedule_test" not in database_url:
        raise RuntimeError(
            "Зупинка: DATABASE_URL має вказувати на telegram_schedule_test"
        )

    pool = await asyncpg.create_pool(database_url)
    db._pool = pool
    created = False

    try:
        async with pool.acquire() as conn:
            exists = await conn.fetchval(
                "SELECT EXISTS(SELECT 1 FROM work_groups WHERE slug=$1)",
                SLUG,
            )
            if exists:
                raise RuntimeError(
                    f"Група {SLUG} вже існує; зупинка без змін."
                )

            group = await conn.fetchrow(
                """
                INSERT INTO work_groups (slug, name, sort_order)
                VALUES ($1, $2, 999)
                RETURNING id
                """,
                SLUG,
                "Temporary rotation with days off test",
            )
            created = True
            group_id = group["id"]

            for station in range(1, 6):
                await conn.execute(
                    """
                    INSERT INTO work_group_stations
                        (group_id, station_number, active)
                    VALUES ($1, $2, TRUE)
                    """,
                    group_id,
                    station,
                )

            ordinary_ids = []
            for number in range(1, 8):
                worker_id = await conn.fetchval(
                    """
                    INSERT INTO group_workers
                        (group_id, team_code, name, is_reserve)
                    VALUES ($1, 'A', $2, FALSE)
                    RETURNING id
                    """,
                    group_id,
                    f"Days-off worker {number}",
                )
                ordinary_ids.append(worker_id)

            fixed_id = await conn.fetchval(
                """
                INSERT INTO group_workers
                    (group_id, team_code, name, is_reserve)
                VALUES ($1, 'A', 'Permanent reserve', TRUE)
                RETURNING id
                """,
                group_id,
            )

            # Worker 1 is absent Monday; worker 2 Wednesday;
            # worker 3 Friday.
            absences = [
                (ordinary_ids[0], WEEK_START),
                (ordinary_ids[1], WEEK_START + timedelta(days=2)),
                (ordinary_ids[2], WEEK_START + timedelta(days=4)),
            ]
            for worker_id, work_date in absences:
                await conn.execute(
                    """
                    INSERT INTO group_worker_days_off
                        (group_id, worker_id, work_date)
                    VALUES ($1, $2, $3)
                    """,
                    group_id,
                    worker_id,
                    work_date,
                )

        await db.set_group_schedule_settings(SLUG, WEEK_START, 3)
        week = await db.get_or_create_schedule_week(WEEK_START)
        result = await db.generate_group_schedule_assignments(
            week["id"], WEEK_START, SLUG
        )
        print("Результат генератора:", result)

        async with pool.acquire() as conn:
            assignments = await conn.fetch(
                """
                SELECT work_date, worker_id, station_id
                FROM group_schedule_assignments
                WHERE group_id=$1 AND week_id=$2 AND team_code='A'
                ORDER BY work_date, worker_id
                """,
                group_id,
                week["id"],
            )

            reserves = await conn.fetch(
                """
                SELECT work_date, worker_id
                FROM group_schedule_reserves
                WHERE group_id=$1 AND week_id=$2 AND team_code='A'
                ORDER BY work_date, worker_id
                """,
                group_id,
                week["id"],
            )

            daily_assignments = await conn.fetch(
                """
                SELECT work_date, COUNT(*) AS amount
                FROM group_schedule_assignments
                WHERE group_id=$1 AND week_id=$2 AND team_code='A'
                GROUP BY work_date ORDER BY work_date
                """,
                group_id,
                week["id"],
            )

            daily_reserves = await conn.fetch(
                """
                SELECT work_date, COUNT(*) AS amount
                FROM group_schedule_reserves
                WHERE group_id=$1 AND week_id=$2 AND team_code='A'
                GROUP BY work_date ORDER BY work_date
                """,
                group_id,
                week["id"],
            )

            absent_assignments = await conn.fetch(
                """
                SELECT a.work_date, a.worker_id
                FROM group_schedule_assignments a
                JOIN group_worker_days_off d
                  ON d.group_id=a.group_id
                 AND d.worker_id=a.worker_id
                 AND d.work_date=a.work_date
                WHERE a.group_id=$1 AND a.week_id=$2
                """,
                group_id,
                week["id"],
            )

            absent_reserves = await conn.fetch(
                """
                SELECT r.work_date, r.worker_id
                FROM group_schedule_reserves r
                JOIN group_worker_days_off d
                  ON d.group_id=r.group_id
                 AND d.worker_id=r.worker_id
                 AND d.work_date=r.work_date
                WHERE r.group_id=$1 AND r.week_id=$2
                """,
                group_id,
                week["id"],
            )

            fixed_assignments = await conn.fetchval(
                """
                SELECT COUNT(*)
                FROM group_schedule_assignments
                WHERE group_id=$1 AND week_id=$2 AND worker_id=$3
                """,
                group_id,
                week["id"],
                fixed_id,
            )

            fixed_reserves = await conn.fetchval(
                """
                SELECT COUNT(*)
                FROM group_schedule_reserves
                WHERE group_id=$1 AND week_id=$2 AND worker_id=$3
                """,
                group_id,
                week["id"],
                fixed_id,
            )

            ordinary_reserve_counts = await conn.fetch(
                """
                SELECT w.id, w.name, COUNT(r.worker_id) AS reserve_days
                FROM group_workers w
                LEFT JOIN group_schedule_reserves r
                  ON r.group_id=w.group_id
                 AND r.worker_id=w.id
                 AND r.week_id=$2
                WHERE w.group_id=$1 AND w.is_reserve=FALSE
                GROUP BY w.id, w.name
                ORDER BY w.name
                """,
                group_id,
                week["id"],
            )

        print("Призначень за днями:", [r["amount"] for r in daily_assignments])
        print("Резервістів за днями:", [r["amount"] for r in daily_reserves])
        print("Призначень у дні відсутності:", len(absent_assignments))
        print("Резервів у дні відсутності:", len(absent_reserves))
        print("Призначень постійного резервіста:", fixed_assignments)
        print("Днів постійного резерву:", fixed_reserves)
        print(
            "Резервні дні звичайних працівників:",
            [r["reserve_days"] for r in ordinary_reserve_counts],
        )

        if absent_assignments:
            raise RuntimeError("Помилка: відсутній працівник призначений на станцію")
        if absent_reserves:
            raise RuntimeError("Помилка: відсутній працівник включений у резерв")
        if fixed_assignments != 0:
            raise RuntimeError("Помилка: постійний резервіст призначений на станцію")
        if fixed_reserves != 5:
            raise RuntimeError(
                f"Очікувалося 5 днів постійного резерву, отримано {fixed_reserves}"
            )
        if [r["amount"] for r in daily_assignments] != [5, 5, 5, 5, 5]:
            raise RuntimeError("Очікується по 5 призначень на станції щодня")
        if [r["amount"] for r in daily_reserves] != [2, 3, 2, 3, 2]:
            raise RuntimeError("Очікується 3 резервісти щодня: 1 постійний + 2 звичайні")
        if result["assignments"] != 25 or result["reserves"] != 12:
            raise RuntimeError("Неочікувана загальна кількість призначень/резервів")

        print("ТЕСТ ВІДПУСТОК І ПОСТІЙНОГО РЕЗЕРВУ ПРОЙДЕНО")

    finally:
        try:
            if created:
                async with pool.acquire() as conn:
                    await conn.execute(
                        "DELETE FROM work_groups WHERE slug=$1",
                        SLUG,
                    )
                print("Тимчасову групу видалено")
        finally:
            await pool.close()
            db._pool = None


asyncio.run(main())
