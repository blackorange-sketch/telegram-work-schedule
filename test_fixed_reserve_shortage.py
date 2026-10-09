import asyncio
import os
from datetime import date

import asyncpg
import bot.database as db

SLUG = "zz_test_reserve_shortage_20261009"
WEEK_START = date(2026, 10, 5)


async def main():
    database_url = os.environ.get("DATABASE_URL", "")
    if "telegram_schedule_test" not in database_url:
        raise RuntimeError(
            "Зупинка: DATABASE_URL має вказувати на telegram_schedule_test"
        )

    pool = await asyncpg.create_pool(database_url)
    db._pool = pool
    group_id = None

    try:
        async with pool.acquire() as conn:
            exists = await conn.fetchval(
                "SELECT EXISTS(SELECT 1 FROM work_groups WHERE slug=$1)",
                SLUG,
            )
            if exists:
                raise RuntimeError(
                    f"Тестова група {SLUG} вже існує; зупинка без змін."
                )

            group = await conn.fetchrow(
                """
                INSERT INTO work_groups (slug, name, sort_order)
                VALUES ($1, $2, 999)
                RETURNING id
                """,
                SLUG,
                "Temporary fixed reserve test",
            )
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

            fixed_ids = []
            ordinary_ids = []

            # Одна команда: 5 станцій, 5 звичайних працівників
            # і 2 працівники, постійно позначені як резерв.
            for number in range(1, 4):
                worker_id = await conn.fetchval(
                    """
                    INSERT INTO group_workers
                        (group_id, team_code, name, is_reserve)
                    VALUES ($1, 'A', $2, FALSE)
                    RETURNING id
                    """,
                    group_id,
                    f"Ordinary {number}",
                )
                ordinary_ids.append(worker_id)

            for number in range(1, 3):
                worker_id = await conn.fetchval(
                    """
                    INSERT INTO group_workers
                        (group_id, team_code, name, is_reserve)
                    VALUES ($1, 'A', $2, TRUE)
                    RETURNING id
                    """,
                    group_id,
                    f"Fixed reserve {number}",
                )
                fixed_ids.append(worker_id)

        await db.set_group_schedule_settings(SLUG, WEEK_START, 1)
        week = await db.get_or_create_schedule_week(WEEK_START)
        result = await db.generate_group_schedule_assignments(
            week["id"], WEEK_START, SLUG
        )

        async with pool.acquire() as conn:
            assigned_fixed = await conn.fetch(
                """
                SELECT worker_id, work_date
                FROM group_schedule_assignments
                WHERE group_id=$1 AND week_id=$2
                  AND worker_id = ANY($3::bigint[])
                """,
                group_id,
                week["id"],
                fixed_ids,
            )

            reserve_fixed = await conn.fetchval(
                """
                SELECT COUNT(*)
                FROM group_schedule_reserves
                WHERE group_id=$1 AND week_id=$2
                  AND worker_id = ANY($3::bigint[])
                """,
                group_id,
                week["id"],
                fixed_ids,
            )

            ordinary_assigned = await conn.fetchval(
                """
                SELECT COUNT(*)
                FROM group_schedule_assignments
                WHERE group_id=$1 AND week_id=$2
                  AND worker_id = ANY($3::bigint[])
                """,
                group_id,
                week["id"],
                ordinary_ids,
            )

            station_count = await conn.fetchval(
                """
                SELECT COUNT(*)
                FROM work_group_stations
                WHERE group_id=$1 AND active=TRUE
                """,
                group_id,
            )

        print("Результат генератора:", result)
        print("Призначень постійного резерву:", len(assigned_fixed))
        print("Записів постійного резерву:", reserve_fixed)
        print("Призначень звичайних працівників:", ordinary_assigned)

        if assigned_fixed:
            raise AssertionError(
                "ПОМИЛКА: працівник із is_reserve=True отримав станцію"
            )

        # 2 постійні резервісти × 5 робочих днів.
        if reserve_fixed != 10:
            raise AssertionError(
                f"Очікувалося 10 записів постійного резерву, отримано {reserve_fixed}"
            )

        # П'ять звичайних працівників мають зайняти п'ять станцій
        # кожного з п'яти робочих днів.
        if ordinary_assigned != 15:
            raise AssertionError(
                f"Очікувалося 15 призначень звичайних працівників, "
                f"отримано {ordinary_assigned}"
            )

        # Щодня мають бути зайняті 3 різні станції з 5.
        async with pool.acquire() as conn:
            daily_counts = await conn.fetch(
                """
                SELECT d.work_date,
                       COUNT(DISTINCT a.station_id) AS occupied
                FROM generate_series(
                    $3::date, $3::date + INTERVAL '4 days', INTERVAL '1 day'
                ) AS d(work_date)
                LEFT JOIN group_schedule_assignments a
                  ON a.group_id = $1
                 AND a.week_id = $2
                 AND a.work_date = d.work_date::date
                GROUP BY d.work_date
                ORDER BY d.work_date
                """,
                group_id,
                week["id"],
                WEEK_START,
            )

        if len(daily_counts) != 5:
            raise AssertionError(
                f"Очікувалося 5 робочих днів, отримано {len(daily_counts)}"
            )

        for row in daily_counts:
            if row["occupied"] != 3:
                raise AssertionError(
                    f"{row['work_date']}: очікувалося 3 зайняті станції, "
                    f"отримано {row['occupied']}"
                )
            print(f"{row['work_date']}: 3 зайняті, 2 вільні станції")

        print("ТЕСТ ПОСТІЙНОГО РЕЗЕРВУ ТА ВІЛЬНИХ СТАНЦІЙ ПРОЙДЕНО")

    finally:
        if group_id is not None:
            async with pool.acquire() as conn:
                await conn.execute(
                    "DELETE FROM work_groups WHERE id=$1",
                    group_id,
                )
            print("Тимчасову групу видалено")

        await pool.close()
        db._pool = None


asyncio.run(main())
