window.addEventListener("error", e => alert("JS ERROR: " + (e.error?.stack || e.message))); window.addEventListener("unhandledrejection", e => alert("PROMISE ERROR: " + e.reason));
const tg = window.Telegram.WebApp;

tg.ready();

if (tg.setHeaderColor) {
    tg.setHeaderColor("#f8f8fa");
}

if (tg.setBackgroundColor) {
if (tg.requestFullscreen) {
    try {
        tg.requestFullscreen();
    } catch (error) {
        tg.expand();
    }
} else {
    tg.expand();
}
    tg.expand();
}

let workers = [];
let scheduleDays = [];
let scheduleShift = null;
let scheduleAssignments = [];
let scheduleLoaded = false;
let changingStations = new Set();
let workersScreenLoaded = false;
let lunchScreenLoaded = false;
let lunchSettings = [];

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

function getLunchForWorker(workerId, shift) {
    const setting = lunchSettings.find(item =>
        item.shift === shift &&
        (item.worker1_id === workerId || item.worker2_id === workerId)
    );

    if (!setting) {
        return null;
    }

    const pairNumber = setting.pair_number;
    const pairSettings = lunchSettings.find(item =>
        item.shift === shift &&
        item.pair_number === pairNumber
    );

    return {
        pairNumber,
        startTime: pairSettings?.start_time
            ? String(pairSettings.start_time).slice(0, 5)
            : null
    };
}

function renderSchedule() {
    const body = document.getElementById("scheduleBody");
    updateScheduleDayHeaders();

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

        const lunchInfo = getLunchForWorker(worker.id, scheduleShift);

        if (lunchInfo) {
            const setting = lunchSettings.find(item =>
                item.shift === scheduleShift &&
                item.pair_number === lunchInfo.pairNumber
            );

            if (setting) {
                const [hour, minute] = String(setting.start_time)
                    .slice(0, 5)
                    .split(":")
                    .map(Number);

                const totalMinutes =
                    (hour * 60 + minute + (lunchInfo.pairNumber - 1) * 30) % 1440;

                const lunchHour = String(Math.floor(totalMinutes / 60)).padStart(2, "0");
                const lunchMinute = String(totalMinutes % 60).padStart(2, "0");

                lunch.textContent = `${lunchHour}:${lunchMinute}`;
            } else {
                lunch.textContent = "—";
            }
        } else {
            lunch.textContent = "—";
        }

        row.appendChild(lunch);
        body.appendChild(row);
    });

    if (changingStations.size) {
        setTimeout(() => {
            changingStations.clear();
        }, 600);
    }
}


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

function updateScheduleDayHeaders() {
    const dayNames = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Нд"];
    const weekStart = getWeekStart();

    dayNames.forEach((name, index) => {
        const date = new Date(weekStart);
        date.setDate(date.getDate() + index);

        const element = document.getElementById(`scheduleDay${index}`);

        if (element) {
            const day = String(date.getDate()).padStart(2, "0");
            const month = String(date.getMonth() + 1).padStart(2, "0");
            element.textContent = `${name} ${day}.${month}`;
        }
    });
}


const weekTitle = document.getElementById("weekTitle");

function updateWeek() {
    const weekStart = getWeekStart();
    const weekEnd = new Date(weekStart);
    weekEnd.setDate(weekEnd.getDate() + 6);

    const formatShortDate = date =>
        `${String(date.getDate()).padStart(2, "0")}.${String(date.getMonth() + 1).padStart(2, "0")}`;

    weekTitle.textContent = `${formatShortDate(weekStart)} — ${formatShortDate(weekEnd)}`;
}



