
const API = window.APP_CONFIG.API_BASE_URL.replace(/\/$/, "");

const TYPES = [
    "Cargo Ship",
    "Passenger Ship",
    "Container Ship",
    "Tanker",
    "Naval Ship",
    "Other"
];

const STATUSES = [
    "Ready",
    "In Service",
    "Docked",
    "Under Maintenance",
    "Inactive"
];

const MSTATUSES = [
    "Scheduled",
    "In Progress",
    "Completed",
    "Delayed"
];

const BADGE = {
    "Ready": "b-ready",
    "In Service": "b-service",
    "Docked": "b-docked",
    "Under Maintenance": "b-maint",
    "Inactive": "b-inactive",
    "Scheduled": "b-scheduled",
    "In Progress": "b-progress",
    "Completed": "b-completed",
    "Delayed": "b-delayed",
    "Arrival": "b-arrival",
    "Departure": "b-departure"
};

const TITLES = {
    dashboard: "Dashboard",
    vessels: "Manage Vessels",
    register: "Register Vessel",
    maintenance: "Maintenance",
    movements: "Vessel Movement",
    reports: "Reports"
};

let token = sessionStorage.getItem("token");
let me = null;

const $ = (id) => document.getElementById(id);

let currentShips = [];
let editingId = null;
let recentShips = [];
let allShips = [];
let maintRows = [];
let editingMaint = null;
let detailShip = null;
let searchTimer = null;

// =====================================================
// API AND HELPERS
// =====================================================

async function api(path, options = {}) {
    let res;

    try {
        const headers = {
            "Content-Type": "application/json",
            ...(options.headers || {})
        };

        if (token) {
            headers.Authorization = "Bearer " + token;
        }

        res = await fetch(API + path, {
            ...options,
            headers
        });

    } catch (e) {
        throw new Error(
            "Cannot reach the server at " + API +
            ". Please check whether the backend is running."
        );
    }

    let data = {};

    try {
        data = await res.json();
    } catch (e) {
        // Response may not contain JSON.
    }

    if (res.status === 401 && path !== "/api/auth/login") {
        showLogin();
        throw new Error("Session expired. Please sign in again.");
    }

    if (!res.ok) {
        throw new Error(
            data.error ||
            data.message ||
            "Request failed (" + res.status + ")."
        );
    }

    return data;
}

const esc = (s) => {
    const d = document.createElement("div");
    d.textContent = s == null ? "" : s;
    return d.innerHTML;
};

const badge = (s) =>
    `<span class="badge ${BADGE[s] || "b-inactive"}">${esc(s)}</span>`;

function toast(message, type = "info") {
    const container = $("toasts");
    if (!container) return;

    const t = document.createElement("div");
    t.className = "toast " + type;
    t.textContent = message;

    container.appendChild(t);

    setTimeout(() => t.remove(), 3500);
}

function fillOptions(select, items) {
    if (!select) return;

    items.forEach((item) => {
        select.insertAdjacentHTML(
            "beforeend",
            `<option value="${esc(item)}">${esc(item)}</option>`
        );
    });
}

["shipType", "filterType"].forEach((id) => {
    fillOptions($(id), TYPES);
});

["shipStatus", "filterStatus"].forEach((id) => {
    fillOptions($(id), STATUSES);
});

["mdStatus", "mFilterStatus"].forEach((id) => {
    fillOptions($(id), MSTATUSES);
});

// =====================================================
// DASHBOARD WELCOME AND CLOCK
// =====================================================

function updateDashboardWelcome() {
    if (!me) return;

    const hour = new Date().getHours();

    let greeting = "Good evening";

    if (hour < 12) {
        greeting = "Good morning";
    } else if (hour < 17) {
        greeting = "Good afternoon";
    }

    const welcomeTitle = $("welcomeTitle");
    const welcomeSubtitle = $("welcomeSubtitle");

    if (welcomeTitle) {
        welcomeTitle.textContent =
            `${greeting}, ${me.username}!`;
    }

    if (welcomeSubtitle) {
        const role = String(me.role || "user");

        welcomeSubtitle.textContent =
            `${role.charAt(0).toUpperCase() + role.slice(1)} access · Here's your shipyard operations overview.`;
    }
}

