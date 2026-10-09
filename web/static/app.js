const appLog = [];
const appLogStartedAt = Date.now();

function appLogEvent(message, data = null) {
    const time = new Date().toISOString();
    const elapsed = Date.now() - appLogStartedAt;
    let line = `[${time}] +${elapsed}ms ${message}`;

    if (data !== null) {
        try {
            line += ` | ${JSON.stringify(data)}`;
        } catch {
            line += ` | ${String(data)}`;
        }
    }

    appLog.push(line);
    console.log(line);

    if (appLog.length > 500) {
        appLog.shift();
    }
}

appLogEvent("APP.JS START", {
    visibility: document.visibilityState,
    readyState: document.readyState,
    url: location.origin + location.pathname
});

window.addEventListener("error", (event) => {
    appLogEvent("WINDOW ERROR CAPTURE", {
        message: event.message,
        filename: event.filename,
        lineno: event.lineno,
        colno: event.colno,
        target: event.target?.tagName || "",
        targetSrc: event.target?.src || "",
        targetHref: event.target?.href || "",
        error: event.error?.stack || String(event.error || "")
    });
}, true);

window.addEventListener("error", (event) => {
    appLogEvent("WINDOW ERROR", {
        message: event.message,
        filename: event.filename,
        lineno: event.lineno,
        colno: event.colno,
        error: event.error?.stack || String(event.error || "")
    });

    // Непрозора помилка "Script error." без файлу, рядка та стеку — це помилка зі
    // сторонього домену (telegram.org/js/telegram-web-app.js), яку браузер
    // приховує. Вона не походить із коду застосунку і не повинна блокувати UI
    // червоним екраном (типово виникає при згортанні/розгортанні Mini App).
    const isOpaqueCrossOriginError =
        !event.error &&
        !event.filename &&
        !event.lineno &&
        /^script error\.?$/i.test(String(event.message || "").trim());

    if (isOpaqueCrossOriginError) {
        appLogEvent("OPAQUE CROSS-ORIGIN ERROR IGNORED", {
            visibility: document.visibilityState,
            telegramVersion: window.Telegram?.WebApp?.version || "unknown",
            platform: window.Telegram?.WebApp?.platform || "unknown"
        });
        return;
    }

    const box = document.getElementById("jsError");
    const text = document.getElementById("jsErrorText");

    if (box && text) {
        box.style.display = "";
        text.textContent =
            event.error?.stack ||
            `${event.message || "Script error"}\nURL: ${event.filename || "невідомо"}\nРядок: ${event.lineno || "?"}, колонка: ${event.colno || "?"}`;
    }
});

window.addEventListener("unhandledrejection", (event) => {
    appLogEvent("UNHANDLED REJECTION", {
        reason: event.reason?.stack || String(event.reason)
    });

    const box = document.getElementById("jsError");
    const text = document.getElementById("jsErrorText");

    if (box && text) {
        box.style.display = "";
        text.textContent = event.reason?.stack || String(event.reason);
    }
});

document.addEventListener("visibilitychange", () => {
    appLogEvent("VISIBILITY CHANGE", {
        visibility: document.visibilityState
    });

    if (
        document.visibilityState === "visible" &&
        shareMessageInProgress
    ) {
        appLogEvent("SHARE RECOVERED AFTER VISIBILITY RETURN");

        shareMessageInProgress = false;
        preparedShareMessageId = null;
        preparedShareWeek = null;
        updateShareButtonState();

        setTimeout(() => {
            if (document.visibilityState !== "visible") {
                appLogEvent("SHARE RECOVERY PREPARE SKIPPED: APP HIDDEN");
                return;
            }

            appLogEvent("SHARE RECOVERY PREPARE START");
            prepareShareInBackground();
        }, 100);
    }
});

window.addEventListener("pageshow", () => {
    appLogEvent("PAGE SHOW");
});

window.addEventListener("pagehide", () => {
    appLogEvent("PAGE HIDE");
});

window.addEventListener("freeze", () => {
    appLogEvent("PAGE FREEZE");
});

window.addEventListener("resume", () => {
    appLogEvent("PAGE RESUME");
});

appLogEvent("PAGE STATE", {
    wasDiscarded: document.wasDiscarded === true
});

const originalConsoleError = console.error.bind(console);
const originalConsoleWarn = console.warn.bind(console);

console.error = (...args) => {
    appLogEvent("CONSOLE ERROR", args.map(String).join(" "));
    originalConsoleError(...args);
};

console.warn = (...args) => {
    appLogEvent("CONSOLE WARN", args.map(String).join(" "));
    originalConsoleWarn(...args);
};

const copyJsLogHeaderButton = document.getElementById("copyJsLogHeaderButton");

if (copyJsLogHeaderButton) {
    copyJsLogHeaderButton.addEventListener("click", () => {
        const button = document.getElementById("copyJsLogButton");
        if (button) {
            button.click();
        }
    });
}

const copyJsLogButton = document.getElementById("copyJsLogButton");

if (copyJsLogButton) {
    copyJsLogButton.addEventListener("click", async () => {
        appLogEvent("COPY DIAGNOSTIC LOG");

        const resources = performance
            .getEntriesByType("resource")
            .slice(-100)
            .map(resource => `${resource.name} | ${Math.round(resource.duration)}ms`);

        const scripts = Array.from(document.scripts)
            .map(script => script.src || "[inline script]");

        const log = [
            "=== TELEGRAM MINI APP DIAGNOSTIC LOG ===",
            `Generated: ${new Date().toISOString()}`,
            `Visibility: ${document.visibilityState}`,
            `Telegram: ${!!window.Telegram}`,
            `WebApp: ${!!tg}`,
            `Platform: ${tg?.platform || "unknown"}`,
            `WebApp API: ${tg?.version || "unknown"}`,
            `User-Agent: ${navigator.userAgent || "unknown"}`,
            `Telegram Android: ${(navigator.userAgent.match(/Telegram-Android\/([0-9.]+)/i) || [])[1] || "not detected"}`,
            `InitData length: ${tg?.initData?.length || 0}`,
            "",
            "=== APP EVENTS ===",
            ...appLog,
            "",
            "=== LOADED SCRIPTS ===",
            ...scripts,
            "",
            "=== RESOURCE TIMING ===",
            ...resources
        ].join("\n");

        try {
            await navigator.clipboard.writeText(log);
            copyJsLogButton.textContent = "✓ Лог скопійовано";
            setTimeout(() => {
                copyJsLogButton.textContent = "Скопіювати діагностичний лог";
            }, 1800);
        } catch (error) {
            appLogEvent("COPY LOG ERROR", error?.stack || String(error));
            prompt("Скопіюйте діагностичний лог:", log);
        }
    });
}

const tg = window.Telegram?.WebApp;




const originalFetch = window.fetch.bind(window);

window.fetch = async (input, init = {}) => {
    const url = typeof input === "string" ? input : input.url;
    const method = init.method || "GET";

    appLogEvent("FETCH START", {
        method,
        url
    });

    const requestUrl = new URL(url, window.location.origin);
        const isApiRequest =
            requestUrl.origin === window.location.origin &&
            requestUrl.pathname.startsWith("/api/");

        if (isApiRequest) {
        const headers = new Headers(init.headers || {});

        if (!headers.has("X-Telegram-Init-Data")) {
            headers.set("X-Telegram-Init-Data", tg?.initData || "");
        }

        init.headers = headers;
    }

    try {
        const response = await originalFetch(input, init);

        appLogEvent("FETCH END", {
            method,
            url,
            status: response.status,
            ok: response.ok
        });

        return response;
    } catch (error) {
        appLogEvent("FETCH ERROR", {
            method,
            url,
            error: error?.stack || String(error)
        });

        throw error;
    }
};

let currentAuth = null;

async function checkAdminAccess() {
    appLogEvent("ADMIN AUTH START", {
        telegramAvailable: !!window.Telegram,
        webAppAvailable: !!tg,
        initDataLength: tg?.initData?.length || 0,
        platform: tg?.platform || "unknown",
        version: tg?.version || "unknown"
    });

    const denied = document.getElementById("accessDenied");

    const response = await fetch("/api/auth/me");

    appLogEvent("ADMIN AUTH RESPONSE", {
        status: response.status,
        ok: response.ok
    });

    if (!response.ok) {
        denied.querySelector("h2").textContent = "Доступ заборонено";
        denied.querySelector("p").textContent =
            "Цей Mini App доступний лише адміністраторам.";
        throw new Error("Admin access denied");
    }

    denied.style.display = "none";
    document.querySelector(".app").style.display = "block";

    currentAuth = await response.json();
    return currentAuth;
}
let preparedShareMessageId = null;
let preparedShareWeek = null;
let shareMessageInProgress = false;
if (tg?.onEvent) {
    tg.onEvent("shareMessageSent", () => {
        console.log("SHARE SENT");
        appLogEvent("SHARE SENT");
        preparedShareMessageId = null;
        preparedShareWeek = null;
        shareMessageInProgress = false;
    });
    tg.onEvent("shareMessageFailed", (error) => {
        console.log("SHARE FAILED:", error);
        appLogEvent("SHARE FAILED: " + JSON.stringify(error));
        preparedShareMessageId = null;
        preparedShareWeek = null;
        shareMessageInProgress = false;
    });
}

