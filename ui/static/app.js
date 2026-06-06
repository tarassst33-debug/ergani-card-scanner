const SHIFT_DAY_LABELS = ["Δευ", "Τρί", "Τετ", "Πέμ", "Παρ", "Σάβ", "Κυρ"];
let shiftGridPersistTimer = null;
let shiftGridLoadedForCompany = null;

const ERGANI_PANELS = [
  "employer",
  "branches",
  "personnel",
  "card-punches",
  "workcard",
  "overtime",
  "daily",
  "weekly",
  "services",
];

const state = {
  appUser: null,
  appRole: null,
  companyName: null,
  currentCompanyId: null,
  companies: [],
  connected: false,
  employer: null,
  branches: [],
  personnel: [],
  shiftGrid: null,
  adminCompanies: [],
  adminUsers: [],
  companySwitching: false,
};

let shiftEditContext = null;

const $ = (sel) => document.querySelector(sel);
const $$ = (sel) => document.querySelectorAll(sel);

function showStatus(message, kind = "info") {
  const bar = $("#global-status");
  bar.textContent = message;
  bar.className = `status-bar ${kind}`;
  bar.classList.remove("hidden");
}

function hideStatus() {
  $("#global-status").classList.add("hidden");
}

function showGateStatus(message, kind = "info") {
  const el = $("#gate-status");
  if (!el) return;
  el.textContent = message;
  el.className = `gate-status ${kind}`;
  el.classList.remove("hidden");
}

function hideGateStatus() {
  $("#gate-status")?.classList.add("hidden");
}

function showKiosk() {
  document.body.classList.add("kiosk-only");
  $("#app-gate")?.classList.add("hidden");
  $("#app-layout")?.classList.add("hidden");
  hideGateStatus();
  hideStatus();
  $("#app-kiosk")?.classList.add("hidden");
  window.KioskMode?.stop?.();
  window.KioskMode?.showSetup?.();
}

function hideKiosk() {
  $("#app-kiosk")?.classList.add("hidden");
  window.KioskMode?.hideSetup?.();
  window.KioskMode?.stop();
}

function openAdminLogin() {
  document.body.classList.remove("kiosk-only");
  hideKiosk();
  showGate("login");
  showGateStatus("Σύνδεση διαχείρισης (admin).", "info");
}

window.openAdminLogin = openAdminLogin;

function showGate(step) {
  document.body.classList.remove("kiosk-only");
  hideKiosk();
  $("#app-gate")?.classList.remove("hidden");
  $("#app-layout")?.classList.add("hidden");
  $("#gate-login-form")?.classList.toggle("hidden", step !== "login");
  $("#gate-step-company")?.classList.toggle("hidden", step !== "company");
  hideGateStatus();
  if (step === "login") {
    const passInput = $("#app-password");
    if (passInput) passInput.value = "";
    $("#app-username")?.focus();
  } else if (step === "company") {
    $("#company-select")?.focus();
  }
}

function showAppLayout() {
  document.body.classList.remove("kiosk-only");
  hideKiosk();
  $("#app-gate")?.classList.add("hidden");
  $("#app-layout")?.classList.remove("hidden");
  hideGateStatus();
}

function showResults(containerId, data) {
  const el = $(containerId);
  el.innerHTML = `<pre>${JSON.stringify(data, null, 2)}</pre>`;
  el.classList.remove("hidden");
}

async function api(path, options = {}) {
  const res = await fetch(path, {
    headers: { "Content-Type": "application/json", ...options.headers },
    credentials: "same-origin",
    ...options,
  });
  const body = await res.json().catch(() => ({}));
  if (!res.ok) {
    let msg = body.error || body.warning;
    if (typeof msg !== "string" || !msg.trim() || /^Error message:\s*$/i.test(msg)) {
      if (res.status === 401) {
        msg = "Λάθος χρήστης ή κωδικός Ergani (401).";
      } else if (res.status === 404) {
        msg =
          "404 — έλεγξε Base URL εταιρείας (π.χ. https://eservices.yeka.gr/WebservicesAPI/Api).";
      } else {
        msg = `Σφάλμα ${res.status}`;
      }
    }
    const err = new Error(msg);
    if (res.status === 422 && Array.isArray(body.punches)) {
      err.punchesPayload = body;
    }
    throw err;
  }
  return body;
}

function setConnected(on) {
  state.connected = on;
  const badge = $("#conn-badge");
  badge.textContent = on ? "Συνδεδεμένος Ergani" : "Χωρίς Ergani";
  badge.classList.toggle("on", on);
  updateNavState();
}

function updateNavState() {
  const connected = state.connected;
  $$("#nav button").forEach((btn) => {
    const panel = btn.dataset.panel;
    if (panel === "admin") {
      btn.classList.toggle("hidden", state.appRole !== "admin");
      btn.disabled = !state.appUser;
    } else if (ERGANI_PANELS.includes(panel)) {
      btn.disabled = !connected;
    }
  });
  const userLabel = $("#app-user-label");
  const backKioskBtn = $("#btn-back-kiosk");
  if (backKioskBtn) backKioskBtn.classList.toggle("hidden", !connected);
  const logoutBtn = $("#btn-app-logout");
  if (userLabel) {
    userLabel.classList.toggle("hidden", !state.appUser);
    if (state.appUser) {
      userLabel.textContent = state.companyName
        ? `${state.appUser} · ${state.companyName}`
        : state.appUser;
    }
  }
  logoutBtn?.classList.toggle("hidden", !state.appUser);
  $("#sidebar-company-block")?.classList.toggle("hidden", !state.appUser);
}

async function applyErganiSession(data) {
  state.employer = data.employer || null;
  setConnected(true);
  if (data.employer) renderEmployer(data.employer);
  await loadBranches();
}

function fillCompanySelectElement(sel, companies, selectedId = null) {
  if (!sel) return;
  const opts = ['<option value="">— Επιλογή εταιρείας —</option>'];
  for (const c of companies) {
    const selected = selectedId != null && Number(c.id) === Number(selectedId);
    opts.push(
      `<option value="${c.id}"${selected ? " selected" : ""}>${escapeHtml(c.name)}</option>`
    );
  }
  sel.innerHTML = opts.join("");
}

function fillCompanySelect(companies, selectedId = null) {
  state.companies = companies;
  fillCompanySelectElement($("#company-select"), companies, selectedId);
  fillCompanySelectElement($("#sidebar-company-select"), companies, selectedId);
  const gateBtn = $("#btn-gate-company");
  if (gateBtn) gateBtn.disabled = !companies.length;
  $("#btn-gate-admin-only")?.classList.toggle(
    "hidden",
    state.appRole !== "admin"
  );
}

function setGateCompanyLoading(on) {
  const btn = $("#btn-gate-company");
  if (btn) {
    btn.disabled = on;
    btn.textContent = on ? "Σύνδεση…" : "Σύνδεση στην εταιρεία";
  }
}

async function loadCompaniesForSession() {
  const { companies } = await api("/api/auth/companies");
  fillCompanySelect(companies, state.currentCompanyId);
  return companies;
}

async function selectCompany(companyId, options = {}) {
  const { stayOnGate = false, silent = false } = options;
  if (!companyId || state.companySwitching) return;
  if (Number(state.currentCompanyId) === Number(companyId) && state.connected) return;

  state.companySwitching = true;
  if (stayOnGate) setGateCompanyLoading(true);
  if (!silent) hideStatus();

  try {
    const data = await api("/api/auth/select-company", {
      method: "POST",
      body: JSON.stringify({ company_id: companyId }),
    });
    state.currentCompanyId = companyId;
    state.companyName = data.company?.name || null;
    fillCompanySelect(state.companies, companyId);
    await applyErganiSession(data);
    shiftGridLoadedForCompany = null;
    state.shiftGrid = null;
    await loadShiftGridFromFirestore();
    showAppLayout();
    if (!silent) {
      showStatus(`Συνδέθηκες στην ${state.companyName || "εταιρεία"}.`, "ok");
    }
    void switchPanel("branches");
  } catch (err) {
    if (stayOnGate) showGateStatus(err.message, "err");
    else showStatus(err.message, "err");
  } finally {
    state.companySwitching = false;
    if (stayOnGate) setGateCompanyLoading(false);
    updateNavState();
  }
}

function enterAdminPanelOnly() {
  showAppLayout();
  hideGateStatus();
  setConnected(false);
  void switchPanel("admin");
}