function updateDashboardClock() {
    const now = new Date();

    const dateElement = $("dashboardDate");
    const timeElement = $("dashboardTime");

    if (dateElement) {
        dateElement.textContent =
            now.toLocaleDateString("en-IN", {
                weekday: "long",
                day: "numeric",
                month: "long",
                year: "numeric"
            });
    }

    if (timeElement) {
        timeElement.textContent =
            now.toLocaleTimeString("en-IN", {
                hour: "2-digit",
                minute: "2-digit",
                second: "2-digit",
                hour12: true,
                timeZone: "Asia/Kolkata"
            });
    }
}

updateDashboardClock();
setInterval(updateDashboardClock, 1000);

// =====================================================
// NAVIGATION
// =====================================================

function showView() {
    let view = location.hash.replace("#", "");

    if (!TITLES[view]) {
        view = "dashboard";
    }

    if (view === "register" && me && me.role === "viewer") {
        view = "dashboard";
    }

    document.querySelectorAll(".view").forEach((element) => {
        element.classList.toggle(
            "active",
            element.id === "view-" + view
        );
    });

    document.querySelectorAll(".sidebar nav a").forEach((element) => {
        element.classList.toggle(
            "active",
            element.dataset.view === view
        );
    });

    if ($("pageTitle")) {
        $("pageTitle").textContent =
            view === "register" && editingId
                ? "Edit Vessel"
                : TITLES[view];
    }

    if ($("heroRegTitle")) {
        $("heroRegTitle").textContent =
            editingId ? "Edit Vessel" : "Register a Vessel";
    }

    window.scrollTo(0, 0);

    $("sidebar")?.classList.remove("open");

    if (view === "dashboard" || view === "reports") {
        loadStats();
    }

    if (view === "vessels") {
        loadShips();
    }

    if (view === "maintenance") {
        loadShipOptions().then(loadMaintenance);
    }

    if (view === "movements") {
        loadShipOptions().then(loadMovements);
    }
}

window.addEventListener("hashchange", showView);

$("menuBtn")?.addEventListener("click", (e) => {
    e.stopPropagation();
    $("sidebar")?.classList.toggle("open");
});

document.addEventListener("click", (e) => {
    if (!e.target.closest("#sidebar")) {
        $("sidebar")?.classList.remove("open");
    }
});

// =====================================================
// DASHBOARD STAT CARD NAVIGATION
// =====================================================

document.querySelectorAll(".stat.clickable").forEach((element) => {
    element.addEventListener("click", () => {
        $("searchInput").value = "";
        $("filterType").value = "";
        $("filterStatus").value = element.dataset.status;

        if (location.hash === "#vessels") {
            loadShips();
        } else {
            location.hash = "vessels";
        }
    });
});

$("recentMoves")?.addEventListener("click", () => {
    location.hash = "movements";
});

// =====================================================
// DASHBOARD AND REPORTS
// =====================================================

