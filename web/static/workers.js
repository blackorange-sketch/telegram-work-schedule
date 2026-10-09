let editingWorkerId = null;
let selectedWorkerTeam = "A";
let editingWorkerTeam = "A";

async function showWorkersScreen() {
    const screen = document.getElementById("workersScreen");

    screen.innerHTML = `
        <section class="card workers-card">
            <div class="card-title">👥 Працівники</div>

            <div class="worker-team-tabs" role="tablist" aria-label="Бригада">
                <button type="button" data-team="A" class="worker-team-tab active">Бригада A</button>
                <button type="button" data-team="B" class="worker-team-tab">Бригада B</button>
                <button type="button" data-team="C" class="worker-team-tab">Бригада C</button>
            </div>

            <div id="workersTeamLabel" class="workers-team-label">Бригада A</div>
            <div id="workersList">Завантаження…</div>

            <button id="addWorkerButton" class="add-worker-button">
                ＋ Додати працівника
            </button>

            <div id="workerModal" class="worker-modal hidden">
                <div class="worker-modal-box">
                    <div class="worker-modal-title">Новий працівник</div>

                    <input
                        id="workerNameInput"
                        type="text"
                        maxlength="100"
                        placeholder="Імʼя працівника"
                    >

                    <label class="worker-team-field" for="workerTeamInput">
                        Бригада
                        <select id="workerTeamInput">
                            <option value="A">A</option>
                            <option value="B">B</option>
                            <option value="C">C</option>
                        </select>
                    </label>

                    <label class="worker-reserve-field">
                        <input id="workerReserveInput" type="checkbox">
                        Резервний працівник
                    </label>

                    <div class="worker-modal-buttons">
                        <button id="cancelWorkerButton" type="button">Скасувати</button>
                        <button id="saveWorkerButton" type="button">Додати</button>
                    </div>
                </div>
            </div>
        </section>
    `;

    screen.querySelectorAll("[data-team]").forEach(button => {
        button.addEventListener("click", async () => {
            selectedWorkerTeam = button.dataset.team;

            screen.querySelectorAll("[data-team]").forEach(tab => {
                const active = tab.dataset.team === selectedWorkerTeam;
                tab.classList.toggle("active", active);
                tab.setAttribute("aria-selected", String(active));
            });

            document.getElementById("workersTeamLabel").textContent =
                `Бригада ${selectedWorkerTeam}`;

            await loadWorkers();
        });
    });

    setupWorkerButtons();
    await loadWorkers();
}

async function loadWorkers() {
    const list = document.getElementById("workersList");
    if (!list) return;

    list.textContent = "Завантаження…";

    try {
        const url =
            `/api/workers?group=${encodeURIComponent(selectedExotecGroup)}` +
            `&team_code=${encodeURIComponent(selectedWorkerTeam)}` +
            `&t=${Date.now()}`;

        const response = await fetch(url);
        if (!response.ok) {
            throw new Error(`HTTP ${response.status}`);
        }

        const data = await response.json();
        if (!Array.isArray(data)) {
            throw new Error("Некоректна відповідь API");
        }

        renderWorkers(data);
    } catch (error) {
        list.textContent = "Не вдалося завантажити працівників.";
        console.error("Помилка завантаження працівників:", error);
    }
}