async function refreshAuth() {
  let auth;
  try {
    auth = await api("/api/auth/status");
  } catch {
    state.appUser = null;
    state.appRole = null;
    state.companyName = null;
    setConnected(false);
    updateNavState();
    showKiosk();
    return;
  }

  state.appUser = auth.app_user;
  state.appRole = auth.app_role;
  state.companyName = auth.company?.name || null;
  state.currentCompanyId = auth.company?.id ?? null;
  updateNavState();

  if (!auth.app_user) {
    setConnected(false);
    showKiosk();
    return;
  }

  if (auth.ergani_connected && auth.company?.id) {
    try {
      const sess = await api("/api/session");
      if (sess.connected) {
        const companies = await loadCompaniesForSession();
        const employerData = await api("/api/employer");
        await applyErganiSession({ employer: employerData.employer });
        showAppLayout();
        void switchPanel("branches");
        return;
      }
    } catch {
      try {
        await api("/api/session", { method: "DELETE" });
      } catch {
        /* ignore */
      }
    }
  }

  setConnected(false);
  try {
    const { companies } = await api("/api/auth/companies");
    if (!companies.length) {
      showGate("company");
      fillCompanySelect([]);
      if (state.appRole === "admin") {
        showGateStatus("Πρόσθεσε εταιρεία από τη Διαχείριση.", "info");
      } else {
        showGateStatus(
          "Δεν έχεις ανατεθεί εταιρεία. Επικοινώνησε με τον admin.",
          "err"
        );
      }
      return;
    }
    fillCompanySelect(companies);
    showGate("company");
  } catch (err) {
    showGate("login");
    showGateStatus(err.message, "err");
  }
}

async function loadAdminData() {
  const [companiesRes, usersRes] = await Promise.all([
    api("/api/admin/companies"),
    api("/api/admin/users"),
  ]);
  state.adminCompanies = companiesRes.companies || [];
  state.adminUsers = usersRes.users || [];
  renderAdminCompaniesTable();
  renderAdminUsersTable();
  renderAdminCompanyChecks();
}

function renderAdminCompanyChecks(selectedIds = []) {
  const wrap = $("#au-company-checks");
  if (!wrap) return;
  const selected = new Set(selectedIds.map(String));
  wrap.innerHTML = state.adminCompanies
    .map(
      (c) => `<label>
        <input type="checkbox" value="${c.id}" ${selected.has(String(c.id)) ? "checked" : ""} />
        ${escapeHtml(c.name)}
      </label>`
    )
    .join("");
}

function renderAdminCompaniesTable() {
  const wrap = $("#admin-companies-table-wrap");
  if (!wrap) return;
  wrap.innerHTML = `<table class="data"><thead><tr>
    <th>ID</th><th>Όνομα</th><th>Ergani user</th><th></th>
  </tr></thead><tbody>
    ${state.adminCompanies
      .map(
        (c) => `<tr>
          <td>${c.id}</td>
          <td>${escapeHtml(c.name)}</td>
          <td>${escapeHtml(c.ergani_username)}</td>
          <td><button type="button" class="btn btn-secondary btn-edit-company" data-id="${c.id}">Επεξεργασία</button></td>
        </tr>`
      )
      .join("")}
  </tbody></table>`;
  wrap.querySelectorAll(".btn-edit-company").forEach((btn) => {
    btn.addEventListener("click", () => {
      const company = state.adminCompanies.find(
        (c) => c.id === parseInt(btn.dataset.id, 10)
      );
      if (!company) return;
      $("#ac-id").value = company.id;
      $("#ac-name").value = company.name;
      $("#ac-ergani-user").value = company.ergani_username;
      $("#ac-ergani-pass").value = "";
      $("#ac-user-type").value = company.user_type;
      $("#ac-base-url").value = company.base_url;
    });
  });
}

function renderAdminUsersTable() {
  const wrap = $("#admin-users-table-wrap");
  if (!wrap) return;
  wrap.innerHTML = `<table class="data"><thead><tr>
    <th>Χρήστης</th><th>Ρόλος</th><th>Ενεργός</th><th></th>
  </tr></thead><tbody>
    ${state.adminUsers
      .map(
        (u) => `<tr>
          <td>${escapeHtml(u.username)}</td>
          <td>${u.role}</td>
          <td>${u.active ? "Ναι" : "Όχι"}</td>
          <td><button type="button" class="btn btn-secondary btn-edit-user" data-id="${u.id}">Επεξεργασία</button></td>
        </tr>`
      )
      .join("")}
  </tbody></table>`;
  wrap.querySelectorAll(".btn-edit-user").forEach((btn) => {
    btn.addEventListener("click", () => {
      const user = state.adminUsers.find((u) => u.id === parseInt(btn.dataset.id, 10));
      if (!user) return;
      $("#au-id").value = user.id;
      $("#au-username").value = user.username;
      $("#au-password").value = "";
      $("#au-role").value = user.role;
      $("#au-active").value = user.active ? "1" : "0";
      renderAdminCompanyChecks(user.company_ids || []);
    });
  });
}

async function switchPanel(name) {
  $$(".panel").forEach((p) => p.classList.remove("active"));
  $(`#panel-${name}`).classList.add("active");
  $$("#nav button").forEach((b) => {
    b.classList.toggle("active", b.dataset.panel === name);
  });
  if (
    (name === "personnel" || name === "card-punches" || name === "workcard") &&
    state.connected &&
    !state.branches.length
  ) {
    try {
      await loadBranches();
    } catch {
      /* shown on manual load */
    }
  }
  if (name === "personnel" && state.connected) {
    void loadStoredPersonnel();
  }
  if (name === "card-punches" && state.connected) {
    initPunchDateFilters();
    void loadStoredPunches();
    void loadPunchServiceHints();
  }
  if (name === "workcard") {
    setWorkcardFabVisible(true);
    void initWorkcardPanel();
  } else {
    setWorkcardFabVisible(false);
    closeManualPunchSheet();
  }
  if (name === "admin" && state.appRole === "admin") {
    void loadAdminData();
  }
}

function todayDate() {
  return new Date().toISOString().slice(0, 10);
}

function normalizeTime24(raw) {
  let s = String(raw || "").trim();
  if (!s) return null;
  s = s.replace(/[¨·.,]/g, ":");
  s = s.replace(/\s*(πμ|μμ|am|pm)\s*/gi, "").trim();
  const match = s.match(/^(\d{1,2}):(\d{2})$/);
  if (!match) return null;
  const hours = parseInt(match[1], 10);
  const minutes = parseInt(match[2], 10);
  if (hours < 0 || hours > 23 || minutes < 0 || minutes > 59) return null;
  return `${String(hours).padStart(2, "0")}:${String(minutes).padStart(2, "0")}`;
}

function parseTime24Input(raw, label) {
  const normalized = normalizeTime24(raw);
  if (!normalized) {
    throw new Error(
      `Μη έγκυρη ώρα ${label}. Χρησιμοποίησε 24ωρη μορφή (π.χ. 09:00 ή 13:00).`
    );
  }
  return normalized;
}

function movementDatetimeIso(dateStr, timeStr) {
  if (!dateStr || !timeStr) {
    throw new Error("Συμπλήρωσε ημερομηνία και ώρα κίνησης.");
  }
  const normalized = parseTime24Input(timeStr, "κίνησης");
  const [h, m] = normalized.split(":");
  return `${dateStr}T${h}:${m}:00`;
}

async function postWorkCardPayload(payload, meta) {
  try {
    const data = await api("/api/work-card", {
      method: "POST",
      body: JSON.stringify(payload),
    });
    if (meta.resultsId) showResults(meta.resultsId, data);
    const protocol = data.submissions?.[0]?.protocol ?? "—";
    const labels = {
      ARRIVAL: "Προσέλευση",
      DEPARTURE: "Αποχώρηση",
      BOTH: "Πρόγραμμα (προσέλευση + αποχώρηση)",
    };
    const label = labels[meta.mode] || "Υποβολή";
    const n = meta.employeeCount ?? payload.entries.length;
    showStatus(
      `${label}: ${n} εργαζόμενοι, ${payload.entries.length} κινήσεις. Πρωτόκολλο: ${protocol}`,
      "ok"
    );
    return data;
  } catch (err) {
    showStatus(err.message, "err");
    throw err;
  }
}

function fillBranchSelects(branches) {
  const selects = [
    "#wc-branch",
    "#punches-branch",
    "#ot-branch",
    "#ds-branch",
    "#ws-branch",
  ];
  for (const sel of selects) {
    const el = $(sel);
    if (!el) continue;
    const prev = el.value;
    const keepAll = sel === "#punches-branch";
    el.innerHTML = keepAll ? '<option value="">Όλα</option>' : "";
    for (const b of branches) {
      const opt = document.createElement("option");
      const labelAddr = b.address || "—";
      opt.value = b.branch_number;
      opt.textContent =
        sel === "#wc-branch"
          ? String(b.branch_number)
          : `#${b.branch_number} — ${labelAddr}`;
      opt.dataset.sepe = b.sepe_service_code || "";
      opt.dataset.kad = b.business_branch_activity_code || "";
      opt.dataset.kallikratis = b.kallikratis_municipal_code || "";
      el.appendChild(opt);
    }
    if (prev !== "" && [...el.options].some((o) => o.value === prev)) {
      el.value = prev;
    }
  }
}

