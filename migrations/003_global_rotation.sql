BEGIN;

-- Одна ротація змін для всіх груп: бригади A, B, C чергуються однаково
-- на всьому складі. Лише один рядок (id = 1).
-- start_shift_slot — «фаза» ротації на тижні start_week
-- (фаза 2: A у зміні 1, B у 2, C у 3).
CREATE TABLE IF NOT EXISTS rotation_settings (
    id SMALLINT PRIMARY KEY DEFAULT 1 CHECK (id = 1),
    start_week DATE NOT NULL,
    start_shift_slot INTEGER NOT NULL
        CHECK (start_shift_slot BETWEEN 1 AND 3),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Якщо ротацію вже задавали для якоїсь групи, беремо останню збережену.
INSERT INTO rotation_settings (id, start_week, start_shift_slot)
SELECT 1, start_week, start_shift_slot
FROM group_schedule_settings
WHERE start_week IS NOT NULL AND start_shift_slot IS NOT NULL
ORDER BY updated_at DESC
LIMIT 1
ON CONFLICT (id) DO NOTHING;

INSERT INTO schema_migrations (version)
VALUES ('003_global_rotation')
ON CONFLICT (version) DO NOTHING;

COMMIT;
