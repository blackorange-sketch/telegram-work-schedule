const tg = window.Telegram.WebApp;

tg.ready();
tg.expand();

const workers = [
    { name: "Андрій", stations: [15, 16, 17, 18, 19], lunch: "10:00" },
    { name: "Олег", stations: [16, 17, 18, 19, 20], lunch: "10:00" },
    { name: "Іван", stations: [17, 18, 19, 20, 21], lunch: "10:30" },
    { name: "Петро", stations: [18, 19, 20, 21, 22], lunch: "10:30" },
    { name: "Микола", stations: [19, 20, 21, 22, 23], lunch: "11:00" },
    { name: "Сергій", stations: [20, 21, 22, 23, 24], lunch: "11:00" },
    { name: "Віталій", stations: [21, 22, 23, 24, 15], lunch: "11:30" },
    { name: "Роман", stations: [22, 23, 24, 15, 16], lunch: "11:30" },
    { name: "Максим", stations: [23, 24, 15, 16, 17], lunch: "12:00" },
    { name: "Дмитро", stations: [24, 15, 16, 17, 18], lunch: "12:00" },
    { name: "Олексій", stations: [15, 17, 19, 21, 23], lunch: "12:30" },
    { name: "Богдан", stations: [16, 18, 20, 22, 24], lunch: "12:30" }
];

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

document.getElementById("prevWeek").addEventListener("click", () => {
    weekOffset--;
    updateWeek();
});

document.getElementById("nextWeek").addEventListener("click", () => {
    weekOffset++;
    updateWeek();
});
