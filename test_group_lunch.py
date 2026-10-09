import asyncio
import os
from datetime import date, timedelta

import asyncpg
import bot.database as db

SLUG = "zz_test_lunch_20261009"
OTHER_SLUG = "zz_test_lunch_other_20261009"
WEEK_START = date(2026, 10, 5)
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


async def create_group(conn, created, slug):
    exists = await conn.fetchval(
        "SELECT EXISTS(SELECT 1 FROM work_groups WHERE slug=$1)", slug
    )
    if exists:
        raise RuntimeError(f"Група {slug} вже існує; зупинка без змін.")
    group_id = await conn.fetchval(
        """
        INSERT INTO work_groups (slug, name, sort_order)
        VALUES ($1, 'Temporary lunch test', 999)
        RETURNING id
        """,
        slug,
    )
    created.append(slug)
    return group_id


async def add_worker(conn, group_id, name, team):
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


def names(pairs):
    return [[m["name"] for m in pair] for pair in pairs]


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
            migrated = await conn.fetchval(
                "SELECT to_regclass('public.group_lunch_members') IS NOT NULL"
            )
            if not migrated:
                raise RuntimeError(
                    "Спершу застосуйте migrations/002_group_lunch_groups.sql до тестової БД"
                )
            group_id = await create_group(conn, created, SLUG)
            other_id = await create_group(conn, created, OTHER_SLUG)
            a = [await add_worker(conn, group_id, f"Lunch A{i}", "A") for i in range(1, 6)]
            b1 = await add_worker(conn, group_id, "Lunch B1", "B")
            other = await add_worker(conn, other_id, "Other A1", "A")

        week_id = (await db.get_or_create_schedule_week(WEEK_START))["id"]
        next_week_id = (await db.get_or_create_schedule_week(NEXT_WEEK))["id"]

        print("\n===== L1: без налаштувань обідів =====")
        data = await db.get_group_lunch(week_id, WEEK_START, SLUG)
        check(
            data["start_times"] == {"1": "10:00", "2": "18:00", "3": "02:00"},
            "типовий час початку 10:00/18:00/02:00",
        )
        check(data["teams"] == {"A": [], "B": [], "C": []}, "обідніх груп ще немає")

        print("\n===== L2: групи різного розміру =====")
        await db.set_group_schedule_settings(SLUG, WEEK_START, 3)
        await db.set_group_lunch_team(
            week_id, SLUG, "A", [[a[0]], [a[1], a[2], a[3]], [], [a[4]]]
        )
        data = await db.get_group_lunch(week_id, WEEK_START, SLUG)
        print("  Бригада A:", names(data["teams"]["A"]), "| зміни:", data["team_slots"])
        check(
            names(data["teams"]["A"])
            == [["Lunch A1"], ["Lunch A2", "Lunch A3", "Lunch A4"], ["Lunch A5"]],
            "1, 3 і 1 особа; порожня група відкинута, нумерація без пропусків",
        )
        check(data["team_slots"] == {"C": 1, "A": 2, "B": 3}, "зміни бригад за ротацією")
        check(data["teams"]["B"] == [], "бригада B не зачеплена")

        print("\n===== L3: повне перезаписування бригади =====")
        await db.set_group_lunch_team(week_id, SLUG, "A", [[a[4], a[0]]])
        data = await db.get_group_lunch(week_id, WEEK_START, SLUG)
        check(names(data["teams"]["A"]) == [["Lunch A5", "Lunch A1"]], "старі групи замінено новими")

        print("\n===== L4: перевірки =====")
        await expect_value_error(
            db.set_group_lunch_team(week_id, SLUG, "A", [[a[0]], [a[0]]]),
            "один працівник у двох групах відхилено",
        )
        await expect_value_error(
            db.set_group_lunch_team(week_id, SLUG, "A", [[b1]]),
            "працівник бригади B у групі бригади A відхилено",
        )
        await expect_value_error(
            db.set_group_lunch_team(week_id, SLUG, "A", [[other]]),
            "працівник іншої групи відхилено",
        )
        await expect_value_error(
            db.set_group_lunch_team(week_id, SLUG, "D", []),
            "неіснуюча бригада відхилена",
        )
        data = await db.get_group_lunch(week_id, WEEK_START, SLUG)
        check(
            names(data["teams"]["A"]) == [["Lunch A5", "Lunch A1"]],
            "після відмов дані не змінились",
        )

        print("\n===== L5: тижні незалежні =====")
        data = await db.get_group_lunch(next_week_id, NEXT_WEEK, SLUG)
        check(data["teams"]["A"] == [], "наступний тиждень порожній")
        check(
            data["team_slots"] == {"A": 1, "B": 2, "C": 3},
            "на наступному тижні зміни зсунулися",
        )

        print("\n===== L6: час початку =====")
        saved = await db.set_group_lunch_start_times(SLUG, {"1": "09:40", "3": "01:30"})
        check(saved == {"1": "09:40", "3": "01:30"}, "збережено два слоти")
        data = await db.get_group_lunch(week_id, WEEK_START, SLUG)
        check(
            data["start_times"] == {"1": "09:40", "2": "18:00", "3": "01:30"},
            "незмінений слот лишився типовим",
        )
        other_data = await db.get_group_lunch(week_id, WEEK_START, OTHER_SLUG)
        check(other_data["start_times"]["1"] == "10:00", "інша група не зачеплена")
        await expect_value_error(
            db.set_group_lunch_start_times(SLUG, {"4": "10:00"}),
            "неіснуюча зміна відхилена",
        )
        await expect_value_error(
            db.set_group_lunch_start_times(SLUG, {"1": "25:00"}),
            "некоректний час відхилено",
        )

        print("\n===== L7: деактивований працівник зникає з обідів =====")
        async with pool.acquire() as conn:
            await conn.execute("UPDATE group_workers SET active=FALSE WHERE id=$1", a[4])
        data = await db.get_group_lunch(week_id, WEEK_START, SLUG)
        check(names(data["teams"]["A"]) == [["Lunch A1"]], "лишився лише активний")

        if errors:
            raise RuntimeError("Помилки:\n- " + "\n- ".join(errors))
        print("\nТЕСТ ОБІДІВ ПРОЙДЕНО")

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
