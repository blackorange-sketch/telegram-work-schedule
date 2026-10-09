import asyncio
import os
from datetime import date

import asyncpg
import bot.database as db


SLUG = "zz_test_rotation_20261009"
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
                "Temporary reserve rotation test",
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

            for number in range(1, 8):
                await conn.execute(
                    """
                    INSERT INTO group_workers
                        (group_id, team_code, name, is_reserve)
                    VALUES ($1, 'A', $2, FALSE)
                    """,
                    group_id,
                    f"Rotation worker {number}",
                )

        await db.set_group_schedule_settings(SLUG, WEEK_START, 3)
        week = await db.get_or_create_schedule_week(WEEK_START)

        result = await db.generate_group_schedule_assignments(
            week["id"], WEEK_START, SLUG
        )
        print("Результат генератора:", result)

        async with pool.acquire() as conn:
            daily = await conn.fetch(
                """
                SELECT work_date, COUNT(*) AS reserve_count
                FROM group_schedule_reserves
                WHERE group_id=$1 AND week_id=$2 AND team_code='A'
                GROUP BY work_date
                ORDER BY work_date
                """,
                group_id,
                week["id"],
            )

            worker_counts = await conn.fetch(
                """
                SELECT w.name, COUNT(sr.worker_id) AS reserve_days
                FROM group_workers w
                LEFT JOIN group_schedule_reserves sr
                  ON sr.worker_id = w.id
                 AND sr.group_id = w.group_id
                 AND sr.week_id = $2
                WHERE w.group_id = $1
                  AND w.team_code = 'A'
                  AND w.is_reserve = FALSE
                GROUP BY w.id, w.name
                ORDER BY w.name
                """,
                group_id,
                week["id"],
            )

            reserve_by_day = await conn.fetch(
                """
                SELECT work_date, worker_id
                FROM group_schedule_reserves
                WHERE group_id=$1 AND week_id=$2 AND team_code='A'
                ORDER BY work_date
                """,
                group_id,
                week["id"],
            )

        daily_counts = [row["reserve_count"] for row in daily]
        counts = sorted(row["reserve_days"] for row in worker_counts)

        cumulative_unique = set()
        unique_by_day = []
        for row in daily:
            cumulative_unique.update(
                item["worker_id"]
                for item in reserve_by_day
                if item["work_date"] == row["work_date"]
            )
            unique_by_day.append(len(cumulative_unique))

        print("Резервістів за днями:", daily_counts)
        print("Дні резерву за працівниками:")
        for row in worker_counts:
            print(f"  {row['name']}: {row['reserve_days']}")
        print("Кількість різних резервістів накопичувально:", unique_by_day)

        if len(daily_counts) != 5 or daily_counts != [2, 2, 2, 2, 2]:
            raise RuntimeError("Помилка: очікується по 2 резервісти щодня")

        if counts != [1, 1, 1, 1, 2, 2, 2]:
            raise RuntimeError(
                f"Нерівномірний розподіл резерву: {counts}"
            )

        if unique_by_day != [2, 4, 6, 7, 7]:
            raise RuntimeError(
                "Ротація порушена: працівники повторно потрапляють "
                "у резерв до того, як усі отримали перше призначення"
            )

        if result["reserves"] != 10 or result["assignments"] != 25:
            raise RuntimeError("Неочікувана кількість призначень/резервів")

        print("ТЕСТ РОТАЦІЇ РЕЗЕРВУ ПРОЙДЕНО")

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