function mondayOfWeek(dateInput) {
  const d = new Date(`${dateInput}T12:00:00`);
  const day = d.getDay();
  const diff = day === 0 ? -6 : 1 - day;
  d.setDate(d.getDate() + diff);
  return d.toISOString().slice(0, 10);
}

function addDaysIso(isoDate, days) {
  const d = new Date(`${isoDate}T12:00:00`);
  d.setDate(d.getDate() + days);
  return d.toISOString().slice(0, 10);
}

function formatDayHeader(isoDate) {
  const d = new Date(`${isoDate}T12:00:00`);
  const dd = String(d.getDate()).padStart(2, "0");
  const mm = String(d.getMonth() + 1).padStart(2, "0");
  return `${dd}/${mm}`;
}

function defaultWeekShifts() {
  return Array.from({ length: 7 }, () => ({
    empty: true,
    off: false,
    arrival: "09:00",
    departure: "17:00",
  }));
}

function normalizeShift(shift) {
  if (!shift) {
    return { empty: true, off: false, arrival: "09:00", departure: "17:00" };
  }
  if (shift.empty === undefined) {
    return { ...shift, empty: false };
  }
  return shift;
}

function isShiftWork(shift) {
  const s = normalizeShift(shift);
  return !s.empty && !s.off;
}

function countWorkShiftsForDay(dayIndex) {
  ensureShiftGrid();
  return state.shiftGrid.employees.filter((emp) => {
    const shifts = emp.shifts || defaultWeekShifts();
    return isShiftWork(shifts[dayIndex]);
  }).length;
}

function defaultShiftGrid() {
  return {
    weekStart: mondayOfWeek(todayDate()),
    employees: [],
  };
}

function ensureShiftGrid() {
  if (!state.shiftGrid) {
    state.shiftGrid = defaultShiftGrid();
  }
  if (!state.shiftGrid.weekStart) {
    state.shiftGrid.weekStart = mondayOfWeek(todayDate());
  }
  const weekInput = $("#wc-week-start");
  if (weekInput && weekInput.value !== state.shiftGrid.weekStart) {
    weekInput.value = state.shiftGrid.weekStart;
  }
}

async function loadShiftGridFromFirestore() {
  if (!state.currentCompanyId || !state.connected) {
    state.shiftGrid = defaultShiftGrid();
    shiftGridLoadedForCompany = null;
    return;
  }
  if (shiftGridLoadedForCompany === state.currentCompanyId && state.shiftGrid) {
    return;
  }
  try {
    const data = await api("/api/shift-grid");
    state.shiftGrid =
      data.grid && typeof data.grid === "object" ? data.grid : defaultShiftGrid();
    if (!state.shiftGrid.weekStart) {
      state.shiftGrid.weekStart = mondayOfWeek(todayDate());
    }
    shiftGridLoadedForCompany = state.currentCompanyId;
  } catch {
    state.shiftGrid = defaultShiftGrid();
    shiftGridLoadedForCompany = state.currentCompanyId;
  }
  const weekInput = $("#wc-week-start");
  if (weekInput) weekInput.value = state.shiftGrid.weekStart;
}

function persistShiftGrid() {
  if (!state.shiftGrid || !state.connected || !state.currentCompanyId) return;
  clearTimeout(shiftGridPersistTimer);
  shiftGridPersistTimer = setTimeout(async () => {
    try {
      await api("/api/shift-grid", {
        method: "PUT",
        body: JSON.stringify({ grid: state.shiftGrid }),
      });
    } catch (err) {
      showStatus(`Αποθήκευση προγράμματος: ${err.message}`, "err");
    }
  }, 450);
}

function weekDatesFromStart(weekStart) {
  return Array.from({ length: 7 }, (_, i) => addDaysIso(weekStart, i));
}

function shiftCellLabel(shift) {
  const s = normalizeShift(shift);
  if (s.empty) return "—";
  if (s.off) return "ΡΕΠΟ";
  return `${s.arrival} – ${s.departure}`;
}

function renderShiftCell(shift, empIndex, dayIndex) {
  const s = normalizeShift(shift);
  const cls = s.empty ? "is-empty" : s.off ? "is-repo" : "is-work";
  const text = shiftCellLabel(s);
  return `<td>
    <button type="button" class="shiftgrid-cell ${cls}" data-emp="${empIndex}" data-day="${dayIndex}">${escapeHtml(text)}</button>
  </td>`;
}

function closeShiftPopover() {
  shiftEditContext = null;
  $("#shift-cell-popover")?.classList.add("hidden");
}

function positionShiftPopover(anchor) {
  const pop = $("#shift-cell-popover");
  if (!pop || !anchor) return;
  const rect = anchor.getBoundingClientRect();
  const margin = 8;
  pop.classList.remove("hidden");
  const popRect = pop.getBoundingClientRect();
  let top = rect.bottom + margin;
  let left = rect.left;
  if (top + popRect.height > window.innerHeight - margin) {
    top = Math.max(margin, rect.top - popRect.height - margin);
  }
  if (left + popRect.width > window.innerWidth - margin) {
    left = Math.max(margin, window.innerWidth - popRect.width - margin);
  }
  pop.style.top = `${top}px`;
  pop.style.left = `${left}px`;
}

function openShiftPopover(empIndex, dayIndex, anchor) {
  ensureShiftGrid();
  const emp = state.shiftGrid.employees[empIndex];
  if (!emp) return;
  if (!emp.shifts || emp.shifts.length !== 7) emp.shifts = defaultWeekShifts();
  const shift = normalizeShift(emp.shifts[dayIndex]);
  const dates = weekDatesFromStart(state.shiftGrid.weekStart);
  shiftEditContext = { empIndex, dayIndex };
  const name = `${emp.last_name || ""} ${emp.first_name || ""}`.trim() || emp.afm;
  $("#shift-popover-title").textContent = `${name} — ${SHIFT_DAY_LABELS[dayIndex]} ${formatDayHeader(dates[dayIndex])}`;
  $("#shift-popover-off").checked = !!shift.off;
  $("#shift-popover-arrival").value = shift.empty && !shift.off ? "09:00" : shift.arrival || "09:00";
  $("#shift-popover-departure").value =
    shift.empty && !shift.off ? "17:00" : shift.departure || "17:00";
  const off = !!shift.off;
  $("#shift-popover-arrival").disabled = off;
  $("#shift-popover-departure").disabled = off;
  positionShiftPopover(anchor);
  if (!off) $("#shift-popover-arrival")?.focus();
}

function saveShiftPopover(clearCell) {
  if (!shiftEditContext) return;
  const { empIndex, dayIndex } = shiftEditContext;
  const emp = state.shiftGrid.employees[empIndex];
  if (!emp) return;
  if (!emp.shifts || emp.shifts.length !== 7) emp.shifts = defaultWeekShifts();
  if (clearCell) {
    emp.shifts[dayIndex] = defaultWeekShifts()[dayIndex];
  } else {
    const off = $("#shift-popover-off").checked;
    let arrival = "09:00";
    let departure = "17:00";
    if (!off) {
      try {
        arrival = parseTime24Input($("#shift-popover-arrival").value, "προσέλευσης");
        departure = parseTime24Input(
          $("#shift-popover-departure").value,
          "αποχώρησης"
        );
      } catch (err) {
        showStatus(err.message, "err");
        return;
      }
    }
    emp.shifts[dayIndex] = {
      empty: false,
      off,
      arrival,
      departure,
    };
  }
  persistShiftGrid();
  closeShiftPopover();
  renderShiftGrid();
  renderTodayStaffList();
}

function upsertShiftEmployee(emp) {
  ensureShiftGrid();
  const afm = (emp.afm || emp.tax_identification_number || "").trim();
  const first = (emp.first_name || "").trim();
  const last = (emp.last_name || "").trim();
  if (!afm) return false;
  let row = state.shiftGrid.employees.find((e) => e.afm === afm);
  if (!row) {
    row = { afm, first_name: first, last_name: last, shifts: defaultWeekShifts() };
    state.shiftGrid.employees.push(row);
  } else {
    row.first_name = first || row.first_name;
    row.last_name = last || row.last_name;
  }
  return true;
}

