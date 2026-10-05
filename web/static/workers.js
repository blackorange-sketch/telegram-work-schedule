function showWorkersScreen() {
    const main = document.querySelector("main");

    main.innerHTML = `
        <section class="card workers-card">
            <div class="card-title">👥 Працівники</div>
            <div id="workersList"></div>
        </section>
    `;
    loadWorkers();
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
