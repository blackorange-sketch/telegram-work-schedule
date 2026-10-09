import asyncio
import os
from datetime import date, timedelta

import asyncpg
import bot.database as db

SLUG = "zz_test_days_reserve_20261009"
OTHER_SLUG = "zz_test_days_reserve_other_20261009"
WEEK_START = date(2026, 10, 5)
MONDAY = WEEK_START
TUESDAY = WEEK_START + timedelta(days=1)
NEXT_WEEK = WEEK_START + timedelta(days=7)

errors = []


def check(cond, msg):
    print("  OK:" if cond else "  ПОМИЛКА:", msg)
    if not cond:
        errors.append(msg)


async def expect_value_error(coro, msg):
    try:
        await coro
    except ValueError as exc:
        print("  Відмова:", exc)
        check(True, msg)
        return
    check(False, msg)


async def create_group(conn, created, slug, stations):
    exists = await conn.fetchval(
        "SELECT EXISTS(SELECT 1 FROM work_groups WHERE slug=$1)", slug
    )
    if exists:
        raise RuntimeError(f"Група {slug} вже існує; зупинка без змін.")
    group_id = await conn.fetchval(
        """
        INSERT INTO work_groups (slug, name, sort_order)
        VALUES ($1, 'Temporary days/reserve test', 999)
        RETURNING id
        """,
        slug,
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


async def add_worker(conn, group_id, name, team="A"):
    return await conn.fetchval(
        """
        INSERT INTO group_workers (group_id, team_code, name, is_reserve)
        VALUES ($1, $2, $3, FALSE)
        RETURNING id
        """,
        group_id,
        team,
        name,
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
            group_id = await create_group(conn, created, SLUG, 5)
            other_id = await create_group(conn, created, OTHER_SLUG, 3)
            w1 = await add_worker(conn, group_id, "Days W1")
            w2 = await add_worker(conn, group_id, "Days W2")
            w3 = await add_worker(conn, group_id, "Days W3")
            w4 = await add_worker(conn, group_id, "Days W4")
            other_w = await add_worker(conn, other_id, "Other W1")

        await db.set_group_schedule_settings(SLUG, WEEK_START, 3)
        await db.set_group_schedule_settings(OTHER_SLUG, WEEK_START, 3)
        week_id = (await db.get_or_create_schedule_week(WEEK_START))["id"]
        next_week_id = (await db.get_or_create_schedule_week(NEXT_WEEK))["id"]

        async def count(table, worker_id, work_date, wk=None):
            async with pool.acquire() as conn:
                return await conn.fetchval(
                    f"""
                    SELECT COUNT(*) FROM {table}
                    WHERE worker_id=$1 AND work_date=$2
                      AND ($3::int IS NULL OR week_id=$3)
                    """,
                    worker_id,
                    work_date,
                    wk,
                )

        async def week_rows(gid, wk):
            async with pool.acquire() as conn:
                a = await conn.fetchval(
                    "SELECT COUNT(*) FROM group_schedule_assignments "
                    "WHERE group_id=$1 AND week_id=$2",
                    gid,
                    wk,
                )
                r = await conn.fetchval(
                    "SELECT COUNT(*) FROM group_schedule_reserves "
                    "WHERE group_id=$1 AND week_id=$2",
                    gid,
                    wk,
                )
            return a, r

        print("\n===== D1: вихідний знімає зі станції =====")
        await db.set_group_schedule_assignment(week_id, MONDAY, w1, 1, 1, SLUG)
        await db.set_group_worker_day_off(SLUG, w1, MONDAY)
        check(
            await count("group_schedule_assignments", w1, MONDAY) == 0,
            "W1 знятий зі станції в день вихідного",
        )
        days = await db.get_group_worker_days_off(SLUG, WEEK_START, WEEK_START + timedelta(days=4))
        check(
            [(d["worker_id"], d["work_date"]) for d in days] == [(w1, MONDAY)],
            "вихідний видно через get_group_worker_days_off",
        )

        print("\n===== D2: повторне встановлення вихідного без дубля =====")
        await db.set_group_worker_day_off(SLUG, w1, MONDAY)
        async with pool.acquire() as conn:
            dup = await conn.fetchval(
                "SELECT COUNT(*) FROM group_worker_days_off WHERE worker_id=$1",
                w1,
            )
        check(dup == 1, "лише один запис вихідного")

        print("\n===== D3: вихідний знімає з резерву =====")
        await db.set_group_schedule_reserve(week_id, TUESDAY, w2, SLUG)
        await db.set_group_worker_day_off(SLUG, w2, TUESDAY)
        check(
            await count("group_schedule_reserves", w2, TUESDAY) == 0,
            "W2 прибраний із резерву в день вихідного",
        )

        print("\n===== D4: генератор і ручне призначення бачать вихідний =====")
        await expect_value_error(
            db.set_group_schedule_assignment(week_id, MONDAY, w1, 2, 1, SLUG),
            "ручне призначення W1 у вихідний відхилено",
        )
        await db.generate_group_schedule_assignments(week_id, WEEK_START, SLUG)
        check(
            await count("group_schedule_assignments", w1, MONDAY) == 0
            and await count("group_schedule_reserves", w1, MONDAY) == 0,
            "генератор не поставив W1 у понеділок",
        )

        print("\n===== D5: скасування вихідного =====")
        removed = await db.delete_group_worker_day_off(SLUG, w1, MONDAY)
        check(removed is not None and removed["worker_id"] == w1, "вихідний W1 видалено")
        check(
            await db.delete_group_worker_day_off(SLUG, w1, MONDAY) is None,
            "повторне видалення повертає None",
        )
        await db.set_group_schedule_assignment(week_id, MONDAY, w1, 1, 1, SLUG)
        check(
            await count("group_schedule_assignments", w1, MONDAY) == 1,
            "після скасування W1 можна призначити",
        )

        print("\n===== R1: резерв знімає зі станції =====")
        await db.set_group_schedule_reserve(week_id, MONDAY, w1, SLUG)
        check(
            await count("group_schedule_assignments", w1, MONDAY) == 0,
            "W1 знятий зі станції",
        )
        check(
            await count("group_schedule_reserves", w1, MONDAY) == 1,
            "W1 у резерві",
        )
        await db.set_group_schedule_reserve(week_id, MONDAY, w1, SLUG)
        check(
            await count("group_schedule_reserves", w1, MONDAY) == 1,
            "повторний резерв без дубля",
        )

        print("\n===== R2: резерв для відсутнього відхилено =====")
        await expect_value_error(
            db.set_group_schedule_reserve(week_id, TUESDAY, w2, SLUG),
            "W2 у вихідний не можна поставити в резерв",
        )

        print("\n===== R3: чужий працівник відхилений =====")
        await expect_value_error(
            db.set_group_schedule_reserve(week_id, MONDAY, other_w, SLUG),
            "працівника іншої групи не можна поставити в резерв",
        )
        await expect_value_error(
            db.set_group_worker_day_off(SLUG, other_w, MONDAY),
            "працівнику іншої групи не можна поставити вихідний",
        )

        print("\n===== R4: зняття з резерву =====")
        check(
            await db.delete_group_schedule_reserve(week_id, MONDAY, w1, SLUG),
            "W1 знятий із резерву",
        )
        check(
            not await db.delete_group_schedule_reserve(week_id, MONDAY, w1, SLUG),
            "повторне зняття повертає False",
        )

        print("\n===== C1: очищення тижня лише для своєї групи =====")
        await db.set_group_schedule_assignment(next_week_id, NEXT_WEEK, w3, 1, 1, SLUG)
        await db.set_group_schedule_assignment(week_id, MONDAY, other_w, 1, 1, OTHER_SLUG)
        await db.set_group_schedule_reserve(week_id, MONDAY, w4, SLUG)
        before_next = await week_rows(group_id, next_week_id)
        before_other = await week_rows(other_id, week_id)
        deleted = await db.clear_group_schedule_week(week_id, SLUG)
        print("  Видалено:", deleted)
        check(await week_rows(group_id, week_id) == (0, 0), "тиждень групи очищено")
        check(deleted["reserves"] >= 1, "звіт містить видалені резерви")
        check(await week_rows(group_id, next_week_id) == before_next, "наступний тиждень не зачеплено")
        check(await week_rows(other_id, week_id) == before_other, "інша група не зачеплена")
        days = await db.get_group_worker_days_off(SLUG, WEEK_START, WEEK_START + timedelta(days=4))
        check(len(days) == 1, "очищення тижня не видаляє вихідні")

        if errors:
            raise RuntimeError("Помилки:\n- " + "\n- ".join(errors))
        print("\nТЕСТ ВИХІДНИХ, РЕЗЕРВУ Й ОЧИЩЕННЯ ПРОЙДЕНО")

    finally:
        try:
            if created:
                async with pool.acquire() as conn:
                    for slug in created:
                        await conn.execute("DELETE FROM work_groups WHERE slug=$1", slug)
                print("Тимчасові групи видалено:", created)
        finally:
            await pool.close()
            db._pool = None


asyncio.run(main())