function renderShiftGrid() {
  closeShiftPopover();
  ensureShiftGrid();
  const head = $("#shiftgrid-head");
  const body = $("#shiftgrid-body");
  if (!head || !body) return;

  const dates = weekDatesFromStart(state.shiftGrid.weekStart);
  head.innerHTML = `<tr>
    <th class="shiftgrid-col-name">Εργαζόμενος</th>
    ${dates
      .map((iso, dayIndex) => {
        const label = SHIFT_DAY_LABELS[dayIndex];
        const dh = formatDayHeader(iso);
        return `<th class="shiftgrid-col-day">
          <span class="shiftgrid-day-title">${label}</span>
          <span class="shiftgrid-day-date">${dh}</span>
          <div class="shift-day-actions">
            <button type="button" class="shift-day-btn arrival" data-day="${dayIndex}" data-mode="ARRIVAL" title="Προσέλευση">Πρ.</button>
            <button type="button" class="shift-day-btn departure" data-day="${dayIndex}" data-mode="DEPARTURE" title="Αποχώρηση">Απ.</button>
            <button type="button" class="shift-day-btn both" data-day="${dayIndex}" data-mode="BOTH" title="Προσέλευση + αποχώρηση">Και τα 2</button>
          </div>
        </th>`;
      })
      .join("")}
  </tr>`;

  if (!state.shiftGrid.employees.length) {
    body.innerHTML = `<tr><td colspan="8" class="shiftgrid-empty">
      Φόρτωσε προσωπικό ή πρόσθεσε εργαζόμενους για να εμφανιστεί ο πίνακας.
    </td></tr>`;
    return;
  }

  body.innerHTML = state.shiftGrid.employees
    .map((emp, empIndex) => {
      const name = `${emp.last_name || ""} ${emp.first_name || ""}`.trim() || "—";
      const cells = (emp.shifts || defaultWeekShifts())
        .map((shift, dayIndex) => renderShiftCell(shift, empIndex, dayIndex))
        .join("");
      return `<tr>
        <td class="shiftgrid-name-cell">
          <div class="shiftgrid-name">${escapeHtml(name)}</div>
          <div class="shiftgrid-afm">${escapeHtml(emp.afm)}</div>
          <button type="button" class="shiftgrid-remove btn btn-danger" data-emp="${empIndex}" title="Αφαίρεση">×</button>
        </td>
        ${cells}
      </tr>`;
    })
    .join("");
  renderTodayStaffList();
}

function todayDayIndexInGrid() {
  ensureShiftGrid();
  return weekDatesFromStart(state.shiftGrid.weekStart).indexOf(todayDate());
}

function renderTodayStaffList() {
  const el = $("#wc-today-list");
  if (!el) return;
  ensureShiftGrid();
  const dayIndex = todayDayIndexInGrid();
  const todayLabel = formatDisplayDate(todayDate());

  if (dayIndex < 0) {
    el.innerHTML = `<p class="hint">Η σημερινή ημερομηνία (${escapeHtml(todayLabel)}) δεν είναι στην εμφανιζόμενη εβδομάδα. Άλλαξε την εβδομάδα (Δευτέρα) ή χρησιμοποίησε το <strong>+</strong> κάτω δεξιά.</p>`;
    return;
  }

  if (!state.shiftGrid.employees.length) {
    el.innerHTML =
      '<p class="hint">Δεν υπάρχει προσωπικό. Πάτα «Φόρτωση από Προσωπικό» ή το κουμπί <strong>+</strong> κάτω δεξιά.</p>';
    return;
  }

  el.innerHTML = `<div class="wc-today-cards">${state.shiftGrid.employees
    .map((emp, empIndex) => {
      const shift = normalizeShift((emp.shifts || defaultWeekShifts())[dayIndex]);
      const name = `${emp.last_name || ""} ${emp.first_name || ""}`.trim() || emp.afm;
      const time = shiftCellLabel(shift);
      const cls = shift.empty ? "is-empty" : shift.off ? "is-repo" : "is-work";
      return `<article class="wc-today-card ${cls}">
        <div class="wc-today-card-name">${escapeHtml(name)}</div>
        <div class="wc-today-card-time">${escapeHtml(time)}</div>
        <div class="wc-today-card-actions">
          <button type="button" class="btn btn-sm btn-primary wc-today-punch" data-emp="${empIndex}" data-mode="ARRIVAL">Check-in</button>
          <button type="button" class="btn btn-sm btn-secondary wc-today-punch" data-emp="${empIndex}" data-mode="DEPARTURE">Check-out</button>
        </div>
      </article>`;
    })
    .join("")}</div>`;
}

function setWorkcardFabVisible(on) {
  $("#wc-manual-fab")?.classList.toggle("hidden", !on);
}

function closeManualPunchSheet() {
  const sheet = $("#wc-manual-sheet");
  if (!sheet) return;
  sheet.classList.add("hidden");
  sheet.setAttribute("aria-hidden", "true");
}

async function ensurePersonnelLoaded() {
  if (state.personnel.length) return state.personnel;
  if (!state.connected) return [];
  try {
    const data = await api("/api/employees/stored");
    renderPersonnel(data.employees || [], data.synced_at);
  } catch {
    /* ignore */
  }
  return state.personnel;
}

function renderManualPersonnelList() {
  const list = $("#wc-manual-list");
  if (!list) return;
  const people = state.personnel.length
    ? state.personnel
    : (state.shiftGrid?.employees || []).map((e) => ({
        tax_identification_number: e.afm,
        afm: e.afm,
        first_name: e.first_name,
        last_name: e.last_name,
      }));
  if (!people.length) {
    list.innerHTML =
      '<p class="hint" style="padding:0.75rem">Δεν υπάρχει προσωπικό. Σύνδεση Ergani από το μενού «Προσωπικό».</p>';
    return;
  }
  list.innerHTML = people
    .map((e, idx) => {
      const afm = (e.tax_identification_number || e.afm || "").trim();
      const first = (e.first_name || "").trim();
      const last = (e.last_name || "").trim();
      const name = `${last} ${first}`.trim() || afm || "—";
      return `<label class="wc-manual-row">
        <input type="checkbox" class="wc-manual-check" data-idx="${idx}" data-afm="${escapeHtml(afm)}" data-first="${escapeHtml(first)}" data-last="${escapeHtml(last)}" />
        <span>${escapeHtml(name)}</span>
        <small>${escapeHtml(afm)}</small>
      </label>`;
    })
    .join("");
}

async function openManualPunchSheet() {
  await ensurePersonnelLoaded();
  if (!state.shiftGrid?.employees?.length && state.personnel.length) {
    importPersonnelToShiftGrid(state.personnel);
  }
  const dateEl = $("#wc-manual-date");
  if (dateEl && !dateEl.value) dateEl.value = todayDate();
  renderManualPersonnelList();
  const sheet = $("#wc-manual-sheet");
  sheet?.classList.remove("hidden");
  sheet?.setAttribute("aria-hidden", "false");
}

function getSelectedManualEmployees() {
  const rows = [];
  $$(".wc-manual-check:checked").forEach((cb) => {
    rows.push({
      afm: cb.dataset.afm || "",
      first_name: cb.dataset.first || "",
      last_name: cb.dataset.last || "",
    });
  });
  return rows.filter((r) => r.afm);
}

async function submitManualPunch(mode) {
  hideStatus();
  const employerAfm = $("#wc-employer-afm")?.value.trim();
  if (!employerAfm) {
    showStatus("Συμπλήρωσε Α.Φ.Μ. εργοδότη.", "err");
    return;
  }
  const date = $("#wc-manual-date")?.value || todayDate();
  const selected = getSelectedManualEmployees();
  if (!selected.length) {
    showStatus("Επίλεξε τουλάχιστον ένα άτομο.", "err");
    return;
  }
  let timeRaw;
  try {
    timeRaw =
      mode === "ARRIVAL"
        ? parseTime24Input($("#wc-manual-arrival")?.value, "Check-in")
        : parseTime24Input($("#wc-manual-departure")?.value, "Check-out");
  } catch (err) {
    showStatus(err.message, "err");
    return;
  }
  const label = mode === "ARRIVAL" ? "Check-in" : "Check-out";
  const ok = window.confirm(
    `Αποστολή ${label} στο Ergani;\n\n${selected.length} εργαζόμενοι\nΗμερομηνία: ${formatDisplayDate(date)}\nΏρα: ${timeRaw}`
  );
  if (!ok) return;

  const late = $("#wc-late")?.value || null;
  const entries = selected.map((emp) => ({
    employee_afm: emp.afm,
    first_name: emp.first_name,
    last_name: emp.last_name,
    movement_type: mode,
    submission_date: date,
    movement_datetime: movementDatetimeIso(date, timeRaw),
    late_justification: late,
  }));

  await postWorkCardPayload(
    {
      employer_afm: employerAfm,
      branch_number: parseInt($("#wc-branch")?.value, 10),
      comments: $("#wc-comments")?.value || "",
      entries,
    },
    {
      resultsId: "#workcard-results",
      mode,
      employeeCount: selected.length,
    }
  );
  closeManualPunchSheet();
  renderTodayStaffList();
}