async function loadStats() {
    try {
        const s = await api("/api/dashboard/stats");

        $("sTotal").textContent = s.total ?? 0;
        $("sReady").textContent = s.ready ?? 0;
        $("sService").textContent = s.active ?? 0;
        $("sMaint").textContent = s.under_maintenance ?? 0;
        $("sDocked").textContent = s.docked ?? 0;
        $("sInactive").textContent = s.inactive ?? 0;

        const bars = (rows, total) => {
            if (!rows || !rows.length) {
                return '<p class="muted">No data yet.</p>';
            }

            return rows.map(([label, n]) => `
                <div class="bar-row">
                    <div class="top">
                        <span>${esc(label)}</span>
                        <strong>${Number(n) || 0}</strong>
                    </div>
                    <div class="bar">
                        <i style="width:${total ? ((Number(n) || 0) / total) * 100 : 0}%"></i>
                    </div>
                </div>
            `).join("");
        };

        const statusRows = [
            ["Ready", s.ready],
            ["In Service", s.in_service],
            ["Docked", s.docked],
            ["Under Maintenance", s.under_maintenance],
            ["Inactive", s.inactive]
        ];

        $("statusBars").innerHTML =
            bars(statusRows, s.total);

        $("dashStatusBars").innerHTML =
            bars(statusRows, s.total);

        const maintenanceRows = Object.entries(
            s.maintenance_by_status || {}
        );

        $("dashMaintBars").innerHTML =
            bars(
                maintenanceRows,
                maintenanceRows.reduce(
                    (sum, row) => sum + (Number(row[1]) || 0),
                    0
                )
            );

        $("typeBars").innerHTML =
            bars(
                (s.by_type || []).map((item) => [
                    item.ship_type,
                    item.count
                ]),
                s.total
            );

        // Recent registrations
        recentShips = s.recent_ships || [];

        $("recentBody").innerHTML =
            recentShips.map((v) => `
                <tr class="clickable" data-id="${v.id}">
                    <td>${esc(v.ship_id)}</td>
                    <td>${esc(v.ship_name)}</td>
                    <td>${esc(v.ship_type)}</td>
                    <td>${esc(v.registration_date)}</td>
                    <td>${badge(v.status)}</td>
                    <td>${esc(v.berth_number) || "-"}</td>
                </tr>
            `).join("") ||
            '<tr><td colspan="6" class="muted">No vessels registered yet.</td></tr>';

        // Recent movements
        $("recentMoves").innerHTML =
            (s.recent_movements || []).map((m) => `
                <tr>
                    <td>${esc(m.movement_date)}</td>
                    <td>
                        ${esc(m.ship_name)}
                        <span class="muted">(${esc(m.ship_id)})</span>
                    </td>
                    <td>${badge(m.movement_type)}</td>
                    <td>${esc(m.berth_number) || "-"}</td>
                </tr>
            `).join("") ||
            '<tr><td colspan="4" class="muted">No movements recorded yet.</td></tr>';

    } catch (e) {
        toast(e.message, "error");
    }
}

$("recentBody")?.addEventListener("click", (e) => {
    const tr = e.target.closest("tr[data-id]");

    if (tr) {
        openDetails(
            recentShips.find(
                (ship) => ship.id === Number(tr.dataset.id)
            )
        );
    }
});

// =====================================================
// VESSEL LIST
// =====================================================

async function loadShips() {
    const params = new URLSearchParams();

    if ($("searchInput").value.trim()) {
        params.set("search", $("searchInput").value.trim());
    }

    if ($("filterType").value) {
        params.set("type", $("filterType").value);
    }

    if ($("filterStatus").value) {
        params.set("status", $("filterStatus").value);
    }

    $("shipTableBody").innerHTML =
        '<tr><td colspan="8" class="muted">Loading...</td></tr>';

    try {
        currentShips = await api("/api/ships?" + params);

        $("emptyMsg").hidden = currentShips.length > 0;

        $("shipTableBody").innerHTML =
            currentShips.map((v, i) => `
                <tr>
                    <td>${i + 1}</td>
                    <td>${esc(v.ship_id)}</td>
                    <td>${esc(v.ship_name)}</td>
                    <td>${esc(v.ship_type)}</td>
                    <td>${esc(v.registration_date)}</td>
                    <td>${badge(v.status)}</td>
                    <td>${esc(v.berth_number) || "-"}</td>
                    <td>
                        <button class="btn btn-secondary btn-sm"
                                data-act="view" data-id="${v.id}">
                            View
                        </button>

                        <button class="btn btn-secondary btn-sm w"
                                data-act="edit" data-id="${v.id}">
                            Edit
                        </button>

                        <button class="btn btn-danger btn-sm adm"
                                data-act="delete" data-id="${v.id}">
                            Delete
                        </button>
                    </td>
                </tr>
            `).join("");

    } catch (e) {
        $("shipTableBody").innerHTML = "";
        toast(e.message, "error");
    }
}

