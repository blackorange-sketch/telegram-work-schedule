import asyncio
import os
from datetime import date, timedelta

import asyncpg
import bot.database as db

SLUG = "zz_test_days_off_minimal_20261009"
WEEK_START = date(2026, 10, 5)
DAYS = [WEEK_START + timedelta(days=i) for i in range(5)]


def per_day(rows):
    counts = {d: 0 for d in DAYS}
    for r in rows:
        counts[r["work_date"]] += 1
    return [counts[d] for d in DAYS]


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
                raise RuntimeError(f"Група {SLUG} вже існує; зупинка без змін.")

            group = await conn.fetchrow(
                """
                INSERT INTO work_groups (slug, name, sort_order)
                VALUES ($1, $2, 999)
                RETURNING id
                """,
                SLUG,
                "Temporary minimal staff days off test",
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
            for number in range(1, 7):
                worker_id = await conn.fetchval(
                    """
                    INSERT INTO group_workers
                        (group_id, team_code, name, is_reserve)
                    VALUES ($1, 'A', $2, FALSE)
                    RETURNING id
                    """,
                    group_id,
                    f"Minimal worker {number}",
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

            w1, w2 = ordinary_ids[0], ordinary_ids[1]
            # W1: Пн і Ср; R: Чт; W2: Пт.
            absences = [
                (w1, DAYS[0]),
                (w1, DAYS[2]),
                (fixed_id, DAYS[3]),
                (w2, DAYS[4]),
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
                """,
                group_id,
                week["id"],
            )
            reserves = await conn.fetch(
                """
                SELECT work_date, worker_id
                FROM group_schedule_reserves
                WHERE group_id=$1 AND week_id=$2 AND team_code='A'
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
            repeats = await conn.fetch(
                """
                SELECT worker_id, station_id, COUNT(*) AS amount
                FROM group_schedule_assignments
                WHERE group_id=$1 AND week_id=$2
                GROUP BY worker_id, station_id
                HAVING COUNT(*) > 1
                """,
                group_id,
                week["id"],
            )

        daily_assignments = per_day(assignments)
        daily_reserves = per_day(reserves)
        ordinary_reserves = [r for r in reserves if r["worker_id"] != fixed_id]
        daily_ordinary_reserves = per_day(ordinary_reserves)
        fixed_assignments = sum(1 for a in assignments if a["worker_id"] == fixed_id)
        fixed_reserves = sum(1 for r in reserves if r["worker_id"] == fixed_id)
        w1_assignments = sum(1 for a in assignments if a["worker_id"] == w1)
        ordinary_reserve_workers = {r["worker_id"] for r in ordinary_reserves}

        print("Призначень за днями:", daily_assignments)
        print("Резервістів за днями:", daily_reserves)
        print("Звичайних резервістів за днями:", daily_ordinary_reserves)
        print("Призначень у дні відсутності:", len(absent_assignments))
        print("Резервів у дні відсутності:", len(absent_reserves))
        print("Призначень постійного резервіста:", fixed_assignments)
        print("Днів постійного резерву:", fixed_reserves)
        print("Призначень W1:", w1_assignments)
        print("Повторів станцій:", len(repeats))
        print("Різних звичайних резервістів:", len(ordinary_reserve_workers))

        errors = []
        if absent_assignments:
            errors.append("відсутній працівник призначений на станцію")
        if absent_reserves:
            errors.append("відсутній працівник включений у резерв")
        if fixed_assignments != 0:
            errors.append("постійний резервіст призначений на станцію")
        if fixed_reserves != 4:
            errors.append(f"очікувалося 4 дні постійного резерву, є {fixed_reserves}")
        if daily_assignments != [5, 5, 5, 5, 5]:
            errors.append(f"призначення за днями {daily_assignments} != [5,5,5,5,5]")
        if daily_reserves != [1, 2, 1, 1, 1]:
            errors.append(f"резерв за днями {daily_reserves} != [1,2,1,1,1]")
        if daily_ordinary_reserves != [0, 1, 0, 1, 0]:
            errors.append(
                f"звичайний резерв {daily_ordinary_reserves} != [0,1,0,1,0]"
            )
        # Кожен звичайний працівник: станції = доступні дні - дні резерву.
        # (Чи потрапить W1 у резерв, залежить від випадкового вибору.)
        for worker_id in ordinary_ids:
            off = sum(1 for wid, _ in absences if wid == worker_id)
            got = sum(1 for a in assignments if a["worker_id"] == worker_id)
            res = sum(1 for r in reserves if r["worker_id"] == worker_id)
            if got != 5 - off - res:
                errors.append(
                    f"працівник {worker_id}: {got} станцій, "
                    f"очікувалось {5 - off - res} (відсутній {off}, резерв {res})"
                )
        if repeats:
            errors.append(f"повтори станцій: {[dict(r) for r in repeats]}")
        if len(ordinary_reserve_workers) != 2:
            errors.append("Вт і Чт мали б різних звичайних резервістів")
        if result["assignments"] != 25 or result["reserves"] != 6:
            errors.append(f"підсумок {result} != 25 призначень / 6 резервів")

        if errors:
            raise RuntimeError("Помилки:\n- " + "\n- ".join(errors))

        print("ТЕСТ МІНІМАЛЬНОГО СКЛАДУ І ВІДСУТНОСТЕЙ ПРОЙДЕНО")

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