async function punchEmployeeToday(empIndex, mode) {
  hideStatus();
  const dayIndex = todayDayIndexInGrid();
  if (dayIndex < 0) {
    showStatus("Η σημερινή ημέρα δεν είναι στον πίνακα εβδομάδας.", "err");
    return;
  }
  ensureShiftGrid();
  const emp = state.shiftGrid.employees[empIndex];
  if (!emp) return;
  const shift = normalizeShift((emp.shifts || defaultWeekShifts())[dayIndex]);
  if (!isShiftWork(shift)) {
    showStatus("Ορίσε ώρες στο κελί της σημερινής ημέρας (κλικ στον πίνακα).", "err");
    return;
  }
  const employerAfm = $("#wc-employer-afm")?.value.trim();
  if (!employerAfm) {
    showStatus("Συμπλήρωσε Α.Φ.Μ. εργοδότη.", "err");
    return;
  }
  const date = weekDatesFromStart(state.shiftGrid.weekStart)[dayIndex];
  const time = mode === "ARRIVAL" ? shift.arrival : shift.departure;
  const label = mode === "ARRIVAL" ? "Check-in" : "Check-out";
  const name = `${emp.last_name || ""} ${emp.first_name || ""}`.trim() || emp.afm;
  const ok = window.confirm(
    `${label} στο Ergani;\n\n${name}\n${formatDisplayDate(date)} ${time}`
  );
  if (!ok) return;

  const late = $("#wc-late")?.value || null;
  await postWorkCardPayload(
    {
      employer_afm: employerAfm,
      branch_number: parseInt($("#wc-branch")?.value, 10),
      comments: $("#wc-comments")?.value || "",
      entries: [
        {
          employee_afm: emp.afm,
          first_name: emp.first_name,
          last_name: emp.last_name,
          movement_type: mode,
          submission_date: date,
          movement_datetime: movementDatetimeIso(date, time),
          late_justification: late,
        },
      ],
    },
    { resultsId: "#workcard-results", mode, employeeCount: 1 }
  );
  renderTodayStaffList();
}

async function initWorkcardPanel() {
  if (state.connected) {
    await loadStoredPersonnel();
  }
  await loadShiftGridFromFirestore();
  ensureShiftGrid();
  if (!state.shiftGrid.employees.length && state.personnel.length) {
    importPersonnelToShiftGrid(state.personnel);
    showStatus(
      `Φορτώθηκαν ${state.shiftGrid.employees.length} εργαζόμενοι στο πρόγραμμα.`,
      "ok"
    );
  } else {
    renderShiftGrid();
  }
  const manualDate = $("#wc-manual-date");
  if (manualDate && !manualDate.value) manualDate.value = todayDate();
  if (!$("#wc-manual-arrival")?.value) $("#wc-manual-arrival").value = "09:00";
  if (!$("#wc-manual-departure")?.value) $("#wc-manual-departure").value = "17:00";
}

function escapeHtml(value) {
  return String(value)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
}

function importPersonnelToShiftGrid(employees) {
  let added = 0;
  for (const e of employees) {
    if (
      upsertShiftEmployee({
        afm: e.tax_identification_number || e.afm,
        first_name: e.first_name,
        last_name: e.last_name,
      })
    ) {
      added += 1;
    }
  }
  persistShiftGrid();
  renderShiftGrid();
  renderTodayStaffList();
  return added;
}

async function submitShiftGridDay(dayIndex, mode) {
  hideStatus();
  ensureShiftGrid();
  if (!state.shiftGrid.employees.length) {
    showStatus("Πρόσθεσε εργαζόμενους στον πίνακα.", "err");
    return;
  }
  const employerAfm = $("#wc-employer-afm").value.trim();
  if (!employerAfm) {
    showStatus("Συμπλήρωσε Α.Φ.Μ. εργοδότη.", "err");
    return;
  }
  const dates = weekDatesFromStart(state.shiftGrid.weekStart);
  const date = dates[dayIndex];
  const dayLabel = `${SHIFT_DAY_LABELS[dayIndex]} ${formatDayHeader(date)}`;
  const workCount = countWorkShiftsForDay(dayIndex);

  if (mode === "ARRIVAL" || mode === "BOTH") {
    if (workCount === 0) {
      showStatus(
        `Δεν έχει οριστεί βάρδια για ${dayLabel}. Βάλε ώρες Πρ./Απ. στα κελιά.`,
        "info"
      );
      return;
    }
    const action =
      mode === "BOTH" ? "προσέλευση και αποχώρηση" : "προσέλευση";
    const ok = window.confirm(
      `Είσαι σίγουρος;\n\nΘα υποβληθεί ${action} για ${workCount} εργαζόμενους την ${dayLabel}.`
    );
    if (!ok) return;
  }

  const late = $("#wc-late").value || null;
  const entries = [];

  try {
    for (const emp of state.shiftGrid.employees) {
      const shift = normalizeShift((emp.shifts || defaultWeekShifts())[dayIndex]);
      if (!isShiftWork(shift)) continue;
      if (mode === "ARRIVAL" || mode === "BOTH") {
        entries.push({
          employee_afm: emp.afm,
          first_name: emp.first_name,
          last_name: emp.last_name,
          movement_type: "ARRIVAL",
          submission_date: date,
          movement_datetime: movementDatetimeIso(date, shift.arrival),
          late_justification: late,
        });
      }
      if (mode === "DEPARTURE" || mode === "BOTH") {
        entries.push({
          employee_afm: emp.afm,
          first_name: emp.first_name,
          last_name: emp.last_name,
          movement_type: "DEPARTURE",
          submission_date: date,
          movement_datetime: movementDatetimeIso(date, shift.departure),
          late_justification: late,
        });
      }
    }
  } catch (err) {
    showStatus(err.message, "err");
    return;
  }

  if (!entries.length) {
    showStatus(
      `Δεν υπάρχουν βάρδιες για ${dayLabel} (κενά κελιά ή ΡΕΠΟ).`,
      "info"
    );
    return;
  }

  const workers = new Set(entries.map((e) => e.employee_afm)).size;
  await postWorkCardPayload(
    {
      employer_afm: $("#wc-employer-afm").value.trim(),
      branch_number: parseInt($("#wc-branch").value, 10),
      comments: $("#wc-comments").value,
      entries,
    },
    {
      resultsId: "#workcard-results",
      mode,
      employeeCount: workers,
    }
  );
}

function formatSyncedAt(iso) {
  if (!iso) return "";
  try {
    const d = new Date(iso);
    return d.toLocaleString("el-GR");
  } catch {
    return iso;
  }
}

function renderPersonnel(employees, syncedAt = null) {
  state.personnel = employees;
  const tbody = $("#personnel-body");
  if (!employees.length) {
    tbody.innerHTML =
      '<tr class="personnel-empty"><td colspan="3">Δεν βρέθηκαν εργαζόμενοι. Πάτα «Σύνδεση με Ergani».</td></tr>';
  } else {
    tbody.innerHTML = employees
      .map(
        (e, i) => `<tr data-index="${i}">
        <td>${escapeHtml(e.tax_identification_number ?? e.afm ?? "")}</td>
        <td>${escapeHtml(e.first_name ?? "")}</td>
        <td>${escapeHtml(e.last_name ?? "")}</td>
      </tr>`
      )
      .join("");
  }
  const countEl = $("#personnel-count");
  if (countEl) {
    countEl.textContent = employees.length ? `${employees.length} εργαζόμενοι` : "";
  }
  const syncInfo = $("#personnel-sync-info");
  if (syncInfo) {
    syncInfo.textContent = syncedAt
      ? `Τελευταία αποθήκευση Firebase: ${formatSyncedAt(syncedAt)}`
      : "Πάτα «Σύνδεση με Ergani» για λήψη και αποθήκευση.";
  }
}

async function loadStoredPersonnel() {
  if (!state.connected) return;
  try {
    const data = await api("/api/employees/stored");
    renderPersonnel(data.employees || [], data.synced_at);
    if (!(data.employees || []).length) {
      showStatus("Δεν υπάρχει αποθηκευμένο προσωπικό. Πάτα ανανέωση από Ergani.", "info");
    }
  } catch (err) {
    showStatus(err.message, "err");
  }
}

function initPunchDateFilters() {
  const fromEl = $("#punches-date-from");
  const toEl = $("#punches-date-to");
  if (!fromEl || !toEl) return;
  if (!toEl.value) toEl.value = todayDate();
  if (!fromEl.value) {
    const d = new Date();
    d.setDate(d.getDate() - 6);
    fromEl.value = d.toISOString().slice(0, 10);
  }
}

function formatDisplayDate(isoDate) {
  if (!isoDate) return "—";
  try {
    const [y, m, d] = isoDate.split("-").map(Number);
    return new Date(y, m - 1, d).toLocaleDateString("el-GR");
  } catch {
    return isoDate;
  }
}

