/** Kiosk — scanner, δεξιά slide bar, εταιρεία (localStorage), Ergani connect. */
(function () {
  function getKioskKey() {
    return (window.KIOSK_KEY || "").trim();
  }
  let bootstrap =
    typeof window.KIOSK_BOOTSTRAP === "object" && window.KIOSK_BOOTSTRAP
      ? window.KIOSK_BOOTSTRAP
      : null;
  const STORAGE_COMPANY = "ergani_kiosk_company_id";
  let loginBound = false;
  let config = null;
  let companies = [];
  let scanner = null;
  let pendingMovement = null;
  let scanHandled = false;
  let clockTimer = null;
  let adminTapCount = 0;
  let adminTapTimer = null;
  let lastSyncLabel = "";
  let eventsBound = false;
  let setupBound = false;

  const $ = (id) => document.getElementById(id);

  function needsSetup() {
    const stored = localStorage.getItem(STORAGE_COMPANY);
    if (!stored) return true;
    const id = parseInt(stored, 10);
    return !(Number.isFinite(id) && id > 0);
  }

  function setSetupStatus(text, kind) {
    const el = $("kiosk-setup-status");
    if (!el) return;
    if (!text) {
      el.textContent = "";
      el.className = "gate-status hidden";
      return;
    }
    el.textContent = text;
    el.className = `gate-status ${kind || "info"}`;
    el.classList.remove("hidden");
  }

  function webGateEnabled() {
    if (typeof window.KIOSK_WEB_GATE === "boolean") {
      return window.KIOSK_WEB_GATE;
    }
    return Boolean(bootstrap?.web_gate);
  }

  function setLoginStatus(text, kind) {
    setSetupStatus(text, kind);
  }

  function showSetupLoginStep() {
    $("kiosk-setup-step-login")?.classList.remove("hidden");
    $("kiosk-setup-step-company")?.classList.add("hidden");
    $("kiosk-web-username")?.focus();
  }

  function showSetupCompanyStep() {
    $("kiosk-setup-step-login")?.classList.add("hidden");
    $("kiosk-setup-step-company")?.classList.remove("hidden");
  }

  async function applyBootstrap(data) {
    bootstrap = data || {};
    window.KIOSK_BOOTSTRAP = bootstrap;
    if (data?.kiosk_key) {
      window.KIOSK_KEY = data.kiosk_key;
    }
    if (Array.isArray(data?.companies)) {
      companies = data.companies;
    }
  }

  async function fetchBootstrap() {
    const res = await fetch("/api/kiosk/bootstrap", { credentials: "same-origin" });
    const data = await safeJson(res);
    if (!res.ok) {
      throw new Error(data.error || "Αποτυχία φόρτωσης.");
    }
    await applyBootstrap(data);
    return data;
  }

  async function checkWebAuth() {
    const res = await fetch("/api/kiosk/web-auth/status", { credentials: "same-origin" });
    const data = await safeJson(res);
    if (!res.ok) {
      throw new Error(data.error || "Σφάλμα ελέγχου σύνδεσης.");
    }
    bootstrap = { ...(bootstrap || {}), web_gate: Boolean(data.web_gate) };
    window.KIOSK_BOOTSTRAP = bootstrap;
    if (data.web_gate && !data.authenticated) {
      return false;
    }
    if (data.web_gate) {
      await fetchBootstrap();
    }
    return true;
  }

  function showLogin() {
    showSetup();
    showSetupLoginStep();
    setLoginStatus("");
  }

  function hideLogin() {
    showSetupCompanyStep();
    setLoginStatus("");
  }

  async function submitKioskLogin() {
    setLoginStatus("");
    const username = $("kiosk-web-username")?.value.trim() || "";
    const password = ($("kiosk-web-password")?.value || "").trim();
    if (!username || !password) {
      setLoginStatus("Συμπλήρωσε όνομα και κωδικό.", "err");
      return;
    }
    const btn = $("kiosk-login-submit");
    if (btn) {
      btn.disabled = true;
      btn.textContent = "Σύνδεση…";
    }
    try {
      const res = await fetch("/api/kiosk/web-login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "same-origin",
        body: JSON.stringify({ username, password }),
      });
      const data = await safeJson(res);
      if (!res.ok) {
        throw new Error(data.error || "Λάθος όνομα ή κωδικός.");
      }
      if (data.web_gate !== false) {
        await fetchBootstrap();
      }
      hideLogin();
      await loadSetupScreen();
    } catch (e) {
      setLoginStatus(e.message || "Αποτυχία σύνδεσης.", "err");
    } finally {
      if (btn) {
        btn.disabled = false;
        btn.textContent = "Σύνδεση";
      }
    }
  }

  function bindLoginEvents() {
    if (loginBound) return;
    loginBound = true;
    bindAdminHotspots();
    $("kiosk-login-form")?.addEventListener("submit", (e) => {
      e.preventDefault();
      void submitKioskLogin();
    });
  }

  function kioskKeyError() {
    const key = getKioskKey();
    if (!key || key === "__KIOSK_KEY__") {
      return (
        "Λάθος server: άνοιξε http://<IP-Mac>:5050/ (όχι /static/) και κάνε restart:\n" +
        "set -a && source ui/.env && set +a && PYTHONPATH=$PWD python3 ui/app.py"
      );
    }
    return null;
  }

  async function safeJson(res) {
    const text = await res.text();
    if (!text) {
      if (!res.ok) {
        throw new Error(
          res.status === 404
            ? "Παλιό server — κάνε restart το ui/app.py (λείπει kiosk API)."
            : `Σφάλμα server (${res.status})`
        );
      }
      return {};
    }
    try {
      return JSON.parse(text);
    } catch {
      if (res.status === 404) {
        throw new Error(
          "Παλιό server χωρίς kiosk API — σταμάτα το παλιό process στη θύρα 5050 και ξανά-run το ui/app.py."
        );
      }
      throw new Error(
        `Μη έγκυρη απάντηση server (${res.status}). Έλεγξε ότι τρέχει ui/app.py στο http://IP:5050/`
      );
    }
  }

  function applyBootstrapCompanies() {
    const list = bootstrap?.companies;
    if (!Array.isArray(list) || !list.length) return false;
    companies = list;
    return true;
  }

  function getSelectedCompanyId() {
    const stored = localStorage.getItem(STORAGE_COMPANY);
    if (stored) {
      const id = parseInt(stored, 10);
      if (Number.isFinite(id) && id > 0) return id;
    }
    return companies[0]?.id ?? null;
  }

  function setSelectedCompanyId(id) {
    localStorage.setItem(STORAGE_COMPANY, String(id));
  }

  function headers(companyId) {
    const h = {
      "Content-Type": "application/json",
      "X-Kiosk-Key": getKioskKey(),
    };
    const cid = companyId ?? getSelectedCompanyId();
    if (cid != null && Number.isFinite(Number(cid)) && Number(cid) > 0) {
      h["X-Kiosk-Company-Id"] = String(cid);
    }
    return h;
  }

  function setStatus(text, kind) {
    const el = $("kiosk-status-line");
    if (!el) return;
    el.textContent = text || "";
    el.className = "status-line kiosk-status" + (kind ? ` is-${kind}` : "");
  }

  function showToast(text, isError) {
    const el = $("kiosk-toast");
    if (!el) return;
    el.textContent = text;
    el.className = "toast " + (isError ? "is-err" : "is-ok");
    el.classList.remove("hidden");
    clearTimeout(showToast._t);
    showToast._t = setTimeout(() => el.classList.add("hidden"), 5000);
  }

  function updateClock() {
    const now = new Date();
    const timeEl = $("kiosk-clock-time");
    const dateEl = $("kiosk-clock-date");
    if (!timeEl || !dateEl) return;
    timeEl.textContent = now.toLocaleTimeString("el-GR", {
      hour: "2-digit",
      minute: "2-digit",
      hour12: false,
    });
    dateEl.textContent = now.toLocaleDateString("el-GR", {
      weekday: "long",
      day: "numeric",
      month: "numeric",
    });
  }

  function updateDrawerHeader() {
    const dc = $("kiosk-drawer-company");
    const dv = $("kiosk-drawer-vat");
    const db = $("kiosk-drawer-branch");
    const name = config?.company_name || "—";
    if (dc) dc.textContent = name;
    if (dv) dv.textContent = `VAT: ${config?.employer_afm || "—"}`;
    if (db) db.textContent = `Branch: ${config?.branch_label || "(0) ΕΔΡΑ"}`;
    const syncLbl = $("kiosk-sync-label");
    if (syncLbl) syncLbl.textContent = lastSyncLabel;
  }

  function renderCompanyList() {
    const list = $("kiosk-company-list");
    if (!list) return;
    const selected = getSelectedCompanyId();
    if (!companies.length) {
      list.innerHTML =
        '<li class="kiosk-muted">Δεν υπάρχουν εταιρείες στο server.</li>';
      return;
    }
    list.innerHTML = companies
      .map((c) => {
        const active = c.id === selected ? " is-selected" : "";
        return `<li><button type="button" class="kiosk-company-pick${active}" data-id="${c.id}">${escapeHtml(c.name)}</button></li>`;
      })
      .join("");
  }

  function pickCompany(companyId) {
    setSelectedCompanyId(companyId);
    renderCompanyList();
    const setupSel = $("kiosk-setup-company");
    if (setupSel) setupSel.value = String(companyId);
  }

  async function loadCompanies() {
    const keyErr = kioskKeyError();
    if (keyErr) throw new Error(keyErr);

    if (applyBootstrapCompanies()) {
      const stored = localStorage.getItem(STORAGE_COMPANY);
      if (!stored && companies.length) setSelectedCompanyId(companies[0].id);
      renderCompanyList();
    }

    try {
      const res = await fetch("/api/kiosk/companies", { headers: headers(null) });
      const data = await safeJson(res);
      if (!res.ok) throw new Error(data.error || "Σφάλμα εταιρειών");
      companies = data.companies || companies;
    } catch (e) {
      if (companies.length) return companies;
      throw e;
    }
    const stored = localStorage.getItem(STORAGE_COMPANY);
    if (!stored && companies.length) setSelectedCompanyId(companies[0].id);
    renderCompanyList();
    return companies;
  }

  async function loadConfig() {
    const keyErr = kioskKeyError();
    if (keyErr) {
      setStatus(keyErr, "err");
      return;
    }
    const cid = getSelectedCompanyId();
    if (!cid) {
      setStatus("Άνοιξε ☰ δεξιά → διάλεξε εταιρεία → Σύνδεση Ergani", "info");
      return;
    }
    try {
      const res = await fetch("/api/kiosk/config", { headers: headers() });
      const data = await safeJson(res);
      if (!res.ok) throw new Error(data.error || "Σφάλμα ρύθμισης");
      config = data;
      if (data.company_id) setSelectedCompanyId(data.company_id);
      lastSyncLabel = data.synced_at_label || "";
      updateDrawerHeader();
      setStatus("Πάτα Check-in ή Check-out · σκάναρε QR", "ok");
    } catch (e) {
      config = null;
      setStatus(e.message || "Άνοιξε ☰ → Σύνδεση με Ergani", "err");
    }
  }

  async function connectErgani() {
    const cid = getSelectedCompanyId();
    if (!cid) {
      showToast("Διάλεξε εταιρεία από τη λίστα.", true);
      return false;
    }
    setStatus("Σύνδεση Ergani…", "info");
    try {
      const res = await fetch("/api/kiosk/connect", {
        method: "POST",
        headers: headers(),
        body: JSON.stringify({ company_id: cid }),
      });
      const data = await safeJson(res);
      if (!res.ok) throw new Error(data.error || "Αποτυχία σύνδεσης");
      config = data;
      lastSyncLabel = data.synced_at_label || "";
      updateDrawerHeader();
      setStatus("Συνδεδεμένο · Check-in / Check-out", "ok");
      showToast(`Ergani: ${data.company_name || "OK"}`, false);
      closeDrawer();
      return true;
    } catch (e) {
      config = null;
      setStatus(e.message || "Δεν συνδέθηκε", "err");
      showToast(e.message || "Σφάλμα", true);
      return false;
    }
  }

  function fillSetupSelect() {
    const sel = $("kiosk-setup-company");
    const btn = $("kiosk-setup-connect");
    if (!sel) return;
    const opts = ['<option value="">— Επιλογή εταιρείας —</option>'];
    for (const c of companies) {
      opts.push(
        `<option value="${c.id}">${escapeHtml(c.name || `Εταιρεία ${c.id}`)}</option>`
      );
    }
    sel.innerHTML = opts.join("");
    const saved = getSelectedCompanyId();
    if (saved) {
      sel.value = String(saved);
      if (btn) btn.disabled = false;
    } else if (companies.length === 1) {
      sel.value = String(companies[0].id);
      if (btn) btn.disabled = false;
    } else if (btn) {
      btn.disabled = true;
    }
  }

  async function loadSetupScreen() {
    const keyErr = kioskKeyError();
    if (keyErr) {
      setSetupStatus(keyErr, "err");
      return;
    }
    setSetupStatus("Φόρτωση εταιρειών…", "info");
    try {
      await loadCompanies();
      fillSetupSelect();
      if (!companies.length) {
        setSetupStatus(
          "Δεν υπάρχουν εταιρείες — όρισε ERGANI_KIOSK_COMPANY_ID στο .env του server.",
          "err"
        );
        return;
      }
      setSetupStatus("Διάλεξε εταιρεία και πάτα Σύνδεση.", "info");
    } catch (e) {
      setSetupStatus(e.message || "Σφάλμα φόρτωσης", "err");
    }
  }

  function showSetup() {
    document.body.classList.add("kiosk-active");
    $("app-kiosk-setup")?.classList.remove("hidden");
    $("app-kiosk-setup")?.setAttribute("aria-hidden", "false");
    $("app-kiosk")?.classList.add("hidden");
    bindSetupEvents();
    bindLoginEvents();
    if (!webGateEnabled()) {
      showSetupCompanyStep();
      void loadSetupScreen();
    }
  }

  function hideSetup() {
    $("app-kiosk-setup")?.classList.add("hidden");
    $("app-kiosk-setup")?.setAttribute("aria-hidden", "true");
    setSetupStatus("");
  }

  async function finishSetup() {
    const raw = $("kiosk-setup-company")?.value || "";
    const companyId = parseInt(raw, 10);
    if (!companyId) {
      setSetupStatus("Επίλεξε εταιρεία.", "err");
      return;
    }
    const btn = $("kiosk-setup-connect");
    if (btn) {
      btn.disabled = true;
      btn.textContent = "Σύνδεση…";
    }
    setSetupStatus("Σύνδεση με Ergani…", "info");
    setSelectedCompanyId(companyId);
    const ok = await connectErgani();
    if (btn) {
      btn.disabled = false;
      btn.textContent = "Συνέχεια στο Scanner";
    }
    if (!ok) {
      setSetupStatus(
        $("kiosk-status-line")?.textContent || "Αποτυχία σύνδεσης Ergani.",
        "err"
      );
      return;
    }
    hideSetup();
    $("app-kiosk")?.classList.remove("hidden");
    if (!eventsBound) {
      bindEvents();
      eventsBound = true;
      updateClock();
      if (!clockTimer) clockTimer = setInterval(updateClock, 1000);
      showView("home");
    }
    setSetupStatus("");
  }

  function bindSetupEvents() {
    if (setupBound) return;
    setupBound = true;
    bindAdminHotspots();
    $("kiosk-setup-company")?.addEventListener("change", () => {
      const companyId = parseInt($("kiosk-setup-company")?.value || "", 10);
      const btn = $("kiosk-setup-connect");
      if (btn) btn.disabled = !companyId;
    });
    $("kiosk-setup-connect")?.addEventListener("click", () => void finishSetup());
  }

  async function runSync() {
    if (!config) {
      showToast("Πρώτα Σύνδεση με Ergani από το μενού.", true);
      return;
    }
    closeDrawer();
    setStatus("Συγχρονισμός προσωπικού…", "info");
    try {
      const res = await fetch("/api/kiosk/sync", {
        method: "POST",
        headers: headers(),
        body: JSON.stringify({ company_id: getSelectedCompanyId() }),
      });
      const data = await safeJson(res);
      if (!res.ok) throw new Error(data.error || "Αποτυχία sync");
      lastSyncLabel = data.synced_at_label || "";
      updateDrawerHeader();
      showToast(`Sync OK — ${data.count} εργαζόμενοι`, false);
      setStatus("Έτοιμο για scan", "ok");
    } catch (e) {
      showToast(e.message, true);
      setStatus(e.message, "err");
    }
  }

  function formatStmtDate(isoDate) {
    if (!isoDate) return "—";
    const parts = String(isoDate).slice(0, 10).split("-");
    if (parts.length !== 3) return isoDate;
    return `${parts[2]}/${parts[1]}/${parts[0]}`;
  }

  function formatPunchRow(p) {
    const name = p.full_name || `${p.last_name || ""} ${p.first_name || ""}`.trim();
    const label = p.movement_label || (p.movement_type === "ARRIVAL" ? "Check-in" : "Check-out");
    const day = formatStmtDate(p.reference_date || p.movement_date || p.date || "");
    const time = p.movement_time || p.time || "—";
    const afm = p.afm || p.employee_afm || "";
    const kind = p.movement_type === "ARRIVAL" ? "is-in" : "is-out";
    return `<li class="kiosk-stmt-card ${kind}">
      <div class="kiosk-stmt-head">
        <strong class="kiosk-stmt-type">${escapeHtml(label)}</strong>
        <span class="kiosk-stmt-time">${escapeHtml(time)}</span>
      </div>
      <div class="kiosk-stmt-body">
        <span class="kiosk-stmt-name">${escapeHtml(name || afm || "—")}</span>
        ${afm ? `<span class="kiosk-stmt-vat">VAT: ${escapeHtml(afm)}</span>` : ""}
      </div>
      <div class="kiosk-stmt-foot">
        <span class="kiosk-stmt-date">${escapeHtml(day)}</span>
      </div>
    </li>`;
  }

  function escapeHtml(value) {
    return String(value)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;");
  }

  async function loadStatements() {
    const list = $("kiosk-statements-list");
    if (!list) return;
    list.innerHTML = '<p class="kiosk-muted">Φόρτωση…</p>';
    try {
      const res = await fetch("/api/kiosk/statements", { headers: headers() });
      const data = await safeJson(res);
      if (!res.ok) throw new Error(data.error || "Σφάλμα");
      const punches = data.punches || [];
      if (!punches.length) {
        list.innerHTML = '<p class="kiosk-muted">Δεν υπάρχουν χτυπήματα ακόμα.</p>';
        return;
      }
      list.innerHTML = `<ul class="kiosk-stmt-ul">${punches.map(formatPunchRow).join("")}</ul>`;
    } catch (e) {
      list.innerHTML = `<p class="kiosk-muted">${escapeHtml(e.message)}</p>`;
    }
  }

  function showView(name) {
    $("kiosk-view-home")?.classList.toggle("hidden", name !== "home");
    $("kiosk-view-statements")?.classList.toggle("hidden", name !== "statements");
    document.querySelectorAll(".kiosk-nav-item").forEach((btn) => {
      btn.classList.toggle("is-active", btn.dataset.kioskNav === name);
    });
    if (name === "statements") void loadStatements();
  }

  function openDrawer() {
    const d = $("kiosk-drawer");
    if (!d) return;
    renderCompanyList();
    updateDrawerHeader();
    d.classList.remove("hidden");
    d.setAttribute("aria-hidden", "false");
  }

  function closeDrawer() {
    const d = $("kiosk-drawer");
    if (!d) return;
    d.classList.add("hidden");
    d.setAttribute("aria-hidden", "true");
  }

  async function submitPunch(movementType, qrPayload) {
    const res = await fetch("/api/kiosk/punch", {
      method: "POST",
      headers: headers(),
      body: JSON.stringify({
        movement_type: movementType,
        qr_payload: qrPayload,
        company_id: getSelectedCompanyId(),
        employer_afm: config?.employer_afm,
        branch_number: config?.branch_number ?? 0,
      }),
    });
    const data = await safeJson(res);
    if (!res.ok) throw new Error(data.error || "Αποτυχία υποβολής");
    return data;
  }

  const isIOS =
    /iPad|iPhone|iPod/.test(navigator.userAgent) ||
    (navigator.platform === "MacIntel" && navigator.maxTouchPoints > 1);
  const isAndroid = /Android/i.test(navigator.userAgent);

  function cameraHelpSteps() {
    if (isIOS) {
      return [
        "Άνοιξε Ρυθμίσεις → Safari → Κάμερα → «Ερώτηση» ή «Να επιτρέπεται».",
        "Ή στο Safari: πάτα «aA» / διεύθυνση → Ρυθμίσεις ιστότοπου → Κάμερα → Επίτρεψε.",
        "Κλείσε και ξανάνοιξε αυτή τη σελίδα (http://IP:5050).",
        "Πάτα ξανά Check-in και «Επίτρεψε» όταν ζητηθεί.",
      ];
    }
    if (isAndroid) {
      return [
        "Στο Chrome: πάτα το κλειδί/εικονίδιο δίπλα στη διεύθυνση → Δικαιώματα.",
        "Βάλε Κάμερα → Επίτρεψε (ή «Να επιτρέπεται κάθε φορά»).",
        "Αν δεν φαίνεται: Ρυθμίσεις τηλεφώνου → Εφαρμογές → Chrome → Άδειες → Κάμερα.",
        "Κλείσε την καρτέλα και ξανάνοιξε το Ergani · πάτα Check-in.",
      ];
    }
    return [
      "Επίτρεψε πρόσβαση στην κάμερα όταν το browser το ζητήσει.",
      "Έλεγξε ότι δεν είναι αποκλεισμένη στις ρυθμίσεις του browser για αυτόν τον ιστότοπο.",
      "Χρησιμοποίησε HTTPS ή τοπική διεύθυνση (π.χ. http://192.168.x.x:5050).",
    ];
  }

  function showCameraHelp(reason) {
    const modal = $("kiosk-camera-help");
    const stepsEl = $("kiosk-camera-help-steps");
    const lead = $("kiosk-camera-help-lead");
    if (!modal || !stepsEl) return;
    const steps = cameraHelpSteps();
    stepsEl.innerHTML = steps.map((s) => `<li>${escapeHtml(s)}</li>`).join("");
    let extra = "";
    if (reason === "denied" || reason === "NotAllowedError") {
      extra = " Η κάμερα είναι αποκλεισμένη — άλλαξε τις ρυθμίσεις παρακάτω.";
    } else if (reason === "unsupported") {
      extra = " Ο browser δεν υποστηρίζει κάμερα — δοκίμασε Safari ή Chrome.";
    }
    if (lead) {
      lead.textContent =
        "Για σάρωση QR χρειάζεται κάμερα." + extra;
    }
    modal.classList.remove("hidden");
    modal.setAttribute("aria-hidden", "false");
  }

  function hideCameraHelp() {
    const modal = $("kiosk-camera-help");
    if (!modal) return;
    modal.classList.add("hidden");
    modal.setAttribute("aria-hidden", "true");
  }

  async function ensureCameraAccess() {
    if (!navigator.mediaDevices?.getUserMedia) {
      return { ok: false, reason: "unsupported" };
    }
    if (navigator.permissions?.query) {
      try {
        const perm = await navigator.permissions.query({ name: "camera" });
        if (perm.state === "denied") {
          return { ok: false, reason: "denied" };
        }
      } catch {
        /* ignore — not all browsers support camera permission query */
      }
    }
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        video: { facingMode: { ideal: "environment" } },
        audio: false,
      });
      stream.getTracks().forEach((t) => t.stop());
      return { ok: true };
    } catch (e) {
      const name = e?.name || "";
      if (name === "NotAllowedError" || name === "PermissionDeniedError") {
        return { ok: false, reason: "denied" };
      }
      if (name === "NotFoundError" || name === "DevicesNotFoundError") {
        return { ok: false, reason: "notfound" };
      }
      return { ok: false, reason: name || "error", message: e?.message };
    }
  }

  let pendingScannerTitle = "";
  let pendingQrPayload = null;

  function hidePunchConfirm() {
    const modal = $("kiosk-punch-confirm");
    if (!modal) return;
    modal.classList.add("hidden");
    modal.setAttribute("aria-hidden", "true");
    const warn = $("kiosk-confirm-warning");
    if (warn) warn.classList.add("hidden");
  }

  function showPunchConfirm(movementType, detailsText, warningText) {
    const modal = $("kiosk-punch-confirm");
    const movEl = $("kiosk-confirm-movement");
    const detEl = $("kiosk-confirm-details");
    const warnEl = $("kiosk-confirm-warning");
    if (!modal || !movEl || !detEl) return;
    movEl.textContent =
      movementType === "ARRIVAL"
        ? "Check-in · Προσέλευση"
        : "Check-out · Αποχώρηση";
    detEl.textContent = detailsText || "—";
    if (warnEl) {
      if (warningText) {
        warnEl.textContent = warningText;
        warnEl.classList.remove("hidden");
      } else {
        warnEl.textContent = "";
        warnEl.classList.add("hidden");
      }
    }
    modal.classList.remove("hidden");
    modal.setAttribute("aria-hidden", "false");
  }

  async function loadPunchPreview(movementType, qrPayload) {
    const res = await fetch("/api/kiosk/preview", {
      method: "POST",
      headers: headers(),
      body: JSON.stringify({
        movement_type: movementType,
        qr_payload: qrPayload,
        company_id: getSelectedCompanyId(),
      }),
    });
    const data = await safeJson(res);
    if (!res.ok) throw new Error(data.error || "Σφάλμα προεπισκόπησης");
    return data;
  }

  async function openPunchConfirm(movementType, qrPayload) {
    pendingQrPayload = qrPayload;
    showPunchConfirm(movementType, "Φόρτωση στοιχείων…", "");
    try {
      const data = await loadPunchPreview(movementType, qrPayload);
      const lines = [];
      if (data.company_name) lines.push(`Εταιρεία: ${data.company_name}`);
      if (data.afm) lines.push(`ΑΦΜ: ${data.afm}`);
      else lines.push("ΑΦΜ: δεν αναγνωρίστηκε από το QR");
      if (data.employee?.display_name) {
        lines.push(`Εργαζόμενος: ${data.employee.display_name}`);
      } else if (data.afm) {
        lines.push("Εργαζόμενος: δεν βρέθηκε — κάνε Sync προσωπικού.");
      }
      const warning = !data.afm
        ? "Δεν μπορεί να σταλεί χωρίς έγκυρο ΑΦΜ στο QR."
        : !data.employee
          ? "Ο εργαζόμενος δεν είναι στη λίστα — κάνε Sync πριν την αποστολή."
          : "";
      showPunchConfirm(movementType, lines.join("\n"), warning);
      const yesBtn = $("kiosk-btn-confirm-yes");
      if (yesBtn) yesBtn.disabled = !data.afm;
    } catch (e) {
      showPunchConfirm(
        movementType,
        "Δεν φορτώθηκαν στοιχεία.\n" + (e.message || ""),
        "Έλεγξε σύνδεση και ξανάδοκίμασε."
      );
      const yesBtn = $("kiosk-btn-confirm-yes");
      if (yesBtn) yesBtn.disabled = true;
    }
  }

  async function confirmAndSubmitPunch() {
    const movement = pendingMovement;
    const payload = pendingQrPayload;
    if (!movement || !payload) return;
    hidePunchConfirm();
    pendingQrPayload = null;
    const yesBtn = $("kiosk-btn-confirm-yes");
    if (yesBtn) {
      yesBtn.disabled = true;
      yesBtn.textContent = "Αποστολή…";
    }
    try {
      const result = await submitPunch(movement, payload);
      const name = result.employee?.display_name || "";
      const label = result.movement_label || movement;
      const proto = result.protocol ? `\nΠρωτόκολλο: ${result.protocol}` : "";
      showToast(`${label}\n${name}${proto}`, false);
      setStatus("Έτοιμο για επόμενο scan", "ok");
    } catch (e) {
      showToast(e.message || "Σφάλμα", true);
      setStatus(e.message || "Σφάλμα", "err");
    } finally {
      if (yesBtn) {
        yesBtn.disabled = false;
        yesBtn.textContent = "Επιβεβαίωση & αποστολή";
      }
      pendingMovement = null;
      scanHandled = false;
    }
  }

  function cancelPunchConfirm() {
    hidePunchConfirm();
    pendingQrPayload = null;
    scanHandled = false;
    const movement = pendingMovement;
    const title = pendingScannerTitle;
    if (movement && title) void startScanner(movement, title);
  }

  async function stopScanner(opts = {}) {
    $("kiosk-scanner-overlay")?.classList.add("hidden");
    $("kiosk-scanner-overlay")?.setAttribute("aria-hidden", "true");
    if (!opts.keepPending) {
      scanHandled = false;
      pendingMovement = null;
    }
    if (scanner) {
      try {
        await scanner.stop();
        scanner.clear();
      } catch (_) {
        /* ignore */
      }
      scanner = null;
    }
  }

  async function onScanSuccess(decodedText) {
    if (scanHandled || !pendingMovement) return;
    scanHandled = true;
    const payload = (decodedText || "").trim();
    if (!payload) {
      scanHandled = false;
      return;
    }
    await stopScanner({ keepPending: true });
    void openPunchConfirm(pendingMovement, payload);
  }

  async function startScanner(movementType, title) {
    if (!config) {
      showToast("Άνοιξε ☰ → διάλεξε εταιρεία → Σύνδεση Ergani.", true);
      return;
    }
    pendingMovement = movementType;
    pendingScannerTitle = title;
    scanHandled = false;

    const cam = await ensureCameraAccess();
    if (!cam.ok) {
      showCameraHelp(cam.reason);
      setStatus("Άνοιξε τις ρυθμίσεις κάμερας (βλ. οδηγίες).", "err");
      return;
    }

    hideCameraHelp();
    const titleEl = $("kiosk-scanner-title");
    if (titleEl) titleEl.textContent = title;
    const overlay = $("kiosk-scanner-overlay");
    overlay?.classList.remove("hidden");
    overlay?.setAttribute("aria-hidden", "false");

    scanner = new Html5Qrcode("kiosk-qr-reader");
    try {
      await scanner.start(
        { facingMode: "environment" },
        { fps: 10, qrbox: { width: 250, height: 250 } },
        onScanSuccess,
        () => {}
      );
    } catch (e) {
      await stopScanner();
      const reason = e?.name || "error";
      showCameraHelp(reason === "NotAllowedError" ? "denied" : reason);
      setStatus("Δεν ανοίγει η κάμερα — δες τις ρυθμίσεις.", "err");
    }
  }

  async function retryCameraAndScan() {
    hideCameraHelp();
    if (!pendingMovement) return;
    await startScanner(pendingMovement, pendingScannerTitle);
  }

  function onAdminHotspotTap() {
    adminTapCount += 1;
    clearTimeout(adminTapTimer);
    adminTapTimer = setTimeout(() => {
      adminTapCount = 0;
    }, 2500);
    if (adminTapCount >= 5 && typeof window.openAdminLogin === "function") {
      adminTapCount = 0;
      closeDrawer();
      window.openAdminLogin();
    }
  }

  function bindAdminHotspots() {
    for (const id of [
      "kiosk-admin-hotspot-version",
      "kiosk-admin-hotspot-title",
      "kiosk-admin-hotspot-brand",
    ]) {
      const el = $(id);
      if (el && !el.dataset.adminHotspotBound) {
        el.dataset.adminHotspotBound = "1";
        el.addEventListener("click", onAdminHotspotTap);
      }
    }
  }

  function bindEvents() {
    if (eventsBound) return;
    eventsBound = true;
    bindAdminHotspots();
    $("kiosk-menu-btn")?.addEventListener("click", openDrawer);
    $("kiosk-drawer-backdrop")?.addEventListener("click", closeDrawer);
    $("kiosk-btn-connect")?.addEventListener("click", () => void connectErgani());

    $("kiosk-company-list")?.addEventListener("click", (e) => {
      const btn = e.target.closest(".kiosk-company-pick");
      if (!btn) return;
      pickCompany(parseInt(btn.dataset.id, 10));
    });

    document.querySelectorAll("[data-kiosk-nav]").forEach((btn) => {
      btn.addEventListener("click", () => {
        const nav = btn.dataset.kioskNav;
        closeDrawer();
        if (nav === "home") showView("home");
        else if (nav === "statements") showView("statements");
        else if (nav === "sync") void runSync();
      });
    });

    $("kiosk-btn-arrival")?.addEventListener("click", () => {
      startScanner("ARRIVAL", "Προσέλευση — στόχευσε το QR");
    });
    $("kiosk-btn-departure")?.addEventListener("click", () => {
      startScanner("DEPARTURE", "Αποχώρηση — στόχευσε το QR");
    });
    $("kiosk-btn-scanner-cancel")?.addEventListener("click", () => {
      hidePunchConfirm();
      pendingQrPayload = null;
      void stopScanner();
    });
    $("kiosk-btn-confirm-yes")?.addEventListener("click", () => void confirmAndSubmitPunch());
    $("kiosk-btn-confirm-no")?.addEventListener("click", cancelPunchConfirm);
    document
      .querySelector(".kiosk-punch-confirm-backdrop")
      ?.addEventListener("click", cancelPunchConfirm);
    $("kiosk-btn-camera-retry")?.addEventListener("click", () => void retryCameraAndScan());
    $("kiosk-btn-camera-close")?.addEventListener("click", hideCameraHelp);
    document
      .querySelector(".kiosk-camera-help-backdrop")
      ?.addEventListener("click", hideCameraHelp);
  }

  async function isWebAuthenticated() {
    if (!webGateEnabled()) {
      return true;
    }
    try {
      const res = await fetch("/api/kiosk/web-auth/status", { credentials: "same-origin" });
      if (!res.ok) {
        return false;
      }
      const data = await safeJson(res);
      window.KIOSK_WEB_GATE = Boolean(data.web_gate);
      bootstrap = { ...(bootstrap || {}), web_gate: window.KIOSK_WEB_GATE };
      return !data.web_gate || Boolean(data.authenticated);
    } catch {
      return false;
    }
  }

  async function enterKioskFlow() {
    document.body.classList.add("kiosk-only");
    $("app-gate")?.classList.add("hidden");
    hideSetup();
    $("app-kiosk")?.classList.add("hidden");

    if (webGateEnabled()) {
      const authed = await isWebAuthenticated();
      if (!authed) {
        showLogin();
        return;
      }
      try {
        await fetchBootstrap();
      } catch (e) {
        showLogin();
        setLoginStatus(e.message || "Αποτυχία φόρτωσης.", "err");
        return;
      }
    }

    if (needsSetup()) {
      showSetup();
      showSetupCompanyStep();
      await loadSetupScreen();
      return;
    }
    window.KioskMode.start();
  }

  window.KioskMode = {
    needsSetup,
    showSetup,
    hideSetup,
    showLogin,
    enterKioskFlow,
    start() {
      document.body.classList.add("kiosk-active");
      hideSetup();
      bindEvents();
      updateClock();
      if (!clockTimer) clockTimer = setInterval(updateClock, 1000);
      showView("home");
      void (async () => {
        try {
          await loadCompanies();
          await loadConfig();
        } catch (e) {
          setStatus(e.message || "Σφάλμα φόρτωσης", "err");
        }
      })();
    },
    stop() {
      hidePunchConfirm();
      pendingQrPayload = null;
      void stopScanner();
      hideCameraHelp();
      closeDrawer();
      hideSetup();
      document.body.classList.remove("kiosk-active");
    },
  };
})();
