const tg = window.Telegram.WebApp;

tg.ready();

if (tg.setHeaderColor) {
    tg.setHeaderColor("#f8f8fa");
}

if (tg.setBackgroundColor) {
    tg.setBackgroundColor("#f8f8fa");
}
if (tg.requestFullscreen) {
    tg.requestFullscreen();
} else {
    tg.expand();
}
const scheduleTemplate = document.querySelector("main").innerHTML;

let workers = [];
let scheduleDays = [];
let scheduleShift = null;
let scheduleAssignments = [];
let scheduleLoaded = false;
let changingStations = new Set();
let workersScreenLoaded = false;

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


async function saveScheduleAssignment(assignment, workDate) {
    const weekStart = formatDate(getWeekStart());

    const response = await fetch("/api/schedule/assignment", {
        method: "PUT",
        headers: {
            "Content-Type": "application/json"
        },
        body: JSON.stringify({
            week_start: weekStart,
            work_date: workDate,
            worker_id: assignment.worker_id,
            station: assignment.station,
            shift: assignment.shift || scheduleShift
        })
    });

    if (!response.ok) {
        alert("Не вдалося зберегти зміну");
        return false;
    }

    return true;
}

function openStationModal(assignment, workDate) {
    const modal = document.getElementById("stationModal");
    const title = document.getElementById("stationModalTitle");
    const list = document.getElementById("stationWorkerList");
    const clearButton = document.getElementById("clearStationButton");
    const cancelButton = document.getElementById("cancelStationButton");

    title.textContent = `Станція ${assignment.station}`;
    list.innerHTML = "";

    workers.forEach(worker => {
        const button = document.createElement("button");
        button.className = "station-worker-option";
        button.textContent = worker.name;

        button.onclick = async () => {
            const selectedAssignment = scheduleAssignments.find(item =>
                item.work_date === workDate &&
                item.worker_id === worker.id
            );

            changingStations.add(`${workDate}_${assignment.station}`);

            if (selectedAssignment && selectedAssignment !== assignment) {
                changingStations.add(`${workDate}_${selectedAssignment.station}`);

                selectedAssignment.worker_id = assignment.worker_id;
                selectedAssignment.worker_name = assignment.worker_name;

                await saveScheduleAssignment(selectedAssignment, workDate);
            }

            assignment.worker_id = worker.id;
            assignment.worker_name = worker.name;

            const saved = await saveScheduleAssignment(assignment, workDate);

            if (!saved) {
                return;
            }

            modal.classList.add("hidden");
            renderSchedule();
        };

        list.appendChild(button);
    });

    clearButton.onclick = async () => {
        const weekStart = formatDate(getWeekStart());

        const response = await fetch("/api/schedule/assignment", {
            method: "DELETE",
            headers: {
                "Content-Type": "application/json"
            },
            body: JSON.stringify({
                week_start: weekStart,
                work_date: workDate,
                station: assignment.station
            })
        });

        if (!response.ok) {
            alert("Не вдалося звільнити станцію");
            return;
        }

        const index = scheduleAssignments.indexOf(assignment);

        if (index !== -1) {
            scheduleAssignments.splice(index, 1);
        }

        changingStations.add(`${workDate}_${assignment.station}`);

        modal.classList.add("hidden");
        renderSchedule();
    };

    cancelButton.onclick = () => {
        modal.classList.add("hidden");
    };

    modal.onclick = event => {
        if (event.target === modal) {
            modal.classList.add("hidden");
        }
    };

    modal.classList.remove("hidden");
}