function renderCardPunches(punches, meta = {}) {
  const tbody = $("#punches-body");
  if (!tbody) return;
  if (!punches.length) {
    tbody.innerHTML =
      '<tr class="personnel-empty"><td colspan="4">Δεν βρέθηκαν χτυπήματα για το διάστημα.</td></tr>';
  } else {
    tbody.innerHTML = punches
      .map((p) => {
        const typeClass =
          p.movement_type === "ARRIVAL"
            ? "punch-type punch-type--arrival"
            : p.movement_type === "DEPARTURE"
              ? "punch-type punch-type--departure"
              : "punch-type";
        return `<tr>
          <td>${escapeHtml(p.full_name || `${p.last_name || ""} ${p.first_name || ""}`.trim() || "—")}</td>
          <td>${escapeHtml(formatDisplayDate(p.movement_date || p.reference_date))}</td>
          <td>${escapeHtml(p.movement_time || "—")}</td>
          <td><span class="${typeClass}">${escapeHtml(p.movement_label || "—")}</span></td>
        </tr>`;
      })
      .join("");
  }
  const countEl = $("#punches-count");
  if (countEl) {
    countEl.textContent = punches.length
      ? `${punches.length} χτυπήματα`
      : "";
  }
  const syncInfo = $("#punches-sync-info");
  if (syncInfo) {
    const parts = [];
    if (meta.synced_at) {
      parts.push(`Τελευταία φόρτωση: ${formatSyncedAt(meta.synced_at)}`);
    }
    if (meta.service_code) {
      parts.push(`Υπηρεσία: ${meta.service_code}`);
    }
    syncInfo.textContent =
      parts.join(" · ") ||
      "Επίλεξε διάστημα και πάτα «Φόρτωση από Ergani». Αν αποτύχει, δες «Λίστα υπηρεσιών».";
  }
}

async function loadPunchServiceHints() {
  if (!state.connected) return;
  try {
    const data = await api("/api/work-card/punches/hints");
    const names = (data.services || []).map((s) => s.name).filter(Boolean);
    if (!names.length) return;
    const syncInfo = $("#punches-sync-info");
    if (syncInfo) {
      syncInfo.textContent = `Διαθέσιμες υπηρεσίες Ergani για κάρτα: ${names.join(", ")}`;
    }
  } catch {
    /* optional */
  }
}

async function loadStoredPunches() {
  if (!state.connected) return;
  initPunchDateFilters();
  const from = $("#punches-date-from")?.value;
  const to = $("#punches-date-to")?.value;
  const qs = new URLSearchParams();
  if (from) qs.set("date_from", from);
  if (to) qs.set("date_to", to);
  try {
    const data = await api(`/api/work-card/punches?${qs}`);
    renderCardPunches(data.punches || [], data);
  } catch (err) {
    showStatus(err.message, "err");
  }
}

async function syncPunchesFromErgani() {
  if (!state.connected) {
    showStatus("Συνδέσου πρώτα σε εταιρεία.", "err");
    return;
  }
  initPunchDateFilters();
  const dateFrom = $("#punches-date-from")?.value;
  const dateTo = $("#punches-date-to")?.value;
  if (!dateFrom || !dateTo) {
    showStatus("Συμπλήρωσε ημερομηνία από και έως.", "err");
    return;
  }
  const btn = $("#btn-sync-punches");
  if (btn) {
    btn.disabled = true;
    btn.textContent = "Φόρτωση από Ergani…";
  }
  hideStatus();
  const body = { date_from: dateFrom, date_to: dateTo };
  const branch = $("#punches-branch")?.value;
  if (branch !== undefined && branch !== "") {
    body.branch_number = parseInt(branch, 10);
  }
  try {
    const data = await api("/api/work-card/punches/sync", {
      method: "POST",
      body: JSON.stringify(body),
    });
    renderCardPunches(data.punches || [], data);
    showStatus(
      `Φορτώθηκαν ${data.count ?? 0} χτυπήματα από Ergani.`,
      "ok"
    );
  } catch (err) {
    if (err.punchesPayload) {
      renderCardPunches(
        err.punchesPayload.punches || [],
        err.punchesPayload
      );
      showStatus(err.message, "info");
    } else {
      showStatus(err.message, "err");
      await loadStoredPunches();
    }
  } finally {
    if (btn) {
      btn.disabled = false;
      btn.textContent = "Φόρτωση από Ergani";
    }
  }
}

async function syncPersonnelFromErgani() {
  if (!state.connected) {
    showStatus("Συνδέσου πρώτα σε εταιρεία.", "err");
    return;
  }
  const btn = $("#btn-sync-personnel");
  if (btn) {
    btn.disabled = true;
    btn.textContent = "Φόρτωση από Ergani…";
  }
  hideStatus();
  try {
    const body = { all_branches: true };
    const data = await api("/api/employees/sync", {
      method: "POST",
      body: JSON.stringify(body),
    });
    renderPersonnel(data.employees || [], data.synced_at);
    showStatus(
      `Αποθηκεύτηκαν ${data.count ?? 0} εργαζόμενοι στο Firebase.`,
      "ok"
    );
  } catch (err) {
    showStatus(err.message, "err");
  } finally {
    if (btn) {
      btn.disabled = false;
      btn.textContent = "Σύνδεση με Ergani";
    }
  }
}

function renderEmployer(employer) {
  const dl = $("#employer-summary");
  if (!employer) {
    dl.innerHTML = "";
    return;
  }
  const rows = [
    ["Επωνυμία", employer.name],
    ["Διακριτικός τίτλος", employer.distinctive_title],
    ["Α.Φ.Μ.", employer.employer_tax_identification_number],
    ["Α.Μ.Ε.", employer.employer_registry_number],
    ["Τομέας κάρτας", employer.is_in_card_sector ? "Ναι" : "Όχι / —"],
  ];
  dl.innerHTML = rows
    .map(([k, v]) => `<dt>${k}</dt><dd>${v ?? "—"}</dd>`)
    .join("");
  if (employer.employer_tax_identification_number) {
    $("#wc-employer-afm").value = employer.employer_tax_identification_number;
  }
}

function renderBranches(branches) {
  const tbody = $("#branches-table tbody");
  tbody.innerHTML = branches
    .map(
      (b) => `<tr>
        <td>${b.branch_number ?? "—"}</td>
        <td>${b.address ?? "—"}</td>
        <td>${b.sepe_service_code ?? "—"}</td>
        <td>${b.business_branch_activity_code ?? "—"}</td>
        <td>${b.status_description ?? "—"}</td>
      </tr>`
    )
    .join("");
  fillBranchSelects(branches);
}

async function loadEmployer() {
  const data = await api("/api/employer");
  state.employer = data.employer;
  renderEmployer(state.employer);
}

async function loadBranches() {
  const data = await api("/api/branches");
  state.branches = data.branches;
  renderBranches(state.branches);
  const otBranch = $("#ot-branch");
  if (otBranch && otBranch.selectedOptions[0]) {
    const opt = otBranch.selectedOptions[0];
    $("#ot-branch-kad").value = opt.dataset.kad || "";
    $("#ot-kallikratis").value = opt.dataset.kallikratis || "";
  }
}

async function refreshSession() {
  document.body.classList.add("kiosk-only");
  try {
    await api("/api/session", { method: "DELETE" });
  } catch {
    /* ignore */
  }
  try {
    await api("/api/auth/logout", { method: "POST" });
  } catch {
    /* ignore */
  }
  state.appUser = null;
  state.appRole = null;
  state.companyName = null;
  state.employer = null;
  setConnected(false);
  showKiosk();
}

function showCompanyStepAfterLogin(companies) {
  state.companies = companies;
  fillCompanySelect(companies);
  showGate("company");
  if (state.appRole === "admin") {
    showGateStatus(
      "Admin: όλες οι εταιρείες. Διάλεξε μία ή πήγαινε στη Διαχείριση.",
      "info"
    );
  }
  if (companies.length === 1) {
    void selectCompany(companies[0].id, { stayOnGate: true });
  }
}

$$("#nav button").forEach((btn) => {
  btn.addEventListener("click", () => {
    if (btn.disabled) return;
    void switchPanel(btn.dataset.panel);
  });
});

async function submitGateLogin() {
  hideGateStatus();
  const username = $("#app-username")?.value.trim() || "";
  const password = ($("#app-password")?.value || "").trim();
  if (!username || !password) {
    showGateStatus("Συμπλήρωσε όνομα και κωδικό.", "err");
    return;
  }
  const btn = $("#btn-gate-login");
  if (btn) {
    btn.disabled = true;
    btn.textContent = "Σύνδεση…";
  }
  try {
    const data = await api("/api/auth/login", {
      method: "POST",
      body: JSON.stringify({ username, password }),
    });
    state.appUser = data.app_user;
    state.appRole = data.app_role;
    updateNavState();
    const companies = data.companies || [];
    if (!companies.length) {
      showGate("company");
      fillCompanySelect([]);
      if (state.appRole === "admin") {
        showGateStatus("Πρόσθεσε εταιρείες από τη Διαχείριση.", "info");
      } else {
        showGateStatus(
          "Δεν έχεις ανατεθεί εταιρεία. Επικοινώνησε με τον admin.",
          "err"
        );
      }
      return;
    }
    showCompanyStepAfterLogin(companies);
  } catch (err) {
    showGateStatus(err.message, "err");
  } finally {
    if (btn) {
      btn.disabled = false;
      btn.textContent = "Σύνδεση";
    }
  }
}