$("shipTableBody").addEventListener("click", async (e) => {
    const btn = e.target.closest("button[data-act]");

    if (!btn) return;

    const ship = currentShips.find(
        (item) => item.id === Number(btn.dataset.id)
    );

    if (!ship) return;

    if (btn.dataset.act === "view") {
        return openDetails(ship);
    }

    if (btn.dataset.act === "edit") {
        return startEdit(ship);
    }

    if (!confirm(
        `Delete vessel ${ship.ship_id} (${ship.ship_name})? This cannot be undone.`
    )) {
        return;
    }

    try {
        await api("/api/ships/" + ship.id, {
            method: "DELETE"
        });

        toast("Vessel " + ship.ship_id + " deleted.", "success");
        loadShips();

    } catch (err) {
        toast(err.message, "error");
    }
});

$("searchInput").addEventListener("input", () => {
    clearTimeout(searchTimer);
    searchTimer = setTimeout(loadShips, 300);
});

$("filterType").addEventListener("change", loadShips);
$("filterStatus").addEventListener("change", loadShips);

$("clearFilters").addEventListener("click", () => {
    $("searchInput").value = "";
    $("filterType").value = "";
    $("filterStatus").value = "";
    loadShips();
});

// =====================================================
// VESSEL DETAILS DIALOG
// =====================================================

function openDetails(ship) {
    if (!ship) return;

    detailShip = ship;

    $("dName").textContent = ship.ship_name;

    $("dBody").innerHTML = [
        ["Vessel ID", esc(ship.ship_id)],
        ["Type", esc(ship.ship_type)],
        ["Registered", esc(ship.registration_date)],
        ["Status", badge(ship.status)],
        ["Berth / Dock", esc(ship.berth_number) || "Not assigned"]
    ].map(([key, value]) => `
        <dt>${key}</dt>
        <dd>${value}</dd>
    `).join("");

    $("detailDialog").showModal();
}

$("dClose").addEventListener("click", () => {
    $("detailDialog").close();
});

$("dEdit").addEventListener("click", () => {
    $("detailDialog").close();
    startEdit(detailShip);
});

$("detailDialog").addEventListener("click", (e) => {
    if (e.target === $("detailDialog")) {
        $("detailDialog").close();
    }
});

// =====================================================
// VESSEL REGISTRATION AND EDITING
// =====================================================

const fields = [
    "shipName",
    "shipId",
    "shipType",
    "regDate",
    "shipStatus"
];

const mark = (id, bad) => {
    $(id).parentElement.classList.toggle("invalid", bad);
};

function resetForm() {
    $("shipForm").reset();

    editingId = null;

    $("formTitle").textContent = "Register a Vessel";
    $("submitBtn").textContent = "Register Vessel";
    $("cancelBtn").hidden = true;

    fields.forEach((field) => mark(field, false));
}

function startEdit(ship) {
    editingId = ship.id;

    $("shipName").value = ship.ship_name;
    $("shipId").value = ship.ship_id;
    $("shipType").value = ship.ship_type;
    $("regDate").value = ship.registration_date;
    $("shipStatus").value = ship.status;
    $("berth").value = ship.berth_number || "";

    $("formTitle").textContent = "Edit Vessel";
    $("submitBtn").textContent = "Update Vessel";
    $("cancelBtn").hidden = false;

    location.hash = "register";
    showView();
}

$("cancelBtn").addEventListener("click", () => {
    resetForm();
    location.hash = "vessels";
});

