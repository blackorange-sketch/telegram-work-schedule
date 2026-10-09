import asyncio
import os
from datetime import date

import asyncpg
import bot.database as db

SLUG = "zz_test_generator_20261009"
WEEK_START = date(2026, 10, 5)


async def main():
    pool = await asyncpg.create_pool(os.environ["DATABASE_URL"])
    db._pool = pool
    created = False

    try:
        async with pool.acquire() as conn:
            exists = await conn.fetchval(
                "SELECT EXISTS(SELECT 1 FROM work_groups WHERE slug=$1)",
                SLUG,
            )
            if exists:
                raise RuntimeError("Тестова група вже існує; зупинка.")

            group = await conn.fetchrow(
                """
                INSERT INTO work_groups (slug, name, sort_order)
                VALUES ($1, $2, 999)
                RETURNING id
                """,
                SLUG, "Temporary generator test",
            )
            group_id = group["id"]
            created = True

            for station in range(1, 6):
                await conn.execute(
                    """
                    INSERT INTO work_group_stations
                        (group_id, station_number, active)
                    VALUES ($1, $2, TRUE)
                    """,
                    group_id, station,
                )

            for team in ("A", "B", "C"):
                for number in range(1, 7):
                    await conn.execute(
                        """
                        INSERT INTO group_workers
                            (group_id, team_code, name, is_reserve)
                        VALUES ($1, $2, $3, FALSE)
                        """,
                        group_id, team, f"Test {team}{number}",
                    )

        await db.set_group_schedule_settings(SLUG, WEEK_START, 3)
        week = await db.get_or_create_schedule_week(WEEK_START)

        result = await db.generate_group_schedule_assignments(
            week["id"], WEEK_START, SLUG
        )
        print("Результат:", result)

        async with pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT worker_id, COUNT(*) AS shifts,
                       COUNT(DISTINCT station_id) AS unique_stations
                FROM group_schedule_assignments
                WHERE group_id=$1 AND week_id=$2
                GROUP BY worker_id
                """,
                group_id, week["id"],
            )

            repeated = [
                dict(row) for row in rows
                if row["shifts"] != row["unique_stations"]
            ]
            print("Працівників із призначеннями:", len(rows))
            print("Повторні станції:", len(repeated))

            if repeated:
                print("Проблемні записи:", repeated)
                raise RuntimeError("Виявлено повторні станції")

            if result["assignments"] != 75 or result["reserves"] != 15:
                raise RuntimeError("Неочікувана кількість призначень/резервів")

            print("ТЕСТ ПРОЙДЕНО")

    finally:
        if created:
            async with pool.acquire() as conn:
                await conn.execute(
                    "DELETE FROM work_groups WHERE slug=$1", SLUG
                )
            print("Тимчасову групу видалено")

        await pool.close()
        db._pool = None


asyncio.run(main())