$("#gate-login-form")?.addEventListener("submit", (e) => {
  e.preventDefault();
  void submitGateLogin();
});

$("#app-username")?.addEventListener("keydown", (e) => {
  if (e.key === "Enter") {
    e.preventDefault();
    $("#app-password")?.focus();
  }
});

$("#btn-gate-company")?.addEventListener("click", () => {
  hideGateStatus();
  const raw = $("#company-select")?.value || "";
  const companyId = parseInt(raw, 10);
  if (!companyId) {
    showGateStatus("Επίλεξε εταιρεία.", "err");
    return;
  }
  void selectCompany(companyId, { stayOnGate: true });
});

$("#company-select")?.addEventListener("change", () => {
  const companyId = parseInt($("#company-select")?.value || "", 10);
  const btn = $("#btn-gate-company");
  if (btn) btn.disabled = !companyId;
});

$("#sidebar-company-select")?.addEventListener("change", () => {
  const companyId = parseInt($("#sidebar-company-select")?.value || "", 10);
  if (companyId) void selectCompany(companyId, { silent: false });
});

$("#btn-gate-admin-only")?.addEventListener("click", () => {
  enterAdminPanelOnly();
});

$("#btn-app-logout")?.addEventListener("click", async () => {
  await api("/api/auth/logout", { method: "POST" });
  state.appUser = null;
  state.appRole = null;
  state.companyName = null;
  state.employer = null;
  state.branches = [];
  state.shiftGrid = null;
  shiftGridLoadedForCompany = null;
  setConnected(false);
  hideStatus();
  const userInput = $("#app-username");
  const passInput = $("#app-password");
  if (userInput) userInput.value = "";
  if (passInput) passInput.value = "";
  showKiosk();
});

async function returnToKioskScanner() {
  try {
    await api("/api/session", { method: "DELETE" });
  } catch {
    /* ignore */
  }
  state.employer = null;
  state.branches = [];
  setConnected(false);
  hideStatus();
  $("#app-layout")?.classList.remove("sidebar-open");
  showKiosk();
}

$("#btn-back-kiosk")?.addEventListener("click", () => void returnToKioskScanner());

$("#btn-mobile-back-kiosk")?.addEventListener("click", () => void returnToKioskScanner());

$("#btn-mobile-menu")?.addEventListener("click", () => {
  $("#app-layout")?.classList.toggle("sidebar-open");
});

document.querySelector("#nav")?.addEventListener("click", (e) => {
  if (e.target.closest("button[data-panel]")) {
    $("#app-layout")?.classList.remove("sidebar-open");
  }
});

$("#form-admin-company")?.addEventListener("submit", async (e) => {
  e.preventDefault();
  hideStatus();
  const id = $("#ac-id").value;
  const payload = {
    name: $("#ac-name").value.trim(),
    ergani_username: $("#ac-ergani-user").value.trim(),
    base_url: $("#ac-base-url").value.trim(),
    user_type: $("#ac-user-type").value,
  };
  const pass = $("#ac-ergani-pass").value;
  if (pass) payload.ergani_password = pass;
  try {
    if (id) {
      await api(`/api/admin/companies/${id}`, {
        method: "PUT",
        body: JSON.stringify(payload),
      });
      showStatus("Η εταιρεία ενημερώθηκε.", "ok");
    } else {
      if (!pass) {
        showStatus("Ο κωδικός Ergani είναι υποχρεωτικό για νέα εταιρεία.", "err");
        return;
      }
      payload.ergani_password = pass;
      await api("/api/admin/companies", {
        method: "POST",
        body: JSON.stringify(payload),
      });
      showStatus("Η εταιρεία προστέθηκε.", "ok");
    }
    $("#form-admin-company").reset();
    $("#ac-id").value = "";
    $("#ac-base-url").value = "https://eservices.yeka.gr/WebservicesAPI/Api";
    await loadAdminData();
    if (state.appUser) {
      try {
        await loadCompaniesForSession();
      } catch {
        /* ignore */
      }
    }
  } catch (err) {
    showStatus(err.message, "err");
  }
});

$("#ac-reset")?.addEventListener("click", () => {
  $("#form-admin-company").reset();
  $("#ac-id").value = "";
  $("#ac-base-url").value = "https://eservices.yeka.gr/WebservicesAPI/Api";
});

$("#form-admin-user")?.addEventListener("submit", async (e) => {
  e.preventDefault();
  hideStatus();
  const id = $("#au-id").value;
  const company_ids = [...$$("#au-company-checks input:checked")].map((el) =>
    parseInt(el.value, 10)
  );
  const payload = {
    username: $("#au-username").value.trim(),
    role: $("#au-role").value,
    active: $("#au-active").value === "1",
    company_ids,
  };
  const pass = $("#au-password").value;
  if (pass) payload.password = pass;
  try {
    if (id) {
      if (!pass) delete payload.password;
      await api(`/api/admin/users/${id}`, {
        method: "PUT",
        body: JSON.stringify(payload),
      });
      showStatus("Ο χρήστης ενημερώθηκε.", "ok");
    } else {
      if (!pass) {
        showStatus("Ο κωδικός είναι υποχρεωτικός για νέο χρήστη.", "err");
        return;
      }
      payload.password = pass;
      await api("/api/admin/users", {
        method: "POST",
        body: JSON.stringify(payload),
      });
      showStatus("Ο χρήστης προστέθηκε.", "ok");
    }
    $("#form-admin-user").reset();
    $("#au-id").value = "";
    await loadAdminData();
  } catch (err) {
    showStatus(err.message, "err");
  }
});

$("#au-reset")?.addEventListener("click", () => {
  $("#form-admin-user").reset();
  $("#au-id").value = "";
  renderAdminCompanyChecks();
});

$("#btn-refresh-employer").addEventListener("click", async () => {
  try {
    await loadEmployer();
    showStatus("Στοιχεία εργοδότη ενημερώθηκαν.", "ok");
  } catch (err) {
    showStatus(err.message, "err");
  }
});

$("#btn-refresh-branches").addEventListener("click", async () => {
  try {
    await loadBranches();
    showStatus("Παραρτήματα ενημερώθηκαν.", "ok");
  } catch (err) {
    showStatus(err.message, "err");
  }
});

$("#btn-sync-personnel")?.addEventListener("click", () => {
  void syncPersonnelFromErgani();
});

$("#btn-sync-punches")?.addEventListener("click", () => {
  void syncPunchesFromErgani();
});

$("#punches-date-from")?.addEventListener("change", () => {
  if (state.connected) void loadStoredPunches();
});
$("#punches-date-to")?.addEventListener("change", () => {
  if (state.connected) void loadStoredPunches();
});

$("#wc-week-prev")?.addEventListener("click", () => {
  ensureShiftGrid();
  state.shiftGrid.weekStart = addDaysIso(state.shiftGrid.weekStart, -7);
  $("#wc-week-start").value = state.shiftGrid.weekStart;
  persistShiftGrid();
  renderShiftGrid();
  renderTodayStaffList();
});

$("#wc-week-next")?.addEventListener("click", () => {
  ensureShiftGrid();
  state.shiftGrid.weekStart = addDaysIso(state.shiftGrid.weekStart, 7);
  $("#wc-week-start").value = state.shiftGrid.weekStart;
  persistShiftGrid();
  renderShiftGrid();
  renderTodayStaffList();
});

$("#wc-week-start")?.addEventListener("change", () => {
  ensureShiftGrid();
  state.shiftGrid.weekStart = mondayOfWeek($("#wc-week-start").value);
  $("#wc-week-start").value = state.shiftGrid.weekStart;
  persistShiftGrid();
  renderShiftGrid();
  renderTodayStaffList();
});

$("#wc-today-list")?.addEventListener("click", (e) => {
  const btn = e.target.closest(".wc-today-punch");
  if (!btn) return;
  void punchEmployeeToday(parseInt(btn.dataset.emp, 10), btn.dataset.mode);
});

$("#wc-manual-fab")?.addEventListener("click", () => void openManualPunchSheet());
$("#wc-manual-close")?.addEventListener("click", closeManualPunchSheet);
document.querySelector(".wc-manual-sheet-backdrop")?.addEventListener("click", closeManualPunchSheet);
$("#wc-manual-checkin")?.addEventListener("click", () => void submitManualPunch("ARRIVAL"));
$("#wc-manual-checkout")?.addEventListener("click", () => void submitManualPunch("DEPARTURE"));
$("#wc-manual-select-all")?.addEventListener("click", () => {
  $$(".wc-manual-check").forEach((cb) => {
    cb.checked = true;
  });
});
$("#wc-manual-select-none")?.addEventListener("click", () => {
  $$(".wc-manual-check").forEach((cb) => {
    cb.checked = false;
  });
});

