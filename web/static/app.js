const tg = window.Telegram.WebApp;

tg.ready();
tg.expand();
const scheduleTemplate = document.querySelector("main").innerHTML;

let workers = [];
let scheduleDays = [];
let scheduleShift = null;
let scheduleAssignments = [];

async function loadScheduleAssignments() {
    const weekStart = formatDate(getWeekStart());
    const response = await fetch(`/api/schedule/assignments?week_start=${weekStart}`);

    if (!response.ok) {
        alert("Не вдалося завантажити призначення");
        scheduleAssignments = [];
        return;
    }

    const data = await response.json();
    scheduleAssignments = data.assignments;
}


function renderSchedule() {
    const body = document.getElementById("scheduleBody");

    body.innerHTML = "";

    const assignmentsByWorkerDate = new Map();

    scheduleAssignments.forEach(assignment => {
        assignmentsByWorkerDate.set(
            `${assignment.worker_id}_${assignment.work_date}`,
            assignment
        );
    });

    workers.forEach(worker => {
        const row = document.createElement("tr");

        const name = document.createElement("td");
        name.className = "name name-column";
        name.textContent = worker.name;
        row.appendChild(name);

        for (let dayOffset = 0; dayOffset < 7; dayOffset++) {
            const date = new Date(getWeekStart());
            date.setDate(date.getDate() + dayOffset);

            const workDate = formatDate(date);
            const assignment = assignmentsByWorkerDate.get(
                `${worker.id}_${workDate}`
            );

            const cell = document.createElement("td");

            if (assignment) {
                const station = document.createElement("div");
                station.className = "station";
                station.textContent = assignment.station;

                cell.appendChild(station);
            }

            row.appendChild(cell);
        }

        const lunch = document.createElement("td");
        lunch.className = "lunch lunch-column";
        lunch.textContent = "—";

        row.appendChild(lunch);
        body.appendChild(row);
    });
}

renderSchedule();

let weekOffset = 0;

function getWeekStart(offset = weekOffset) {
    const date = new Date();
    const day = date.getDay();
    const diff = day === 0 ? -6 : 1 - day;
    date.setDate(date.getDate() + diff + offset * 7);
    date.setHours(0, 0, 0, 0);
    return date;
}

function formatDate(date) {
    const year = date.getFullYear();
    const month = String(date.getMonth() + 1).padStart(2, "0");
    const day = String(date.getDate()).padStart(2, "0");
    return `${year}-${month}-${day}`;
}


const weekTitle = document.getElementById("weekTitle");

function updateWeek() {
    if (weekOffset === 0) {
        weekTitle.textContent = "Поточний тиждень";
    } else if (weekOffset < 0) {
        weekTitle.textContent = "Попередній тиждень";
    } else {
        weekTitle.textContent = "Наступний тиждень";
    }
}



const navButtons = document.querySelectorAll(".bottom-nav button");
navButtons[1].addEventListener("click", () => {
    showWorkersScreen();
    setActiveNav(1);
});

async function loadScheduleWorkers() {
    const response = await fetch("/api/workers");
    if (!response.ok) {
        alert("Не вдалося завантажити працівників");
        return;
    }
    const data = await response.json();
    workers = data;
}

async function loadScheduleDays() {
    const weekStart = formatDate(getWeekStart());
    const response = await fetch(`/api/schedule/days?week_start=${weekStart}`);

    if (!response.ok) {
        alert("Не вдалося завантажити дні розкладу");
        scheduleDays = [];
        return;
    }

    const data = await response.json();
    scheduleDays = data.days;
}


async function loadScheduleShift() {
    const weekStart = formatDate(getWeekStart());
    const response = await fetch(`/api/schedule/shift?week_start=${weekStart}`);

    if (!response.ok) {
        scheduleShift = null;
        return;
    }

    const data = await response.json();
    scheduleShift = data.shift;
}

async function showScheduleScreen() {
    const main = document.querySelector("main");
    main.innerHTML = scheduleTemplate;
    await loadScheduleWorkers();
    await loadScheduleDays();
    await loadScheduleShift();
    await loadScheduleAssignments();
    renderSchedule();
    bindScheduleButtons();
}
function bindScheduleButtons() {
    document.getElementById("prevWeek").onclick = async () => {
        weekOffset--;
        updateWeek();
        await loadScheduleDays();
    await loadScheduleShift();
    await loadScheduleAssignments();
        renderSchedule();
    };

    document.getElementById("nextWeek").onclick = async () => {
        weekOffset++;
        updateWeek();
        await loadScheduleDays();
    await loadScheduleShift();
    await loadScheduleAssignments();
        renderSchedule();
    };
    document.getElementById("generateScheduleButton").onclick = async () => {
        const weekStart = formatDate(getWeekStart());

        const settingsResponse = await fetch("/api/schedule/settings");

        if (!settingsResponse.ok) {
            alert("Не вдалося перевірити налаштування зміни");
            return;
        }

        const settings = await settingsResponse.json();

        if (!settings) {
            const selectedShift = prompt(
                "Вкажіть початкову зміну:\n\n1 — 06:00–14:00\n2 — 14:00–22:00\n3 — 22:00–06:00"
            );

            if (!["1", "2", "3"].includes(selectedShift)) {
                return;
            }

            const settingsSaveResponse = await fetch("/api/schedule/settings", {
                method: "PUT",
                headers: {
                    "Content-Type": "application/json"
                },
                body: JSON.stringify({
                    start_week: weekStart,
                    start_shift: Number(selectedShift)
                })
            });

            if (!settingsSaveResponse.ok) {
                const data = await settingsSaveResponse.json().catch(() => ({}));
                alert(data.detail || "Не вдалося зберегти початкову зміну");
                return;
            }
        }

        const response = await fetch("/api/schedule/generate", {
            method: "POST",
            headers: {
                "Content-Type": "application/json"
            },
            body: JSON.stringify({
                week_start: weekStart
            })
        });

        if (!response.ok) {
            const data = await response.json().catch(() => ({}));
            alert(data.detail || "Не вдалося згенерувати розклад");
            return;
        }

        await loadScheduleShift();
        await loadScheduleAssignments();
        renderSchedule();
    };
}


navButtons[0].addEventListener("click", () => {
    showScheduleScreen();
    setActiveNav(0);
});

function setActiveNav(index) {
    navButtons.forEach((button, i) => {
        button.classList.toggle("active", i === index);
    });
}