function renderWorkers(workerList) {
    const list = document.getElementById("workersList");
    if (!list) return;

    list.replaceChildren();

    if (workerList.length === 0) {
        const empty = document.createElement("p");
        empty.className = "workers-empty";
        empty.textContent = `У бригаді ${selectedWorkerTeam} ще немає працівників.`;
        list.appendChild(empty);
        return;
    }

    workerList.forEach(worker => {
        const row = document.createElement("div");
        row.className = "worker-row";

        const name = document.createElement("span");
        name.className = "worker-name";
        name.append(document.createTextNode(worker.name));

        if (worker.is_reserve) {
            const label = document.createElement("small");
            label.textContent = " 🟢 Резерв";
            name.appendChild(label);
        }

        const actions = document.createElement("div");
        actions.className = "worker-actions";

        const editButton = document.createElement("button");
        editButton.type = "button";
        editButton.className = "edit-worker-btn";
        editButton.textContent = "✏️";
        editButton.title = "Редагувати";
        editButton.addEventListener("click", () => editWorker(worker));

        const reserveButton = document.createElement("button");
        reserveButton.type = "button";
        reserveButton.textContent = worker.is_reserve ? "🟢" : "🛡️";
        reserveButton.title = worker.is_reserve
            ? "Прибрати з резерву"
            : "Позначити як резерв";
        reserveButton.addEventListener("click", () =>
            toggleReserve(worker.id, worker.is_reserve)
        );

        const deleteButton = document.createElement("button");
        deleteButton.type = "button";
        deleteButton.textContent = "🗑";
        deleteButton.title = "Деактивувати";
        deleteButton.addEventListener("click", () => deleteWorker(worker.id));

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

    addButton.addEventListener("click", () => {
        editingWorkerId = null;
        editingWorkerTeam = selectedWorkerTeam;

        input.value = "";
        document.getElementById("workerTeamInput").value = selectedWorkerTeam;
        document.getElementById("workerReserveInput").checked = false;
        document.querySelector(".worker-modal-title").textContent = "Новий працівник";
        saveButton.textContent = "Додати";

        modal.classList.remove("hidden");
        input.focus();
    });

    const closeModal = () => {
        editingWorkerId = null;
        modal.classList.add("hidden");
    };

    modal.addEventListener("click", event => {
        if (event.target === modal) closeModal();
    });

    cancelButton.addEventListener("click", closeModal);
    saveButton.addEventListener("click", saveWorker);

    input.addEventListener("keydown", event => {
        if (event.key === "Enter") saveButton.click();
    });
}

function editWorker(worker) {
    editingWorkerId = worker.id;
    editingWorkerTeam = worker.team_code;

    const modal = document.getElementById("workerModal");
    const input = document.getElementById("workerNameInput");

    input.value = worker.name;
    document.getElementById("workerTeamInput").value = worker.team_code;
    document.getElementById("workerReserveInput").checked = worker.is_reserve;
    document.querySelector(".worker-modal-title").textContent = "Редагувати працівника";
    document.getElementById("saveWorkerButton").textContent = "Зберегти";

    modal.classList.remove("hidden");
    input.focus();
    input.select();
}

async function saveWorker() {
    const input = document.getElementById("workerNameInput");
    const saveButton = document.getElementById("saveWorkerButton");
    const name = input.value.trim();

    if (!name) {
        input.focus();
        return;
    }

    const editing = editingWorkerId !== null;
    const teamCode = document.getElementById("workerTeamInput").value;
    const isReserve = document.getElementById("workerReserveInput").checked;

    const url = editing
        ? `/api/workers/${editingWorkerId}?group=${encodeURIComponent(selectedExotecGroup)}`
        : `/api/workers?group=${encodeURIComponent(selectedExotecGroup)}`;

    saveButton.disabled = true;

    try {
        const response = await fetch(url, {
            method: editing ? "PUT" : "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                name,
                team_code: teamCode,
                is_reserve: isReserve
            })
        });

        if (!response.ok) {
            const detail = await response.text();
            throw new Error(detail || `HTTP ${response.status}`);
        }

        editingWorkerId = null;
        document.getElementById("workerModal").classList.add("hidden");

        if (editing && editingWorkerTeam !== teamCode) {
            selectedWorkerTeam = teamCode;
            document.querySelectorAll("[data-team]").forEach(tab => {
                const active = tab.dataset.team === teamCode;
                tab.classList.toggle("active", active);
                tab.setAttribute("aria-selected", String(active));
            });
            document.getElementById("workersTeamLabel").textContent =
                `Бригада ${teamCode}`;
        }

        await loadWorkers();
    } catch (error) {
        console.error("Помилка збереження працівника:", error);
        alert(editing
            ? "Не вдалося змінити працівника."
            : "Не вдалося додати працівника.");
    } finally {
        saveButton.disabled = false;
    }
}

async function deleteWorker(id) {
    if (!confirm("Деактивувати цього працівника?")) return;

    try {
        const response = await fetch(
            `/api/workers/${id}?group=${encodeURIComponent(selectedExotecGroup)}`,
            { method: "DELETE" }
        );

        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        await loadWorkers();
    } catch (error) {
        console.error("Помилка деактивації працівника:", error);
        alert("Не вдалося деактивувати працівника.");
    }
}

async function toggleReserve(id, currentState) {
    try {
        const response = await fetch(
            `/api/workers/${id}/reserve?group=${encodeURIComponent(selectedExotecGroup)}`,
            {
                method: "PUT",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ is_reserve: !currentState })
            }
        );

        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        await loadWorkers();
    } catch (error) {
        console.error("Помилка зміни резерву:", error);
        alert("Не вдалося змінити статус резерву.");
    }
}
