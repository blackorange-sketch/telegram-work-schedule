BEGIN;

-- Час початку обіду для кожного часового слота (зміни 1/2/3) окремо в кожній групі.
-- Якщо рядка немає, застосунок бере типовий час: 10:00 / 18:00 / 02:00.
CREATE TABLE IF NOT EXISTS group_lunch_start_times (
    group_id BIGINT NOT NULL
        REFERENCES work_groups(id) ON DELETE CASCADE,
    shift_slot INTEGER NOT NULL
        CHECK (shift_slot BETWEEN 1 AND 3),
    start_time TIME NOT NULL,
    PRIMARY KEY (group_id, shift_slot)
);

-- Обідні групи: окремо для групи, бригади й тижня.
-- pair_number — порядковий номер обідньої групи (1, 2, 3 ...);
-- обід групи N починається через (N-1) * 30 хв після часу початку зміни.
-- У групі може бути будь-яка кількість працівників.
CREATE TABLE IF NOT EXISTS group_lunch_members (
    id BIGSERIAL PRIMARY KEY,
    group_id BIGINT NOT NULL
        REFERENCES work_groups(id) ON DELETE CASCADE,
    team_code CHAR(1) NOT NULL
        CHECK (team_code IN ('A', 'B', 'C')),
    week_id INTEGER NOT NULL
        REFERENCES schedule_weeks(id) ON DELETE CASCADE,
    pair_number INTEGER NOT NULL CHECK (pair_number > 0),
    worker_id BIGINT NOT NULL,
    FOREIGN KEY (worker_id, group_id, team_code)
        REFERENCES group_workers(id, group_id, team_code) ON DELETE CASCADE,
    -- Працівник обідає лише в одній групі протягом тижня.
    UNIQUE (group_id, week_id, worker_id)
);

CREATE INDEX IF NOT EXISTS idx_group_lunch_members_week
    ON group_lunch_members (group_id, week_id, team_code, pair_number);

INSERT INTO schema_migrations (version)
VALUES ('002_group_lunch_groups')
ON CONFLICT (version) DO NOTHING;

COMMIT;
