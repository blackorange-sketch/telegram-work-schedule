let editingWorkerId = null;

async function showWorkersScreen() {
    const screen = document.getElementById("workersScreen");

    screen.innerHTML = `
        <section class="card workers-card">
            <div class="card-title">👥 Працівники</div>
            <div id="workersList"></div>

            <button id="addWorkerButton" class="add-worker-button">
                ＋ Додати працівника
            </button>

            <div id="workerModal" class="worker-modal hidden">
                <div class="worker-modal-box">
                    <div class="worker-modal-title">Новий працівник</div>

                    <input
                        id="workerNameInput"
                        type="text"
                        placeholder="Імʼя працівника"
                    >

                    <div class="worker-modal-buttons">
                        <button id="cancelWorkerButton">Скасувати</button>
                        <button id="saveWorkerButton">Додати</button>
                    </div>
                </div>
            </div>
        </section>
    `;

    setupWorkerButtons();
    await loadWorkers();
}

async function loadWorkers() {
    const list = document.getElementById("workersList");

    try {
        const response = await fetch(`/api/workers?group=${encodeURIComponent(selectedExotecGroup)}&t=${Date.now()}`);
        workers = await response.json();

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

        const name = document.createElement("span");
        name.className = "worker-name";
        name.textContent = worker.name;

        if (worker.is_reserve) {
            const reserveLabel = document.createElement("small");
            reserveLabel.textContent = " 🟢 Резерв";
            name.appendChild(reserveLabel);
        }

        const actions = document.createElement("div");
        actions.className = "worker-actions";

        const editButton = document.createElement("button");
        editButton.className = "edit-worker-btn";
        editButton.textContent = "✏️";
        editButton.addEventListener("click", () => {
            editWorker(worker.id, worker.name);
        });

        const reserveButton = document.createElement("button");
        reserveButton.textContent = worker.is_reserve ? "🟢" : "🛡️";
        reserveButton.addEventListener("click", () => {
            toggleReserve(worker.id, worker.is_reserve);
        });

        const deleteButton = document.createElement("button");
        deleteButton.textContent = "🗑";
        deleteButton.addEventListener("click", () => {
            deleteWorker(worker.id);
        });

        actions.append(editButton, reserveButton, deleteButton);
        row.append(name, actions);
        list.appendChild(row);
    });
}
function setupWorkerButtons() {
    const addButton = document.getElementById("addWorkerButton");
    const cancelButton = document.getElementById("cancelWorkerButton");
    const saveButton = document.getElementById("saveWorkerButton");
    const modal = document.getElementById("workerModal");
    const input = document.getElementById("workerNameInput");
    const title = document.querySelector(".worker-modal-title");

    addButton.addEventListener("click", () => {
        editingWorkerId = null;
        modal.classList.remove("hidden");
        input.value = "";
        input.focus();
        title.textContent = "Новий працівник";
        saveButton.textContent = "Додати";
    });

    modal.addEventListener("click", (event) => {
        if (event.target === modal) {
            editingWorkerId = null;
            modal.classList.add("hidden");
        }
    });

    cancelButton.addEventListener("click", () => {
        editingWorkerId = null;
        modal.classList.add("hidden");
    });

    saveButton.addEventListener("click", saveWorker);

    input.addEventListener("keydown", (event) => {
        if (event.key === "Enter") {
            saveButton.click();
        }
    });
}

async function saveWorker() {
    const modal = document.getElementById("workerModal");
    const input = document.getElementById("workerNameInput");
    const saveButton = document.getElementById("saveWorkerButton");
    const name = input.value.trim();

    if (!name) {
        input.focus();
        return;
    }

    const editing = editingWorkerId !== null;
    const url = editing
        ? `/api/workers/${editingWorkerId}?group=${encodeURIComponent(selectedExotecGroup)}`
        : `/api/workers?group=${encodeURIComponent(selectedExotecGroup)}`;

    const response = await fetch(url, {
        method: editing ? "PUT" : "POST",
        headers: {
            "Content-Type": "application/json"
        },
        body: JSON.stringify({ name })
    });

    if (!response.ok) {
        alert(
            editing
                ? "Не вдалося змінити імʼя"
                : "Не вдалося додати працівника"
        );
        return;
    }

    editingWorkerId = null;
    modal.classList.add("hidden");
    input.value = "";
    saveButton.textContent = "Додати";

    await loadWorkers();
}

function editWorker(id, oldName) {
    const modal = document.getElementById("workerModal");
    const input = document.getElementById("workerNameInput");
    const saveButton = document.getElementById("saveWorkerButton");
    const title = document.querySelector(".worker-modal-title");

    editingWorkerId = id;
    modal.classList.remove("hidden");
    input.value = oldName;
    input.focus();
    input.select();
    title.textContent = "Редагувати працівника";
    saveButton.textContent = "Зберегти";
}

async function deleteWorker(id) {
    if (!confirm("Деактивувати цього працівника?")) {
        return;
    }

    const response = await fetch(`/api/workers/${id}?group=${encodeURIComponent(selectedExotecGroup)}`, {
        method: "DELETE"
    });

    if (!response.ok) {
        alert("Не вдалося деактивувати працівника");
        return;
    }

    await loadWorkers();
}

async function toggleReserve(id, currentState) {
    const response = await fetch(`/api/workers/${id}/reserve?group=${encodeURIComponent(selectedExotecGroup)}`, {
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