$("#wc-import-personnel")?.addEventListener("click", async () => {
  await ensurePersonnelLoaded();
  if (!state.personnel.length) {
    showStatus("Πήγαινε πρώτα στο Προσωπικό και πάτα «Σύνδεση με Ergani».", "err");
    return;
  }
  const added = importPersonnelToShiftGrid(state.personnel);
  showStatus(`Προστέθηκαν/ενημερώθηκαν ${added} εργαζόμενοι.`, "ok");
});

$("#wc-add-employee")?.addEventListener("click", () => {
  const afm = window.prompt("Α.Φ.Μ. εργαζομένου:");
  if (!afm?.trim()) return;
  const first = window.prompt("Όνομα:") || "";
  const last = window.prompt("Επώνυμο:") || "";
  ensureShiftGrid();
  upsertShiftEmployee({ afm: afm.trim(), first_name: first.trim(), last_name: last.trim() });
  persistShiftGrid();
  renderShiftGrid();
});

$("#shift-popover-off")?.addEventListener("change", (e) => {
  const off = e.target.checked;
  $("#shift-popover-arrival").disabled = off;
  $("#shift-popover-departure").disabled = off;
});

$("#shift-popover-save")?.addEventListener("click", () => saveShiftPopover(false));
$("#shift-popover-clear")?.addEventListener("click", () => saveShiftPopover(true));
$("#shift-popover-cancel")?.addEventListener("click", closeShiftPopover);

document.addEventListener("mousedown", (e) => {
  const pop = $("#shift-cell-popover");
  if (!pop || pop.classList.contains("hidden")) return;
  if (pop.contains(e.target)) return;
  if (e.target.closest(".shiftgrid-cell")) return;
  closeShiftPopover();
});

$("#shiftgrid-table")?.addEventListener("click", (e) => {
  const cellBtn = e.target.closest(".shiftgrid-cell");
  if (cellBtn) {
    openShiftPopover(
      parseInt(cellBtn.dataset.emp, 10),
      parseInt(cellBtn.dataset.day, 10),
      cellBtn
    );
    return;
  }
  const removeBtn = e.target.closest(".shiftgrid-remove");
  if (removeBtn) {
    const idx = parseInt(removeBtn.dataset.emp, 10);
    ensureShiftGrid();
    state.shiftGrid.employees.splice(idx, 1);
    persistShiftGrid();
    renderShiftGrid();
    return;
  }
  const dayBtn = e.target.closest(".shift-day-btn");
  if (dayBtn) {
    void submitShiftGridDay(parseInt(dayBtn.dataset.day, 10), dayBtn.dataset.mode);
  }
});

function parseEmployeeLines(text) {
  const rows = [];
  for (const line of text.split(/\r?\n/)) {
    const trimmed = line.trim();
    if (!trimmed || trimmed.startsWith("#")) continue;
    const parts = trimmed.split(/[,\t;]/).map((p) => p.trim());
    if (parts.length < 3) continue;
    rows.push({
      afm: parts[0],
      first_name: parts[1],
      last_name: parts.slice(2).join(" "),
    });
  }
  return rows;
}

$("#btn-wc-paste").addEventListener("click", () => {
  const text = window.prompt(
    "Επικόλλησε γραμμές:\nΑΦΜ, Όνομα, Επώνυμο\n(μία γραμμή ανά εργαζόμενο)"
  );
  if (!text) return;
  const rows = parseEmployeeLines(text);
  if (!rows.length) {
    showStatus("Δεν βρέθηκαν έγκυρες γραμμές. Μορφή: ΑΦΜ, Όνομα, Επώνυμο", "err");
    return;
  }
  ensureShiftGrid();
  const added = importPersonnelToShiftGrid(
    rows.map((row) => ({
      tax_identification_number: row.afm,
      first_name: row.first_name,
      last_name: row.last_name,
    }))
  );
  showStatus(`Προστέθηκαν/ενημερώθηκαν ${added} εργαζόμενοι.`, "ok");
});

$("#form-workcard").addEventListener("submit", (e) => e.preventDefault());

$("#ot-branch").addEventListener("change", () => {
  const opt = $("#ot-branch").selectedOptions[0];
  if (opt) {
    $("#ot-branch-kad").value = opt.dataset.kad || "";
    $("#ot-kallikratis").value = opt.dataset.kallikratis || "";
  }
});

$("#form-overtime").addEventListener("submit", async (e) => {
  e.preventDefault();
  hideStatus();
  const branchOpt = $("#ot-branch").selectedOptions[0];
  const payload = {
    comments: "",
    branch: {
      branch_number: parseInt($("#ot-branch").value, 10),
      sepe_service_code: branchOpt?.dataset.sepe || "",
      primary_kad: $("#ot-primary-kad").value.trim(),
      branch_kad: $("#ot-branch-kad").value.trim(),
      kallikratis: $("#ot-kallikratis").value.trim(),
      legal_rep_afm: $("#ot-legal-afm").value.trim(),
    },
    entries: [
      {
        employee_afm: $("#ot-employee-afm").value.trim(),
        amka: $("#ot-amka").value.trim(),
        first_name: $("#ot-first-name").value.trim(),
        last_name: $("#ot-last-name").value.trim(),
        overtime_date: $("#ot-date").value,
        start_time: $("#ot-from").value,
        end_time: $("#ot-to").value,
        cancellation: $("#ot-cancel").checked,
        profession_code: $("#ot-profession").value.trim(),
        justification: $("#ot-justification").value,
        weekly_workdays: $("#ot-weekdays").value,
      },
    ],
  };
  try {
    const data = await api("/api/overtime", {
      method: "POST",
      body: JSON.stringify(payload),
    });
    showResults("#overtime-results", data);
    showStatus("Υπερωρία υποβλήθηκε.", "ok");
  } catch (err) {
    showStatus(err.message, "err");
  }
});

$("#form-daily").addEventListener("submit", async (e) => {
  e.preventDefault();
  hideStatus();
  const scheduleDate = $("#ds-date").value;
  const payload = {
    branch_number: parseInt($("#ds-branch").value, 10),
    start_date: scheduleDate,
    end_date: scheduleDate,
    employee_schedules: [
      {
        employee_afm: $("#ds-employee-afm").value.trim(),
        first_name: $("#ds-first-name").value.trim(),
        last_name: $("#ds-last-name").value.trim(),
        schedule_date: scheduleDate,
        workdays: [
          {
            work_type: $("#ds-work-type").value,
            start_time: $("#ds-from").value,
            end_time: $("#ds-to").value,
          },
        ],
      },
    ],
  };
  try {
    const data = await api("/api/daily-schedule", {
      method: "POST",
      body: JSON.stringify(payload),
    });
    showResults("#daily-results", data);
    showStatus("Ημερήσιο πρόγραμμα υποβλήθηκε.", "ok");
  } catch (err) {
    showStatus(err.message, "err");
  }
});

$("#form-weekly").addEventListener("submit", async (e) => {
  e.preventDefault();
  hideStatus();
  const payload = {
    branch_number: parseInt($("#ws-branch").value, 10),
    start_date: $("#ws-from-period").value,
    end_date: $("#ws-to-period").value,
    employee_schedules: [
      {
        employee_afm: $("#ws-employee-afm").value.trim(),
        first_name: $("#ws-first-name").value.trim(),
        last_name: $("#ws-last-name").value.trim(),
        schedule_date: $("#ws-date").value,
        workdays: [
          {
            work_type: $("#ws-work-type").value,
            start_time: $("#ws-from").value,
            end_time: $("#ws-to").value,
          },
        ],
      },
    ],
  };
  try {
    const data = await api("/api/weekly-schedule", {
      method: "POST",
      body: JSON.stringify(payload),
    });
    showResults("#weekly-results", data);
    showStatus("Εβδομαδιαίο πρόγραμμα υποβλήθηκε.", "ok");
  } catch (err) {
    showStatus(err.message, "err");
  }
});

$("#btn-services").addEventListener("click", async () => {
  try {
    const data = await api("/api/services");
    showResults("#services-results", data);
    $("#services-results").classList.remove("hidden");
  } catch (err) {
    showStatus(err.message, "err");
  }
});

$("#wc-week-start").value = mondayOfWeek(todayDate());

const tomorrow = new Date();
tomorrow.setDate(tomorrow.getDate() + 1);
$("#ds-date").value = tomorrow.toISOString().slice(0, 10);
$("#ot-date").value = todayDate();
$("#ws-date").value = todayDate();
$("#ws-from-period").value = todayDate();
const weekEnd = new Date();
weekEnd.setDate(weekEnd.getDate() + 6);
$("#ws-to-period").value = weekEnd.toISOString().slice(0, 10);

refreshSession().catch(() => {});
