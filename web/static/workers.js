function showWorkersScreen() {
    const main = document.querySelector("main");

    main.innerHTML = `
        <section class="card workers-card">
            <div class="card-title">👥 Працівники</div>
            <div id="workersList"></div><button id="addWorkerButton" class="add-worker-button">＋ Додати працівника</button>
        <div id="workerModal" class="worker-modal hidden"><div class="worker-modal-box"><div class="worker-modal-title">Новий працівник</div><input id="workerNameInput" type="text" placeholder="Імʼя працівника"><div class="worker-modal-buttons"><button id="cancelWorkerButton">Скасувати</button><button id="saveWorkerButton">Додати</button></div></div></div></section>
    `;
    if (!workersScreenLoaded) {
        loadWorkers();
        workersScreenLoaded = true;
    }
    setupWorkerButtons();
}

async function loadWorkers() {
    const list = document.getElementById("workersList");

    try {
        const response = await fetch("/api/workers?t=" + Date.now());
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
            <span class="worker-name">${worker.name}${worker.is_reserve ? ' <small>🟢 Резерв</small>' : ""}</span>
            <div class="worker-actions">
                <button class="edit-worker-btn">✏️</button><button onclick="toggleReserve(${worker.id}, ${worker.is_reserve})">${worker.is_reserve ? "🟢" : "🛡️"}</button>
                <button onclick="deleteWorker(${worker.id})">🗑</button>
            </div>
        `;

        row.querySelector(".edit-worker-btn").onclick = () => editWorker(worker.id, worker.name);
        list.appendChild(row);
    });
}
function setupWorkerButtons() {
    const addButton = document.getElementById("addWorkerButton");
    const cancelButton = document.getElementById("cancelWorkerButton");
    const saveButton = document.getElementById("saveWorkerButton");
    const modal = document.getElementById("workerModal");
    const input = document.getElementById("workerNameInput");

    addButton.onclick = () => {
        modal.classList.remove("hidden");
        input.value = "";
        input.focus();
        saveButton.onclick = addWorker;
    };

    modal.onclick = (event) => {
        if (event.target === modal) {
            modal.classList.add("hidden");
        }
    };
    cancelButton.onclick = () => {
        modal.classList.add("hidden");
    };

    saveButton.onclick = addWorker;
    input.onkeydown = (event) => {
        if (event.key === "Enter") {
            saveButton.click();
        }
    };
}

async function addWorker() {
    const modal = document.getElementById("workerModal");
    const input = document.getElementById("workerNameInput");
    const name = input.value.trim();

    if (!name) {
        input.focus();
        return;
    }

    const response = await fetch("/api/workers", {
        method: "POST",
        headers: {
            "Content-Type": "application/json"
        },
        body: JSON.stringify({
            name: name
        })
    });

    if (!response.ok) {
        alert("Не вдалося додати працівника");
        return;
    }

    modal.classList.add("hidden");
    input.value = "";
    await loadWorkers();
}

async function editWorker(id, oldName) {
    const modal = document.getElementById("workerModal");
    const input = document.getElementById("workerNameInput");
    const saveButton = document.getElementById("saveWorkerButton");

    modal.classList.remove("hidden");
    input.value = oldName;
    input.focus();
    input.select();

    saveButton.onclick = async () => {
        const name = input.value.trim();

        if (!name) {
            input.focus();
            return;
        }

        const response = await fetch(`/api/workers/${id}`, {
            method: "PUT",
            headers: {
                "Content-Type": "application/json"
            },
            body: JSON.stringify({
                name: name
            })
        });

        if (!response.ok) {
            alert("Не вдалося змінити імʼя");
            return;
        }

        modal.classList.add("hidden");
        input.value = "";
        await loadWorkers();
    };
}

async function deleteWorker(id) {
    if (!confirm("Деактивувати цього працівника?")) {
        return;
    }

    const response = await fetch(`/api/workers/${id}`, {
        method: "DELETE"
    });

    if (!response.ok) {
        alert("Не вдалося деактивувати працівника");
        return;
    }

    await loadWorkers();
}

async function toggleReserve(id, currentState) {
    const response = await fetch(`/api/workers/${id}/reserve`, {
        method: "PUT",
        headers: {
            "Content-Type": "application/json"
        },
        body: JSON.stringify({
            is_reserve: !currentState
        })
    });

    if (!response.ok) {
        alert("Не вдалося змінити статус резерву");
        return;
    }

    await loadWorkers();
}
