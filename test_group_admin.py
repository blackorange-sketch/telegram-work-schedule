import asyncio
import os
from datetime import date

import asyncpg
import bot.database as db

NAME = "zz test admin 20261009"
SLUG = "zz_test_admin_20261009"
WEEK_START = date(2026, 10, 5)

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
            if await conn.fetchval("SELECT EXISTS(SELECT 1 FROM work_groups WHERE slug=$1)", SLUG):
                raise RuntimeError(f"Група {SLUG} вже існує; зупинка без змін.")

        async def stations(active_only=True):
            rows = await db.get_work_group_stations(SLUG, active_only)
            return [r["station_number"] for r in rows]

        print("\n===== G1: створення групи =====")
        result = await db.create_work_group(NAME, "1-5, 8")
        created.append(result["slug"])
        check(result["slug"] == SLUG, f"slug згенеровано з назви ({result['slug']})")
        check(await stations() == [1, 2, 3, 4, 5, 8], "станції 1-5 і 8")
        groups = {g["slug"]: g for g in await db.get_work_groups_admin()}
        check(groups[SLUG]["stations_text"] == "1-5, 8", "у списку адміна «1-5, 8»")
        check(any(g["slug"] == SLUG for g in await db.get_work_groups()), "група видна у виборі групи")
        settings = await db.get_group_schedule_settings(SLUG)
        check(settings and settings["start_week"] is None, "ротація ще не налаштована")

        print("\n===== G2: заборонені значення =====")
        await expect_value_error(db.create_work_group(NAME.upper(), "1-3"), "дубль назви (без урахування регістру)")
        await expect_value_error(db.create_work_group("  ", "1-3"), "порожня назва")
        await expect_value_error(db.create_work_group("zz other", "abc"), "некоректні станції")

        print("\n===== G3: зміна станцій зі збереженням історії =====")
        async with pool.acquire() as conn:
            worker_id = await conn.fetchval(
                """
                INSERT INTO group_workers (group_id, team_code, name)
                SELECT id, 'A', 'Admin W1' FROM work_groups WHERE slug=$1
                RETURNING id
                """,
                SLUG,
            )
        await db.set_group_schedule_settings(SLUG, WEEK_START, 2)
        week_id = (await db.get_or_create_schedule_week(WEEK_START))["id"]
        await db.set_group_schedule_assignment(week_id, WEEK_START, worker_id, 8, 1, SLUG)

        await db.update_work_group(SLUG, stations_text="2-6")
        check(await stations() == [2, 3, 4, 5, 6], "активні станції тепер 2-6")
        check(8 in await stations(active_only=False), "станція 8 вимкнена, але не видалена")
        async with pool.acquire() as conn:
            kept = await conn.fetchval(
                """
                SELECT COUNT(*) FROM group_schedule_assignments a
                JOIN work_groups g ON g.id = a.group_id
                WHERE g.slug=$1
                """,
                SLUG,
            )
        check(kept == 1, "старе призначення на станції 8 збережено")
        await expect_value_error(
            db.set_group_schedule_assignment(week_id, WEEK_START, worker_id, 8, 1, SLUG),
            "на вимкнену станцію нове призначення не ставиться",
        )
        await db.update_work_group(SLUG, stations_text="2-6, 8")
        check(8 in await stations(), "станцію 8 можна ввімкнути знову")

        print("\n===== G4: перейменування і вимкнення =====")
        await db.update_work_group(SLUG, name=NAME + " renamed")
        groups = {g["slug"]: g for g in await db.get_work_groups_admin()}
        check(groups[SLUG]["name"] == NAME + " renamed", "назву змінено, slug той самий")
        await db.update_work_group(SLUG, active=False)
        check(not any(g["slug"] == SLUG for g in await db.get_work_groups()), "вимкнена група зникла з вибору")
        await db.update_work_group(SLUG, active=True)
        check(any(g["slug"] == SLUG for g in await db.get_work_groups()), "увімкнена знову")
        await expect_value_error(db.update_work_group("zz_no_such_group", name="x"), "неіснуюча група")

        if errors:
            raise RuntimeError("Помилки:\n- " + "\n- ".join(errors))
        print("\nТЕСТ КЕРУВАННЯ ГРУПАМИ ПРОЙДЕНО")

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