const adminAccessPromise = checkAdminAccess()
    .then(() => {
        appLogEvent("ADMIN AUTH SUCCESS");

        if (tg?.ready) {
            tg.ready();
            appLogEvent("TELEGRAM READY");
        }

        return true;
    })
    .catch((error) => {
        appLogEvent("ADMIN AUTH ERROR", error?.stack || String(error));
        console.error("ADMIN AUTH:", error);
        return false;
    });

if (tg?.setHeaderColor) {
    tg.setHeaderColor("#f8f8fa");
}

if (tg?.setBackgroundColor) {
    tg.setBackgroundColor("#f8f8fa");
}

if (tg?.expand) {
    tg.expand();
}

if (tg?.requestFullscreen) {
    try {
        const fullscreenResult = tg.requestFullscreen();

        if (fullscreenResult?.catch) {
            fullscreenResult.catch(() => {
                tg.expand?.();
            });
        }
    } catch {
        tg.expand?.();
    }
}

let selectedExotecGroup = "exotec_2";
let availableWorkGroups = [];
let selectedGroupStations = [];

function getSelectedExotecStationNumbers() {
    return selectedGroupStations.map(station => Number(station.station_number));
}

let workers = [];
let scheduleDays = [];
let scheduleShift = null;
let scheduleTeamSlots = null;
let selectedScheduleTeam = "A";
let scheduleAssignments = [];
let scheduleReserves = [];
let scheduleLoaded = false;
let changingStations = new Set();
let lunchScreenLoaded = false;
let lunchSettings = null;
let lunchSettingsPromise = null;
let lunchSettingsPromiseWeek = null;
let workerDaysOff = [];

async function loadWorkerDaysOff() {
    const requestWeek = formatDate(getWeekStart());
    const weekEndDate = new Date(getWeekStart());
    weekEndDate.setDate(weekEndDate.getDate() + 6);
    const weekEnd = formatDate(weekEndDate);

    const response = await fetch(
        `/api/worker-days-off?start_date=${requestWeek}&end_date=${weekEnd}&group=${encodeURIComponent(selectedExotecGroup)}`
    );

    if (!response.ok) {
        if (formatDate(getWeekStart()) !== requestWeek) {
            return;
        }

        alert("Не вдалося завантажити вихідні працівників");
        workerDaysOff = [];
        return;
    }

    const data = await response.json();

    if (formatDate(getWeekStart()) !== requestWeek) {
        return;
    }

    workerDaysOff = data.days_off;
}


async function loadScheduleAssignments() {
    const requestWeek = formatDate(getWeekStart());

    const response = await fetch(
        `/api/schedule/assignments?week_start=${requestWeek}&group=${encodeURIComponent(selectedExotecGroup)}`
    );

    if (!response.ok) {
        if (formatDate(getWeekStart()) !== requestWeek) {
            return;
        }

        alert("Не вдалося завантажити призначення");
        scheduleAssignments = [];
        scheduleReserves = [];
        return;
    }

    const data = await response.json();

    if (formatDate(getWeekStart()) !== requestWeek) {
        return;
    }

    scheduleAssignments = data.assignments;
    scheduleReserves = data.reserves || [];
}


async function saveScheduleAssignment(assignment, workDate) {
    const weekStart = formatDate(getWeekStart());

    const response = await fetch(`/api/schedule/assignment?group=${encodeURIComponent(selectedExotecGroup)}`, {
        method: "PUT",
        headers: {
            "Content-Type": "application/json"
        },
        body: JSON.stringify({
            week_start: weekStart,
            work_date: workDate,
            worker_id: assignment.worker_id,
            station: assignment.station,
            shift: assignment.shift || scheduleShift,
                group: selectedExotecGroup
        })
    });

    if (!response.ok) {
        const errorText = await response.text();
        let message = errorText;
        try {
            message = JSON.parse(errorText).detail || errorText;
        } catch (error) {
            // Відповідь не JSON — показуємо як є.
        }
        alert(`Не вдалося зберегти зміну (${response.status})\n${message}`);
        return false;
    }

    return true;
}