function openStationChoiceModal(worker, workDate) {
    const modal = document.getElementById("stationModal");
    const title = document.getElementById("stationModalTitle");
    const list = document.getElementById("stationWorkerList");
    const clearButton = document.getElementById("clearStationButton");
    const cancelButton = document.getElementById("cancelStationButton");

    title.textContent = `Станція для ${worker.name}`;
    list.innerHTML = "";

    for (let station = 15; station <= 24; station++) {
        const button = document.createElement("button");
        button.className = "station-choice-option";
        button.textContent = station;

        button.onclick = async () => {
            const selectedAssignment = scheduleAssignments.find(item =>
                item.work_date === workDate &&
                item.station === station
            );

            if (selectedAssignment) {
                const oldWorkerId = selectedAssignment.worker_id;
                const oldWorkerName = selectedAssignment.worker_name;

                const workerAssignment = scheduleAssignments.find(item =>
                    item.work_date === workDate &&
                    item.worker_id === worker.id
                );

                changingStations.add(`${workDate}_${station}`);

                if (workerAssignment && workerAssignment !== selectedAssignment) {
                    changingStations.add(
                        `${workDate}_${workerAssignment.station}`
                    );

                    workerAssignment.worker_id = oldWorkerId;
                    workerAssignment.worker_name = oldWorkerName;

                    await saveScheduleAssignment(workerAssignment, workDate);
                }

                selectedAssignment.worker_id = worker.id;
                selectedAssignment.worker_name = worker.name;

                const saved = await saveScheduleAssignment(
                    selectedAssignment,
                    workDate
                );

                if (!saved) {
                    return;
                }
            } else {
                const assignment = {
                    week_id: scheduleAssignments[0]?.week_id,
                    work_date: workDate,
                    worker_id: worker.id,
                    worker_name: worker.name,
                    station: station,
                    shift: scheduleShift
                };

                const saved = await saveScheduleAssignment(
                    assignment,
                    workDate
                );

                if (!saved) {
                    return;
                }

                scheduleAssignments.push(assignment);
                changingStations.add(`${workDate}_${station}`);
            }

            modal.classList.add("hidden");
            clearButton.style.display = "";
            renderSchedule();
        };

        list.appendChild(button);
    }

    clearButton.style.display = "none";

    cancelButton.onclick = () => {
        modal.classList.add("hidden");
        clearButton.style.display = "";
    };

    modal.onclick = event => {
        if (event.target === modal) {
            modal.classList.add("hidden");
            clearButton.style.display = "";
        }
    };

    modal.classList.remove("hidden");
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

    [...workers].sort((a, b) => Number(a.is_reserve) - Number(b.is_reserve)).forEach(worker => {
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
                const stationKey = `${workDate}_${assignment.station}`;
                station.className = changingStations.has(stationKey)
                    ? "station station-changing"
                    : "station";
                station.textContent = assignment.station;

                station.onclick = () => {
                    openStationModal(assignment, workDate);
                };

                cell.appendChild(station);
            } else {
                cell.onclick = () => {
                    openStationChoiceModal(worker, workDate);
                };
            }

            row.appendChild(cell);
        }

        const lunch = document.createElement("td");
        lunch.className = "lunch lunch-column";
        lunch.textContent = "—";

        row.appendChild(lunch);
        body.appendChild(row);
    });

    if (changingStations.size) {
        setTimeout(() => {
            changingStations.clear();
        }, 600);
    }
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
navButtons[1].addEventListener("click", async () => {
    await showWorkersScreen();
    setActiveNav(1);
});
navButtons[2].addEventListener("click", async () => {
    await showLunchScreen();
    setActiveNav(2);
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

    if (!scheduleLoaded) {
        await loadScheduleWorkers();
        await loadScheduleDays();
        await loadScheduleShift();
        await loadScheduleAssignments();
        scheduleLoaded = true;
    }

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

showScheduleScreen();

async function showLunchScreen() {
    const main = document.querySelector("main");

    if (!workers.length) {
        await loadScheduleWorkers();
    }

    const options = workers
        .filter(worker => !worker.is_reserve)
        .map(worker =>
            `<option value="${worker.id}">${worker.name}</option>`
        )
        .join("");

    const pairs = Array.from({ length: 5 }, (_, index) => `
        <div class="lunch-pair">
            <strong>Пара ${index + 1}</strong>
            <select class="lunch-worker">${options}</select>
            <select class="lunch-worker">${options}</select>
        </div>
    `).join("");

    main.innerHTML = `
        <section class="card">
            <div class="card-title">🍽 Обіди</div>

            <div class="lunch-settings">
                <label>
                    Час першої пари
                    <input id="lunchStartTime" type="time" value="11:00">
                </label>
            </div>

            <div class="lunch-pairs">
                ${pairs}
            </div>

            <button class="add-worker-button">
                Зберегти
            </button>
        </section>
    `;
}
