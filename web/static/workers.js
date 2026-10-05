function showWorkersScreen() {
    const main = document.querySelector("main");

    main.innerHTML = `
        <section class="card workers-card">
            <div class="card-title">👥 Працівники</div>
            <div id="workersList"></div><button id="addWorkerButton" class="add-worker-button">＋ Додати працівника</button>
        </section>
    `;
    loadWorkers();
    setupWorkerButtons();
}

async function loadWorkers() {
    const list = document.getElementById("workersList");

    try {
        const response = await fetch("/api/workers");
        const workers = await response.json();

        renderWorkers(workers);
    } catch (error) {
        list.textContent = "Не вдалося завантажити працівників";
    }
}

function renderWorkers(workers) {
    const list = document.getElementById("workersList");
    list.innerHTML = "";

    workers.forEach(worker => {
        const row = document.createElement("div");
        row.className = "worker-row";

        row.innerHTML = `
            <span class="worker-name">${worker.name}</span>
        `;

        list.appendChild(row);
    });
}

function setupWorkerButtons() {
    const button = document.getElementById("addWorkerButton");

    button.addEventListener("click", addWorker);
}

async function addWorker() {
    const name = prompt("Ім'я працівника:");

    if (!name || !name.trim()) {
        return;
    }

    await fetch("/api/workers", {
        method: "POST",
        headers: {
            "Content-Type": "application/json"
        },
        body: JSON.stringify({
            name: name.trim()
        })
    });

    await loadWorkers();
}