function openStationChoiceModal(worker, workDate, currentAssignment = null) {
    const modal = document.getElementById("stationModal");
    const title = document.getElementById("stationModalTitle");
    const list = document.getElementById("stationWorkerList");
    const clearButton = document.getElementById("clearStationButton");
    const cancelButton = document.getElementById("cancelStationButton");

    title.textContent = `Станція для ${worker.name}`;
    list.innerHTML = "";
    clearButton.style.display = currentAssignment ? "" : "none";

    const dayOffButton = document.createElement("button");
    dayOffButton.className = "station-choice-option";
    dayOffButton.textContent = "Встановити вихідний";

    dayOffButton.onclick = async () => {
        const response = await fetch(`/api/worker-days-off?group=${encodeURIComponent(selectedExotecGroup)}`, {
            method: "PUT",
            headers: {
                "Content-Type": "application/json"
            },
            body: JSON.stringify({
                worker_id: worker.id,
                work_date: workDate,
                is_day_off: true,
                group: selectedExotecGroup
            })
        });

        if (!response.ok) {
            alert("Не вдалося встановити вихідний");
            return;
        }

        workerDaysOff.push({
            worker_id: worker.id,
            work_date: workDate
        });

        scheduleAssignments = scheduleAssignments.filter(item =>
            !(Number(item.worker_id) === Number(worker.id) &&
              item.work_date === workDate)
        );

        modal.classList.add("hidden");
        clearButton.style.display = "";
        markScheduleChanged();
    };

    list.appendChild(dayOffButton);

    const reserveButton = document.createElement("button");
    reserveButton.className = "station-choice-option";
    reserveButton.textContent = "Встановити Reserve";

    reserveButton.onclick = async () => {
        const response = await fetch(`/api/schedule/reserve?group=${encodeURIComponent(selectedExotecGroup)}`, {
            method: "PUT",
            headers: {
                "Content-Type": "application/json"
            },
            body: JSON.stringify({
                week_start: formatDate(getWeekStart()),
                work_date: workDate,
                worker_id: worker.id,
                            group: selectedExotecGroup
            })
        });

        if (!response.ok) {
            alert("Не вдалося встановити Reserve");
            return;
        }

        modal.classList.add("hidden");
        await loadScheduleAssignments();
        markScheduleChanged();
    };

    list.appendChild(reserveButton);

    const stationAssignments = new Map();
    const workerAssignments = new Map();

    const modalTeam = String(worker.team_code).trim();

    for (const item of scheduleAssignments) {
        if (item.work_date !== workDate) {
            continue;
        }

        // Станцію займає лише працівник тієї ж бригади (зміни).
        if (String(item.team_code || getWorkerTeam(item.worker_id)).trim() !== modalTeam) {
            continue;
        }

        if (!stationAssignments.has(item.station)) {
            stationAssignments.set(item.station, item);
        }

        if (!workerAssignments.has(Number(item.worker_id))) {
            workerAssignments.set(Number(item.worker_id), item);
        }
    }

    for (const station of getSelectedExotecStationNumbers()) {
        const button = document.createElement("button");
        button.className = "station-choice-option";
        button.textContent = station;

        const selectedAssignment = stationAssignments.get(station);

        if (selectedAssignment) {
            button.style.opacity = "0.45";
            button.title = `Зайнята: ${selectedAssignment.worker_name}`;
        } else {
            button.title = "Вільна";
        }

        button.onclick = async () => {
            const selectedAssignment = stationAssignments.get(station);

            if (selectedAssignment) {
                const oldWorkerId = selectedAssignment.worker_id;
                const oldWorkerName = selectedAssignment.worker_name;
                const workerAssignment = workerAssignments.get(Number(worker.id));

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
                    shift: getTeamShift(modalTeam),
                    team_code: modalTeam
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
            markScheduleChanged();
        };

        list.appendChild(button);
    }

    clearButton.style.display = currentAssignment ? "" : "none";

    if (currentAssignment) {
        clearButton.onclick = async () => {
            const weekStart = formatDate(getWeekStart());

            const response = await fetch(`/api/schedule/assignment?group=${encodeURIComponent(selectedExotecGroup)}`, {
                method: "DELETE",
                headers: {
                    "Content-Type": "application/json"
                },
                body: JSON.stringify({
                    week_start: weekStart,
                    work_date: workDate,
                    station: currentAssignment.station,
                    worker_id: currentAssignment.worker_id,
                    group: selectedExotecGroup
                })
            });

            if (!response.ok) {
                alert("Не вдалося звільнити станцію");
                return;
            }

            scheduleAssignments = scheduleAssignments.filter(item =>
                item !== currentAssignment
            );

            changingStations.add(
                `${workDate}_${currentAssignment.station}`
            );

            modal.classList.add("hidden");
            clearButton.style.display = "";
            markScheduleChanged();
        };
    }

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

function addMinutesToTime(time, minutes) {
    const [hour, minute] = String(time).slice(0, 5).split(":").map(Number);
    if (Number.isNaN(hour) || Number.isNaN(minute)) {
        return null;
    }
    const total = (((hour * 60 + minute + minutes) % 1440) + 1440) % 1440;
    return `${String(Math.floor(total / 60)).padStart(2, "0")}:${String(total % 60).padStart(2, "0")}`;
}

// Час обіду обідньої групи бригади: початок зміни + (N-1) × інтервал.
function getLunchPairTime(teamCode, pairNumber) {
    if (!lunchSettings) {
        return null;
    }
    const slot = lunchSettings.team_slots
        ? lunchSettings.team_slots[teamCode]
        : null;
    const start = slot ? lunchSettings.start_times[String(slot)] : null;
    if (!start) {
        return null;
    }
    const interval = lunchSettings.interval_minutes || 30;
    return addMinutesToTime(start, (pairNumber - 1) * interval);
}

function getLunchForWorker(workerId) {
    const team = getWorkerTeam(workerId);
    if (!team || !lunchSettings || !lunchSettings.teams) {
        return null;
    }

    const pairs = lunchSettings.teams[team] || [];
    const index = pairs.findIndex(pair =>
        pair.some(member => Number(member.id) === Number(workerId))
    );

    if (index === -1) {
        return null;
    }

    return {
        pairNumber: index + 1,
        time: getLunchPairTime(team, index + 1)
    };
}

function openDayOffModal(worker, workDate) {
    const modal = document.getElementById("stationModal");
    const title = document.getElementById("stationModalTitle");
    const list = document.getElementById("stationWorkerList");
    const clearButton = document.getElementById("clearStationButton");
    const cancelButton = document.getElementById("cancelStationButton");

    title.textContent = `Day off — ${worker.name}`;
    list.innerHTML = "";

    const cancelDayOffButton = document.createElement("button");
    cancelDayOffButton.className = "station-choice-option";
    cancelDayOffButton.textContent = "Скасувати вихідний";

    cancelDayOffButton.onclick = async () => {
        const response = await fetch(`/api/worker-days-off?group=${encodeURIComponent(selectedExotecGroup)}`, {
            method: "PUT",
            headers: {
                "Content-Type": "application/json"
            },
            body: JSON.stringify({
                worker_id: worker.id,
                work_date: workDate,
                is_day_off: false,
                group: selectedExotecGroup
            })
        });

        if (!response.ok) {
            alert("Не вдалося скасувати вихідний");
            return;
        }

        workerDaysOff = workerDaysOff.filter(dayOff =>
            !(Number(dayOff.worker_id) === Number(worker.id) &&
              String(dayOff.work_date).slice(0, 10) === workDate)
        );

        modal.classList.add("hidden");
        clearButton.style.display = "";
        markScheduleChanged();
    };

    list.appendChild(cancelDayOffButton);

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
    updateScheduleDayHeaders();
    updateScheduleTeamTabs();

    body.innerHTML = "";

    const weekStart = getWeekStart();
    const weekDates = Array.from({ length: 7 }, (_, dayOffset) => {
        const date = new Date(weekStart);
        date.setDate(date.getDate() + dayOffset);
        return formatDate(date);
    });

    const dayOffKeys = new Set(
        workerDaysOff.map(dayOff =>
            `${dayOff.worker_id}_${String(dayOff.work_date).slice(0, 10)}`
        )
    );

    const reserveKeys = new Set(
        scheduleReserves.map(reserve =>
            `${reserve.worker_id}_${String(reserve.work_date).slice(0, 10)}`
        )
    );

    const assignmentsByWorkerDate = new Map();

    scheduleAssignments.forEach(assignment => {
        assignmentsByWorkerDate.set(
            `${assignment.worker_id}_${assignment.work_date}`,
            assignment
        );
    });

    const teamWorkers = workers.filter(worker =>
        String(worker.team_code).trim() === selectedScheduleTeam
    );

    if (!teamWorkers.length) {
        const row = document.createElement("tr");
        const cell = document.createElement("td");
        cell.colSpan = 9;
        cell.className = "workers-empty";
        cell.textContent = `У бригаді ${selectedScheduleTeam} ще немає працівників.`;
        row.appendChild(cell);
        body.appendChild(row);
    }

    [...teamWorkers].sort((a, b) => Number(a.is_reserve) - Number(b.is_reserve)).forEach(worker => {
        const row = document.createElement("tr");

        const name = document.createElement("td");
        name.className = "name name-column";
        name.textContent = worker.name;
        row.appendChild(name);

        for (let dayOffset = 0; dayOffset < 7; dayOffset++) {
            const workDate = weekDates[dayOffset];
            const assignment = assignmentsByWorkerDate.get(
                `${worker.id}_${workDate}`
            );

            const cell = document.createElement("td");

            const workerDateKey = `${worker.id}_${workDate}`;
            const isDayOff = dayOffKeys.has(workerDateKey);
            const isReserve = reserveKeys.has(workerDateKey);

        if (isDayOff) {
                cell.textContent = "";
                cell.className = "day-off";
                cell.onclick = () => {
                    openDayOffModal(worker, workDate);
                };
            } else if (isReserve) {
            cell.textContent = "";
            cell.className = "reserve";
            cell.onclick = async () => {
                const weekStart = formatDate(getWeekStart());

                const response = await fetch(
                    `/api/schedule/reserve?week_start=${weekStart}&work_date=${workDate}&worker_id=${worker.id}&group=${encodeURIComponent(selectedExotecGroup)}`,
                    { method: "DELETE" }
                );

                if (!response.ok) {
                    alert("Не вдалося зняти Reserve");
                    return;
                }

                await loadScheduleAssignments();
                markScheduleChanged();
            };
        } else if (assignment) {
                const station = document.createElement("div");
                const stationKey = `${workDate}_${assignment.station}`;
                station.className = changingStations.has(stationKey)
                    ? "station station-changing"
                    : "station";
                station.textContent = assignment.station;

                station.onclick = () => {
                    openStationChoiceModal(worker, workDate, assignment);
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

        const lunchInfo = getLunchForWorker(worker.id);
        lunch.textContent = lunchInfo && lunchInfo.time ? lunchInfo.time : "—";

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
let weekNavigationVersion = 0;

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
    const dayNames = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];
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
const todayDate = document.getElementById("todayDate");

function updateTodayDate() {
    const today = new Date();
    const day = String(today.getDate()).padStart(2, "0");
    const month = String(today.getMonth() + 1).padStart(2, "0");
    const year = today.getFullYear();

    if (todayDate) {
        todayDate.textContent = `${day}.${month}.${year}`;
    }
}

updateTodayDate();


function updateWeek() {
    const weekStart = getWeekStart();
    const weekEnd = new Date(weekStart);
    weekEnd.setDate(weekEnd.getDate() + 6);

    const formatShortDate = date =>
        `${String(date.getDate()).padStart(2, "0")}.${String(date.getMonth() + 1).padStart(2, "0")}`;

    weekTitle.textContent = `${formatShortDate(weekStart)} — ${formatShortDate(weekEnd)}`;
}

updateWeek();



const navButtons = document.querySelectorAll(".bottom-nav button");

let workersScriptPromise = null;

function preloadWorkersScript() {
    if (window.showWorkersScreen) return Promise.resolve();
    if (workersScriptPromise) return workersScriptPromise;

    appLogEvent("WORKERS SCRIPT PRELOAD START");
    workersScriptPromise = new Promise((resolve, reject) => {
        const script = document.createElement("script");
        script.src = "/static/workers.js?v=2";
        script.onload = () => {
            appLogEvent("WORKERS SCRIPT PRELOAD SUCCESS");
            resolve();
        };
        script.onerror = () => {
            appLogEvent("WORKERS SCRIPT PRELOAD ERROR");
            workersScriptPromise = null;
            reject(new Error("Не вдалося завантажити workers.js"));
        };
        document.body.appendChild(script);
    });

    return workersScriptPromise;
}
navButtons[0].addEventListener("click", async () => {
    showScreen("scheduleScreen");
    setActiveNav(0);
    await showScheduleScreen();
});

navButtons[1].addEventListener("click", async () => {
    showScreen("workersScreen");
    if (!window.showWorkersScreen) {
        await preloadWorkersScript();
    }
    await showWorkersScreen();
    setActiveNav(1);
});

navButtons[2].addEventListener("click", async () => {
    showScreen("lunchScreen");
    await showLunchScreen();
    setActiveNav(2);
});


async function loadScheduleWorkers() {
    const response = await fetch(
        `/api/workers?group=${encodeURIComponent(selectedExotecGroup)}`
    );

    if (!response.ok) {
        alert("Не вдалося завантажити працівників");
        return;
    }

    const data = await response.json();
    workers = data;
}

async function loadScheduleDays() {
    const requestWeek = formatDate(getWeekStart());

    const response = await fetch(
        `/api/schedule/days?week_start=${requestWeek}&group=${encodeURIComponent(selectedExotecGroup)}`
    );

    if (!response.ok) {
        if (formatDate(getWeekStart()) !== requestWeek) {
            return;
        }

        alert("Не вдалося завантажити дні розкладу");
        scheduleDays = [];
        return;
    }

    const data = await response.json();

    if (formatDate(getWeekStart()) !== requestWeek) {
        return;
    }

    scheduleDays = data.days;
}


async function loadScheduleShift() {
    const requestWeek = formatDate(getWeekStart());

    const response = await fetch(
        `/api/schedule/shift?week_start=${requestWeek}&group=${encodeURIComponent(selectedExotecGroup)}`
    );

    if (!response.ok) {
        if (formatDate(getWeekStart()) !== requestWeek) {
            return;
        }

        scheduleShift = null;
        scheduleTeamSlots = null;
        return;
    }

    const data = await response.json();

    if (formatDate(getWeekStart()) !== requestWeek) {
        return;
    }

    scheduleShift = data.shift;
    scheduleTeamSlots = data.team_slots || null;
}

// Часовий слот (зміна 1/2/3), у якому бригада працює вибраного тижня.
function getTeamShift(teamCode) {
    if (!scheduleTeamSlots || !teamCode) {
        return null;
    }
    return scheduleTeamSlots[String(teamCode).trim()] || null;
}

function getWorkerTeam(workerId) {
    const worker = workers.find(item => Number(item.id) === Number(workerId));
    return worker ? String(worker.team_code).trim() : null;
}

function updateScheduleTeamTabs() {
    document.querySelectorAll("[data-schedule-team]").forEach(tab => {
        const active = tab.dataset.scheduleTeam === selectedScheduleTeam;
        tab.classList.toggle("active", active);
        tab.setAttribute("aria-selected", active ? "true" : "false");
    });

    const info = document.getElementById("scheduleTeamInfo");
    if (info) {
        const shift = getTeamShift(selectedScheduleTeam);
        info.innerHTML = "";
        const text = document.createElement("span");
        text.textContent = shift
            ? `Бригада ${selectedScheduleTeam} · зміна ${shift} (${SHIFT_HOURS[shift]})`
            : `Бригада ${selectedScheduleTeam} · ротацію змін не налаштовано`;
        const button = document.createElement("button");
        button.type = "button";
        button.className = "rotation-button";
        button.textContent = shift ? "⚙️ Ротація (усі групи)" : "⚙️ Налаштувати ротацію";
        button.onclick = configureGroupRotation;
        info.append(text, button);
    }
}

const SHIFT_HOURS = {
    1: "06:00–14:00",
    2: "14:00–22:00",
    3: "22:00–06:00"
};

// Ротація спільна для всіх груп. Задаємо її через зміну бригади A на поточному тижні.
// Сервер зберігає «фазу»: фаза 2 → A у зміні 1, фаза 3 → A у 2, фаза 1 → A у 3.
async function configureGroupRotation() {
    const weekStart = formatDate(getWeekStart());
    const weekTitle = document.getElementById("weekTitle");
    const weekLabel = weekTitle ? weekTitle.textContent.trim() : weekStart;

    const answer = prompt(
        `Ротація змін для всіх груп.\n` +
        `У якій зміні працює бригада A на тижні ${weekLabel}?\n\n` +
        `1 — ${SHIFT_HOURS[1]}\n2 — ${SHIFT_HOURS[2]}\n3 — ${SHIFT_HOURS[3]}`
    );

    if (answer === null) {
        return false;
    }

    const teamAShift = Number(String(answer).trim());
    if (![1, 2, 3].includes(teamAShift)) {
        alert("Потрібно ввести 1, 2 або 3");
        return false;
    }

    const response = await fetch("/api/rotation", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
            start_week: weekStart,
            start_shift: (teamAShift % 3) + 1
        })
    });

    if (!response.ok) {
        const data = await response.json().catch(() => ({}));
        alert(data.detail || "Не вдалося зберегти ротацію");
        return false;
    }

    const slots = await loadRotationCard();
    if (selectedExotecGroup && scheduleLoaded) {
        await loadScheduleShift();
        lunchSettingsPromise = null;
        lunchSettingsPromiseWeek = null;
        await loadLunchSettings();
        lunchScreenLoaded = false;
        markScheduleChanged();
    }

    if (slots) {
        alert(
            "Ротацію збережено для всіх груп. Цього тижня:\n" +
            ["A", "B", "C"]
                .map(team => `Бригада ${team} — зміна ${slots[team]} (${SHIFT_HOURS[slots[team]]})`)
                .join("\n") +
            "\n\nНа наступних тижнях зміни чергуються автоматично."
        );
    }
    return true;
}

document.querySelectorAll("[data-schedule-team]").forEach(tab => {
    tab.addEventListener("click", () => {
        if (tab.dataset.scheduleTeam === selectedScheduleTeam) {
            return;
        }
        selectedScheduleTeam = tab.dataset.scheduleTeam;
        markScheduleChanged();
    });
});

async function showScheduleScreen() {
    const screen = document.getElementById("scheduleScreen");

    if (!scheduleLoaded) {
        await Promise.all([
            loadScheduleWorkers(),
            loadScheduleDays(),
            loadScheduleShift(),
            loadScheduleAssignments(),
            loadWorkerDaysOff(),
            loadLunchSettings()
        ]);

        scheduleLoaded = true;

        renderSchedule();
        bindScheduleButtons();
        prepareShareInBackground();
        return;
    }

    screen.hidden = false;
}

async function exportScheduleImage(mode) {
    const table = document.querySelector(".schedule");
    if (!table) {
        alert("Розклад ще не завантажено");
        return;
    }

    const currentWeek = formatDate(getWeekStart());

        if (
            cachedScheduleImageBlob &&
            cachedScheduleImageWeek === currentWeek
        ) {
            appLogEvent("SCHEDULE IMAGE CACHE HIT", {
                mode,
                week: currentWeek,
                size: cachedScheduleImageBlob.size
            });

            await processExportBlob(
                cachedScheduleImageBlob,
                mode,
                currentWeek
            );
            return;
        }

        exportImageInProgress = true;
        updateExportButtonState();

        const rows = [...table.querySelectorAll("tr")];
    const scale = 2;
    const padding = 40;
    const rowHeight = 54;
    const colWidths = [220, 95, 95, 95, 95, 95, 95, 95, 110];

    const canvas = document.createElement("canvas");
    canvas.width = (colWidths.reduce((sum, width) => sum + width, 0) + padding * 2) * scale;
    canvas.height = (100 + rows.length * rowHeight + padding) * scale;

    const ctx = canvas.getContext("2d");
    ctx.scale(scale, scale);

    ctx.fillStyle = "#ffffff";
    ctx.fillRect(0, 0, canvas.width / scale, canvas.height / scale);

    ctx.fillStyle = "#111827";
    ctx.font = "bold 24px sans-serif";
    const groupLabel = document.getElementById("currentExotecGroupLabel");
    const groupName = groupLabel ? groupLabel.textContent.trim() : selectedExotecGroup;
    const teamShift = getTeamShift(selectedScheduleTeam);
    ctx.fillText(
        `${groupName} · Бригада ${selectedScheduleTeam}` +
            (teamShift ? ` · зміна ${teamShift}` : ""),
        padding,
        38
    );

    const weekTitle = document.getElementById("weekTitle");
    ctx.font = "16px sans-serif";
    ctx.fillStyle = "#6b7280";
    ctx.fillText(weekTitle ? weekTitle.textContent.trim() : "", padding, 64);

    let y = 90;

    rows.forEach((row, rowIndex) => {
        const cells = [...row.children];
        let x = padding;

        cells.forEach((cell, columnIndex) => {
            const width = colWidths[columnIndex] || 100;

            if (rowIndex === 0) {
                ctx.fillStyle = "#e5e7eb";
            } else if (cell.classList.contains("day-off")) {
                ctx.fillStyle = "#dff3e3";
            } else {
                ctx.fillStyle = "#f9fafb";
            }
            ctx.fillRect(x, y, width, rowHeight);

            ctx.strokeStyle = "#d1d5db";
            ctx.strokeRect(x, y, width, rowHeight);

            ctx.fillStyle = "#111827";
            ctx.font = rowIndex === 0 ? "bold 20px sans-serif" : "bold 22px sans-serif";

            const text = cell.textContent.trim();
            const lines = text.split(/\n+/).map(line => line.trim()).filter(Boolean);

            lines.slice(0, 2).forEach((line, index) => {
                ctx.textAlign = columnIndex === 0 ? "left" : "center";
            ctx.fillText(line, columnIndex === 0 ? x + 10 : x + width / 2, y + 32 + index * 22);
            });

            ctx.textAlign = "left";
        x += width;
        });

        y += rowHeight;
    });

    const toBlobStart = performance.now();
    appLogEvent("SHARE CANVAS TOBLOB START");

    return new Promise(resolve => {
        canvas.toBlob(async blob => {
            appLogEvent("SHARE CANVAS TOBLOB END", {
                durationMs: Math.round(performance.now() - toBlobStart),
                size: blob ? blob.size : 0
            });
            try {
        if (!blob) {
            alert("Не вдалося створити зображення");
            return;
        }

        const generatedWeek = currentWeek;
        cachedScheduleImageBlob = blob;
        cachedScheduleImageWeek = generatedWeek;

        appLogEvent("SCHEDULE IMAGE CACHED", {
            week: generatedWeek,
            size: blob.size
        });

        await processExportBlob(blob, mode, currentWeek);

        } finally {
                exportImageInProgress = false;
                updateExportButtonState();
                resolve();
            }
        }, "image/jpeg", 0.95);
    });
}

let cachedScheduleImageBlob = null;
let cachedScheduleImageWeek = null;
let exportImageInProgress = false;

function invalidateScheduleImageCache() {
    cachedScheduleImageBlob = null;
    cachedScheduleImageWeek = null;
    preparedShareMessageId = null;
    preparedShareWeek = null;

    updateShareButtonState();
}

function markScheduleChanged() {
    invalidateScheduleImageCache();
    renderSchedule();
    prepareShareInBackground();
}

async function processExportBlob(blob, mode, exportWeek) {
    if (!blob) {
        alert("Не вдалося створити зображення");
        return;
    }

    const weekStart = getWeekStart();
    const weekEnd = new Date(weekStart);
    weekEnd.setDate(weekEnd.getDate() + 6);
    const fileName = `${formatDate(weekStart)}_${formatDate(weekEnd).slice(5)}.jpg`;

    if (mode === "save") {
        const uploadResponse = await fetch("/api/export/schedule", {
            method: "POST",
            headers: {
                "Content-Type": "image/jpeg"
            },
            body: blob
        });

        if (!uploadResponse.ok) {
            alert("Не вдалося підготувати файл");
            return;
        }

        const exportData = await uploadResponse.json();
        const fileUrl = `${window.location.origin}${exportData.url}`;

        if (window.Telegram?.WebApp?.downloadFile) {
            window.Telegram.WebApp.downloadFile(
                {
                    url: fileUrl,
                    file_name: fileName
                },
                () => {}
            );
            return;
        }

        alert("Збереження файлів не підтримується цією версією Telegram");
        return;
    }

    if (mode === "prepare-share") {

        try {
            if (document.visibilityState === "hidden") {
                appLogEvent("SHARE PREPARE FETCH BLOCKED: APP HIDDEN");
                return;
            }

            const response = await fetch("/api/export/share-prepared", {
                method: "POST",
                headers: {
                    "Content-Type": "image/jpeg",
                    "X-Telegram-Init-Data": window.Telegram?.WebApp?.initData || ""
                },
                body: blob
            });

            if (!response.ok) return;

            const data = await response.json();
            preparedShareMessageId = data.prepared_message_id || null;
            preparedShareWeek = exportWeek;

            console.log(
                "SHARE PREPARED:",
                preparedShareMessageId,
                "WEEK:",
                preparedShareWeek
            );

            updateShareButtonState();
        } catch (error) {
            preparedShareMessageId = null;
            preparedShareWeek = null;

            console.log("SHARE PREPARE ERROR:", error);
            updateShareButtonState();
        }

        return;
    }
}

let sharePreparationPromise = null;

function prepareShareInBackground() {
    if (document.visibilityState === "hidden") {
        appLogEvent("SHARE PREPARE SKIPPED: APP HIDDEN");
        return null;
    }

    if (sharePreparationPromise) {
        return sharePreparationPromise;
    }

    const preparationWeek = formatDate(getWeekStart());

    sharePreparationPromise = exportScheduleImage("prepare-share")
        .then(() => {
            if (
                preparedShareMessageId &&
                preparedShareWeek === preparationWeek &&
                formatDate(getWeekStart()) === preparationWeek
            ) {
                return preparedShareMessageId;
            }

            return null;
        })
        .catch(error => {
            console.log("SHARE PREPARE PROMISE ERROR:", error);
            return null;
        })
        .finally(() => {
            sharePreparationPromise = null;
            updateExportButtonState();
        });

    return sharePreparationPromise;
}


function updateExportButtonState() {
    const saveScheduleImageButton =
        document.getElementById("saveScheduleImageButton");

    const shareScheduleImageButton =
        document.getElementById("shareScheduleImageButton");

    if (!saveScheduleImageButton || !shareScheduleImageButton) {
        return;
    }

    const currentWeek = formatDate(getWeekStart());

    const imageReady =
        !!cachedScheduleImageBlob &&
        cachedScheduleImageWeek === currentWeek;

    const shareReady =
        !!preparedShareMessageId &&
        preparedShareWeek === currentWeek &&
        !shareMessageInProgress;

    const preparing =
        exportImageInProgress ||
        !!sharePreparationPromise ||
        shareMessageInProgress;

    const ready =
        imageReady &&
        shareReady &&
        !preparing;

    saveScheduleImageButton.classList.toggle(
        "export-disabled",
        !ready
    );

    shareScheduleImageButton.classList.toggle(
        "export-disabled",
        !ready
    );

    appLogEvent("EXPORT BUTTON STATE", {
        ready,
        imageReady,
        shareReady,
        preparing,
        week: currentWeek,
        hasImage: !!cachedScheduleImageBlob,
        hasMessageId: !!preparedShareMessageId
    });
}

function updateShareButtonState() {
    updateExportButtonState();
}

async function changeScheduleWeek(offset) {
    const navigationVersion = ++weekNavigationVersion;

    weekOffset += offset;
    updateWeek();

    await Promise.all([
        loadScheduleDays(),
        loadScheduleShift(),
        loadScheduleAssignments(),
        loadWorkerDaysOff(),
        loadLunchSettings()
    ]);

    if (navigationVersion !== weekNavigationVersion) {
        return;
    }

    lunchScreenLoaded = false;
    markScheduleChanged();

    if (!document.getElementById("lunchScreen").hidden) {
        await showLunchScreen();
    }

    await new Promise(resolve =>
        requestAnimationFrame(() =>
            requestAnimationFrame(resolve)
        )
    );
}

function bindScheduleButtons() {
    const exportModal = document.getElementById("exportModal");

    document.getElementById("exportScheduleButton").onclick = () => {
        exportModal.classList.remove("hidden");
        appLogEvent("EXPORT OPENED");
        updateExportButtonState();
        prepareShareInBackground();
    };

    document.getElementById("saveScheduleImageButton").onclick = async () => {
        exportModal.classList.add("hidden");
        await exportScheduleImage("save");
    };

    const shareScheduleImageButton =
        document.getElementById("shareScheduleImageButton");

    shareScheduleImageButton.onclick = async () => {
        appLogEvent("SHARE BUTTON CLICK");
        exportModal.classList.add("hidden");

        if (!window.Telegram?.WebView?.postEvent) {
            alert("Поширення через Telegram не підтримується");
            return;
        }

        if (
            !preparedShareMessageId ||
            preparedShareWeek !== formatDate(getWeekStart())
        ) {
            appLogEvent("SHARE SKIPPED: NOT READY");
            updateShareButtonState();
            return;
        }

        if (shareMessageInProgress) {
            appLogEvent("SHARE SKIPPED: ALREADY SHARING");
            return;
        }

        shareMessageInProgress = true;
        updateShareButtonState();

        const messageId = preparedShareMessageId;
        const currentWeek = preparedShareWeek;

        console.log("SHARE MESSAGE ID:", messageId);
        appLogEvent("SHARE MESSAGE ID: " + messageId);
        appLogEvent("SHARE DIRECT POSTEVENT");

        try {
            Telegram.WebView.postEvent(
                "web_app_send_prepared_message",
                false,
                { id: messageId }
            );

            appLogEvent("SHARE NEXT PREPARE START");

            preparedShareMessageId = null;
            preparedShareWeek = null;

            updateShareButtonState();

            prepareShareInBackground()
                .then(nextMessageId => {
                    if (
                        nextMessageId &&
                        formatDate(getWeekStart()) === currentWeek
                    ) {
                        appLogEvent("SHARE NEXT PREPARE READY", {
                            messageId: nextMessageId,
                            week: currentWeek
                        });
                    } else {
                        appLogEvent("SHARE NEXT PREPARE NOT READY");
                    }

                    shareMessageInProgress = false;
                    updateShareButtonState();
                })
                .catch(error => {
                    console.log("SHARE NEXT PREPARE ERROR:", error);
                    appLogEvent("SHARE NEXT PREPARE ERROR: " + String(error));

                    shareMessageInProgress = false;
                    updateShareButtonState();
                });

        } catch (error) {
            shareMessageInProgress = false;
            updateShareButtonState();

            console.log("SHARE POSTEVENT ERROR:", error);
            appLogEvent("SHARE POSTEVENT ERROR: " + String(error));
        }
    };

    updateShareButtonState();

    document.getElementById("cancelExportButton").onclick = () => {
        exportModal.classList.add("hidden");
    };

    exportModal.onclick = event => {
        if (event.target === exportModal) {
            exportModal.classList.add("hidden");
        }
    };

    document.getElementById("prevWeek").onclick = () =>
        changeScheduleWeek(-1);

    document.getElementById("nextWeek").onclick = () =>
        changeScheduleWeek(1);

    document.getElementById("generateScheduleButton").onclick = async () => {
        const weekStart = formatDate(getWeekStart());
        const generationNavigationVersion = weekNavigationVersion;

        const settingsResponse = await fetch(`/api/schedule/settings?group=${encodeURIComponent(selectedExotecGroup)}`);

        if (!settingsResponse.ok) {
            alert("Не вдалося перевірити налаштування зміни");
            return;
        }

        const settings = await settingsResponse.json();

        // Сервер завжди повертає рядок налаштувань групи, тому перевіряємо поля.
        if (!settings || !settings.start_week || !settings.start_shift_slot) {
            const configured = await configureGroupRotation();
            if (!configured) {
                return;
            }
        }

        if (scheduleAssignments.length > 0) {
            const confirmed = confirm(
                "Для цього тижня розклад уже існує.\n\nТочно згенерувати повторно? Поточні призначення буде замінено."
            );

            if (!confirmed) {
                return;
            }
        }



        if (generationNavigationVersion !== weekNavigationVersion) {
            return;
        }

        const response = await fetch(`/api/schedule/generate?group=${encodeURIComponent(selectedExotecGroup)}`, {
            method: "POST",
            headers: {
                "Content-Type": "application/json"
            },
            body: JSON.stringify({
                week_start: weekStart,
                group: selectedExotecGroup
            })
        });

        if (!response.ok) {
            const data = await response.json().catch(() => ({}));
            alert(data.detail || "Не вдалося згенерувати розклад");
            return;
        }

        if (generationNavigationVersion !== weekNavigationVersion) {
            return;
        }

        await Promise.all([
            loadScheduleShift(),
            loadScheduleAssignments()
        ]);

        if (generationNavigationVersion !== weekNavigationVersion) {
            return;
        }

        markScheduleChanged();

        await new Promise(resolve =>
            requestAnimationFrame(() => requestAnimationFrame(resolve))
        );
    };
}


function setActiveNav(index) {
    navButtons.forEach((button, i) => {
        button.classList.toggle("active", i === index);
    });
}

function showScreen(screenId) {
    document.querySelectorAll("main > div[id$='Screen']").forEach(screen => {
        screen.hidden = screen.id !== screenId;
    });

    document.body.classList.toggle("group-select-mode", screenId === "groupSelectScreen");
}

function saveSelectedExotecGroup() {
    localStorage.setItem("selectedExotecGroup", selectedExotecGroup);
}

function loadSelectedExotecGroup() {
    const savedGroup = localStorage.getItem("selectedExotecGroup");
    if (savedGroup) selectedExotecGroup = savedGroup;
}

async function loadSelectedGroupStations() {
    const response = await fetch(
        `/api/groups/${encodeURIComponent(selectedExotecGroup)}/stations`
    );
    if (!response.ok) {
        throw new Error(`Помилка завантаження станцій: HTTP ${response.status}`);
    }

    const data = await response.json();
    selectedGroupStations = Array.isArray(data.stations) ? data.stations : [];

    const label = document.getElementById("currentExotecGroupLabel");
    if (label && data.group) label.textContent = data.group.name;

    const groupButton = document.querySelector(
        `[data-exotec-group="${CSS.escape(selectedExotecGroup)}"]`
    );
    const description = groupButton?.querySelector("span");
    if (description) {
        const numbers = getSelectedExotecStationNumbers();
        description.textContent = numbers.length
            ? `Станції: ${numbers.join(", ")}`
            : "Станцій немає";
    }
}

async function loadAvailableWorkGroups() {
    const response = await fetch("/api/groups");
    if (!response.ok) {
        throw new Error(`Помилка завантаження груп: HTTP ${response.status}`);
    }

    const data = await response.json();
    availableWorkGroups = Array.isArray(data.groups) ? data.groups : [];

    const list = document.getElementById("exotecGroupList");
    if (!list) throw new Error("Не знайдено exotecGroupList");

    list.replaceChildren();
    for (const group of availableWorkGroups) {
        const button = document.createElement("button");
        button.type = "button";
        button.dataset.exotecGroup = group.slug;

        const title = document.createElement("strong");
        title.textContent = group.name;

        const description = document.createElement("span");
        description.textContent = "Станції…";

        button.append(title, description);
        list.appendChild(button);
    }

    bindExotecGroupSelector();

    if (!availableWorkGroups.some(g => g.slug === selectedExotecGroup)) {
        selectedExotecGroup =
            availableWorkGroups.find(g => g.slug === "exotec_2")?.slug
            || availableWorkGroups[0]?.slug
            || "";
    }

    if (selectedExotecGroup) await loadSelectedGroupStations();
}

async function selectExotecGroup(group) {
    if (!availableWorkGroups.some(item => item.slug === group)) return;

    selectedExotecGroup = group;
    saveSelectedExotecGroup();
    updateCurrentExotecGroupLabel();
    await loadSelectedGroupStations();

    scheduleLoaded = false;
    lunchScreenLoaded = false;
    lunchSettings = null;
    lunchSettingsPromise = null;
    lunchSettingsPromiseWeek = null;
    scheduleAssignments = [];
    scheduleReserves = [];
    workerDaysOff = [];
    changingStations.clear();

    showScreen("scheduleScreen");
    setActiveNav(0);

    await showScheduleScreen();
}

function showExotecGroupSelector() {
    showScreen("groupSelectScreen");
    if (document.getElementById("rotationCard")) {
        loadRotationCard();
    }
}

function updateCurrentExotecGroupLabel() {
    const label = document.getElementById("currentExotecGroupLabel");

    if (!label) {
        return;
    }
    label.textContent = availableWorkGroups.find(g => g.slug === selectedExotecGroup)?.name || selectedExotecGroup;
}

function bindCurrentExotecGroupButton() {
    const button = document.getElementById("changeExotecGroupButton");

    if (!button) {
        return;
    }

    button.addEventListener("click", () => {
        showExotecGroupSelector();
    });
}

function bindExotecGroupSelector() {
    const groupList = document.getElementById("exotecGroupList");
    if (!groupList || groupList.dataset.groupSelectorBound === "true") {
        return;
    }

    groupList.dataset.groupSelectorBound = "true";

    groupList.addEventListener("click", event => {
        const button = event.target.closest("[data-exotec-group]");
        if (!button || !groupList.contains(button)) {
            return;
        }

        selectExotecGroup(button.dataset.exotecGroup).catch(error => {
            console.error("EXOTEC GROUP SELECT:", error);
            appLogEvent(
                "EXOTEC GROUP SELECT ERROR: " + (error?.stack || String(error))
            );
        });
    });
}
loadSelectedExotecGroup();
bindCurrentExotecGroupButton();
showExotecGroupSelector();

adminAccessPromise.then(async authorized => {
    if (!authorized) return;
    try {
        await loadAvailableWorkGroups();
        updateCurrentExotecGroupLabel();
        setupRotationCard();
        await loadRotationCard();
        setupGroupAdmin();
        showExotecGroupSelector();
    } catch (error) {
        console.error("LOAD GROUPS ERROR:", error);
        appLogEvent("LOAD GROUPS ERROR: " + (error?.stack || String(error)));
    }
});

async function loadLunchSettings() {
    const weekStart = formatDate(getWeekStart());

    if (
        lunchSettingsPromise &&
        lunchSettingsPromiseWeek === weekStart
    ) {
        return lunchSettingsPromise;
    }

    const requestWeek = weekStart;

    const requestPromise = fetch(
        `/api/lunch/settings?week_start=${requestWeek}&group=${encodeURIComponent(selectedExotecGroup)}`
    )
        .then(async response => {
            if (!response.ok) {
                throw new Error("Не вдалося завантажити налаштування обідів");
            }

            const settings = await response.json();

            if (formatDate(getWeekStart()) === requestWeek) {
                lunchSettings = settings;
            }

            return settings;
        })
        .catch(error => {
            alert(error.message);
            return null;
        })
        .finally(() => {
            if (lunchSettingsPromise === requestPromise) {
                lunchSettingsPromise = null;
                lunchSettingsPromiseWeek = null;
            }
        });

    lunchSettingsPromise = requestPromise;
    lunchSettingsPromiseWeek = requestWeek;

    return requestPromise;
}

let lunchTeam = "A";
let lunchDraft = [];
let lunchDraftDirty = false;

function escapeHtml(value) {
    return String(value)
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;");
}

function resetLunchDraft() {
    const pairs = lunchSettings && lunchSettings.teams
        ? lunchSettings.teams[lunchTeam] || []
        : [];
    lunchDraft = pairs.map(pair => pair.map(member => ({ ...member })));
    lunchDraftDirty = false;
}

async function showLunchScreen() {
    if (lunchScreenLoaded) {
        return;
    }

    if (!workers.length) {
        await Promise.all([
            loadScheduleWorkers(),
            loadLunchSettings()
        ]);
    } else {
        await loadLunchSettings();
    }

    lunchTeam = selectedScheduleTeam;
    resetLunchDraft();
    renderLunchScreen();
    lunchScreenLoaded = true;
}

function renderLunchScreen() {
    const screen = document.getElementById("lunchScreen");
    const settings = lunchSettings || {
        start_times: { 1: "10:00", 2: "18:00", 3: "02:00" },
        team_slots: null,
        teams: { A: [], B: [], C: [] },
        interval_minutes: 30
    };

    const slot = settings.team_slots ? settings.team_slots[lunchTeam] : null;
    const teamInfo = slot
        ? `Бригада ${lunchTeam} цього тижня працює в зміні ${slot}, обід з ${settings.start_times[String(slot)]}`
        : `Бригада ${lunchTeam}: ротацію змін не налаштовано, час обіду не розраховується`;

    const groupsHtml = lunchDraft.map((pair, index) => {
        const time = getLunchPairTime(lunchTeam, index + 1);
        const members = pair.map(member => `
            <button type="button" class="lunch-member-chip"
                    data-group="${index}" data-worker-id="${member.id}"
                    title="Прибрати з групи">
                ${escapeHtml(member.name)} <span aria-hidden="true">✕</span>
            </button>
        `).join("");

        return `
            <div class="lunch-group">
                <div class="lunch-group-head">
                    <strong>Група ${index + 1}</strong>
                    <span class="lunch-group-time">${time || "—"}</span>
                    <button type="button" class="lunch-group-remove"
                            data-group="${index}" aria-label="Видалити групу">🗑</button>
                </div>
                <div class="lunch-members">
                    ${members || '<span class="lunch-empty">Порожня група</span>'}
                    <button type="button" class="lunch-member-add" data-group="${index}">
                        + Працівник
                    </button>
                </div>
            </div>
        `;
    }).join("");

    const shiftRows = [1, 2, 3].map(shift => `
        <div class="lunch-shift">
            <strong>Зміна ${shift}</strong>
            <label>
                Початок обіду
                <button type="button" class="lunch-time-button"
                        data-shift="${shift}"
                        data-time="${settings.start_times[String(shift)]}">${settings.start_times[String(shift)]}</button>
            </label>
        </div>
    `).join("");

    screen.innerHTML = `
        <section class="card lunch-card">
            <div class="card-title">🍽 Обіди</div>

            <div class="worker-team-tabs" role="tablist" aria-label="Бригада">
                ${["A", "B", "C"].map(team => `
                    <button type="button" data-lunch-team="${team}"
                            class="worker-team-tab${team === lunchTeam ? " active" : ""}">
                        Бригада ${team}
                    </button>
                `).join("")}
            </div>

            <div class="lunch-team-info">${escapeHtml(teamInfo)}</div>

            <div class="lunch-groups">
                ${groupsHtml || '<div class="workers-empty">Обідніх груп ще немає. Додайте першу групу.</div>'}
            </div>

            <button type="button" class="station-choice-option lunch-add-group">
                + Додати групу
            </button>

            <button type="button" class="add-worker-button lunch-save-team">
                Зберегти обіди бригади ${lunchTeam}
            </button>
        </section>

        <section class="card lunch-card">
            <div class="card-title">⏰ Початок обіду за змінами</div>
            <div class="lunch-hint">
                Наступні групи обідають кожні ${settings.interval_minutes || 30} хв.
                Час однаковий для всіх бригад групи й діє для всіх тижнів.
            </div>
            <div class="lunch-shifts">${shiftRows}</div>
            <button type="button" class="add-worker-button lunch-save-times">
                Зберегти час
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

    screen.querySelectorAll("[data-lunch-team]").forEach(tab => {
        tab.onclick = () => {
            const team = tab.dataset.lunchTeam;
            if (team === lunchTeam) {
                return;
            }
            if (
                lunchDraftDirty &&
                !confirm("Незбережені зміни обідів цієї бригади буде втрачено. Продовжити?")
            ) {
                return;
            }
            lunchTeam = team;
            resetLunchDraft();
            renderLunchScreen();
        };
    });

    screen.querySelectorAll(".lunch-member-chip").forEach(chip => {
        chip.onclick = () => {
            const group = Number(chip.dataset.group);
            const workerId = Number(chip.dataset.workerId);
            lunchDraft[group] = lunchDraft[group].filter(
                member => Number(member.id) !== workerId
            );
            lunchDraftDirty = true;
            renderLunchScreen();
        };
    });

    screen.querySelectorAll(".lunch-group-remove").forEach(button => {
        button.onclick = () => {
            const group = Number(button.dataset.group);
            if (
                lunchDraft[group].length &&
                !confirm(`Видалити групу ${group + 1}?`)
            ) {
                return;
            }
            lunchDraft.splice(group, 1);
            lunchDraftDirty = true;
            renderLunchScreen();
        };
    });

    screen.querySelectorAll(".lunch-member-add").forEach(button => {
        button.onclick = () => openLunchMemberModal(Number(button.dataset.group));
    });

    screen.querySelector(".lunch-add-group").onclick = () => {
        lunchDraft.push([]);
        lunchDraftDirty = true;
        renderLunchScreen();
    };

    screen.querySelector(".lunch-save-team").onclick = saveLunchTeam;
    screen.querySelector(".lunch-save-times").onclick = saveLunchStartTimes;
}

function openLunchMemberModal(groupIndex) {
    const modal = document.getElementById("lunchModal");
    const title = document.getElementById("lunchModalTitle");
    const content = document.getElementById("lunchModalContent");
    const cancelButton = document.getElementById("lunchModalCancel");

    title.textContent = `Група ${groupIndex + 1}: додати працівника`;
    content.innerHTML = "";

    const used = new Set(
        lunchDraft.flat().map(member => Number(member.id))
    );

    const available = workers.filter(worker =>
        String(worker.team_code).trim() === lunchTeam &&
        !used.has(Number(worker.id))
    );

    if (!available.length) {
        const empty = document.createElement("div");
        empty.className = "workers-empty";
        empty.textContent = "Усі працівники бригади вже в обідніх групах.";
        content.appendChild(empty);
    }

    available.forEach(worker => {
        const option = document.createElement("button");
        option.type = "button";
        option.className = "station-worker-option";
        option.textContent = worker.is_reserve
            ? `${worker.name} (резерв)`
            : worker.name;

        option.onclick = () => {
            lunchDraft[groupIndex].push({ id: worker.id, name: worker.name });
            lunchDraftDirty = true;
            modal.classList.add("hidden");
            renderLunchScreen();
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

async function readErrorMessage(response, fallback) {
    const data = await response.json().catch(() => ({}));
    return data.detail || fallback;
}

async function reloadLunchAfterSave() {
    lunchSettingsPromise = null;
    lunchSettingsPromiseWeek = null;
    await loadLunchSettings();
    resetLunchDraft();
    renderLunchScreen();
    markScheduleChanged();
}

async function saveLunchTeam() {
    const pairs = lunchDraft
        .map(pair => pair.map(member => Number(member.id)))
        .filter(pair => pair.length);

    const response = await fetch(
        `/api/lunch/settings?group=${encodeURIComponent(selectedExotecGroup)}`,
        {
            method: "PUT",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                week_start: formatDate(getWeekStart()),
                team_code: lunchTeam,
                pairs
            })
        }
    );

    if (!response.ok) {
        alert(await readErrorMessage(response, "Не вдалося зберегти обіди"));
        return;
    }

    await reloadLunchAfterSave();
    alert(`Обіди бригади ${lunchTeam} збережено`);
}

async function saveLunchStartTimes() {
    const startTimes = {};
    document.querySelectorAll("#lunchScreen .lunch-time-button").forEach(button => {
        startTimes[button.dataset.shift] = button.dataset.time;
    });

    const response = await fetch(
        `/api/lunch/start-times?group=${encodeURIComponent(selectedExotecGroup)}`,
        {
            method: "PUT",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ start_times: startTimes })
        }
    );

    if (!response.ok) {
        alert(await readErrorMessage(response, "Не вдалося зберегти час обіду"));
        return;
    }

    const dirty = lunchDraftDirty;
    const draft = lunchDraft;
    await reloadLunchAfterSave();
    if (dirty) {
        // Незбережений склад груп не губимо через збереження часу.
        lunchDraft = draft;
        lunchDraftDirty = true;
        renderLunchScreen();
    }
    alert("Час обіду збережено");
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
        // Поки модальне вікно було приховане, прокрутка не застосовувалась,
        // і «Готово» без прокручування давало 00:00.
        scrollWheelToIndex(hourWheel, hourIndex);
        scrollWheelToIndex(minuteWheel, minuteIndex);
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
    const timeButton = event.target.closest(".lunch-time-button");

    if (timeButton) {
        openLunchTimeModal(timeButton);
    }
});

document.getElementById("clearScheduleButton").onclick = async () => {
    const confirmed = confirm(
        "⚠️ УВАГА!\n\nВесь графік для вибраного тижня буде очищено, включно з Reserve.\n\nЦю дію не можна скасувати.\n\nОчистити графік?"
    );

    if (!confirmed) return;

    const weekStart = formatDate(getWeekStart());
    const clearNavigationVersion = weekNavigationVersion;

    const response = await fetch(`/api/schedule/clear?group=${encodeURIComponent(selectedExotecGroup)}`, {
        method: "DELETE",
        headers: {
            "Content-Type": "application/json"
        },
        body: JSON.stringify({
            week_start: weekStart,
            group: selectedExotecGroup
        })
    });

    if (!response.ok) {
        const data = await response.json().catch(() => ({}));
        alert(data.detail || "Не вдалося очистити графік");
        return;
    }

    if (clearNavigationVersion !== weekNavigationVersion) {
        return;
    }

    await Promise.all([
        loadScheduleShift(),
        loadScheduleAssignments()
    ]);

    if (clearNavigationVersion !== weekNavigationVersion) {
        return;
    }

    markScheduleChanged();

    await new Promise(resolve =>
        requestAnimationFrame(() =>
            requestAnimationFrame(resolve)
        )
    );
};


// =========================
// Керування групами (лише super admin)
// =========================

function setupGroupAdmin() {
    if (!currentAuth || !currentAuth.is_super_admin) {
        return;
    }
    const section = document.querySelector("#groupSelectScreen .group-select");
    if (!section || document.getElementById("groupAdminButton")) {
        return;
    }

    const button = document.createElement("button");
    button.type = "button";
    button.id = "groupAdminButton";
    button.className = "group-admin-open";
    button.textContent = "⚙️ Керування групами";
    button.onclick = openGroupAdmin;

    const panel = document.createElement("div");
    panel.id = "groupAdminPanel";
    panel.hidden = true;

    section.append(button, panel);
}

async function openGroupAdmin() {
    const panel = document.getElementById("groupAdminPanel");
    const list = document.getElementById("exotecGroupList");
    const button = document.getElementById("groupAdminButton");

    const response = await fetch("/api/admin/groups");
    if (!response.ok) {
        alert(await readErrorMessage(response, "Не вдалося завантажити групи"));
        return;
    }
    const data = await response.json();

    list.hidden = true;
    button.hidden = true;
    panel.hidden = false;
    panel.innerHTML = "";

    const title = document.createElement("div");
    title.className = "group-admin-title";
    title.textContent = "Керування групами";
    panel.appendChild(title);

    for (const group of data.groups) {
        const row = document.createElement("div");
        row.className = "group-admin-row" + (group.active ? "" : " inactive");

        const info = document.createElement("div");
        info.className = "group-admin-info";
        const name = document.createElement("strong");
        name.textContent = group.active ? group.name : `${group.name} (вимкнена)`;
        const details = document.createElement("span");
        details.textContent =
            `Станції: ${group.stations_text || "немає"} · ${group.stations.length} шт · ` +
            `працівників: ${group.workers}`;
        info.append(name, details);

        const edit = document.createElement("button");
        edit.type = "button";
        edit.className = "group-admin-edit";
        edit.textContent = "Змінити";
        edit.onclick = () => openGroupForm(group);

        row.append(info, edit);
        panel.appendChild(row);
    }

    const add = document.createElement("button");
    add.type = "button";
    add.className = "station-choice-option";
    add.textContent = "+ Нова група";
    add.onclick = () => openGroupForm(null);

    const back = document.createElement("button");
    back.type = "button";
    back.className = "station-cancel-button";
    back.textContent = "← До вибору групи";
    back.onclick = closeGroupAdmin;

    panel.append(add, back);
}

function closeGroupAdmin() {
    document.getElementById("groupAdminPanel").hidden = true;
    document.getElementById("exotecGroupList").hidden = false;
    document.getElementById("groupAdminButton").hidden = false;
}

function countStationsPreview(text) {
    const numbers = new Set();
    for (const raw of String(text).replace(/;/g, ",").split(",")) {
        const part = raw.trim().replace(/[–—]/g, "-");
        if (!part) continue;
        const match = part.match(/^(\d+)\s*-\s*(\d+)$/);
        if (match) {
            let [a, b] = [Number(match[1]), Number(match[2])];
            if (a > b) [a, b] = [b, a];
            if (b - a > 1000) return null;
            for (let n = a; n <= b; n++) numbers.add(n);
        } else if (/^\d+$/.test(part)) {
            numbers.add(Number(part));
        } else {
            return null;
        }
    }
    return numbers.size;
}

function openGroupForm(group) {
    const old = document.getElementById("groupFormModal");
    if (old) old.remove();

    const modal = document.createElement("div");
    modal.id = "groupFormModal";
    modal.className = "station-modal";
    modal.innerHTML = `
        <div class="station-modal-box group-form">
            <div class="station-modal-title">${group ? "Змінити групу" : "Нова група"}</div>
            <label>
                Назва
                <input type="text" id="groupFormName" maxlength="60" autocomplete="off"
                       placeholder="Наприклад, Exotec 4">
            </label>
            <label>
                Станції
                <input type="text" id="groupFormStations" autocomplete="off" inputmode="text"
                       placeholder="Наприклад, 15-24 або 1-10, 12">
            </label>
            <div id="groupFormPreview" class="group-form-hint"></div>
            ${group ? `
            <label class="group-form-check">
                <input type="checkbox" id="groupFormActive">
                Група активна (видно у виборі групи)
            </label>` : ""}
            <button type="button" id="groupFormSave" class="add-worker-button">Зберегти</button>
            <button type="button" id="groupFormCancel" class="station-cancel-button">Скасувати</button>
        </div>
    `;
    document.body.appendChild(modal);

    const nameInput = document.getElementById("groupFormName");
    const stationsInput = document.getElementById("groupFormStations");
    const preview = document.getElementById("groupFormPreview");
    const activeInput = document.getElementById("groupFormActive");

    nameInput.value = group ? group.name : "";
    stationsInput.value = group ? group.stations_text : "";
    if (activeInput) activeInput.checked = !!group.active;

    const updatePreview = () => {
        const count = countStationsPreview(stationsInput.value);
        preview.textContent = count === null
            ? "Формат: діапазони через дефіс, окремі номери через кому"
            : `Станцій: ${count}` +
              (count && count < 5
                  ? ". Увага: якщо працівник працює 5 днів, а станцій менше 5, генератор не складе розклад без повторів."
                  : "");
    };
    stationsInput.addEventListener("input", updatePreview);
    updatePreview();

    const close = () => modal.remove();
    document.getElementById("groupFormCancel").onclick = close;
    modal.onclick = event => {
        if (event.target === modal) close();
    };

    document.getElementById("groupFormSave").onclick = async () => {
        const payload = {
            name: nameInput.value,
            stations: stationsInput.value
        };
        if (activeInput) payload.active = activeInput.checked;

        if (
            group &&
            group.stations_text &&
            payload.stations.trim() !== group.stations_text &&
            !confirm("Змінити станції групи? Вимкнені станції зникнуть з нових розкладів, історія залишиться.")
        ) {
            return;
        }

        const response = await fetch(
            group
                ? `/api/admin/groups/${encodeURIComponent(group.slug)}`
                : "/api/admin/groups",
            {
                method: group ? "PUT" : "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify(payload)
            }
        );

        if (!response.ok) {
            alert(await readErrorMessage(response, "Не вдалося зберегти групу"));
            return;
        }

        close();
        await loadAvailableWorkGroups();
        if (group && group.slug === selectedExotecGroup) {
            scheduleLoaded = false;
        }
        await openGroupAdmin();
    };

    nameInput.focus();
}


// =========================
// Спільна ротація змін на екрані вибору групи
// =========================

function setupRotationCard() {
    const section = document.querySelector("#groupSelectScreen .group-select");
    const list = document.getElementById("exotecGroupList");
    if (!section || !list || document.getElementById("rotationCard")) {
        return;
    }
    const card = document.createElement("div");
    card.id = "rotationCard";
    card.className = "rotation-card";
    section.insertBefore(card, list);
}

async function loadRotationCard() {
    const card = document.getElementById("rotationCard");
    const weekStart = formatDate(getWeekStart());

    let data = null;
    try {
        const response = await fetch(`/api/rotation?week_start=${weekStart}`);
        if (response.ok) {
            data = await response.json();
        }
    } catch (error) {
        appLogEvent("ROTATION LOAD ERROR: " + String(error));
    }

    if (!card) {
        return data ? data.team_slots : null;
    }

    const weekTitle = document.getElementById("weekTitle");
    const weekLabel = weekTitle ? weekTitle.textContent.trim() : weekStart;
    card.innerHTML = "";

    const head = document.createElement("div");
    head.className = "rotation-card-head";
    const title = document.createElement("strong");
    title.textContent = "Ротація змін";
    const week = document.createElement("span");
    week.textContent = weekLabel;
    head.append(title, week);
    card.appendChild(head);

    if (data && data.team_slots) {
        const teams = document.createElement("div");
        teams.className = "rotation-card-teams";
        ["A", "B", "C"].forEach(team => {
            const slot = data.team_slots[team];
            const item = document.createElement("div");
            item.className = "rotation-card-team";
            item.innerHTML = `<b>Бригада ${team}</b><span>зміна ${slot}</span><small>${SHIFT_HOURS[slot]}</small>`;
            teams.appendChild(item);
        });
        card.appendChild(teams);
    } else {
        const empty = document.createElement("div");
        empty.className = "rotation-card-empty";
        empty.textContent = "Ротацію ще не налаштовано. Вона спільна для всіх груп.";
        card.appendChild(empty);
    }

    const button = document.createElement("button");
    button.type = "button";
    button.className = "rotation-button";
    button.textContent = data && data.team_slots ? "⚙️ Змінити ротацію" : "⚙️ Налаштувати ротацію";
    button.onclick = configureGroupRotation;
    card.appendChild(button);

    return data ? data.team_slots : null;
}
