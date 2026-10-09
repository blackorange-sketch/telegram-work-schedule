import asyncio
import os
from datetime import date

import asyncpg
import bot.database as db

SLUG = "zz_test_manual_assignment_20261009"
WEEK_START = date(2026, 10, 5)
WORK_DATE = date(2026, 10, 5)


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
                raise RuntimeError(
                    "Тестова група вже існує. Зупинка без змін."
                )

            group = await conn.fetchrow(
                """
                INSERT INTO work_groups (slug, name, sort_order)
                VALUES ($1, $2, 999)
                RETURNING id
                """,
                SLUG,
                "Temporary manual assignment test",
            )
            group_id = group["id"]
            created = True

            for station in (1, 2, 3):
                await conn.execute(
                    """
                    INSERT INTO work_group_stations
                        (group_id, station_number, active)
                    VALUES ($1, $2, TRUE)
                    """,
                    group_id,
                    station,
                )

        workers = {}
        for code in ("A1", "A2", "A3"):
            workers[code] = await db.add_group_worker(
                SLUG, f"Test worker {code}", "A"
            )

        await db.set_group_schedule_settings(
            SLUG, WEEK_START, 3
        )
        week = await db.get_or_create_schedule_week(WEEK_START)
        week_id = week["id"]

        async def assign(code, station):
            result = await db.set_group_schedule_assignment(
                week_id,
                WORK_DATE,
                workers[code]["id"],
                station,
                1,
                SLUG,
            )
            print(
                f"Призначення {code} -> станція {station}:",
                result,
            )
            return result

        async def snapshot():
            async with pool.acquire() as conn:
                rows = await conn.fetch(
                    """
                    SELECT w.name, a.worker_id, s.station_number,
                           a.shift_slot, a.team_code
                    FROM group_schedule_assignments a
                    JOIN group_workers w
                      ON w.id = a.worker_id
                     AND w.group_id = a.group_id
                    JOIN work_group_stations s
                      ON s.id = a.station_id
                     AND s.group_id = a.group_id
                    JOIN work_groups g ON g.id = a.group_id
                    WHERE g.slug = $1
                      AND a.week_id = $2
                      AND a.work_date = $3
                    ORDER BY s.station_number
                    """,
                    SLUG,
                    week_id,
                    WORK_DATE,
                )
                result = [dict(row) for row in rows]
                print("Поточний розклад:", result)
                return result

        print("\n===== TEST 1: Вільна станція =====")
        await assign("A1", 1)
        await assign("A2", 2)
        rows = await snapshot()
        assert len(rows) == 2, "Очікували два призначення"

        print("\n===== TEST 2: Переміщення на вільну станцію =====")
        await assign("A1", 3)
        rows = await snapshot()
        positions = {r["name"]: r["station_number"] for r in rows}
        assert positions["Test worker A1"] == 3
        assert positions["Test worker A2"] == 2
        assert len(rows) == 2

        print("\n===== TEST 3: Обмін зайнятих станцій =====")
        await assign("A1", 2)
        rows = await snapshot()
        positions = {r["name"]: r["station_number"] for r in rows}
        assert positions["Test worker A1"] == 2
        assert positions["Test worker A2"] == 3
        assert len(rows) == 2

        print(
            "\n===== TEST 4: Незайнятий працівник "
            "призначається на зайняту станцію ====="
        )
        await assign("A3", 2)
        rows = await snapshot()
        positions = {r["name"]: r["station_number"] for r in rows}

        assert positions.get("Test worker A3") == 2
        assert positions.get("Test worker A2") == 3
        displaced_has_assignment = "Test worker A1" in positions
        print(
            "Чи залишився A1 у розкладі:",
            displaced_has_assignment,
        )

        async with pool.acquire() as conn:
            reserve_count = await conn.fetchval(
                """
                SELECT COUNT(*)
                FROM group_schedule_reserves r
                JOIN work_groups g ON g.id = r.group_id
                WHERE g.slug = $1
                  AND r.week_id = $2
                  AND r.work_date = $3
                  AND r.worker_id = $4
                """,
                SLUG,
                week_id,
                WORK_DATE,
                workers["A1"]["id"],
            )
        print("Чи доданий A1 до резерву:", reserve_count > 0)

        print("\nУСІ ПЕРЕВІРКИ ЗАВЕРШЕНО")

    finally:
        try:
            if created:
                async with pool.acquire() as conn:
                    await conn.execute(
                        "DELETE FROM work_groups WHERE slug=$1",
                        SLUG,
                    )
                print("Тимчасову тестову групу видалено")
        finally:
            await pool.close()
            db._pool = None


asyncio.run(main())
