import asyncio
import os
from datetime import date, timedelta

import asyncpg
import bot.database as db

SLUGS = ["zz_test_rot_one_20261009", "zz_test_rot_two_20261009"]
WEEK_START = date(2026, 10, 5)

errors = []


def check(cond, msg):
    print("  OK:" if cond else "  ПОМИЛКА:", msg)
    if not cond:
        errors.append(msg)


async def main():
    database_url = os.environ.get("DATABASE_URL", "")
    if "telegram_schedule_test" not in database_url:
        raise RuntimeError(
            "Зупинка: DATABASE_URL має вказувати на telegram_schedule_test"
        )

    pool = await asyncpg.create_pool(database_url)
    db._pool = pool
    created = []
    saved = None

    try:
        async with pool.acquire() as conn:
            if await conn.fetchval("SELECT to_regclass('public.rotation_settings') IS NULL"):
                raise RuntimeError("Спершу застосуйте migrations/003_global_rotation.sql до тестової БД")
            for slug in SLUGS:
                if await conn.fetchval("SELECT EXISTS(SELECT 1 FROM work_groups WHERE slug=$1)", slug):
                    raise RuntimeError(f"Група {slug} вже існує; зупинка без змін.")
                await conn.execute(
                    "INSERT INTO work_groups (slug, name, sort_order) VALUES ($1, $1, 999)", slug
                )
                created.append(slug)
        saved = await db.get_rotation_settings()

        print("\n===== R1: одна ротація для всіх груп =====")
        await db.set_rotation_settings(WEEK_START, 2)
        one = await db.get_group_team_shift_slots(SLUGS[0], WEEK_START)
        two = await db.get_group_team_shift_slots(SLUGS[1], WEEK_START)
        check(one == two == {"A": 1, "B": 2, "C": 3}, f"обидві групи: {one} / {two}")

        print("\n===== R2: зміна через будь-яку групу змінює всі =====")
        await db.set_group_schedule_settings(SLUGS[0], WEEK_START, 3)
        two = await db.get_group_team_shift_slots(SLUGS[1], WEEK_START)
        check(two == {"C": 1, "A": 2, "B": 3}, f"друга група теж змінилась: {two}")

        print("\n===== R3: чергування по тижнях =====")
        await db.set_rotation_settings(WEEK_START, 2)
        weeks = [await db.get_group_team_shift_slots(SLUGS[0], WEEK_START + timedelta(days=7 * i)) for i in range(4)]
        print("  Бригада A по тижнях:", [w["A"] for w in weeks])
        check([w["A"] for w in weeks] == [1, 3, 2, 1], "A: 1 → 3 → 2 → 1")
        check(all(sorted(w.values()) == [1, 2, 3] for w in weeks), "щотижня кожна зміна зайнята однією бригадою")

        if errors:
            raise RuntimeError("Помилки:\n- " + "\n- ".join(errors))
        print("\nТЕСТ СПІЛЬНОЇ РОТАЦІЇ ПРОЙДЕНО")

    finally:
        try:
            async with pool.acquire() as conn:
                if saved:
                    await db.set_rotation_settings(saved["start_week"], saved["start_shift_slot"])
                for slug in created:
                    await conn.execute("DELETE FROM work_groups WHERE slug=$1", slug)
            print("Тимчасові групи видалено, ротацію тестової БД відновлено")
        finally:
            await pool.close()
            db._pool = None


asyncio.run(main())
