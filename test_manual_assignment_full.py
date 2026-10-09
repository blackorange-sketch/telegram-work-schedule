import asyncio
import os
from datetime import date, timedelta

import asyncpg
import bot.database as db

SLUG = "zz_test_manual_full_20261009"
OTHER_SLUG = "zz_test_manual_other_20261009"
WEEK_START = date(2026, 10, 5)
WORK_DATE = WEEK_START
NEXT_WEEK = WEEK_START + timedelta(days=7)

errors = []


def check(cond, msg):
    if cond:
        print("  OK:", msg)
    else:
        print("  ПОМИЛКА:", msg)
        errors.append(msg)


async def create_group(conn, created, slug, name, stations):
    exists = await conn.fetchval(
        "SELECT EXISTS(SELECT 1 FROM work_groups WHERE slug=$1)", slug
    )
    if exists:
        raise RuntimeError(f"Група {slug} вже існує; зупинка без змін.")
    group_id = await conn.fetchval(
        """
        INSERT INTO work_groups (slug, name, sort_order)
        VALUES ($1, $2, 999)
        RETURNING id
        """,
        slug,
        name,
    )
    created.append(slug)
    for station in range(1, stations + 1):
        await conn.execute(
            """
            INSERT INTO work_group_stations (group_id, station_number, active)
            VALUES ($1, $2, TRUE)
            """,
            group_id,
            station,
        )
    return group_id


async def add_worker(conn, group_id, name, team, is_reserve=False):
    return await conn.fetchval(
        """
        INSERT INTO group_workers (group_id, team_code, name, is_reserve)
        VALUES ($1, $2, $3, $4)
        RETURNING id
        """,
        group_id,
        team,
        name,
        is_reserve,
    )