$("shipForm").addEventListener("submit", async (e) => {
    e.preventDefault();

    const ship = {
        ship_name: $("shipName").value.trim(),
        ship_id: $("shipId").value.trim(),
        ship_type: $("shipType").value,
        registration_date: $("regDate").value,
        status: $("shipStatus").value,
        berth_number: $("berth").value.trim()
    };

    const missing = {
        shipName: !ship.ship_name,
        shipId: !ship.ship_id,
        shipType: !ship.ship_type,
        regDate: !ship.registration_date,
        shipStatus: !ship.status
    };

    Object.entries(missing).forEach(([id, bad]) => mark(id, bad));

    if (Object.values(missing).some(Boolean)) {
        return toast("Please fill in all required fields.", "error");
    }

    const isEdit = editingId !== null;

    $("submitBtn").disabled = true;

    try {
        await api(
            isEdit ? "/api/ships/" + editingId : "/api/ships",
            {
                method: isEdit ? "PUT" : "POST",
                body: JSON.stringify(ship)
            }
        );

        toast(
            isEdit
                ? "Vessel updated."
                : `Vessel '${ship.ship_name}' registered.`,
            "success"
        );

        resetForm();
        location.hash = "vessels";

    } catch (err) {
        if (/already exists/i.test(err.message)) {
            mark("shipId", true);
        }

        toast(err.message, "error");

    } finally {
        $("submitBtn").disabled = false;
    }
});

// =====================================================
// CSV EXPORT
// =====================================================

