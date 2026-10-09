BEGIN;

CREATE TABLE IF NOT EXISTS schema_migrations (
    version TEXT PRIMARY KEY,
    applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Спільний календар тижнів для всіх груп.
CREATE TABLE IF NOT EXISTS schedule_weeks (
    id SERIAL PRIMARY KEY,
    week_start DATE NOT NULL UNIQUE,
    generated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Групи: назва та загальні налаштування.
CREATE TABLE IF NOT EXISTS work_groups (
    id BIGSERIAL PRIMARY KEY,
    slug TEXT NOT NULL UNIQUE
        CHECK (slug ~ '^[a-z0-9][a-z0-9_-]*$'),
    name TEXT NOT NULL,
    active BOOLEAN NOT NULL DEFAULT TRUE,
    sort_order INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Конкретні станції групи. Номери можуть бути довільними.
CREATE TABLE IF NOT EXISTS work_group_stations (
    id BIGSERIAL PRIMARY KEY,
    group_id BIGINT NOT NULL
        REFERENCES work_groups(id) ON DELETE CASCADE,
    station_number INTEGER NOT NULL CHECK (station_number > 0),
    label TEXT,
    active BOOLEAN NOT NULL DEFAULT TRUE,
    UNIQUE (group_id, station_number),
    UNIQUE (id, group_id)
);

-- Користувачі Telegram. telegram_id перевірятиметься на сервері.
CREATE TABLE IF NOT EXISTS app_users (
    telegram_id BIGINT PRIMARY KEY,
    display_name TEXT NOT NULL DEFAULT '',
    role TEXT NOT NULL DEFAULT 'user'
        CHECK (role IN ('super_admin', 'user')),
    active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Доступ користувача до конкретної групи та зміни.
CREATE TABLE IF NOT EXISTS user_group_access (
    id BIGSERIAL PRIMARY KEY,
    telegram_id BIGINT NOT NULL
        REFERENCES app_users(telegram_id) ON DELETE CASCADE,
    group_id BIGINT NOT NULL
        REFERENCES work_groups(id) ON DELETE CASCADE,
    team_code CHAR(1) NOT NULL
        CHECK (team_code IN ('A', 'B', 'C')),
    permissions JSONB NOT NULL DEFAULT '{}'::jsonb
        CHECK (jsonb_typeof(permissions) = 'object'),
    UNIQUE (telegram_id, group_id, team_code)
);

-- Шаблони для повторного створення конфігурацій груп.
CREATE TABLE IF NOT EXISTS group_templates (
    id BIGSERIAL PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    description TEXT NOT NULL DEFAULT '',
    config JSONB NOT NULL
        CHECK (jsonb_typeof(config) = 'object'),
    active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Працівники належать до групи та зміни A/B/C.
CREATE TABLE IF NOT EXISTS group_workers (
    id BIGSERIAL PRIMARY KEY,
    group_id BIGINT NOT NULL
        REFERENCES work_groups(id) ON DELETE CASCADE,
    team_code CHAR(1) NOT NULL
        CHECK (team_code IN ('A', 'B', 'C')),
    name TEXT NOT NULL DEFAULT '',
    is_reserve BOOLEAN NOT NULL DEFAULT FALSE,
    reserve_number INTEGER,
    active BOOLEAN NOT NULL DEFAULT TRUE,
    UNIQUE (id, group_id),
    UNIQUE (id, group_id, team_code)
);

CREATE INDEX IF NOT EXISTS idx_group_workers_group_team
    ON group_workers (group_id, team_code, active);

-- Вихідні працівників.
CREATE TABLE IF NOT EXISTS group_worker_days_off (
    id BIGSERIAL PRIMARY KEY,
    group_id BIGINT NOT NULL,
    worker_id BIGINT NOT NULL,
    work_date DATE NOT NULL,
    FOREIGN KEY (worker_id, group_id)
        REFERENCES group_workers(id, group_id) ON DELETE CASCADE,
    UNIQUE (worker_id, work_date)
);

CREATE INDEX IF NOT EXISTS idx_group_days_off_date_worker
    ON group_worker_days_off (group_id, work_date, worker_id);

-- Розклад: team_code — особиста зміна A/B/C,
-- shift_slot — номер робочого часового слота 1/2/3.
CREATE TABLE IF NOT EXISTS group_schedule_assignments (
    id BIGSERIAL PRIMARY KEY,
    group_id BIGINT NOT NULL
        REFERENCES work_groups(id) ON DELETE CASCADE,
    team_code CHAR(1) NOT NULL
        CHECK (team_code IN ('A', 'B', 'C')),
    shift_slot INTEGER NOT NULL
        CHECK (shift_slot BETWEEN 1 AND 3),
    week_id INTEGER NOT NULL
        REFERENCES schedule_weeks(id) ON DELETE CASCADE,
    work_date DATE NOT NULL,
    worker_id BIGINT NOT NULL,
    station_id BIGINT NOT NULL,
    FOREIGN KEY (worker_id, group_id, team_code)
        REFERENCES group_workers(id, group_id, team_code),
    FOREIGN KEY (station_id, group_id)
        REFERENCES work_group_stations(id, group_id),
    UNIQUE (group_id, team_code, week_id, work_date, worker_id),
    UNIQUE (group_id, team_code, week_id, work_date, station_id)
);

CREATE INDEX IF NOT EXISTS idx_group_assignments_date
    ON group_schedule_assignments
       (group_id, team_code, work_date);

-- Резерв у межах конкретної групи та зміни.
CREATE TABLE IF NOT EXISTS group_schedule_reserves (
    id BIGSERIAL PRIMARY KEY,
    group_id BIGINT NOT NULL
        REFERENCES work_groups(id) ON DELETE CASCADE,
    team_code CHAR(1) NOT NULL
        CHECK (team_code IN ('A', 'B', 'C')),
    week_id INTEGER NOT NULL
        REFERENCES schedule_weeks(id) ON DELETE CASCADE,
    work_date DATE NOT NULL,
    worker_id BIGINT NOT NULL,
    FOREIGN KEY (worker_id, group_id, team_code)
        REFERENCES group_workers(id, group_id, team_code),
    UNIQUE (group_id, team_code, week_id, work_date, worker_id)
);

-- Обіди окремо для групи, зміни та часового слота.
CREATE TABLE IF NOT EXISTS group_lunch_settings (
    id BIGSERIAL PRIMARY KEY,
    group_id BIGINT NOT NULL
        REFERENCES work_groups(id) ON DELETE CASCADE,
    team_code CHAR(1) NOT NULL
        CHECK (team_code IN ('A', 'B', 'C')),
    week_id INTEGER NOT NULL
        REFERENCES schedule_weeks(id) ON DELETE CASCADE,
    shift_slot INTEGER NOT NULL
        CHECK (shift_slot BETWEEN 1 AND 3),
    pair_number INTEGER NOT NULL CHECK (pair_number > 0),
    worker1_id BIGINT,
    worker2_id BIGINT,
    start_time TIME NOT NULL,
    FOREIGN KEY (worker1_id, group_id, team_code)
        REFERENCES group_workers(id, group_id, team_code),
    FOREIGN KEY (worker2_id, group_id, team_code)
        REFERENCES group_workers(id, group_id, team_code),
    UNIQUE (group_id, team_code, week_id, shift_slot, pair_number)
);

-- Початкові групи. Повторний запуск не змінює наявні налаштування.
INSERT INTO work_groups (slug, name, sort_order)
VALUES
    ('exotec_1', 'Exotec 1', 1),
    ('exotec_2', 'Exotec 2', 2),
    ('exotec_3', 'Exotec 3', 3)
ON CONFLICT (slug) DO NOTHING;

-- Ротація часового слота налаштовується окремо для кожної групи.
-- NULL означає, що адміністратор ще не налаштував ротацію.
CREATE TABLE IF NOT EXISTS group_schedule_settings (
    group_id BIGINT PRIMARY KEY
        REFERENCES work_groups(id) ON DELETE CASCADE,
    start_week DATE,
    start_shift_slot INTEGER
        CHECK (start_shift_slot BETWEEN 1 AND 3),
    CHECK (
        (start_week IS NULL AND start_shift_slot IS NULL)
        OR
        (start_week IS NOT NULL AND start_shift_slot IS NOT NULL)
    ),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Створюємо порожні налаштування для кожної наявної групи.
INSERT INTO group_schedule_settings (group_id)
SELECT id FROM work_groups
ON CONFLICT (group_id) DO NOTHING;

-- Початкові номери станцій для трьох наявних груп.
WITH station_ranges(slug, first_station, last_station) AS (
    VALUES
        ('exotec_1', 1, 14),
        ('exotec_2', 15, 24),
        ('exotec_3', 25, 34)
)
INSERT INTO work_group_stations (group_id, station_number, label)
SELECT
    g.id,
    s.station_number,
    s.station_number::TEXT
FROM station_ranges r
JOIN work_groups g ON g.slug = r.slug
CROSS JOIN LATERAL generate_series(
    r.first_station, r.last_station
) AS s(station_number)
ON CONFLICT (group_id, station_number) DO NOTHING;

-- Типові шаблони. Номери станцій нової групи задаються окремо.
INSERT INTO group_templates (name, description, config)
VALUES
(
    'Exotec стандарт 10',
    'Група на 10 станцій із трьома змінами',
    '{"station_count":10,"team_codes":["A","B","C"],"shift_slots":[1,2,3],"features":{"reserves":true,"lunches":true,"days_off":true}}'::jsonb
),
(
    'Exotec стандарт 14',
    'Група на 14 станцій із трьома змінами',
    '{"station_count":14,"team_codes":["A","B","C"],"shift_slots":[1,2,3],"features":{"reserves":true,"lunches":true,"days_off":true}}'::jsonb
)
ON CONFLICT (name) DO NOTHING;

INSERT INTO schema_migrations (version)
VALUES ('001_admin_group_model')
ON CONFLICT (version) DO NOTHING;

COMMIT;
