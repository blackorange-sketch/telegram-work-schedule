const tg = window.Telegram.WebApp;

tg.ready();
tg.expand();
const scheduleTemplate = document.querySelector("main").innerHTML;

let workers = [];

function renderSchedule() {
    const body = document.getElementById("scheduleBody");

    body.innerHTML = "";

    workers.forEach(worker => {
        const row = document.createElement("tr");

        const name = document.createElement("td");
        name.className = "name name-column";
        name.textContent = worker.name;
        row.appendChild(name);

        worker.stations.forEach(stationNumber => {
            const cell = document.createElement("td");

            const station = document.createElement("div");
            station.className = "station";
            station.textContent = stationNumber;

            cell.appendChild(station);
            row.appendChild(cell);
        });

        const lunch = document.createElement("td");
        lunch.className = "lunch lunch-column";
        lunch.textContent = worker.lunch;

        row.appendChild(lunch);
        body.appendChild(row);
    });
}

renderSchedule();

let weekOffset = 0;

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

async function showScheduleScreen() {
    const main = document.querySelector("main");
    main.innerHTML = scheduleTemplate;
    await loadScheduleWorkers();
    renderSchedule();
    bindScheduleButtons();
}
function bindScheduleButtons() {
    document.getElementById("prevWeek").onclick = () => {
        weekOffset--;
        updateWeek();
    };

    document.getElementById("nextWeek").onclick = () => {
        weekOffset++;
        updateWeek();
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