async def main():
    database_url = os.environ.get("DATABASE_URL", "")
    if "telegram_schedule_test" not in database_url:
        raise RuntimeError(
            "Зупинка: DATABASE_URL має вказувати на telegram_schedule_test"
        )

    pool = await asyncpg.create_pool(database_url)
    db._pool = pool
    created = []

    try:
        async with pool.acquire() as conn:
            group_id = await create_group(
                conn, created, SLUG, "Temporary manual full test", 5
            )
            other_id = await create_group(
                conn, created, OTHER_SLUG, "Temporary manual other group", 2
            )
            w = {}
            for code in ("A1", "A2", "A3", "A4"):
                w[code] = await add_worker(conn, group_id, f"Manual {code}", "A")
            w["B1"] = await add_worker(conn, group_id, "Manual B1", "B")
            w["R"] = await add_worker(conn, group_id, "Manual R", "A", True)
            other_worker = await add_worker(conn, other_id, "Other A1", "A")

            # A4 відсутній у понеділок.
            await conn.execute(
                """
                INSERT INTO group_worker_days_off (group_id, worker_id, work_date)
                VALUES ($1, $2, $3)
                """,
                group_id,
                w["A4"],
                WORK_DATE,
            )

        await db.set_group_schedule_settings(SLUG, WEEK_START, 3)
        await db.set_group_schedule_settings(OTHER_SLUG, WEEK_START, 3)
        week_id = (await db.get_or_create_schedule_week(WEEK_START))["id"]
        next_week_id = (await db.get_or_create_schedule_week(NEXT_WEEK))["id"]
        names = {v: k for k, v in w.items()}

        async def assign(code, station):
            return await db.set_group_schedule_assignment(
                week_id, WORK_DATE, w[code], station, 1, SLUG
            )

        async def state():
            async with pool.acquire() as conn:
                rows = await conn.fetch(
                    """
                    SELECT a.worker_id, s.station_number
                    FROM group_schedule_assignments a
                    JOIN work_group_stations s
                      ON s.id = a.station_id AND s.group_id = a.group_id
                    WHERE a.group_id=$1 AND a.week_id=$2 AND a.work_date=$3
                    """,
                    group_id,
                    week_id,
                    WORK_DATE,
                )
                res = await conn.fetch(
                    """
                    SELECT worker_id FROM group_schedule_reserves
                    WHERE group_id=$1 AND week_id=$2 AND work_date=$3
                    """,
                    group_id,
                    week_id,
                    WORK_DATE,
                )
            pos = {names[r["worker_id"]]: r["station_number"] for r in rows}
            reserve = {names[r["worker_id"]] for r in res}
            print("  Станції:", dict(sorted(pos.items())), "| Резерв:", sorted(reserve))
            return pos, reserve

        async def outside():
            async with pool.acquire() as conn:
                rows = await conn.fetch(
                    """
                    SELECT group_id, week_id, work_date, worker_id,
                           station_id, team_code
                    FROM group_schedule_assignments
                    WHERE group_id=$1 OR (group_id=$2 AND week_id=$3)
                    ORDER BY 1, 2, 3, 4
                    """,
                    other_id,
                    group_id,
                    next_week_id,
                )
            return [tuple(r) for r in rows]

        print("\n===== Підготовка: записи для перевірки ізоляції =====")
        await db.set_group_schedule_assignment(
            next_week_id, NEXT_WEEK, w["A2"], 5, 1, SLUG
        )
        await db.set_group_schedule_assignment(
            week_id, WORK_DATE, other_worker, 1, 1, OTHER_SLUG
        )
        before_outside = await outside()
        check(len(before_outside) == 2, "створено 2 записи поза тестовою зоною")

        print("\n===== T1: вільні станції =====")
        await assign("A1", 1)
        await assign("A2", 2)
        pos, reserve = await state()
        check(pos == {"A1": 1, "A2": 2}, "A1→1, A2→2")

        print("\n===== T2: переміщення на вільну станцію =====")
        await assign("A1", 3)
        pos, reserve = await state()
        check(pos == {"A1": 3, "A2": 2}, "A1→3, A2 без змін")

        print("\n===== T3: обмін двох призначених =====")
        await assign("A1", 2)
        pos, reserve = await state()
        check(pos == {"A1": 2, "A2": 3}, "A1 і A2 обмінялися")

        print("\n===== T4: непризначений на зайняту станцію =====")
        await assign("A3", 2)
        pos, reserve = await state()
        check(pos == {"A2": 3, "A3": 2}, "A3 зайняв станцію 2, A1 знятий")
        check("A1" in reserve, "витіснений A1 потрапив у резерв")

        print("\n===== T5: з резерву на станцію =====")
        await assign("A1", 1)
        pos, reserve = await state()
        check(pos == {"A1": 1, "A2": 3, "A3": 2}, "A1→1")
        check("A1" not in reserve, "A1 прибраний із резерву")

        print("\n===== T6: постійний резервіст вручну =====")
        async with pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO group_schedule_reserves
                    (group_id, team_code, week_id, work_date, worker_id)
                VALUES ($1, 'A', $2, $3, $4)
                """,
                group_id,
                week_id,
                WORK_DATE,
                w["R"],
            )
        await assign("R", 4)
        pos, reserve = await state()
        check(pos == {"A1": 1, "A2": 3, "A3": 2, "R": 4}, "R→4 дозволено")
        check("R" not in reserve, "R прибраний із резерву")

        print("\n===== T7: відсутній працівник =====")
        try:
            await assign("A4", 5)
            rejected = False
        except ValueError as exc:
            print("  Відмова:", exc)
            rejected = True
        check(rejected, "відсутнього A4 не можна призначити")
        if not rejected:
            async with pool.acquire() as conn:
                await conn.execute(
                    """
                    DELETE FROM group_schedule_assignments
                    WHERE group_id=$1 AND week_id=$2
                      AND work_date=$3 AND worker_id=$4
                    """,
                    group_id,
                    week_id,
                    WORK_DATE,
                    w["A4"],
                )
            print("  Запис A4 прибрано вручну, щоб продовжити тест")
        pos, reserve = await state()
        check("A4" not in pos, "A4 не на станції")

        print("\n===== T8: інша команда на тій самій станції =====")
        await db.set_group_schedule_assignment(
            week_id, WORK_DATE, w["B1"], 2, 1, SLUG
        )
        pos, reserve = await state()
        check(pos.get("B1") == 2 and pos.get("A3") == 2, "B1 і A3 на станції 2")
        await assign("A1", 2)
        pos, reserve = await state()
        check(
            pos == {"A1": 2, "A2": 3, "A3": 1, "R": 4, "B1": 2},
            "обмін A1↔A3 не зачепив B1",
        )

        print("\n===== T9: зняття працівника зі станції =====")
        deleted = await db.delete_group_schedule_assignment(
            week_id, WORK_DATE, 2, SLUG
        )
        print("  Повернуто:", deleted)
        pos, reserve = await state()
        on_2 = sorted(n for n, s in pos.items() if s == 2)
        check(len(on_2) == 1, f"знято лише одного зі станції 2 (лишилось: {on_2})")

        print("\n===== T10: ізоляція інших груп і тижнів =====")
        check(await outside() == before_outside, "записи поза зоною не змінились")

        print("\n===== T11: повторна генерація =====")
        result = await db.generate_group_schedule_assignments(
            week_id, WEEK_START, SLUG
        )
        print("  Результат генератора:", result)
        async with pool.acquire() as conn:
            r_assign = await conn.fetchval(
                """
                SELECT COUNT(*) FROM group_schedule_assignments
                WHERE group_id=$1 AND week_id=$2 AND worker_id=$3
                """,
                group_id,
                week_id,
                w["R"],
            )
            a4_assign = await conn.fetchval(
                """
                SELECT COUNT(*) FROM group_schedule_assignments
                WHERE group_id=$1 AND week_id=$2
                  AND worker_id=$3 AND work_date=$4
                """,
                group_id,
                week_id,
                w["A4"],
                WORK_DATE,
            )
        check(r_assign == 0, "після генерації R без станцій")
        check(a4_assign == 0, "після генерації A4 без станції в день відсутності")
        check(await outside() == before_outside, "генерація не зачепила інші групи/тижні")

        if errors:
            raise RuntimeError("Помилки:\n- " + "\n- ".join(errors))
        print("\nТЕСТ РУЧНИХ ПРИЗНАЧЕНЬ ПРОЙДЕНО")

    finally:
        try:
            if created:
                async with pool.acquire() as conn:
                    for slug in created:
                        await conn.execute(
                            "DELETE FROM work_groups WHERE slug=$1", slug
                        )
                print("Тимчасові групи видалено:", created)
        finally:
            await pool.close()
            db._pool = None


asyncio.run(main())
