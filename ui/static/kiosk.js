(function () {
  const key = (window.KIOSK_KEY || "").trim();
  let config = null;
  let scanner = null;
  let pendingMovement = null;
  let scanHandled = false;

  const $ = (id) => document.getElementById(id);

  let adminTapCount = 0;
  let adminTapTimer = null;

  function headers() {
    return {
      "Content-Type": "application/json",
      "X-Kiosk-Key": key,
    };
  }

  function setStatus(text, kind) {
    const el = $("status-line");
    el.textContent = text || "";
    el.className = "status-line" + (kind ? ` is-${kind}` : "");
  }

  function showToast(text, isError) {
    const el = $("toast");
    el.textContent = text;
    el.className = "toast " + (isError ? "is-err" : "is-ok");
    el.classList.remove("hidden");
    clearTimeout(showToast._t);
    showToast._t = setTimeout(() => el.classList.add("hidden"), 5000);
  }

  function updateClock() {
    const now = new Date();
    $("clock-time").textContent = now.toLocaleTimeString("el-GR", {
      hour: "2-digit",
      minute: "2-digit",
      hour12: false,
    });
    $("clock-date").textContent = now.toLocaleDateString("el-GR", {
      weekday: "long",
      day: "numeric",
      month: "numeric",
    });
  }

  async function loadConfig() {
    if (!key) {
      setStatus("Server: λείπει KIOSK_KEY.", "err");
      return;
    }
    try {
      const res = await fetch("/api/kiosk/config", { headers: headers() });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || "Σφάλμα ρύθμισης");
      config = data;
      $("company-name").textContent = data.company_name || "Ergani";
      setStatus("Έτοιμο — πάτα Check-in ή Check-out", "ok");
    } catch (e) {
      setStatus(e.message || "Δεν συνδέθηκε με server", "err");
    }
  }

  async function submitPunch(movementType, qrPayload) {
    const res = await fetch("/api/kiosk/punch", {
      method: "POST",
      headers: headers(),
      body: JSON.stringify({
        movement_type: movementType,
        qr_payload: qrPayload,
        employer_afm: config?.employer_afm,
        branch_number: config?.branch_number ?? 0,
      }),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || "Αποτυχία υποβολής");
    return data;
  }

  async function stopScanner() {
    const overlay = $("scanner-overlay");
    overlay.classList.add("hidden");
    overlay.setAttribute("aria-hidden", "true");
    scanHandled = false;
    pendingMovement = null;
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
    await stopScanner();
    try {
      const result = await submitPunch(pendingMovement, payload);
      const name = result.employee?.display_name || "";
      const label = result.movement_label || pendingMovement;
      const proto = result.protocol ? `\nΠρωτόκολλο: ${result.protocol}` : "";
      showToast(`${label}\n${name}${proto}`, false);
      setStatus("Επιτυχία — έτοιμο για επόμενο scan", "ok");
    } catch (e) {
      showToast(e.message || "Σφάλμα", true);
      setStatus(e.message || "Σφάλμα", "err");
    }
  }

  async function startScanner(movementType, title) {
    if (!config) {
      showToast("Δεν έχει φορτωθεί η εταιρεία.", true);
      return;
    }
    pendingMovement = movementType;
    scanHandled = false;
    $("scanner-title").textContent = title;
    const overlay = $("scanner-overlay");
    overlay.classList.remove("hidden");
    overlay.setAttribute("aria-hidden", "false");

    scanner = new Html5Qrcode("qr-reader");
    try {
      await scanner.start(
        { facingMode: "environment" },
        { fps: 10, qrbox: { width: 250, height: 250 } },
        onScanSuccess,
        () => {}
      );
    } catch (e) {
      await stopScanner();
      showToast(
        "Δεν ανοίγει η κάμερα. Επίτρεψε πρόσβαση ή χρησιμοποίησε HTTPS.",
        true
      );
    }
  }

  $("btn-arrival").addEventListener("click", () => {
    startScanner("ARRIVAL", "Προσέλευση — στόχευσε το QR");
  });

  $("btn-departure").addEventListener("click", () => {
    startScanner("DEPARTURE", "Αποχώρηση — στόχευσε το QR");
  });

  $("btn-scanner-cancel").addEventListener("click", () => {
    void stopScanner();
  });

  function showAdminLogin() {
    $("admin-overlay").classList.remove("hidden");
    $("admin-overlay").setAttribute("aria-hidden", "false");
    $("admin-login-error").classList.add("hidden");
    $("admin-password").value = "";
    $("admin-username").focus();
  }

  function hideAdminLogin() {
    $("admin-overlay").classList.add("hidden");
    $("admin-overlay").setAttribute("aria-hidden", "true");
  }

  function onAdminHotspotTap() {
    adminTapCount += 1;
    clearTimeout(adminTapTimer);
    adminTapTimer = setTimeout(() => {
      adminTapCount = 0;
    }, 2500);
    if (adminTapCount >= 5) {
      adminTapCount = 0;
      showAdminLogin();
    }
  }

  async function adminLoginSubmit(event) {
    event.preventDefault();
    const username = $("admin-username").value.trim();
    const password = $("admin-password").value;
    const errEl = $("admin-login-error");
    errEl.classList.add("hidden");
    try {
      const loginRes = await fetch("/api/auth/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify({ username, password }),
      });
      const loginData = await loginRes.json();
      if (!loginRes.ok) {
        throw new Error(loginData.error || "Λάθος όνομα ή κωδικός.");
      }
      const companies = loginData.companies || [];
      if (!companies.length) {
        window.location.href = "/";
        return;
      }
      const pick =
        companies.find((c) => c.id === config?.company_id) || companies[0];
      const selRes = await fetch("/api/auth/select-company", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify({ company_id: pick.id }),
      });
      const selData = await selRes.json();
      if (!selRes.ok) {
        throw new Error(selData.error || "Αποτυχία σύνδεσης εταιρείας.");
      }
      window.location.href = "/";
    } catch (e) {
      errEl.textContent = e.message || "Αποτυχία σύνδεσης";
      errEl.classList.remove("hidden");
    }
  }

  $("admin-hotspot").addEventListener("click", onAdminHotspotTap);
  $("admin-login-form").addEventListener("submit", (e) => {
    void adminLoginSubmit(e);
  });
  $("btn-admin-cancel").addEventListener("click", hideAdminLogin);

  updateClock();
  setInterval(updateClock, 1000);
  void loadConfig();
})();