const navButtons = document.querySelectorAll(".bottom-nav button");
navButtons[1].addEventListener("click", async () => {
    showScreen("workersScreen");
    await showWorkersScreen();
    setActiveNav(1);
});
navButtons[2].addEventListener("click", async () => {
    showScreen("lunchScreen");
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
    const screen = document.getElementById("scheduleScreen");

    if (!scheduleLoaded) {
        await loadScheduleWorkers();
        await loadScheduleDays();
        await loadScheduleShift();
        await loadScheduleAssignments();
        await loadLunchSettings();

        scheduleLoaded = true;

        renderSchedule();
        bindScheduleButtons();
        return;
    }

    screen.hidden = false;
}
function bindScheduleButtons() {
    document.getElementById("prevWeek").onclick = async () => {
        weekOffset--;
        updateWeek();
        await loadScheduleDays();
    await loadScheduleShift();
    await loadScheduleAssignments();
        await loadLunchSettings();
        renderSchedule();
    };

    document.getElementById("nextWeek").onclick = async () => {
        weekOffset++;
        updateWeek();
        await loadScheduleDays();
    await loadScheduleShift();
    await loadScheduleAssignments();
        await loadLunchSettings();
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
    showScreen("scheduleScreen");
    showScheduleScreen();
    setActiveNav(0);
});

function setActiveNav(index) {
    navButtons.forEach((button, i) => {
        button.classList.toggle("active", i === index);
    });
}

function showScreen(screenId) {
    document.querySelectorAll("main > div[id$='Screen']").forEach(screen => {
        screen.hidden = screen.id !== screenId;
    });
}

showScreen("scheduleScreen");
showScheduleScreen();

async function loadLunchSettings() {
    const weekStart = formatDate(getWeekStart());
    const response = await fetch(`/api/lunch/settings?week_start=${weekStart}`);

    if (!response.ok) {
        alert("Не вдалося завантажити налаштування обідів");
        return [];
    }

    lunchSettings = await response.json();
    return lunchSettings;
}

async function showLunchScreen() {
    const screen = document.getElementById("lunchScreen");

    if (lunchScreenLoaded) {
        return;
    }

    if (!workers.length) {
        await loadScheduleWorkers();
    }

    await loadLunchSettings();

    const pairs = Array.from({ length: 5 }, (_, index) => `
        <div class="lunch-pair">
            <button class="lunch-worker-button" data-pair="${index}" data-slot="0">
                Обрати працівника
            </button>
            <button class="lunch-worker-button" data-pair="${index}" data-slot="1">
                Обрати працівника
            </button>
        </div>
    `).join("");

    screen.innerHTML = `
        <section class="card">
            <div class="card-title">🍽 Обіди</div>

            <div class="lunch-shifts">
                <div class="lunch-shift">
                    <strong>Зміна 1</strong>
                    <label>
                        Початок обіду
                        <button class="lunch-time-button" data-time="10:00">10:00</button>
                    </label>
                </div>

                <div class="lunch-shift">
                    <strong>Зміна 2</strong>
                    <label>
                        Початок обіду
                        <button class="lunch-time-button" data-time="18:00">18:00</button>
                    </label>
                </div>

                <div class="lunch-shift">
                    <strong>Зміна 3</strong>
                    <label>
                        Початок обіду
                        <button class="lunch-time-button" data-time="02:00">02:00</button>
                    </label>
                </div>
            </div>

            <div class="lunch-pairs">
                ${pairs}
            </div>

            <button class="add-worker-button">
                Зберегти
            </button>
        </section>

        <div id="lunchModal" class="station-modal hidden">
            <div class="station-modal-box">
                <div id="lunchModalTitle" class="station-modal-title"></div>
                <div id="lunchModalContent" class="station-worker-list"></div>
                <button id="lunchModalCancel" class="station-cancel-button">
                    Скасувати
                </button>
            </div>
        </div>
    `;

    const shiftSettings = {
        1: lunchSettings.find(item => item.shift === 1),
        2: lunchSettings.find(item => item.shift === 2),
        3: lunchSettings.find(item => item.shift === 3)
    };

    document.querySelectorAll(".lunch-time-button").forEach(button => {
        const shift = button.closest(".lunch-shift")?.querySelector("strong")?.textContent;
        const match = shift?.match(/Зміна (\\d)/);

        if (!match) {
            return;
        }

        const setting = shiftSettings[Number(match[1])];

        if (setting?.start_time) {
            const time = String(setting.start_time).slice(0, 5);
            button.textContent = time;
            button.dataset.time = time;
        }
    });

    for (let index = 0; index < 5; index++) {
        const setting = lunchSettings.find(
            item => item.shift === 1 && item.pair_number === index + 1
        );

        const buttons = document.querySelectorAll(
            `.lunch-worker-button[data-pair="${index}"]`
        );

        if (!setting) {
            continue;
        }

        if (setting.worker1_id) {
            buttons[0].textContent = setting.worker1_name || "Обрати працівника";
            buttons[0].dataset.workerId = setting.worker1_id;
        }

        if (setting.worker2_id) {
            buttons[1].textContent = setting.worker2_name || "Обрати працівника";
            buttons[1].dataset.workerId = setting.worker2_id;
        }
    }

    const saveLunchButton = screen.querySelector(".add-worker-button");

    saveLunchButton.onclick = async () => {
        const timeButtons = screen.querySelectorAll(".lunch-time-button");
        const times = Array.from(timeButtons).map(button => button.dataset.time);

        for (let shift = 1; shift <= 3; shift++) {
            for (let index = 0; index < 5; index++) {
                const buttons = screen.querySelectorAll(
                    `.lunch-worker-button[data-pair="${index}"]`
                );

                const worker1Id = buttons[0].dataset.workerId
                    ? Number(buttons[0].dataset.workerId)
                    : null;

                const worker2Id = buttons[1].dataset.workerId
                    ? Number(buttons[1].dataset.workerId)
                    : null;

                const response = await fetch("/api/lunch/settings", {
                    method: "PUT",
                    headers: {
                        "Content-Type": "application/json"
                    },
                    body: JSON.stringify({
                        week_start: formatDate(getWeekStart()),
                        shift,
                        pair_number: index + 1,
                        worker1_id: worker1Id,
                        worker2_id: worker2Id,
                        start_time: times[shift - 1]
                    })
                });

                if (!response.ok) {
                    alert("Не вдалося зберегти налаштування обідів");
                    return;
                }
            }
        }

        await loadLunchSettings();
        lunchScreenLoaded = false;
        await showLunchScreen();
        alert("Налаштування обідів збережено");
    };

    lunchScreenLoaded = true;
}


function openLunchWorkerModal(button) {
    const modal = document.getElementById("lunchModal");
    const title = document.getElementById("lunchModalTitle");
    const content = document.getElementById("lunchModalContent");
    const cancelButton = document.getElementById("lunchModalCancel");

    title.textContent = "Обрати працівника";
    content.innerHTML = "";

    workers
        .filter(worker => !worker.is_reserve)
        .forEach(worker => {
            const option = document.createElement("button");
            option.className = "station-worker-option";
            option.textContent = worker.name;

            option.onclick = () => {
                button.textContent = worker.name;
                button.dataset.workerId = worker.id;
                modal.classList.add("hidden");
            };

            content.appendChild(option);
        });

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

function openLunchTimeModal(button) {
    const modal = document.getElementById("lunchModal");
    const title = document.getElementById("lunchModalTitle");
    const content = document.getElementById("lunchModalContent");
    const cancelButton = document.getElementById("lunchModalCancel");

    title.textContent = "Початок обіду";
    content.innerHTML = "";

    const current = button.dataset.time || button.textContent;
    const [currentHour, currentMinute] = current.split(":").map(Number);

    const picker = document.createElement("div");
    picker.className = "lunch-time-picker";

    const hourFrame = document.createElement("div");
    hourFrame.className = "lunch-time-frame";

    const minuteFrame = document.createElement("div");
    minuteFrame.className = "lunch-time-frame";

    const hourWheel = document.createElement("div");
    hourWheel.className = "lunch-time-wheel";

    const minuteWheel = document.createElement("div");
    minuteWheel.className = "lunch-time-wheel";

    const hourSpacerTop = document.createElement("div");
    hourSpacerTop.className = "lunch-time-wheel-spacer";

    const minuteSpacerTop = document.createElement("div");
    minuteSpacerTop.className = "lunch-time-wheel-spacer";

    const hourSpacerBottom = document.createElement("div");
    hourSpacerBottom.className = "lunch-time-wheel-spacer";

    const minuteSpacerBottom = document.createElement("div");
    minuteSpacerBottom.className = "lunch-time-wheel-spacer";

    hourWheel.appendChild(hourSpacerTop);
    minuteWheel.appendChild(minuteSpacerTop);

    for (let i = 0; i < 24; i++) {
        const option = document.createElement("div");
        option.className = "lunch-time-option";
        option.dataset.value = String(i).padStart(2, "0");
        option.textContent = option.dataset.value;
        hourWheel.appendChild(option);
    }

    for (let i = 0; i < 60; i += 10) {
        const option = document.createElement("div");
        option.className = "lunch-time-option";
        option.dataset.value = String(i).padStart(2, "0");
        option.textContent = option.dataset.value;
        minuteWheel.appendChild(option);
    }

    hourWheel.appendChild(hourSpacerBottom);
    minuteWheel.appendChild(minuteSpacerBottom);

    const separator = document.createElement("div");
    separator.className = "lunch-time-separator";
    separator.textContent = ":";

    hourFrame.appendChild(hourWheel);
    minuteFrame.appendChild(minuteWheel);

    picker.append(hourFrame, separator, minuteFrame);
    content.appendChild(picker);

    const hourIndex = Math.max(0, Math.min(23, currentHour));
    const minuteIndex = Math.max(0, Math.min(5, Math.round(currentMinute / 10)));

    const scrollWheelToIndex = (wheel, index) => {
        wheel.scrollTop = index * 40;
    };

    scrollWheelToIndex(hourWheel, hourIndex);
    scrollWheelToIndex(minuteWheel, minuteIndex);

    const updateSelected = wheel => {
        const options = wheel.querySelectorAll(".lunch-time-option");
        const index = Math.round(wheel.scrollTop / 40);

        options.forEach((option, i) => {
            option.classList.toggle("selected", i === index);
        });
    };

    let hourTimer;
    let minuteTimer;

    hourWheel.addEventListener("scroll", () => {
        updateSelected(hourWheel);
        clearTimeout(hourTimer);

        hourTimer = setTimeout(() => {
            const index = Math.max(0, Math.min(23, Math.round(hourWheel.scrollTop / 40)));
            hourWheel.scrollTo({
                top: index * 40,
                behavior: "smooth"
            });
            updateSelected(hourWheel);
        }, 80);
    });

    minuteWheel.addEventListener("scroll", () => {
        updateSelected(minuteWheel);
        clearTimeout(minuteTimer);

        minuteTimer = setTimeout(() => {
            const index = Math.max(0, Math.min(5, Math.round(minuteWheel.scrollTop / 40)));
            minuteWheel.scrollTo({
                top: index * 40,
                behavior: "smooth"
            });
            updateSelected(minuteWheel);
        }, 80);
    });

    hourWheel.addEventListener("click", event => {
        const option = event.target.closest(".lunch-time-option");
        if (!option) return;

        const index = Number(option.dataset.value);
        scrollWheelToIndex(hourWheel, index);
    });

    minuteWheel.addEventListener("click", event => {
        const option = event.target.closest(".lunch-time-option");
        if (!option) return;

        const index = Number(option.dataset.value) / 10;
        scrollWheelToIndex(minuteWheel, index);
    });

    requestAnimationFrame(() => {
        updateSelected(hourWheel);
        updateSelected(minuteWheel);
    });

    const saveButton = document.createElement("button");
    saveButton.className = "station-cancel-button";
    saveButton.textContent = "Готово";

    saveButton.onclick = () => {
        const hourIndex = Math.max(0, Math.min(23, Math.round(hourWheel.scrollTop / 40)));
        const minuteIndex = Math.max(0, Math.min(5, Math.round(minuteWheel.scrollTop / 40)));

        const hour = String(hourIndex).padStart(2, "0");
        const minute = String(minuteIndex * 10).padStart(2, "0");
        const time = `${hour}:${minute}`;

        button.textContent = time;
        button.dataset.time = time;
        modal.classList.add("hidden");
    };

    content.appendChild(saveButton);

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

document.addEventListener("click", event => {
    const workerButton = event.target.closest(".lunch-worker-button");

    if (workerButton) {
        openLunchWorkerModal(workerButton);
        return;
    }

    const timeButton = event.target.closest(".lunch-time-button");

    if (timeButton) {
        openLunchTimeModal(timeButton);
    }
});