async function exportCSV() {
    try {
        const rows = await api("/api/ships");

        if (!rows.length) {
            return toast("No vessels to export.", "error");
        }

        const head = [
            "Vessel ID",
            "Name",
            "Type",
            "Registration Date",
            "Status",
            "Berth"
        ];

        const quote = (value) =>
            '"' + String(value ?? "").replace(/"/g, '""') + '"';

        const csv = [
            head,
            ...rows.map((v) => [
                v.ship_id,
                v.ship_name,
                v.ship_type,
                v.registration_date,
                v.status,
                v.berth_number
            ])
        ].map((row) => row.map(quote).join(",")).join("\n");

        const url = URL.createObjectURL(
            new Blob(["\ufeff" + csv], {
                type: "text/csv;charset=utf-8"
            })
        );

        const a = document.createElement("a");
        a.href = url;
        a.download = "vessels.csv";
        a.click();

        URL.revokeObjectURL(url);

        toast("CSV downloaded.", "success");

    } catch (e) {
        toast(e.message, "error");
    }
}

$("exportBtn").addEventListener("click", exportCSV);
$("exportAllBtn").addEventListener("click", exportCSV);

// =====================================================
// VESSEL DROPDOWNS
// =====================================================

async function loadShipOptions() {
    try {
        allShips = await api("/api/ships");

        const opts = allShips.map((v) => `
            <option value="${v.id}">
                ${esc(v.ship_name)} (${esc(v.ship_id)})
            </option>
        `).join("");

        ["mFilterShip", "mvFilterShip"].forEach((id) => {
            const keep = $(id).value;

            $(id).innerHTML =
                '<option value="">All vessels</option>' + opts;

            $(id).value = keep;
        });

        const keep = $("mvShip").value;

        $("mvShip").innerHTML =
            '<option value="">Select vessel</option>' + opts;

        $("mvShip").value = keep;

        $("mdShip").innerHTML =
            '<option value="">Select vessel</option>' + opts;

    } catch (e) {
        toast(e.message, "error");
    }
}

// =====================================================
// MAINTENANCE
// =====================================================

async function loadMaintenance() {
    const params = new URLSearchParams();

    if ($("mFilterShip").value) {
        params.set("ship_pk", $("mFilterShip").value);
    }

    if ($("mFilterStatus").value) {
        params.set("status", $("mFilterStatus").value);
    }

    try {
        maintRows = await api("/api/maintenance?" + params);

        $("mEmpty").hidden = maintRows.length > 0;

        $("maintBody").innerHTML =
            maintRows.map((m) => `
                <tr>
                    <td>
                        ${esc(m.ship_name)}
                        <span class="muted">(${esc(m.ship_id)})</span>
                    </td>
                    <td class="desc">${esc(m.description)}</td>
                    <td>${esc(m.start_date)}</td>
                    <td>${esc(m.end_date) || "-"}</td>
                    <td>${badge(m.status)}</td>
                    <td>
                        <button class="btn btn-secondary btn-sm w"
                                data-act="edit" data-id="${m.id}">
                            Edit
                        </button>
                        <button class="btn btn-danger btn-sm adm"
                                data-act="delete" data-id="${m.id}">
                            Delete
                        </button>
                    </td>
                </tr>
            `).join("");

    } catch (e) {
        toast(e.message, "error");
    }
}

["mFilterShip", "mFilterStatus"].forEach((id) => {
    $(id).addEventListener("change", loadMaintenance);
});

function openMaint(rec) {
    editingMaint = rec ? rec.id : null;

    $("mdTitle").textContent =
        rec ? "Edit Maintenance Record" : "New Maintenance Record";

    $("maintForm").reset();

    if (rec) {
        $("mdShip").value = rec.ship_pk;
        $("mdDesc").value = rec.description;
        $("mdStart").value = rec.start_date;
        $("mdEnd").value = rec.end_date || "";
        $("mdStatus").value = rec.status;
    } else {
        $("mdStatus").value = "Scheduled";
        $("mdStart").value = new Date().toISOString().slice(0, 10);
    }

    $("maintDialog").showModal();
}

$("mNewBtn").addEventListener("click", () => openMaint(null));

$("mdClose").addEventListener("click", () => {
    $("maintDialog").close();
});

$("maintBody").addEventListener("click", async (e) => {
    const btn = e.target.closest("button[data-act]");

    if (!btn) return;

    const rec = maintRows.find(
        (item) => item.id === Number(btn.dataset.id)
    );

    if (!rec) return;

    if (btn.dataset.act === "edit") {
        return openMaint(rec);
    }

    if (!confirm(`Delete this maintenance record for ${rec.ship_name}?`)) {
        return;
    }

    try {
        await api("/api/maintenance/" + rec.id, {
            method: "DELETE"
        });

        toast("Record deleted.", "success");
        loadMaintenance();

    } catch (err) {
        toast(err.message, "error");
    }
});

$("maintForm").addEventListener("submit", async (e) => {
    e.preventDefault();

    const body = {
        ship_pk: $("mdShip").value,
        description: $("mdDesc").value.trim(),
        start_date: $("mdStart").value,
        end_date: $("mdEnd").value,
        status: $("mdStatus").value
    };

    if (!body.ship_pk || !body.description || !body.start_date) {
        return toast(
            "Vessel, description and start date are required.",
            "error"
        );
    }

    if (body.end_date && body.end_date < body.start_date) {
        return toast(
            "End date cannot be before the start date.",
            "error"
        );
    }

    $("mdSave").disabled = true;

    try {
        await api(
            editingMaint
                ? "/api/maintenance/" + editingMaint
                : "/api/maintenance",
            {
                method: editingMaint ? "PUT" : "POST",
                body: JSON.stringify(body)
            }
        );

        $("maintDialog").close();

        toast("Maintenance record saved.", "success");
        loadMaintenance();

    } catch (err) {
        toast(err.message, "error");

    } finally {
        $("mdSave").disabled = false;
    }
});

// =====================================================
// VESSEL MOVEMENTS
// =====================================================

async function loadMovements() {
    const params = $("mvFilterShip").value
        ? "?ship_pk=" + encodeURIComponent($("mvFilterShip").value)
        : "";

    try {
        const rows = await api("/api/movements" + params);

        $("mvEmpty").hidden = rows.length > 0;

        $("moveBody").innerHTML =
            rows.map((m) => `
                <tr>
                    <td>${esc(m.movement_date)}</td>
                    <td>
                        ${esc(m.ship_name)}
                        <span class="muted">(${esc(m.ship_id)})</span>
                    </td>
                    <td>${badge(m.movement_type)}</td>
                    <td>${esc(m.berth_number) || "-"}</td>
                    <td>${esc(m.notes) || "-"}</td>
                </tr>
            `).join("");

    } catch (e) {
        toast(e.message, "error");
    }
}

$("mvFilterShip").addEventListener("change", loadMovements);

$("mvType").addEventListener("change", () => {
    $("mvBerthLbl").textContent =
        $("mvType").value === "Arrival"
            ? "Berth *"
            : "Berth (optional)";
});

$("mvDate").value = new Date().toISOString().slice(0, 10);

$("moveForm").addEventListener("submit", async (e) => {
    e.preventDefault();

    const body = {
        ship_pk: $("mvShip").value,
        movement_type: $("mvType").value,
        movement_date: $("mvDate").value,
        berth_number: $("mvBerth").value.trim(),
        notes: $("mvNotes").value.trim()
    };

    if (!body.ship_pk || !body.movement_date) {
        return toast("Select a vessel and a date.", "error");
    }

    if (body.movement_type === "Arrival" && !body.berth_number) {
        return toast("Berth is required for an arrival.", "error");
    }

    $("mvBtn").disabled = true;

    try {
        await api("/api/movements", {
            method: "POST",
            body: JSON.stringify(body)
        });

        toast(body.movement_type + " recorded.", "success");

        $("mvBerth").value = "";
        $("mvNotes").value = "";

        await loadShipOptions();
        loadMovements();

    } catch (err) {
        toast(err.message, "error");

    } finally {
        $("mvBtn").disabled = false;
    }
});

// =====================================================
// AUTHENTICATION
// =====================================================

function showLogin() {
    token = null;
    me = null;

    sessionStorage.removeItem("token");

    document.body.className = "logged-out";

    $("loginPass").value = "";

    if ($("loginErr")) {
        $("loginErr").hidden = true;
        $("loginErr").textContent = "";
    }
}

function enterApp(user) {
    if (!user || !user.role || !user.username) {
        throw new Error("The server returned an invalid user response.");
    }

    me = user;

    document.body.className = "role-" + user.role;

    $("userName").textContent = user.username;
    $("userRole").textContent = user.role;

    $("userChip").textContent =
        user.username + " · " + user.role;

    updateDashboardWelcome();
    updateDashboardClock();

    showView();
}

$("loginForm").addEventListener("submit", async (e) => {
    e.preventDefault();

    const username = $("loginUser").value.trim();
    const password = $("loginPass").value;

    if (!username || !password) {
        $("loginErr").textContent = "Enter your username and password.";
        $("loginErr").hidden = false;
        return;
    }

    $("loginErr").className = "login-err";
    $("loginErr").hidden = true;
    $("loginBtn").disabled = true;
    $("loginBtn").textContent = "Signing in...";

    try {
        const r = await api("/api/auth/login", {
            method: "POST",
            body: JSON.stringify({ username, password })
        });

        if (!r.token || !r.user) {
            throw new Error("Invalid login response from server.");
        }

        token = r.token;
        sessionStorage.setItem("token", token);

        enterApp(r.user);

        $("loginPass").value = "";

    } catch (err) {
        token = null;
        me = null;
        sessionStorage.removeItem("token");

        $("loginErr").textContent = err.message;
        $("loginErr").hidden = false;

    } finally {
        $("loginBtn").disabled = false;
        $("loginBtn").textContent = "Sign In";
    }
});

$("logoutBtn").addEventListener("click", async () => {
    try {
        await api("/api/auth/logout", {
            method: "POST"
        });
    } catch (e) {
        // Local session is cleared even if logout endpoint is unavailable.
    }

    showLogin();
});

// =====================================================
// BACKEND CONNECTION CHECK
// =====================================================

async function checkBackend() {
    try {
        const response = await fetch(API + "/", {
            cache: "no-store"
        });

        if (!response.ok) {
            throw new Error("Server returned " + response.status);
        }

        return true;

    } catch (e) {
        if ($("loginErr")) {
            $("loginErr").className = "login-err warn";
            $("loginErr").textContent =
                "Cannot reach the backend at " + API +
                ". Start the backend and reload this page.";
            $("loginErr").hidden = false;
        }

        return false;
    }
}

// =====================================================
// APPLICATION INITIALIZATION
// =====================================================

(async function init() {
    if (!token) {
        showLogin();
        await checkBackend();
        return;
    }

    try {
        const user = await api("/api/auth/me");
        enterApp(user);

    } catch (e) {
        showLogin();
        await checkBackend();
    }
})();
