function showWorkersScreen() {
    const main = document.querySelector("main");

    main.innerHTML = `
        <section class="card workers-card">
            <div class="card-title">👥 Працівники</div>
            <div id="workersList"></div>
        </section>
    `;
}
