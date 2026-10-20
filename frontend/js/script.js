const authSection = document.getElementById("authSection");
const dashboardSection = document.getElementById("dashboardSection");
const authMessage = document.getElementById("authMessage");
const dashboardMessage = document.getElementById("dashboardMessage");
const loginForm = document.getElementById("loginForm");
const registerForm = document.getElementById("registerForm");
let activeUser = null;
let doctors = [];
let appointments = [];

async function api(path, options = {}) {
    const response = await fetch(path, {
        credentials: "same-origin",
        ...options,
        headers: {
            ...(options.body ? {"Content-Type": "application/json"} : {}),
            ...options.headers
        }
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(data.error || `Request failed (${response.status}).`);
    return data;
}

function showMessage(element, message = "", kind = "") {
    element.textContent = message;
    element.className = `notice ${kind}`.trim();
}

function formData(form) {
    return Object.fromEntries(new FormData(form).entries());
}

function setAuthMode(mode) {
    const registering = mode === "register";
    loginForm.hidden = registering;
    registerForm.hidden = !registering;
    document.getElementById("loginTab").classList.toggle("active", !registering);
    document.getElementById("registerTab").classList.toggle("active", registering);
    document.getElementById("loginTab").setAttribute("aria-selected", String(!registering));
    document.getElementById("registerTab").setAttribute("aria-selected", String(registering));
    showMessage(authMessage);
}

function addCell(row, value) {
    const cell = document.createElement("td");
    cell.textContent = value ?? "";
    row.appendChild(cell);
    return cell;
}

function addEmptyRow(body, columns, message) {
    const row = body.insertRow();
    const cell = row.insertCell();
    cell.colSpan = columns;
    cell.textContent = message;
}

function localDate(value) {
    const date = new Date(value);
    return Number.isNaN(date.getTime()) ? value : date.toLocaleString();
}

function renderDoctors() {
    const container = document.getElementById("doctorCards");
    const empty = document.getElementById("doctorEmpty");
    container.replaceChildren();
    empty.hidden = doctors.length > 0;
    doctors.forEach(doctor => {
        const card = document.createElement("article");
        card.className = "doctor-card";
        const avatar = document.createElement("div");
        avatar.className = "doctor-avatar";
        avatar.textContent = doctor.name.trim().slice(0, 1).toUpperCase();
        const name = document.createElement("strong");
        name.textContent = doctor.name;
        const specialty = document.createElement("span");
        specialty.textContent = doctor.specialty || "Hospital physician";
        card.append(avatar, name, specialty);
        container.appendChild(card);
    });
    const select = document.getElementById("doctorSelect");
    select.replaceChildren(new Option("Choose a doctor", ""));
    doctors.forEach(doctor => select.add(new Option(
        `${doctor.name} — ${doctor.specialty || "Physician"}`,
        doctor.id
    )));
}

function renderAppointments() {
    const body = document.getElementById("appointmentsBody");
    const empty = document.getElementById("appointmentsEmpty");
    body.replaceChildren();
    empty.hidden = appointments.length > 0;
    if (!appointments.length) addEmptyRow(body, 6, "No appointments to show yet.");
    appointments.forEach(appointment => {
        const row = body.insertRow();
        addCell(row, appointment.patient_name);
        addCell(row, `${appointment.doctor_name}${appointment.doctor_specialty ? ` · ${appointment.doctor_specialty}` : ""}`);
        addCell(row, localDate(appointment.scheduled_at));
        addCell(row, appointment.reason);
        const statusCell = row.insertCell();
        const status = document.createElement("span");
        status.className = `status-pill status-${appointment.status}`;
        status.textContent = appointment.status;
        statusCell.appendChild(status);
        const actionCell = row.insertCell();
        if (activeUser.role === "doctor" && ["pending", "confirmed"].includes(appointment.status)) {
            const action = document.createElement("button");
            action.className = "button button-outline";
            action.type = "button";
            action.textContent = appointment.status === "pending" ? "Confirm" : "Complete";
            action.addEventListener("click", () => updateAppointment(
                appointment.id,
                appointment.status === "pending" ? "confirmed" : "completed"
            ));
            actionCell.appendChild(action);
        } else if (activeUser.role === "patient" && ["pending", "confirmed"].includes(appointment.status)) {
            const action = document.createElement("button");
            action.className = "button button-outline";
            action.type = "button";
            action.textContent = "Cancel";
            action.addEventListener("click", () => updateAppointment(appointment.id, "cancelled"));
            actionCell.appendChild(action);
        } else {
            actionCell.textContent = "—";
        }
    });

    const eligibleAppointments = appointments.filter(item =>
        activeUser.role === "doctor"
        && ["confirmed", "completed"].includes(item.status)
    );
    const select = document.getElementById("recordAppointmentSelect");
    select.replaceChildren(new Option("Choose an appointment", ""));
    eligibleAppointments.forEach(item => select.add(new Option(
        `${item.patient_name} · ${localDate(item.scheduled_at)}`,
        item.id
    )));
}

function renderRecords(records) {
    const body = document.getElementById("recordsBody");
    const empty = document.getElementById("recordsEmpty");
    body.replaceChildren();
    empty.hidden = records.length > 0;
    if (!records.length) addEmptyRow(body, 5, "No medical records to show yet.");
    records.forEach(record => {
        const row = body.insertRow();
        addCell(row, record.patient_name);
        addCell(row, record.doctor_name);
        addCell(row, localDate(record.appointment_at));
        addCell(row, record.diagnosis);
        addCell(row, record.notes || "—");
    });
}

function renderSummary(summary) {
    const section = document.getElementById("summarySection");
    section.replaceChildren();
    for (const [label, value] of Object.entries(summary)) {
        const card = document.createElement("div");
        card.className = "summary-card";
        const number = document.createElement("strong");
        number.textContent = value;
        const title = document.createElement("span");
        title.textContent = label;
        card.append(number, title);
        section.appendChild(card);
    }
    section.hidden = false;
}

async function refreshDashboard() {
    if (!activeUser) return;
    try {
        const [doctorData, appointmentData, recordData] = await Promise.all([
            api("/api/doctors"),
            api("/api/appointments"),
            api("/api/records")
        ]);
        doctors = doctorData.doctors;
        appointments = appointmentData.appointments;
        renderDoctors();
        renderAppointments();
        renderRecords(recordData.records);
        if (activeUser.role === "admin") renderSummary(await api("/api/admin/summary"));
        showMessage(dashboardMessage, "Your workspace is up to date.", "success");
    } catch (error) {
        showMessage(dashboardMessage, error.message, "error");
    }
}

function enterWorkspace(user) {
    activeUser = user;
    authSection.hidden = true;
    dashboardSection.hidden = false;
    document.getElementById("userBar").hidden = false;
    document.getElementById("welcomeText").textContent = `${user.name} · ${user.role}`;
    document.getElementById("dashboardTitle").textContent =
        user.role === "admin" ? "Hospital overview" : `${user.role[0].toUpperCase()}${user.role.slice(1)} dashboard`;
    document.getElementById("appointmentFormPanel").hidden = user.role !== "patient";
    document.getElementById("doctorFormPanel").hidden = user.role !== "admin";
    document.getElementById("recordFormPanel").hidden = user.role !== "doctor";
    document.getElementById("summarySection").hidden = user.role !== "admin";
    refreshDashboard();
    dashboardSection.scrollIntoView({behavior: "smooth", block: "start"});
}

async function updateAppointment(id, status) {
    try {
        await api(`/api/appointments/${id}`, {
            method: "PATCH",
            body: JSON.stringify({status})
        });
        await refreshDashboard();
    } catch (error) {
        showMessage(dashboardMessage, error.message, "error");
    }
}

loginForm.addEventListener("submit", async event => {
    event.preventDefault();
    showMessage(authMessage, "Signing in…");
    try {
        const result = await api("/api/auth/login", {
            method: "POST",
            body: JSON.stringify(formData(loginForm))
        });
        loginForm.reset();
        enterWorkspace(result.user);
    } catch (error) {
        showMessage(authMessage, error.message, "error");
    }
});

registerForm.addEventListener("submit", async event => {
    event.preventDefault();
    showMessage(authMessage, "Creating your patient account…");
    try {
        const result = await api("/api/auth/register", {
            method: "POST",
            body: JSON.stringify(formData(registerForm))
        });
        registerForm.reset();
        enterWorkspace(result.user);
    } catch (error) {
        showMessage(authMessage, error.message, "error");
    }
});

document.getElementById("loginTab").addEventListener("click", () => setAuthMode("login"));
document.getElementById("registerTab").addEventListener("click", () => setAuthMode("register"));
document.getElementById("logoutButton").addEventListener("click", async () => {
    try {
        await api("/api/auth/logout", {method: "POST"});
        activeUser = null;
        dashboardSection.hidden = true;
        document.getElementById("userBar").hidden = true;
        document.getElementById("summarySection").hidden = true;
        authSection.hidden = false;
        window.scrollTo({top: 0, behavior: "smooth"});
    } catch (error) {
        showMessage(dashboardMessage, error.message, "error");
    }
});
document.getElementById("refreshButton").addEventListener("click", refreshDashboard);

document.getElementById("appointmentForm").addEventListener("submit", async event => {
    event.preventDefault();
    const values = formData(event.currentTarget);
    values.scheduled_at = new Date(values.scheduled_at).toISOString();
    try {
        await api("/api/appointments", {method: "POST", body: JSON.stringify(values)});
        event.currentTarget.reset();
        showMessage(dashboardMessage, "Appointment requested.", "success");
        await refreshDashboard();
    } catch (error) {
        showMessage(dashboardMessage, error.message, "error");
    }
});

document.getElementById("doctorForm").addEventListener("submit", async event => {
    event.preventDefault();
    try {
        const result = await api("/api/doctors", {
            method: "POST",
            body: JSON.stringify(formData(event.currentTarget))
        });
        event.currentTarget.reset();
        showMessage(dashboardMessage, `Doctor account created for ${result.doctor.name}.`, "success");
        await refreshDashboard();
    } catch (error) {
        showMessage(dashboardMessage, error.message, "error");
    }
});

document.getElementById("recordForm").addEventListener("submit", async event => {
    event.preventDefault();
    try {
        await api("/api/records", {
            method: "POST",
            body: JSON.stringify(formData(event.currentTarget))
        });
        event.currentTarget.reset();
        showMessage(dashboardMessage, "Medical record saved.", "success");
        await refreshDashboard();
    } catch (error) {
        showMessage(dashboardMessage, error.message, "error");
    }
});

async function initialize() {
    try {
        const [sessionData, doctorData] = await Promise.all([
            api("/api/auth/me"),
            api("/api/doctors")
        ]);
        doctors = doctorData.doctors;
        renderDoctors();
        if (sessionData.user) enterWorkspace(sessionData.user);
    } catch (error) {
        showMessage(authMessage, `Unable to connect to the application: ${error.message}`, "error");
    }
}

initialize();
