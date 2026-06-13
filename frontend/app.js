
  // ============================ Estado y utilidades ============================
  const API = "/api/v1";
  const LIVE_VIEWS = ["inicio", "cuadros", "alarmas", "control"];
  const STATUS_COLOR = { ok: "#22c55e", warning: "#f59e0b", critical: "#ef4444" };
  const state = { token: localStorage.getItem("ph_token") || null, me: null, view: "inicio", cabinets: [], mapMode: "estado", tileStyle: localStorage.getItem("ph_tile") || "oscuro", idleMinutes: 10, tz: "Europe/Madrid" };

  function emblemAll() {
    const tpl = document.getElementById("phoenix-svg").content;
    document.querySelectorAll(".emblem").forEach(e => { if (!e.childElementCount) e.appendChild(tpl.cloneNode(true)); });
  }
  function $(s) { return document.querySelector(s); }
  function el(tag, cls, html) { const n = document.createElement(tag); if (cls) n.className = cls; if (html != null) n.innerHTML = html; return n; }
  function has(perm) { const p = state.me?.permissions || []; return p.includes("*") || p.includes(perm); }
  // Capitaliza la primera letra para mostrar (ej. "pepe" → "Pepe"). El valor
  // guardado en BD no cambia; el login es case-insensitive.
  function cap(s) { return (s && s.length) ? s[0].toUpperCase() + s.slice(1) : (s || ""); }
  // Nombre visible de un rango ("owner" → "Phoenix", "admin_proyecto" → "Director").
  function rankLabel(id) { const r = (state.ranksCatalog || []).find(x => x.id === id); return r ? r.label : id; }
  // Formato de fechas/horas en la zona horaria del DESPLIEGUE (no la del
  // navegador). state.tz lo fija /auth/info (Europe/Madrid, Atlantic/Canary…).
  function _tzOpts(extra) { return Object.assign({ timeZone: state.tz || "Europe/Madrid" }, extra || {}); }
  function fmtDateTime(x) { try { return new Date(x).toLocaleString("es-ES", _tzOpts()); } catch (e) { return ""; } }
  function fmtTime(x) { try { return new Date(x).toLocaleTimeString("es-ES", _tzOpts()); } catch (e) { return ""; } }
  function fmtDate(x) { try { return new Date(x).toLocaleDateString("es-ES", _tzOpts()); } catch (e) { return ""; } }
  function toast(msg, isErr) { const t = $("#toast"); t.textContent = msg; t.className = "toast show" + (isErr ? " err" : ""); setTimeout(() => t.className = "toast", 3200); }
  function netMsg(e) {
    return /failed to fetch|networkerror|load failed/i.test(e?.message || "")
      ? "No se puede conectar con el backend. Arranca el servidor y abre http://localhost:8000/ui/ (no abras el .html directamente)."
      : (e?.message || "Error");
  }
  function fmt(t, key, unit, d = 1) { const v = t?.[key]; return v == null ? "—" : Number(v).toFixed(d) + unit; }

  async function api(path, opts = {}) {
    opts.headers = Object.assign({ "Content-Type": "application/json" }, opts.headers || {});
    if (state.token) opts.headers["Authorization"] = "Bearer " + state.token;
    opts.credentials = "include";  // device cookie travels with every call
    const r = await fetch(API + path, opts);
    if (r.status === 401) { logout(); throw new Error("Sesión expirada"); }
    const data = await r.json().catch(() => ({}));
    if (!r.ok) throw new Error(data.detail || data.error || ("HTTP " + r.status));
    return data;
  }

  // ============================ Autenticación ============================
  // Login escalonado, una credencial por ventana:
  //   1 → usuario + contraseña + PIN
  //   2 → patrón (si la cuenta lo tiene)
  //   3 → código 2FA (si la cuenta lo tiene)
  // Cada respuesta trae next_step ("pattern"|"totp") o un access_token final.
  async function loginStep1(user, pass, pin) {
    const body = new URLSearchParams({ username: user, password: pass });
    if (pin) body.append("pin", pin);
    const r = await fetch(API + "/auth/login", { method: "POST", credentials: "include", headers: { "Content-Type": "application/x-www-form-urlencoded" }, body });
    const data = await r.json().catch(() => ({}));
    if (r.status === 429) throw new Error(data.detail || "Cuenta bloqueada temporalmente.");
    if (!r.ok) throw new Error(data.detail || "Credenciales inválidas");
    if (data.access_token) { await acceptToken(data.access_token); return { done: true }; }
    return { done: false, challenge: data.challenge_token, next: data.next_step };
  }
  async function loginStep2(challenge, pattern) {
    const r = await fetch(API + "/auth/login/pattern", {
      method: "POST", credentials: "include", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ challenge_token: challenge, pattern }),
    });
    const data = await r.json().catch(() => ({}));
    if (r.status === 429) throw new Error(data.detail || "Cuenta bloqueada temporalmente.");
    if (!r.ok) throw new Error(data.detail || "Patrón incorrecto");
    if (data.access_token) { await acceptToken(data.access_token); return { done: true }; }
    return { done: false, challenge: data.challenge_token, next: data.next_step };
  }
  async function loginStep3(challenge, code) {
    const r = await fetch(API + "/auth/login/totp", {
      method: "POST", credentials: "include", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ challenge_token: challenge, totp: code }),
    });
    const data = await r.json().catch(() => ({}));
    if (r.status === 429) throw new Error(data.detail || "Cuenta bloqueada temporalmente.");
    if (!r.ok) throw new Error(data.detail || "Código 2FA incorrecto");
    await acceptToken(data.access_token);
  }
  async function acceptToken(tok) {
    state.token = tok; localStorage.setItem("ph_token", tok); await boot();
  }
  function showLoginStep(step) {
    $("#login-step1").classList.toggle("hidden", step !== 1);
    $("#login-step2").classList.toggle("hidden", step !== 2);
    $("#login-step3").classList.toggle("hidden", step !== 3);
    $("#login-err").textContent = "";
    if (step === 1) {
      ["li-pass", "li-pin"].forEach(id => { const e = document.getElementById(id); if (e) e.value = ""; });
      setTimeout(() => $("#li-user").focus(), 50);
    }
    if (step === 3) { const t = $("#li-totp3"); if (t) { t.value = ""; setTimeout(() => t.focus(), 50); } }
  }
  async function refreshMe() {
    try {
      state.me = await api("/auth/me");
      $("#btn-lock").style.display = (state.me.has_pin || state.me.has_pattern) ? "" : "none";
    } catch (e) {}
  }
  function logout() {
    state.token = null; state.me = null; localStorage.removeItem("ph_token");
    if (window._ws) { try { window._ws.close(); } catch (e) {} window._ws = null; }
    if (window._dockTimer) { clearInterval(window._dockTimer); window._dockTimer = null; }
    state.eventDock = []; state.dockOpen = false;
    state.projects = []; state.activeProject = null;
    const chip = $("#project-chip"); if (chip) chip.classList.add("hidden");
    const dock = $("#event-dock"); if (dock) { dock._wired = false; dock.classList.add("collapsed"); }
    clearTimeout(window._idle);
    $("#app").classList.add("hidden"); $("#login").classList.remove("hidden");
  }

  // ====== Inactividad con cuenta atrás (estilo Hydra) ============
  // Tres umbrales antes de cerrar: aviso suave a -2 min, aviso a -1 min,
  // y cuenta atrás visible los últimos 30 s. "Sigo aquí" lo cancela.
  function armIdle() {
    if (!state.token) return;
    clearTimeout(window._idle); clearTimeout(window._warn); clearTimeout(window._count);
    const total = (state.idleMinutes || 10) * 60000;
    const warnAt = Math.max(total - 60000, total * 0.7);
    const countdownAt = Math.max(total - 30000, total * 0.9);
    window._warn = setTimeout(() => toast("La sesión se cerrará pronto por inactividad. Mueve el ratón para seguir.", true), warnAt);
    window._count = setTimeout(() => showIdleCountdown(), countdownAt);
    window._idle = setTimeout(() => { closeIdleCountdown(); logout(); toast("Sesión cerrada por inactividad.", true); }, total);
  }
  function startIdleWatch() {
    if (!window._idleBound) {
      ["mousemove", "keydown", "click", "scroll", "touchstart"].forEach(ev => document.addEventListener(ev, () => { if (!window._idleModalOpen) armIdle(); }, { passive: true }));
      window._idleBound = true;
    }
    armIdle();
  }
  function showIdleCountdown() {
    if (window._idleModalOpen) return;
    window._idleModalOpen = true;
    const modal = el("div", "modal"); modal.id = "idle-modal";
    const card = el("div", "modal-card");
    card.innerHTML = `<h3>¿Sigues ahí?</h3><p class="desc">La sesión se cerrará por inactividad.</p><div class="countdown" id="idle-cd">30</div>`;
    const actions = el("div", "actions");
    const stay = el("button", "btn", "Seguir trabajando"); stay.onclick = closeIdleCountdown;
    const out = el("button", "btn ghost", "Cerrar sesión"); out.onclick = () => { closeIdleCountdown(); logout(); };
    actions.append(stay, out); card.append(actions); modal.append(card); document.body.append(modal);
    let left = 30;
    window._cdInterval = setInterval(() => {
      left--; const cd = document.getElementById("idle-cd"); if (cd) cd.textContent = left;
      if (left <= 0) { clearInterval(window._cdInterval); closeIdleCountdown(); logout(); toast("Sesión cerrada por inactividad.", true); }
    }, 1000);
  }
  function closeIdleCountdown() {
    window._idleModalOpen = false;
    clearInterval(window._cdInterval);
    const m = document.getElementById("idle-modal"); if (m) m.remove();
    armIdle();
  }

  // ====== Patrón de 9 puntos (estilo móvil) ============
  // Widget reutilizable: rejilla 3×3 + línea SVG. Captura el trazo con
  // pointer events (ratón y táctil) y reporta la secuencia "0..8" vía onChange.
  function makePatternPad(onChange) {
    const wrap = el("div", "pattern-pad");
    const NS = "http://www.w3.org/2000/svg";
    const svg = document.createElementNS(NS, "svg"); svg.setAttribute("class", "pattern-lines"); svg.setAttribute("viewBox", "0 0 300 300");
    const poly = document.createElementNS(NS, "polyline"); poly.setAttribute("class", "pp-line"); svg.append(poly);
    wrap.append(svg);
    const grid = el("div", "pattern-grid"); const dots = [];
    for (let i = 0; i < 9; i++) { const d = el("div", "pp-dot"); d.append(el("div", "pp-dot-in")); grid.append(d); dots.push(d); }
    wrap.append(grid);
    let seq = [], drawing = false;
    const centers = () => { const pr = wrap.getBoundingClientRect(); return dots.map(d => { const r = d.getBoundingClientRect(); return { x: (r.left + r.width / 2 - pr.left) / pr.width * 300, y: (r.top + r.height / 2 - pr.top) / pr.height * 300 }; }); };
    const redraw = (px, py) => { const c = centers(); const pts = seq.map(i => `${c[i].x},${c[i].y}`); if (px != null) pts.push(`${px},${py}`); poly.setAttribute("points", pts.join(" ")); };
    const addDot = i => { if (seq.includes(i)) return; seq.push(i); dots[i].classList.add("on"); if (navigator.vibrate) navigator.vibrate(12); redraw(); onChange && onChange(seq.join("")); };
    const hit = (x, y) => { for (let i = 0; i < 9; i++) { const r = dots[i].getBoundingClientRect(); const cx = r.left + r.width / 2, cy = r.top + r.height / 2, rad = r.width * 0.5; if ((x - cx) ** 2 + (y - cy) ** 2 <= rad * rad) return i; } return -1; };
    const reset = () => { seq = []; dots.forEach(d => d.classList.remove("on")); poly.setAttribute("points", ""); onChange && onChange(""); };
    const move = e => { if (!drawing) return; const i = hit(e.clientX, e.clientY); if (i >= 0) addDot(i); const pr = wrap.getBoundingClientRect(); redraw((e.clientX - pr.left) / pr.width * 300, (e.clientY - pr.top) / pr.height * 300); e.preventDefault(); };
    const end = () => { if (!drawing) return; drawing = false; redraw(); };
    wrap.addEventListener("pointerdown", e => { reset(); drawing = true; move(e); });
    wrap.addEventListener("pointermove", move);
    window.addEventListener("pointerup", end);
    wrap.reset = reset;
    return wrap;
  }

  // Anti-keylogger: para rotar PIN/patrón hay que demostrar que conoces el
  // actual. Si no hay credencial previa, el "actual" se omite.
  function showSetPin() {
    const hasPin = !!state.me?.has_pin;
    const modal = el("div", "modal"); const card = el("div", "modal-card");
    card.innerHTML = `<h3>${hasPin ? "Cambiar mi PIN" : "Definir mi PIN"}</h3><p class="desc">Entre 4 y 8 dígitos. Se usa en el paso 1 del login y para desbloquear la sesión.</p>`;
    const err = el("div", "err"); err.style.textAlign = "center"; err.style.minHeight = "16px";
    const form = el("div"); form.style.display = "grid"; form.style.gap = "8px";
    let curIn = null;
    if (hasPin) {
      curIn = el("input"); curIn.type = "password"; curIn.inputMode = "numeric"; curIn.maxLength = 8; curIn.placeholder = "PIN actual";
      form.append(curIn);
    }
    const newIn = el("input"); newIn.type = "password"; newIn.inputMode = "numeric"; newIn.maxLength = 8; newIn.placeholder = "PIN nuevo (4-8 dígitos)";
    form.append(newIn);
    card.append(form, err);
    const actions = el("div", "actions");
    const save = el("button", "btn", "Guardar");
    save.onclick = async () => {
      const np = newIn.value.trim();
      if (!/^\d{4,8}$/.test(np)) { err.textContent = "El PIN debe tener 4-8 dígitos."; return; }
      const payload = { pin: np };
      if (hasPin) payload.current_pin = (curIn?.value || "").trim();
      try { await api("/auth/pin", { method: "POST", body: JSON.stringify(payload) }); toast("PIN actualizado"); modal.remove(); await refreshMe(); }
      catch (e) { err.textContent = e.message; }
    };
    const cancel = el("button", "btn ghost", "Cancelar"); cancel.onclick = () => modal.remove();
    const del = hasPin ? el("button", "btn ghost", "Borrar PIN") : null;
    if (del) del.onclick = async () => { try { await api("/auth/pin", { method: "DELETE" }); toast("PIN borrado"); modal.remove(); await refreshMe(); } catch (e) { err.textContent = e.message; } };
    actions.append(save, ...(del ? [del] : []), cancel);
    card.append(actions); modal.append(card); document.body.append(modal);
    setTimeout(() => (curIn || newIn).focus(), 50);
  }

  function showSetPattern() {
    const hasPat = !!state.me?.has_pattern;
    const modal = el("div", "modal"); const card = el("div", "modal-card");
    card.innerHTML = `<h3>${hasPat ? "Cambiar mi patrón" : "Definir mi patrón"}</h3><p class="desc">${hasPat ? "Dibuja primero tu <strong>patrón actual</strong>, luego el nuevo." : "Une al menos <strong>4 puntos</strong> sin levantar el dedo. Es el paso 2 del login."}</p>`;
    const err = el("div", "err"); err.style.textAlign = "center"; err.style.minHeight = "16px";
    const stage = el("div", "muted"); stage.style.textAlign = "center"; stage.style.fontSize = "12px";
    let current = "", next = "";
    let phase = hasPat ? "current" : "next";
    const updateStage = () => { stage.textContent = phase === "current" ? "1) Patrón actual" : (hasPat ? "2) Nuevo patrón" : "Nuevo patrón"); };
    const pad = makePatternPad(seq => {
      if (phase === "current") { current = seq; err.textContent = ""; }
      else { next = seq; err.textContent = ""; }
    });
    card.append(stage, pad, err);
    updateStage();
    const actions = el("div", "actions");
    const main = el("button", "btn", hasPat ? "Siguiente" : "Guardar");
    const setMainLabel = () => { main.textContent = (phase === "current") ? "Siguiente" : "Guardar"; };
    main.onclick = async () => {
      if (phase === "current") {
        if (current.length < 4) { err.textContent = "Une al menos 4 puntos."; return; }
        phase = "next"; pad.reset(); next = ""; updateStage(); setMainLabel(); return;
      }
      if (next.length < 4) { err.textContent = "Une al menos 4 puntos."; return; }
      try {
        const payload = { pattern: next };
        if (hasPat) payload.current_pattern = current;
        await api("/auth/pattern", { method: "POST", body: JSON.stringify(payload) });
        toast("Patrón guardado"); modal.remove(); await refreshMe();
      } catch (e) { err.textContent = e.message; if (hasPat) { phase = "current"; pad.reset(); current = ""; updateStage(); setMainLabel(); } }
    };
    const rep = el("button", "btn ghost", "Repetir"); rep.onclick = () => { pad.reset(); if (phase === "current") current = ""; else next = ""; };
    const del = hasPat ? el("button", "btn ghost", "Borrar patrón") : null;
    if (del) del.onclick = async () => { try { await api("/auth/pattern", { method: "DELETE" }); toast("Patrón borrado"); modal.remove(); await refreshMe(); } catch (e) { err.textContent = e.message; } };
    const cancel = el("button", "btn ghost", "Cancelar"); cancel.onclick = () => modal.remove();
    actions.append(main, rep, ...(del ? [del] : []), cancel);
    card.append(actions); modal.append(card); document.body.append(modal);
  }

  // 2FA TOTP (Google Authenticator). Cuarta credencial, activable por el
  // usuario. Si ya está activo, ofrece desactivarlo; si no, genera el
  // secreto, lo muestra para introducir en la app y pide un código para
  // confirmar y activar.
  // Carga (una vez) una librería QR ligera desde CDN. Si no hay internet,
  // devuelve null y el modal cae al método de clave manual. Mismo supuesto
  // que las tiles del mapa (el navegador del cliente tiene salida a la red).
  function loadQrLib() {
    if (window.QRCode) return Promise.resolve(window.QRCode);
    if (window._qrLibPromise) return window._qrLibPromise;
    window._qrLibPromise = new Promise((resolve) => {
      const s = document.createElement("script");
      s.src = "https://cdnjs.cloudflare.com/ajax/libs/qrcodejs/1.0.0/qrcode.min.js";
      s.onload = () => resolve(window.QRCode || null);
      s.onerror = () => resolve(null);
      document.head.append(s);
    });
    return window._qrLibPromise;
  }
  // Caja con las claves de recuperación + copiar + descargar .txt.
  function recoveryBox(codes) {
    const box = el("div"); box.style.cssText = "margin:10px 0";
    box.innerHTML = `<div class="muted" style="font-size:12px;margin-bottom:6px">🔑 <strong>Claves de recuperación</strong> · guárdalas en lugar seguro. Cada una sirve UNA vez si pierdes el móvil. No se vuelven a mostrar.</div>`;
    const grid = el("div"); grid.style.cssText = "display:grid;grid-template-columns:1fr 1fr;gap:6px;font-family:var(--mono,monospace);font-size:14px;background:rgba(255,255,255,.05);padding:10px;border-radius:8px;user-select:all";
    codes.forEach(cd => { const d = el("div"); d.textContent = cd; grid.append(d); });
    box.append(grid);
    const row = el("div", "row"); row.style.cssText = "gap:8px;margin-top:8px";
    const copy = el("button", "btn ghost sm", "Copiar");
    copy.onclick = () => { navigator.clipboard?.writeText(codes.join("\n")); toast("Claves copiadas"); };
    const dl = el("button", "btn ghost sm", "Descargar .txt");
    dl.onclick = () => {
      const blob = new Blob([`Phoenix Light · Claves de recuperación 2FA\nUsuario: ${state.me?.username || ""}\n\n` + codes.join("\n")], { type: "text/plain" });
      const a = document.createElement("a"); a.href = URL.createObjectURL(blob); a.download = "phoenix-recovery-codes.txt"; a.click();
    };
    row.append(copy, dl); box.append(row);
    return box;
  }

  // Autoformatea un input de código 2FA como "123 456" (3+espacio+3) mientras
  // se teclea. Si el usuario mete una clave de recuperación (tiene letras o
  // guion) no lo toca. El backend ignora los espacios igualmente.
  function attachTotpSpace(inp) {
    inp.addEventListener("input", () => {
      if (/[A-Za-z-]/.test(inp.value)) return;  // clave de recuperación → no formatear
      const d = inp.value.replace(/\D/g, "").slice(0, 6);
      inp.value = d.length > 3 ? d.slice(0, 3) + " " + d.slice(3) : d;
    });
  }

  async function showSetTotp() {
    const modal = el("div", "modal"); const card = el("div", "modal-card"); card.style.maxWidth = "460px"; card.style.maxHeight = "88vh"; card.style.overflowY = "auto";
    const err = el("div", "err"); err.style.textAlign = "center"; err.style.minHeight = "16px";

    // --- Ya activado: estado + claves restantes + regenerar + desactivar ---
    if (state.me?.has_totp) {
      const left = state.me?.totp_recovery_remaining ?? 0;
      card.innerHTML = `<h3>2FA activado ✅</h3><p class="desc">Tu cuenta pide un código de la app al iniciar sesión.</p>
        <div class="muted" style="font-size:13px">🔑 Claves de recuperación sin usar: <strong>${left}</strong></div>`;
      const regenBox = el("div"); card.append(regenBox);
      const actions = el("div", "actions");
      const regen = el("button", "btn ghost", "Regenerar claves");
      regen.onclick = async () => {
        if (!confirm("Esto invalida tus claves actuales y genera unas nuevas. ¿Continuar?")) return;
        try { const r = await api("/auth/totp/recovery", { method: "POST" }); regenBox.innerHTML = ""; regenBox.append(recoveryBox(r.recovery_codes)); toast("Nuevas claves generadas"); await refreshMe(); }
        catch (e) { err.textContent = e.message; }
      };
      const del = el("button", "btn ghost", "Desactivar 2FA"); del.style.color = "#ef4444";
      del.onclick = async () => {
        if (!confirm("¿Desactivar el 2FA? Tu cuenta dejará de pedir el código.")) return;
        try { await api("/auth/totp", { method: "DELETE" }); toast("2FA desactivado"); modal.remove(); await refreshMe(); }
        catch (e) { err.textContent = e.message; }
      };
      const cancel = el("button", "btn ghost", "Cerrar"); cancel.onclick = () => modal.remove();
      actions.append(regen, del, cancel);
      card.append(err, actions); modal.append(card); document.body.append(modal);
      return;
    }

    // --- Activación: QR + clave manual + claves de recuperación + confirmar ---
    card.innerHTML = `<h3>Activar 2FA</h3><p class="desc">Protege tu cuenta con un código que cambia cada 30 s, como en el banco.</p>`;
    const steps = el("div"); steps.innerHTML = `<div class="muted" style="font-size:13px">Generando clave…</div>`;
    card.append(steps, err);
    const actions = el("div", "actions");
    const cancel = el("button", "btn ghost", "Cancelar"); cancel.onclick = () => modal.remove();
    actions.append(cancel); card.append(actions);
    modal.append(card); document.body.append(modal);

    try {
      const setup = await api("/auth/totp/setup", { method: "POST" });
      const grouped = setup.secret.replace(/(.{4})/g, "$1 ").trim();
      steps.innerHTML = `<div style="text-align:center"><div class="muted" style="font-size:13px;margin-bottom:8px">Escanea el QR con <strong>Google Authenticator</strong> (o introduce la clave a mano):</div><div id="totp-qr" style="display:inline-block;background:#fff;padding:8px;border-radius:8px;min-height:160px;min-width:160px"></div></div>
        <div class="mono" style="font-size:14px;letter-spacing:2px;background:rgba(255,255,255,.05);padding:8px;border-radius:8px;margin:10px 0;text-align:center;user-select:all">${grouped}</div>`;
      // QR (best-effort): si carga la lib, lo dibujamos; si no, queda la clave.
      loadQrLib().then(QR => {
        const host = document.getElementById("totp-qr");
        if (QR && host) { host.innerHTML = ""; new QR(host, { text: setup.otpauth_uri, width: 152, height: 152, correctLevel: QR.CorrectLevel.M }); }
        else if (host) { host.innerHTML = `<div class="muted" style="font-size:11px;padding:20px">Sin QR (offline). Usa la clave de arriba.</div>`; }
      });
      // Claves de recuperación.
      steps.append(recoveryBox(setup.recovery_codes));
      // Confirmación.
      const codeIn = el("input"); codeIn.placeholder = "Código (123 456)"; codeIn.inputMode = "numeric"; codeIn.maxLength = 7; codeIn.style.cssText = "width:100%; text-align:center; font-size:18px; letter-spacing:4px; margin-top:6px";
      attachTotpSpace(codeIn);
      steps.append(codeIn);
      const confirm = el("button", "btn", "Confirmar y activar");
      confirm.onclick = async () => {
        const code = codeIn.value.replace(/\s/g, "");
        if (!/^\d{6}$/.test(code)) { err.textContent = "Introduce los 6 dígitos."; return; }
        try { await api("/auth/totp/verify", { method: "POST", body: JSON.stringify({ code }) }); toast("2FA activado ✅"); modal.remove(); await refreshMe(); }
        catch (e) { err.textContent = e.message; }
      };
      actions.insertBefore(confirm, cancel);
      setTimeout(() => codeIn.focus(), 50);
    } catch (e) { steps.innerHTML = ""; err.textContent = e.message; }
  }

  // ====== Bloqueo manual + desbloqueo con PIN o patrón ============
  function showLockScreen() {
    if (!state.token || !state.me) return;
    if (document.getElementById("lock-modal")) return;
    const hasPin = !!state.me.has_pin, hasPattern = !!state.me.has_pattern;
    if (!hasPin && !hasPattern) { toast("Define primero un PIN o un patrón.", true); return; }
    const modal = el("div", "modal"); modal.id = "lock-modal";
    const card = el("div", "modal-card");
    card.innerHTML = `<h3>Pantalla bloqueada</h3><p class="desc">Sesión de <strong>${state.me.username}</strong>.</p>`;
    const err = el("div", "err"); err.style.textAlign = "center"; err.style.minHeight = "16px"; err.id = "unlock-err";
    const body = el("div"); card.append(body, err);

    let mode = hasPin ? "pin" : "pattern";

    const tryUnlock = async (payload, badMsg) => {
      try {
        const r = await fetch(API + "/auth/unlock", { method: "POST", headers: { "Content-Type": "application/json", "Authorization": "Bearer " + state.token }, body: JSON.stringify(payload) });
        const d = await r.json().catch(() => ({}));
        if (r.status === 429) { modal.remove(); logout(); toast(d.detail || "Cuenta bloqueada por intentos fallidos.", true); return; }
        if (!r.ok) throw new Error(d.detail || badMsg);
        state.token = d.access_token; localStorage.setItem("ph_token", state.token);
        modal.remove(); armIdle(); toast("Desbloqueado.");
      } catch (e) { err.textContent = e.message; renderMode(); }
    };

    const renderMode = () => {
      body.innerHTML = "";
      if (mode === "pin") {
        let pin = "";
        const dots = el("div", "pin-display"); dots.id = "pin-dots";
        const renderDots = () => { dots.innerHTML = ""; for (let i = 0; i < Math.max(pin.length, 4); i++) dots.append(el("div", "pin-dot" + (i < pin.length ? " on" : ""))); };
        body.append(dots);
        const kp = el("div", "keypad");
        ["1","2","3","4","5","6","7","8","9","⌫","0","✓"].forEach(k => {
          const b = el("button", null, k);
          if (k === "⌫" || k === "✓") b.classList.add("cancel");
          b.onclick = () => {
            if (k === "⌫") { pin = pin.slice(0, -1); renderDots(); err.textContent = ""; }
            else if (k === "✓") { if (pin.length >= 4) tryUnlock({ pin }, "PIN incorrecto"); }
            else if (pin.length < 8) { pin += k; renderDots(); }
          };
          kp.append(b);
        });
        body.append(kp); renderDots();
        body._key = ev => {
          if (/^\d$/.test(ev.key) && pin.length < 8) { pin += ev.key; renderDots(); err.textContent = ""; }
          else if (ev.key === "Backspace") { pin = pin.slice(0, -1); renderDots(); }
          else if (ev.key === "Enter" && pin.length >= 4) tryUnlock({ pin }, "PIN incorrecto");
        };
      } else {
        let current = "";
        const pad = makePatternPad(seq => {
          current = seq;
          if (seq.length >= 4) { setTimeout(() => tryUnlock({ pattern: current }, "Patrón incorrecto"), 150); }
        });
        body.append(pad);
        body._key = null;
      }
    };

    const actions = el("div", "actions");
    if (hasPin && hasPattern) {
      const sw = el("button", "btn ghost", "Usar patrón");
      sw.onclick = () => { mode = mode === "pin" ? "pattern" : "pin"; sw.textContent = mode === "pin" ? "Usar patrón" : "Usar PIN"; err.textContent = ""; renderMode(); };
      actions.append(sw);
    }
    const out = el("button", "btn ghost", "Cerrar sesión"); out.onclick = () => { modal.remove(); logout(); };
    actions.append(out); card.append(actions);
    modal.append(card); document.body.append(modal);
    renderMode();
    document.addEventListener("keydown", function onKey(ev) {
      if (!document.getElementById("lock-modal")) { document.removeEventListener("keydown", onKey); return; }
      if (body._key) body._key(ev);
    });
  }

  // ====== Modo Emergencia ============
  async function emergencyAllOn() {
    if (!confirm("MODO EMERGENCIA: encender todo y poner dimming al 100%. ¿Continuar?")) return;
    try { const r = await api("/emergency/all-on", { method: "POST" }); toast(`Emergencia aplicada a ${r.cabinets.length} cuadros`); }
    catch (e) { toast(e.message, true); }
  }

  async function boot() {
    state.me = await api("/auth/me");
    $("#login").classList.add("hidden"); $("#app").classList.remove("hidden");
    $("#ub-user").textContent = cap(state.me.username);
    $("#ub-rank").textContent = rankLabel(state.me.rank);
    $("#btn-emergency").style.display = has("cabinet:control") ? "" : "none";
    $("#btn-lock").style.display = (state.me.has_pin || state.me.has_pattern) ? "" : "none";
    document.querySelectorAll("#nav a").forEach(a => {
      const perm = a.dataset.perm; a.style.display = (!perm || has(perm)) ? "" : "none";
    });
    try { state.ranksCatalog = await api("/users/ranks"); } catch (e) { state.ranksCatalog = []; }
    $("#ub-rank").textContent = rankLabel(state.me.rank);  // ya con el catálogo cargado
    await loadProjectsForChip();
    go("inicio");
    await refreshLive();
    connectWS();
    startIdleWatch();
    mountEventDock();
    startClock();
    if (!window._fallback) window._fallback = setInterval(() => {
      if (!window._ws || window._ws.readyState !== 1) refreshLive();
    }, 10000);
  }

  // ============================ Proyecto / ciudad activa ============================
  // El chip de arriba a la derecha muestra la ciudad en la que se opera. Para
  // un Owner es un selector con todos los proyectos (más "Todas"). Para el
  // resto es solo informativo: ese usuario está pinned a su proyecto en BD.
  async function loadProjectsForChip() {
    try { state.projects = await api("/projects"); }
    catch (e) { state.projects = []; }
    state.activeProject = state.activeProject ?? null;  // null = "Todas"
    renderProjectChip();
  }
  function isOwnerUser() { return state.me && (state.me.permissions || []).includes("*"); }
  function renderProjectChip() {
    const chip = $("#project-chip"); if (!chip) return;
    const owner = isOwnerUser();
    const projects = state.projects || [];
    const lockedName = projects.length === 1 ? projects[0].name : null;
    let label;
    if (owner) {
      const active = projects.find(p => p.id === state.activeProject);
      label = active ? active.name : (projects.length ? "Todas las ciudades" : "Sin proyectos");
    } else {
      label = lockedName || (state.me?.project_id ? "Ciudad #" + state.me.project_id : "Sin asignar");
    }
    $("#project-chip-name").textContent = label;
    $("#project-chip-caret").classList.toggle("hidden", !owner);
    chip.classList.toggle("clickable", owner);
    chip.classList.remove("hidden");
    if (owner) chip.onclick = toggleProjectPicker;
    else chip.onclick = null;
  }
  function toggleProjectPicker(e) {
    e?.stopPropagation();
    const picker = $("#project-picker");
    const open = !picker.classList.contains("hidden");
    if (open) { picker.classList.add("hidden"); return; }
    picker.innerHTML = "";
    const all = el("div", "opt" + (state.activeProject === null ? " active" : ""));
    all.innerHTML = `<div><div>Todas las ciudades</div><small>vista global</small></div><div>${state.activeProject === null ? "✓" : ""}</div>`;
    all.onclick = () => pickProject(null);
    picker.append(all);
    (state.projects || []).forEach(p => {
      const o = el("div", "opt" + (state.activeProject === p.id ? " active" : ""));
      o.innerHTML = `<div><div>${p.name}</div><small class="mono">${p.code}</small></div><div>${state.activeProject === p.id ? "✓" : ""}</div>`;
      o.onclick = () => pickProject(p.id);
      picker.append(o);
    });
    picker.classList.remove("hidden");
    setTimeout(() => document.addEventListener("click", closeProjectPicker, { once: true }), 0);
  }
  function closeProjectPicker() { $("#project-picker")?.classList.add("hidden"); }
  function closeUserMenu() { $("#user-dropdown")?.classList.add("hidden"); }
  // Reloj de la topbar: hora cada segundo, fecha en español.
  function startClock() {
    if (window._clockTimer) return;
    const tick = () => {
      const t = $("#clock-time"), d = $("#clock-date");
      if (!t || !d) return;
      const now = new Date();
      const tz = state.tz || "Europe/Madrid";  // hora local del despliegue, no la del navegador
      t.textContent = now.toLocaleTimeString("es-ES", { timeZone: tz });
      d.textContent = now.toLocaleDateString("es-ES", { timeZone: tz, weekday: "short", day: "2-digit", month: "short", year: "numeric" });
    };
    tick(); window._clockTimer = setInterval(tick, 1000);
  }
  function pickProject(id) {
    state.activeProject = id;
    closeProjectPicker();
    renderProjectChip();
    // Re-fetch para que las listas reflejen el nuevo scope.
    refreshLive();
    if (state.view === "usuarios") loadUsers();
  }
  function scopeQuery(path) {
    // Helper: anexa ?project_id=X cuando el owner haya activado un proyecto.
    if (state.activeProject == null) return path;
    const sep = path.includes("?") ? "&" : "?";
    return path + sep + "project_id=" + state.activeProject;
  }

  // ============================ Dock de eventos (estilo Hydra) ============================
  // Acumula los últimos N eventos (alarmas, cambios de estado, login fallidos,
  // bans, etc.) en una caja fija abajo a la derecha. Minimizable, con badge de
  // conteo y "pulso" rojo cuando hay incidencias críticas activas.
  const EVENT_DOCK_MAX = 50;
  const EVENT_DOCK_LABELS = {
    "auth.login": ["ok", "Inicio de sesión"],
    "auth.login_failed": ["bad", "Login fallido"],
    "auth.lockout": ["bad", "Cuenta bloqueada"],
    "auth.unlock": ["ok", "Desbloqueo"],
    "auth.unlock_failed": ["bad", "Desbloqueo fallido"],
    "emergency.all_on": ["warn", "Modo emergencia"],
    "security.ip_banned": ["bad", "IP baneada"],
    "security.siege_on": ["bad", "Modo siege ON"],
    "security.new_device": ["warn", "Nuevo dispositivo"],
    "security.device_mismatch": ["bad", "Cuadro: serial impostor"],
    "role.update": ["warn", "Rango editado"],
    "user.create": ["ok", "Usuario creado"],
  };
  // Etiquetas en español para los AlarmType del motor (operativas). Se
  // usan en el dock y en cualquier vista que muestre alarmas vivas.
  const ALARM_LABELS = {
    LAMP_OUT: "Luminarias apagadas",
    LINE_FAILURE: "Caída de línea",
    OVERVOLTAGE: "Sobretensión",
    UNDERVOLTAGE: "Subtensión",
    OVERCURRENT: "Sobreintensidad",
    CIRCUIT_LOAD_DROP: "Carga caída",
    CIRCUIT_OVERLOAD: "Sobrecarga del circuito",
    CONTACTOR_STUCK: "Contactor pegado",
    DOOR_OPEN: "Puerta abierta",
    CABINET_OVERTEMP: "Temperatura alta en el cuadro",
    INTRUSION: "Intrusión",
    COMMUNICATION_LOSS: "Sin comunicación",
  };
  function mountEventDock() {
    state.eventDock = state.eventDock || [];
    state.dockOpen = state.dockOpen ?? false;
    const dock = $("#event-dock"), toggle = $("#dock-toggle");
    if (!dock || dock._wired) { renderEventDock(); pollDock(); return; }
    dock._wired = true;
    toggle.onclick = () => {
      state.dockOpen = !state.dockOpen;
      dock.classList.toggle("collapsed", !state.dockOpen);
    };
    dock.classList.toggle("collapsed", !state.dockOpen);
    renderEventDock();
    pollDock();
    if (!window._dockTimer) window._dockTimer = setInterval(pollDock, 8000);
  }
  async function pollDock() {
    // Cuadros con alarma activa → entrada al dock.
    const liveAlarms = (state.cabinets || []).flatMap(cab =>
      (cab.alarms || []).map(a => ({
        timestamp: a.timestamp || new Date().toISOString(),
        action: "alarm",
        severity: (a.severity || "").toLowerCase(),
        label: (ALARM_LABELS[a.type] || a.type || "ALARMA") + " · " + cab.cabinet_id,
        sub: a.message || "",
        key: cab.cabinet_id + ":" + a.type,
      })),
    );
    // Eventos de seguridad (login fallido, IPs baneadas, nuevos dispositivos,
    // cambios de rango...): solo admins / owner. El resto de rangos
    // (ingeniero, supervisor, técnico, operador, visualizador) ven SOLO las
    // alarmas operativas de cuadros, fases, circuitos y luminarias.
    let secEvents = [];
    if (has("user:manage")) {
      try {
        const r = await api("/audit/security?limit=20");
        secEvents = r.map(e => ({
          timestamp: e.timestamp,
          action: e.action,
          label: (EVENT_DOCK_LABELS[e.action] || ["", e.action])[1] + " · " + e.username,
          sub: e.detail ? Object.entries(e.detail).slice(0, 2).map(([k, v]) => `${k}=${v}`).join(" · ") : "",
          severity: (EVENT_DOCK_LABELS[e.action] || ["dim"])[0],
          key: "sec:" + e.id,
        }));
      } catch (e) { /* sin permisos → silencio */ }
    }
    const merged = [...liveAlarms, ...secEvents]
      .sort((a, b) => new Date(b.timestamp) - new Date(a.timestamp))
      .slice(0, EVENT_DOCK_MAX);
    state.eventDock = merged;
    renderEventDock();
  }
  function renderEventDock() {
    const body = $("#dock-body"), count = $("#dock-count"), pulse = $("#dock-pulse");
    if (!body) return;
    const list = state.eventDock || [];
    const bad = list.filter(e => e.severity === "bad" || e.severity === "critical").length;
    const warn = list.filter(e => e.severity === "warn" || e.severity === "warning").length;
    count.textContent = list.length;
    count.classList.toggle("bad", bad > 0);
    pulse.className = "dock-pulse " + (bad > 0 ? "bad" : warn > 0 ? "warn" : "");
    body.innerHTML = "";
    if (!list.length) {
      const e = el("div", "dock-empty", "Sin eventos. Red operando con normalidad.");
      body.append(e); return;
    }
    list.forEach(ev => {
      const row = el("div", "dock-row");
      const tick = el("div", "dock-tick " + (ev.severity === "critical" ? "bad" : ev.severity || ""));
      const msg = el("div", "dock-msg");
      msg.innerHTML = `<div>${ev.label}</div>${ev.sub ? `<div class="muted">${ev.sub}</div>` : ""}`;
      const time = el("div", "dock-time", fmtTime(ev.timestamp));
      row.append(tick, msg, time);
      body.append(row);
    });
  }

  // ============================ Datos en vivo (REST + WebSocket) ============================
  function setLive(mode) {
    const dot = $("#live-dot"), lbl = $("#live-label");
    if (mode === "live") { dot.className = "dot ok"; lbl.textContent = "tiempo real"; }
    else if (mode === "poll") { dot.className = "dot warning"; lbl.textContent = "actualizando…"; }
    else { dot.className = "dot critical"; lbl.textContent = "sin conexión"; }
  }

  async function refreshLive() {
    if (!state.token || !has("cabinet:read")) return;
    try {
      state.cabinets = await api(scopeQuery("/cabinets"));   // lista completa con metadatos (nombre, lat/lon)
      if (!window._ws || window._ws.readyState !== 1) setLive("poll");
      rerenderLive();
      if (state.eventDock) pollDock();
    } catch (e) { setLive("down"); }
  }

  function applyLive(liveList) {
    const byId = Object.fromEntries(state.cabinets.map(c => [c.cabinet_id, c]));
    liveList.forEach(l => {
      const ex = byId[l.cabinet_id];
      if (ex) Object.assign(ex, { online: l.online, status: l.status, telemetry: l.telemetry, state: l.state, alarms: l.alarms });
      else state.cabinets.push(l);
    });
    rerenderLive();
  }

  function rerenderLive() {
    // Inicio has a persistent Leaflet map: a full re-render would tear it
    // down and rebuild it on every WS frame, producing the "tile pulse" the
    // user reported. Instead, patch the KPI numbers in place and let
    // drawTopology() repaint the markers.
    if (state.view === "inicio" && window._inicioMapWrap) {
      updateInicioKpis();
      drawTopology();
      return;
    }
    if (LIVE_VIEWS.includes(state.view)) {
      // No re-renderizar el control mientras el operario arrastra el slider:
      // reconstruir el panel lo reiniciaría a mitad de gesto.
      if (state.view === "control" && window._dimDragging) return;
      render();
    }
    else if (state.view === "mapa") drawTopology();
  }

  // Touch the values inside the existing KPI cards without re-creating them.
  // Cheap, no layout shift, no map remount.
  function updateInicioKpis() {
    const cards = document.querySelectorAll("#content .kpis-sm .kpi .v");
    if (cards.length < 4) return;
    const cabs = state.cabinets;
    const online = cabs.filter(x => x.online).length;
    const alarms = cabs.reduce((n, x) => n + x.alarms.length, 0);
    const kw = cabs.reduce((s, x) => s + (x.telemetry?.active_power_w || 0), 0) / 1000;
    cards[0].textContent = String(cabs.length);
    cards[1].textContent = online + " / " + cabs.length;
    cards[1].classList.toggle("accent", online < cabs.length);
    cards[2].textContent = String(alarms);
    cards[2].classList.toggle("accent", alarms > 0);
    cards[3].textContent = kw.toFixed(2) + " kW";
  }

  function connectWS() {
    if (!state.token) return;
    try {
      const proto = location.protocol === "https:" ? "wss" : "ws";
      const ws = new WebSocket(`${proto}://${location.host}/api/v1/ws?token=${encodeURIComponent(state.token)}`);
      window._ws = ws;
      ws.onopen = () => setLive("live");
      ws.onmessage = (ev) => { try { const m = JSON.parse(ev.data); if (m.type === "snapshot") applyLive(m.cabinets); } catch (e) {} };
      ws.onclose = () => { window._ws = null; setLive("poll"); setTimeout(connectWS, 3000); };
      ws.onerror = () => { try { ws.close(); } catch (e) {} };
    } catch (e) { setTimeout(connectWS, 3000); }
  }

  // ============================ Navegación ============================
  const TITLES = {
    inicio: ["Inicio", "Mapa operativo · cuadros, circuitos y luminarias"],
    cuadros: ["Cuadros", "Estado y telemetría de los cuadros"],
    luminarias: ["Luminarias", "Inventario de farolas · ficha por punto de luz"],
    mapa: ["Mapa", "Centros de mando y farolas sobre el plano"],
    topologia: ["Topología", "Centros de mando, circuitos y farolas"],
    control: ["Control", "Encendido, apagado y regulación (dimming)"],
    alarmas: ["Alarmas", "Incidencias activas en la red"],
    usuarios: ["Usuarios", "Cuentas, rangos y permisos"],
    rangos: ["Rangos", "Define qué puede hacer cada rango"],
    permisos: ["Permisos", "Usuarios, rangos y permisos efectivos"],
    proyectos: ["Proyectos", "Ciudades / contratos · aislamiento por proyecto"],
    auditoria: ["Auditoría", "Historial de acciones"],
    seguridad: ["Seguridad", "Inicios de sesión, bloqueos y desbloqueos"],
  };
  function go(view) {
    state.view = view;
    document.querySelectorAll("#nav a").forEach(a => a.classList.toggle("active", a.dataset.view === view));
    $("#view-title").textContent = TITLES[view][0];
    $("#view-sub").textContent = TITLES[view][1];
    render();
    if (view === "topologia") loadTopologia();
    if (view === "luminarias") loadLuminarias();
    if (view === "usuarios") loadUsers();
    if (view === "rangos") loadRoles();
    if (view === "permisos") loadPermisos();
    if (view === "proyectos") loadProyectos();
    if (view === "auditoria") loadAudit();
    if (view === "seguridad") loadSecurity();
  }

  // ============================ Render por sección ============================
  function render() {
    const c = $("#content");
    if (state.view === "inicio") return renderInicio(c);
    // Sidebar no longer exposes 'mapa' as its own entry — the inicio view
    // hosts the operational map directly (Hydra-style). Direct deep links
    // to /ui/#mapa still work and reuse the standalone renderer.
    if (state.view === "cuadros") return renderCuadros(c);
    if (state.view === "mapa") return renderMapa(c);
    if (state.view === "control") return renderControl(c);
    if (state.view === "alarmas") return renderAlarmas(c);
  }

  // Modo "añadir CM en el mapa" (estilo Hydra "activar modo añadir"). Al
  // activarlo, el siguiente click en el mapa captura lat/lon y abre el
  // formulario de nuevo cuadro con esas coordenadas ya rellenas.
  // Overlay del selector de ciudad/proyecto, flotante sobre el mapa (estilo
  // Hydra "Ciudad activa"). Reusa los IDs que ya conocen renderProjectChip /
  // toggleProjectPicker, así que la lógica existente sigue funcionando.
  function buildCityOverlay() {
    const wrap = el("div", "map-city"); wrap.id = "map-city-overlay";
    wrap.innerHTML = `
      <div id="project-chip" class="project-chip hidden">
        <span class="muted" style="font-size:11px">Ciudad</span>
        <span id="project-chip-name">—</span>
        <span id="project-chip-caret" class="caret hidden">▾</span>
      </div>
      <div id="project-picker" class="project-picker hidden"></div>`;
    return wrap;
  }

  // Barra de herramientas del mapa (estilo Hydra, debajo del minimapa). Sólo
  // para cabinet:manage. Tres modos exclusivos: añadir CM, añadir luminaria,
  // mover. Cada uno arma un click en el mapa que captura la posición.
  function buildMapToolbar() {
    const wrap = el("div", "map-toolbar");
    if (!has("cabinet:manage")) return wrap;  // operadores no ven herramientas
    const addCm = el("button", "btn sm ghost", "➕ Centro de mando");
    addCm.onclick = () => toggleAddCmMode();
    const addLight = el("button", "btn sm ghost", "➕ Luminaria");
    addLight.onclick = () => toggleAddLightMode();
    const move = el("button", "btn sm ghost", "✥ Mover");
    move.onclick = () => toggleEditPositions();
    const edit = el("button", "btn sm ghost", "✏ Editar");
    edit.onclick = () => toggleEditMode();
    const del = el("button", "btn sm ghost", "🗑 Eliminar");
    del.onclick = () => toggleDeleteMode();
    state.addCmBtn = addCm; state.addLightBtn = addLight; state.editPosBtn = move;
    state.editBtn = edit; state.deleteBtn = del;
    state.addCmMode = false; state.addLightMode = false; state.editPositions = false;
    state.editMode = false; state.deleteMode = false;
    const hint = el("span", "muted"); hint.id = "map-tool-hint"; hint.style.fontSize = "12px";
    hint.textContent = "Pulsa una herramienta y luego el punto del mapa";
    const btns = el("div", "row"); btns.style.gap = "6px"; btns.style.flexWrap = "wrap";
    btns.append(addCm, addLight, move, edit, del);
    wrap.append(btns, hint);
    return wrap;
  }
  function setToolHint(txt) { const h = document.getElementById("map-tool-hint"); if (h) h.textContent = txt; }
  // Apaga todos los modos de edición (para que sean exclusivos).
  function clearMapModes(except) {
    if (except !== "addcm" && state.addCmMode) finishAddCmMode();
    if (except !== "addlight" && state.addLightMode) finishAddLightMode();
    // Move: limpieza inline (no llamo a toggleEditPositions para evitar recursión).
    if (except !== "move" && state.editPositions) {
      state.editPositions = false;
      if (state.editPosBtn) { state.editPosBtn.classList.add("ghost"); state.editPosBtn.textContent = "✥ Mover"; }
      document.getElementById("edit-pos-banner")?.remove();
      const h = document.getElementById("map"); if (h) h.style.cursor = "";
      applyMarkerDraggable();
    }
    if (except !== "edit" && state.editMode) { state.editMode = false; state.editBtn?.classList.add("ghost"); if (state.editBtn) state.editBtn.textContent = "✏ Editar"; }
    if (except !== "delete" && state.deleteMode) { state.deleteMode = false; state.deleteBtn?.classList.add("ghost"); if (state.deleteBtn) state.deleteBtn.textContent = "🗑 Eliminar"; }
  }
  function toggleEditMode() {
    clearMapModes("edit");
    state.editMode = !state.editMode;
    const b = state.editBtn;
    if (b) { b.classList.toggle("ghost", !state.editMode); b.textContent = state.editMode ? "✕ Cancelar" : "✏ Editar"; }
    const host = document.getElementById("map"); if (host) host.style.cursor = state.editMode ? "pointer" : "";
    setToolHint(state.editMode ? "✏ Pulsa un cuadro o luminaria para editarlo" : "Pulsa una herramienta y luego el punto del mapa");
  }
  function toggleDeleteMode() {
    clearMapModes("delete");
    state.deleteMode = !state.deleteMode;
    const b = state.deleteBtn;
    if (b) { b.classList.toggle("ghost", !state.deleteMode); b.textContent = state.deleteMode ? "✕ Cancelar" : "🗑 Eliminar"; }
    const host = document.getElementById("map"); if (host) host.style.cursor = state.deleteMode ? "not-allowed" : "";
    setToolHint(state.deleteMode ? "🗑 Pulsa un cuadro o luminaria para eliminarlo" : "Pulsa una herramienta y luego el punto del mapa");
  }

  function toggleAddCmMode() {
    const map = window._map;
    if (!map) { toast("El mapa aún no está listo.", true); return; }
    if (!state.addCmMode) clearMapModes("addcm");
    state.addCmMode = !state.addCmMode;
    const btn = state.addCmBtn;
    if (btn) { btn.classList.toggle("ghost", !state.addCmMode); btn.textContent = state.addCmMode ? "✕ Cancelar" : "➕ Centro de mando"; }
    const host = document.getElementById("map");
    if (host) host.style.cursor = state.addCmMode ? "crosshair" : "";
    if (state.addCmMode) {
      setToolHint("📍 Haz click donde está el centro de mando");
      showMapBanner("add-cm-banner", "📍 Haz click en el punto del mapa donde está el centro de mando");
      map.once("click", (ev) => {
        finishAddCmMode();
        openCabinetForm(null, { latitude: ev.latlng.lat, longitude: ev.latlng.lng });
      });
    } else { finishAddCmMode(); }
  }
  function finishAddCmMode() {
    state.addCmMode = false;
    const btn = state.addCmBtn;
    if (btn) { btn.classList.add("ghost"); btn.textContent = "➕ Centro de mando"; }
    const host = document.getElementById("map"); if (host) host.style.cursor = "";
    if (window._map) window._map.off("click");
    document.getElementById("add-cm-banner")?.remove();
    setToolHint("Edición del mapa");
  }

  // Añadir luminaria clicando el mapa: captura lat/lon, geocodifica la
  // dirección y abre la ficha con todo prerelleno; el técnico elige el CM
  // y completa lo que falte (W, tecnología, modelo…).
  function toggleAddLightMode() {
    const map = window._map;
    if (!map) { toast("El mapa aún no está listo.", true); return; }
    const tp = window._topoCache || window._topology;
    if (!tp || !tp.cabinets.length) { toast("Crea antes un centro de mando.", true); return; }
    if (!state.addLightMode) clearMapModes("addlight");
    state.addLightMode = !state.addLightMode;
    const btn = state.addLightBtn;
    if (btn) { btn.classList.toggle("ghost", !state.addLightMode); btn.textContent = state.addLightMode ? "✕ Cancelar" : "➕ Luminaria"; }
    const host = document.getElementById("map");
    if (host) host.style.cursor = state.addLightMode ? "crosshair" : "";
    if (state.addLightMode) {
      setToolHint("💡 Haz click donde está la farola");
      showMapBanner("add-light-banner", "💡 Haz click en el punto del mapa donde está la luminaria", "rgba(250, 204, 21, 0.95)", "#3a2f00");
      map.once("click", async (ev) => {
        finishAddLightMode();
        const ll = { latitude: ev.latlng.lat, longitude: ev.latlng.lng };
        toast("Detectando dirección…");
        const addr = await reverseGeocode(ll.latitude, ll.longitude);
        openLightForm(null, null, { pickCabinet: true, prefill: { ...ll, ...(addr || {}) } });
      });
    } else { finishAddLightMode(); }
  }
  function finishAddLightMode() {
    state.addLightMode = false;
    const btn = state.addLightBtn;
    if (btn) { btn.classList.add("ghost"); btn.textContent = "➕ Luminaria"; }
    const host = document.getElementById("map"); if (host) host.style.cursor = "";
    if (window._map) window._map.off("click");
    document.getElementById("add-light-banner")?.remove();
    setToolHint("Edición del mapa");
  }
  function showMapBanner(id, text, bg, fg) {
    const host = document.getElementById("map");
    if (document.getElementById(id)) return;
    const banner = el("div", "map-add-banner", text); banner.id = id;
    if (bg) banner.style.background = bg; if (fg) banner.style.color = fg;
    host?.parentElement?.append(banner);
  }

  // ============================== INICIO ==============================
  // Hydra-style: the home view IS the operational map. KPIs sit above as a
  // compact strip; the map fills the rest of the screen. The bottom event
  // dock (mountEventDock) lives outside the view container and shows the
  // last incidents without taking up real estate.
  //
  // The Leaflet instance is kept alive across view switches — destroying and
  // re-creating it on every visit caused the famous "tile pulse from 0 to
  // full" because Leaflet re-runs fitBounds with animation each time. We
  // detach the DOM node and re-attach it when the user comes back, which
  // keeps the same map, same zoom, same markers.
  function renderInicio(c) {
    // Limpia modos de edición que quedaran activos de una visita anterior
    // (el mapa persiste entre vistas, así que sus listeners también).
    if (state.addCmMode || document.getElementById("add-cm-banner")) finishAddCmMode();
    if (state.addLightMode || document.getElementById("add-light-banner")) finishAddLightMode();
    if (state.editPositions || document.getElementById("edit-pos-banner")) {
      state.editPositions = false;
      document.getElementById("edit-pos-banner")?.remove();
      const host = document.getElementById("map"); if (host) host.style.cursor = "";
      if (window._map) window._map.off("click");
      applyMarkerDraggable();
    }
    state.editMode = false; state.deleteMode = false;
    const cabs = state.cabinets;
    const online = cabs.filter(x => x.online).length;
    const alarms = cabs.reduce((n, x) => n + x.alarms.length, 0);
    const kw = cabs.reduce((s, x) => s + (x.telemetry?.active_power_w || 0), 0) / 1000;

    // If the map is alive, detach its container before we wipe the content,
    // so we can re-attach it intact below.
    const persistedWrap = window._inicioMapWrap || null;
    const persistedLegend = window._inicioLegend || null;
    if (persistedWrap && persistedWrap.parentNode) persistedWrap.parentNode.removeChild(persistedWrap);
    if (persistedLegend && persistedLegend.parentNode) persistedLegend.parentNode.removeChild(persistedLegend);

    c.innerHTML = "";

    if (typeof L === "undefined") {
      c.append(el("div", "empty", "El mapa requiere conexión a internet (Leaflet)."));
      return;
    }

    // Franja DEBAJO del mapa, estilo Hydra:
    //   Fila 1:  [colorear por: Estado/CM/Circuito/Fase]   ·   [leyenda al lado]
    //   Fila 2:  [caja de Herramientas]                    ·   [KPIs]
    const buildBottomPanel = (legendNode) => {
      const wrap = el("div"); wrap.style.marginTop = "10px"; wrap.style.display = "grid"; wrap.style.gap = "12px";

      // --- Fila 1: colorear por + leyenda al mismo nivel ---
      const row1 = el("div", "row between"); row1.style.gap = "12px"; row1.style.flexWrap = "wrap"; row1.style.alignItems = "center";
      const colorSeg = segGroup(
        [["estado", "Estado"], ["cm", "Centro de mando"], ["circuito", "Circuito"], ["fase", "Fase"]],
        k => state.mapMode === k,
        k => { state.mapMode = k; drawTopology(); });
      legendNode.style.marginTop = "0"; legendNode.style.flex = "1"; legendNode.style.minWidth = "240px";
      row1.append(labeled("colorear por:", colorSeg), legendNode);
      wrap.append(row1);

      // --- Fila 2: caja de herramientas + KPIs al mismo nivel ---
      const row2 = el("div"); row2.style.display = "grid"; row2.style.gridTemplateColumns = "auto 1fr"; row2.style.gap = "12px"; row2.style.alignItems = "stretch";
      const toolBox = el("div", "panel"); toolBox.style.padding = "10px 12px";
      toolBox.append(el("div", "muted", "Herramientas del mapa"));
      const tb = buildMapToolbar(); tb.style.marginTop = "8px";
      toolBox.append(tb);
      const kpis = el("div", "grid kpis kpis-sm");
      kpis.append(
        kpi("Cuadros", cabs.length, false),
        kpi("Online", online + " / " + cabs.length, online < cabs.length),
        kpi("Alarmas activas", alarms, alarms > 0),
        kpi("Potencia total", kw.toFixed(2) + " kW", false),
      );
      row2.append(toolBox, kpis);
      wrap.append(row2);
      return wrap;
    };

    if (persistedWrap && window._map) {
      // Reuse the existing map.
      c.append(persistedWrap);
      c.append(buildBottomPanel(persistedLegend));
      renderProjectChip();
      requestAnimationFrame(() => {
        try { window._map.invalidateSize(false); } catch (e) {}
        drawTopology();
      });
      return;
    }

    // First mount: build the map container and initialise Leaflet.
    const mapWrap = el("div", "map-wrap"); mapWrap.classList.add("inicio-map");
    const div = el("div"); div.id = "map"; mapWrap.append(div, buildMapStylePicker(), buildCityOverlay());
    c.append(mapWrap);
    window._inicioMapWrap = mapWrap;
    renderProjectChip();

    const legend = el("div", "panel legend-thin"); legend.id = "legend"; legend.style.marginTop = "10px";
    window._inicioLegend = legend;
    c.append(buildBottomPanel(legend));

    (async () => {
      try { window._topology = await api("/topology"); } catch (e) { c.append(el("div", "empty", e.message)); return; }
      window._cmMarkers = {}; window._ptMarkers = {}; window._fitDone = false; window._tileLayer = null;
      // fadeAnimation off + zoomAnimation off → the very first paint also
      // lands at the final size, instead of fading in from a smaller frame.
      const map = L.map("map", {
        attributionControl: false,
        fadeAnimation: false, zoomAnimation: false, markerZoomAnimation: false,
        // Zoom abajo-izquierda para no tapar el chip de Ciudad (arriba-izda)
        // ni el selector de estilo de mapa (arriba-dcha).
        zoomControl: false,
      }).setView([40.4168, -3.7038], 13);
      L.control.zoom({ position: "bottomleft" }).addTo(map);
      window._map = map;
      applyTileStyle(map);
      requestAnimationFrame(() => map.invalidateSize(false));
      drawTopology();
    })();
  }
  function kpi(k, v, accent) { const card = el("div", "card kpi"); card.append(el("div", "k", k), el("div", "v" + (accent ? " accent" : ""), v)); return card; }

  function renderCuadros(c) {
    c.innerHTML = "";
    if (!state.cabinets.length) { c.append(el("div", "empty", "No hay cuadros reportando todavía.")); return; }
    const grid = el("div", "grid cards");
    state.cabinets.forEach(cab => {
      const t = cab.telemetry || {};
      const card = el("div", "card");
      const head = el("div", "cab-head");
      head.append(el("div", null, `<div class="id">${cab.cabinet_id}</div><div class="nm">${cab.name || ""}</div>`),
        el("div", null, `<span class="dot ${cab.online ? cab.status : 'off'}"></span> <span class="muted" style="font-size:12px">${cab.online ? cab.status : 'offline'}</span>`));
      card.append(head);
      const m = el("div", "metrics");
      m.append(metric("Tensión", fmt(t, "voltage_v", " V")), metric("Corriente", fmt(t, "current_a", " A", 2)),
        metric("Potencia", fmt(t, "active_power_w", " W", 0)), metric("cos φ", fmt(t, "power_factor", "", 2)));
      card.append(m);
      const dim = cab.state?.dim ?? 0;
      card.append(el("div", null, `<div class="muted" style="font-size:11px;margin-bottom:4px">Dimming · ${dim}%</div><div class="bar"><span style="width:${dim}%"></span></div>`));
      // Chips de infraestructura del cuadro (temperatura, puerta, intrusión).
      const infra = infraChips(t);
      if (infra) card.append(infra);
      grid.append(card);
    });
    c.append(grid);
  }
  function metric(label, val) { const m = el("div", "m"); m.append(el("div", "ml", label), el("div", "mv", val)); return m; }
  // Chips de telemetría de infraestructura del cuadro: temperatura interior,
  // puerta y sensor de intrusión. Devuelve null si la telemetría no los trae.
  function infraChips(t) {
    if (!t) return null;
    const chips = [];
    if (t.cabinet_temp_c != null) {
      const hot = t.cabinet_temp_c > 55;
      chips.push(`<span class="infra-chip ${hot ? "bad" : "ok"}">🌡️ ${t.cabinet_temp_c.toFixed(1)} °C</span>`);
    }
    if (t.door_open != null) {
      chips.push(t.door_open
        ? `<span class="infra-chip bad">🚪 Puerta abierta</span>`
        : `<span class="infra-chip ok">🚪 Cerrada</span>`);
    }
    if (t.intrusion) chips.push(`<span class="infra-chip bad">🚨 Intrusión</span>`);
    if (!chips.length) return null;
    const wrap = el("div", "infra-chips"); wrap.innerHTML = chips.join("");
    return wrap;
  }

  // ============================ Mapa ============================
  const TILE_STYLES = {
    oscuro:   { label: "Oscuro",   swatch: "#0b1120", url: "https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png", opts: { maxZoom: 19, subdomains: "abcd" } },
    claro:    { label: "Claro",    swatch: "#f1f5f9", url: "https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png", opts: { maxZoom: 19, subdomains: "abcd" } },
    calle:    { label: "Calle",    swatch: "#e8d8a0", url: "https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", opts: { maxZoom: 19, subdomains: "abc" } },
    satelite: { label: "Satélite", swatch: "#2f4a2a", url: "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}", opts: { maxZoom: 19 } },
  };
  function applyTileStyle(map) {
    if (!map) return;
    if (window._tileLayer) map.removeLayer(window._tileLayer);
    const st = TILE_STYLES[state.tileStyle] || TILE_STYLES.oscuro;
    window._tileLayer = L.tileLayer(st.url, st.opts).addTo(map);
    window._tileLayer.bringToBack();
  }
  function segGroup(pairs, isActive, onPick) {
    const seg = el("div", "row");
    pairs.forEach(([k, lbl]) => {
      const b = el("button", "btn sm" + (isActive(k) ? "" : " ghost"), lbl);
      b.onclick = () => { seg.querySelectorAll("button").forEach(x => x.classList.add("ghost")); b.classList.remove("ghost"); onPick(k); };
      seg.append(b);
    });
    return seg;
  }
  function labeled(text, node) {
    const wrap = el("div", "row"); const lab = el("span", "muted", text); lab.style.fontSize = "12px";
    wrap.append(lab, node); return wrap;
  }
  function buildMapStylePicker() {
    const wrap = el("div");
    const cur = TILE_STYLES[state.tileStyle] || TILE_STYLES.oscuro;
    const fab = el("button", "map-fab");
    fab.innerHTML = `<span class="sw" style="display:inline-block;width:14px;height:14px;border-radius:4px;border:1px solid #ffffff22;background:${cur.swatch}"></span><span id="fab-label">${cur.label}</span><span class="caret">▾</span>`;
    const panel = el("div", "map-panel");
    Object.entries(TILE_STYLES).forEach(([k, v]) => {
      const opt = el("div", "map-opt" + (state.tileStyle === k ? " active" : ""));
      opt.innerHTML = `<span class="sw" style="background:${v.swatch}"></span><span>${v.label}</span>`;
      opt.onclick = () => {
        state.tileStyle = k; localStorage.setItem("ph_tile", k);
        applyTileStyle(window._map);
        panel.querySelectorAll(".map-opt").forEach(o => o.classList.remove("active")); opt.classList.add("active");
        document.getElementById("fab-label").textContent = v.label;
        fab.querySelector(".sw").style.background = v.swatch;
        panel.classList.remove("open"); fab.classList.remove("open");
      };
      panel.append(opt);
    });
    fab.onclick = (e) => { e.stopPropagation(); panel.classList.toggle("open"); fab.classList.toggle("open"); };
    document.addEventListener("click", (e) => {
      if (!panel.contains(e.target) && e.target !== fab) { panel.classList.remove("open"); fab.classList.remove("open"); }
    }, { once: false });
    wrap.append(fab, panel);
    return wrap;
  }
  async function renderMapa(c) {
    c.innerHTML = "";
    if (typeof L === "undefined") { c.append(el("div", "empty", "El mapa requiere conexión a internet (Leaflet / tiles).")); return; }
    const bar = el("div", "row between"); bar.style.marginBottom = "12px"; bar.style.gap = "16px"; bar.style.flexWrap = "wrap";
    const colorSeg = segGroup(
      [["estado", "Estado"], ["cm", "Centro de mando"], ["circuito", "Circuito"], ["fase", "Fase"]],
      k => state.mapMode === k,
      k => { state.mapMode = k; drawTopology(); });
    bar.append(labeled("colorear por:", colorSeg));
    c.append(bar);
    const mapWrap = el("div", "map-wrap");
    const div = el("div"); div.id = "map"; mapWrap.append(div, buildMapStylePicker());
    c.append(mapWrap);
    const legend = el("div", "panel"); legend.id = "legend"; legend.style.marginTop = "12px"; c.append(legend);
    try { window._topology = await api("/topology"); } catch (e) { c.append(el("div", "empty", e.message)); return; }
    if (window._map) window._map.remove();
    window._cmMarkers = {}; window._ptMarkers = {}; window._fitDone = false; window._tileLayer = null;
    const map = L.map("map", { attributionControl: false }).setView([40.4168, -3.7038], 13);
    window._map = map;
    applyTileStyle(map);
    setTimeout(() => map.invalidateSize(), 60);
    drawTopology();
  }

  // Marcadores como iconos HTML (divIcon): arrastre NATIVO de Leaflet (como
  // Hydra) + coloreado por CSS (estado/CM/circuito/fase) actualizando el
  // fondo del pin. Base además para iconos de farola en el futuro.
  function cmDivIcon(num, col) {
    return L.divIcon({
      className: "pin-wrap",
      html: `<div class="cm-pin" style="background:${col}">CM${num}</div>`,
      iconSize: [30, 30], iconAnchor: [15, 15],
    });
  }
  function ptDivIcon(num, col) {
    return L.divIcon({
      className: "pin-wrap",
      html: `<div class="pt-pin" style="background:${col}"></div><div class="pt-num">${num}</div>`,
      iconSize: [14, 14], iconAnchor: [7, 7],
    });
  }
  // Recolorea un pin existente sin recrear el icono (evita parpadeo en cada
  // frame del WebSocket). getElement() existe una vez el marcador está pintado.
  function recolorPin(marker, kind, col) {
    const root = marker.getElement && marker.getElement();
    if (!root) return;
    const dot = root.querySelector(kind === "cm" ? ".cm-pin" : ".pt-pin");
    if (dot) dot.style.background = col;
  }
  // Activa/desactiva el arrastre nativo en todos los marcadores actuales.
  function applyMarkerDraggable() {
    const on = !!state.editPositions;
    const all = [...Object.values(window._cmMarkers || {}), ...Object.values(window._ptMarkers || {})];
    all.forEach(m => { try { if (m.dragging) { on ? m.dragging.enable() : m.dragging.disable(); } } catch (e) {} });
  }
  async function persistMarkerPosition(kind, id, lat, lng) {
    try {
      if (kind === "cm") {
        await api(`/cabinets/registry/${encodeURIComponent(id)}`, { method: "PATCH", body: JSON.stringify({ latitude: lat, longitude: lng }) });
      } else {
        await api(`/lightpoints/${id}`, { method: "PATCH", body: JSON.stringify({ latitude: lat, longitude: lng }) });
      }
      // Actualizo el cache local para que un redibujo no devuelva el marcador
      // a su posición anterior.
      const tp = window._topology;
      if (tp) {
        tp.cabinets.forEach(cab => {
          if (kind === "cm" && cab.code === id) { cab.latitude = lat; cab.longitude = lng; }
          if (kind === "pt") cab.points.forEach(p => { if (p.id === id) { p.latitude = lat; p.longitude = lng; } });
        });
      }
      toast("📍 Posición actualizada");
    } catch (e) { toast(e.message, true); drawTopology(); }
  }
  // Activa/desactiva el modo edición de posiciones (arrastre). Excluyente con
  // los modos de añadir. Usa el botón guardado en state.editPosBtn.
  function toggleEditPositions() {
    if (!state.editPositions) clearMapModes("move");
    state.editPositions = !state.editPositions;
    const btn = state.editPosBtn;
    if (btn) { btn.classList.toggle("ghost", !state.editPositions); btn.textContent = state.editPositions ? "✓ Arrastrando" : "✥ Mover"; }
    const host = document.getElementById("map");
    if (host) host.style.cursor = state.editPositions ? "move" : "";
    const banner = document.getElementById("edit-pos-banner");
    if (state.editPositions && !banner) {
      const b = el("div", "map-add-banner", "✥ Arrastra los cuadros y luminarias a su sitio · se guardan al soltar");
      b.id = "edit-pos-banner"; b.style.background = "rgba(56, 189, 248, 0.95)"; b.style.color = "#04212f";
      host?.parentElement?.append(b);
    } else if (!state.editPositions && banner) { banner.remove(); }
    setToolHint(state.editPositions ? "✥ Arrastra para recolocar · se guarda al soltar" : "Edición del mapa");
    applyMarkerDraggable();
  }

  function pointColor(cab, circ, pt) {
    const tp = window._topology;
    if (state.mapMode === "cm") return cab.color || "#f97316";
    if (state.mapMode === "circuito") return circ ? circ.color : "#64748b";
    if (state.mapMode === "fase") return (tp.phase_colors || {})[pt.phase] || "#64748b";
    return !cab._online ? "#64748b" : (STATUS_COLOR[cab._status] || "#22c55e");
  }

  function drawTopology() {
    const map = window._map, tp = window._topology; if (!map || !tp) return;
    const liveById = Object.fromEntries(state.cabinets.map(c => [c.cabinet_id, c]));
    const pts = [];
    tp.cabinets.forEach(cab => {
      const live = liveById[cab.code] || {};
      cab._online = live.online ?? cab.online; cab._status = live.status ?? cab.status;
      const tele = live.telemetry ?? cab.telemetry ?? {};
      const circById = Object.fromEntries(cab.circuits.map(x => [x.id, x]));
      if (cab.latitude != null && cab.longitude != null) {
        const col = state.mapMode === "estado" ? (!cab._online ? "#64748b" : (STATUS_COLOR[cab._status] || "#22c55e")) : (cab.color || "#f97316");
        let m = window._cmMarkers[cab.code];
        if (!m) {
          m = L.marker([cab.latitude, cab.longitude], {
            icon: cmDivIcon(cab.number, col),
            draggable: !!state.editPositions, autoPan: true,
          }).addTo(map);
          window._cmMarkers[cab.code] = m;
          m.on("dragend", (e) => { const ll = e.target.getLatLng(); persistMarkerPosition("cm", cab.code, ll.lat, ll.lng); });
          // En modo editar/eliminar, el click sobre el CM ejecuta la acción
          // (y cierra el popup que Leaflet abre por defecto).
          m.on("click", () => {
            if (!state.editMode && !state.deleteMode) return;
            m.closePopup();
            const t = window._topoCache || window._topology;
            const freshCab = t?.cabinets.find(x => x.code === cab.code) || cab;
            if (state.deleteMode) deleteCabinet(freshCab);
            else if (state.editMode) openCabinetForm(freshCab);
          });
        } else {
          m.setLatLng([cab.latitude, cab.longitude]);
          recolorPin(m, "cm", col);
        }
        const ctrl = has("cabinet:control") ? `<button class="btn sm" id="pop-${cab.code}" style="margin-top:8px;width:100%">Operar</button>` : "";
        const infra = [];
        if (tele.cabinet_temp_c != null) infra.push(`🌡️ ${tele.cabinet_temp_c.toFixed(1)}°C`);
        if (tele.door_open != null) infra.push(tele.door_open ? "🚪 abierta" : "🚪 cerrada");
        if (tele.intrusion) infra.push("🚨 intrusión");
        const infraLine = infra.length ? `<br><span class="muted">${infra.join(" · ")}</span>` : "";
        m.bindPopup(`<strong>CM${cab.number} · ${cab.name || cab.code}</strong><br><span class="muted">${cab.code} · ${cab._online ? cab._status : "offline"}</span><br>V ${fmt(tele, "voltage_v", " V")} · I ${fmt(tele, "current_a", " A", 2)}${infraLine}<br>${cab.circuits.length} circuitos · ${cab.points.length} farolas${ctrl}`);
        m.off("popupopen").on("popupopen", () => { const b = document.getElementById("pop-" + cab.code); if (b) b.onclick = () => { window._ctrlSel = cab.code; go("control"); }; });
        pts.push([cab.latitude, cab.longitude]);
      }
      cab.points.forEach(pt => {
        if (pt.latitude == null || pt.longitude == null) return;
        const circ = circById[pt.circuit_id];
        const col = pointColor(cab, circ, pt);
        let m = window._ptMarkers[pt.id];
        if (!m) {
          m = L.marker([pt.latitude, pt.longitude], {
            icon: ptDivIcon(pt.number, col),
            draggable: !!state.editPositions, autoPan: true,
          }).addTo(map);
          window._ptMarkers[pt.id] = m;
          m.on("dragend", (e) => { const ll = e.target.getLatLng(); persistMarkerPosition("pt", pt.id, ll.lat, ll.lng); });
          // Click en la luminaria: según el modo activo de la barra.
          m.on("click", () => {
            if (state.editPositions) return;  // en modo mover, el click arrastra
            const t = window._topoCache || window._topology;
            const freshCab = t?.cabinets.find(x => x.code === cab.code) || cab;
            const freshPt = freshCab.points.find(p => p.id === pt.id) || pt;
            if (state.deleteMode) { deleteLight(freshCab, freshPt); return; }
            if (state.editMode) { openLightForm(freshCab, freshPt); return; }
            openLightDetail(freshCab, freshPt);
          });
        } else {
          m.setLatLng([pt.latitude, pt.longitude]);
          recolorPin(m, "pt", col);
        }
        pts.push([pt.latitude, pt.longitude]);
      });
    });
    if (pts.length && !window._fitDone) { map.fitBounds(pts, { padding: [40, 40] }); window._fitDone = true; }
    renderLegend();
  }

  function renderLegend() {
    const lg = document.getElementById("legend"); if (!lg) return; const tp = window._topology; lg.innerHTML = "";
    const items = [];
    if (state.mapMode === "cm") tp.cabinets.forEach(c => items.push([c.color || "#f97316", "CM" + c.number + " · " + (c.name || c.code)]));
    else if (state.mapMode === "circuito") { const seen = {}; tp.cabinets.forEach(c => c.circuits.forEach(ci => { if (!seen[ci.color]) { seen[ci.color] = 1; items.push([ci.color, "Circuito " + ci.number]); } })); }
    else if (state.mapMode === "fase") Object.entries(tp.phase_colors || {}).forEach(([ph, col]) => items.push([col, "Fase " + ph]));
    else { items.push(["#22c55e", "OK"], ["#f59e0b", "Aviso"], ["#ef4444", "Crítico"], ["#64748b", "Offline"]); }
    lg.append(el("div", "muted", "<strong>Leyenda · " + state.mapMode + "</strong>"));
    const row = el("div", "row"); row.style.marginTop = "8px"; row.style.gap = "16px"; row.style.flexWrap = "wrap";
    items.forEach(([col, lbl]) => { const it = el("div", "row"); it.style.gap = "6px"; it.innerHTML = `<span style="display:inline-block;width:12px;height:12px;border-radius:50%;background:${col};border:1px solid #fff3"></span><span style="font-size:12px">${lbl}</span>`; row.append(it); });
    lg.append(row);
  }

  // ============================ Control ============================
  // Modos de regulación por cuadro (coincide con el backend dimming_mode):
  //   manual   → el operario manda; el programador no toca.
  //   schedule → programa horario + lux. Determinista.
  //   ai       → adaptativo: sol + tarifa + lux + perfil de calle.
  const DIM_MODES = [
    ["manual", "🔧 Manual", "El operario fija el nivel; el programador no lo toca."],
    ["schedule", "🕒 Programa", "Horario astronómico + sensor de luz. Determinista."],
    ["ai", "🧠 IA", "Adaptativo: sol + tarifa + lux + perfil de calle, con suelo de seguridad."],
  ];
  const PROFILE_LABELS = { arterial: "vía principal", residential: "residencial", crossing: "paso de peatones" };
  function renderControl(c) {
    c.innerHTML = "";
    if (!has("cabinet:control")) { c.append(el("div", "empty", "Tu rango no permite operar cuadros. Solo lectura.")); return; }
    const ids = state.cabinets.map(x => x.cabinet_id);
    if (!ids.length) { c.append(el("div", "empty", "No hay cuadros disponibles para controlar.")); return; }
    const cur = state.cabinets.find(x => x.cabinet_id === (window._ctrlSel || ids[0])) || state.cabinets[0];
    window._ctrlSel = cur.cabinet_id;
    const p = el("div", "panel");
    p.append(el("label", null, "Cuadro"));
    const sel = el("select"); ids.forEach(id => { const o = el("option", null, id); o.value = id; if (id === cur.cabinet_id) o.selected = true; sel.append(o); });
    sel.onchange = () => { window._ctrlSel = sel.value; render(); };
    p.append(sel);

    // Modo de regulación: Manual / Programa / IA (por cuadro).
    const mode = cur.dimming_mode || "schedule";
    const hasGeo = cur.latitude != null && cur.longitude != null;
    p.append(el("label", null, "Modo de regulación"));
    const modeRow = el("div", "row"); modeRow.style.gap = "6px"; modeRow.style.flexWrap = "wrap";
    DIM_MODES.forEach(([id, lbl]) => {
      const active = id === mode;
      const b = el("button", "btn sm" + (active ? "" : " ghost"), lbl);
      if (id === "ai" && !hasGeo) { b.disabled = true; b.title = "La IA necesita coordenadas del cuadro (ponlas en su ficha de topología)."; }
      if (!active) b.onclick = () => modeCmd(cur.cabinet_id, id);
      modeRow.append(b);
    });
    p.append(modeRow);
    const modeHint = el("div", "muted"); modeHint.style.fontSize = "11px"; modeHint.style.marginTop = "4px";
    const desc = (DIM_MODES.find(m => m[0] === mode) || [, , ""])[2];
    modeHint.textContent = desc + (mode === "ai" ? ` · perfil de calle: ${PROFILE_LABELS[cur.street_profile || "residential"]}` : "");
    p.append(modeHint);

    p.append(el("label", null, "Encendido / Apagado"));
    const relayRow = el("div", "row");
    const onBtn = el("button", "btn sm", "Encender"); onBtn.onclick = () => relay(cur.cabinet_id, "on");
    const offBtn = el("button", "btn sm ghost", "Apagar"); offBtn.onclick = () => relay(cur.cabinet_id, "off");
    relayRow.append(onBtn, offBtn); p.append(relayRow);

    const dim = cur.state?.dim ?? 100;
    const dimLbl = mode === "manual"
      ? "Regulación (dimming)"
      : `Nivel actual (lo fija el modo ${mode === "ai" ? "IA" : "programa"})`;
    p.append(el("label", null, `${dimLbl} · <span class="mono" id="dimv">${dim}%</span>`));
    const rng = el("input"); rng.type = "range"; rng.min = 0; rng.max = 100; rng.value = dim; rng.style.setProperty("--p", dim + "%");
    // Marco "arrastrando" para que el refresco en vivo no reinicie el slider
    // a mitad de gesto (la sensación de "hace lo que quiere").
    rng.onpointerdown = () => { window._dimDragging = true; };
    rng.oninput = () => { window._dimDragging = true; $("#dimv").textContent = rng.value + "%"; rng.style.setProperty("--p", rng.value + "%"); };
    p.append(rng);
    const send = el("button", "btn", mode === "manual" ? "Aplicar dimming" : "Aplicar (pasa a manual)");
    send.onclick = () => { window._dimDragging = false; dimCmd(cur.cabinet_id, parseInt(rng.value, 10)); };
    p.append(send);
    c.append(p);
  }
  async function modeCmd(id, mode) {
    const lbl = mode === "ai" ? "IA" : (mode === "manual" ? "manual" : "programa");
    try { await api(`/cabinets/${id}/mode`, { method: "POST", body: JSON.stringify({ mode }) }); toast(`${id}: modo ${lbl}`); refreshLive(); }
    catch (e) { toast(e.message, true); }
  }
  async function relay(id, st) {
    try { await api(`/cabinets/${id}/relay`, { method: "POST", body: JSON.stringify({ state: st }) }); toast(`${id}: ${st === "on" ? "encendido" : "apagado"}`); }
    catch (e) { toast(e.message, true); }
  }
  async function dimCmd(id, level) {
    try { await api(`/cabinets/${id}/dim`, { method: "POST", body: JSON.stringify({ level }) }); toast(`${id}: dimming ${level}%`); refreshLive(); }
    catch (e) { toast(e.message, true); }
  }

  // ============================ Alarmas ============================
  function renderAlarmas(c) {
    c.innerHTML = "";
    const all = state.cabinets.flatMap(x => x.alarms.map(a => ({ ...a, cabinet_id: x.cabinet_id })));
    const p = el("div", "panel");
    if (!all.length) p.append(el("div", "empty", "Sin alarmas activas."));
    else p.append(alarmTable(all, has("alarm:ack")));
    c.append(p);
  }
  function alarmTable(alarms, canAck) {
    const t = el("table");
    t.innerHTML = `<thead><tr><th>Cuadro</th><th>Tipo</th><th>Severidad</th><th>Mensaje</th><th></th></tr></thead>`;
    const tb = el("tbody");
    alarms.forEach(a => {
      const tr = el("tr");
      tr.innerHTML = `<td class="mono">${a.cabinet_id}</td><td>${a.type}</td><td><span class="badge ${a.severity}">${a.severity}</span></td><td class="muted">${a.message || ""}</td>`;
      const td = el("td");
      if (canAck) { const b = el("button", "btn sm ghost", "ACK"); b.onclick = () => ackCab(a.cabinet_id); td.append(b); }
      tr.append(td); tb.append(tr);
    });
    t.append(tb); return t;
  }
  async function ackCab(id) {
    try { await api(`/cabinets/${id}/alarms`, { method: "DELETE" }); toast(`Alarmas de ${id} reconocidas`); refreshLive(); }
    catch (e) { toast(e.message, true); }
  }

  // ============================ Luminarias (inventario) ============================
  // Lista plana de TODAS las farolas de la red, como "Cuadros" pero a nivel
  // de punto de luz. Buscador por calle/CM/fabricante/modelo + filtro por CM.
  // Clic en una fila → su ficha completa (openLightDetail).
  async function loadLuminarias() {
    const c = $("#content"); c.innerHTML = "";
    try {
      const tp = await api("/topology");
      window._topoCache = tp;
      // Aplano: cada luminaria + su cuadro y circuito.
      const rows = [];
      tp.cabinets.forEach(cab => {
        const circById = Object.fromEntries(cab.circuits.map(x => [x.id, x]));
        cab.points.forEach(pt => rows.push({ pt, cab, circ: circById[pt.circuit_id] }));
      });

      const bar = el("div", "row"); bar.style.marginBottom = "12px"; bar.style.gap = "10px"; bar.style.flexWrap = "wrap";
      const search = el("input"); search.placeholder = "Buscar por calle, CM, fabricante, modelo, nº…"; search.style.flex = "1"; search.style.minWidth = "240px";
      const cmFilter = el("select"); cmFilter.style.minWidth = "180px";
      // OJO: un <option> sin value devuelve su texto en .value, no "". Hay que
      // fijar value="" para que el filtro "Todos los cuadros" no descarte todo.
      const allCmOpt = el("option", null, "Todos los cuadros"); allCmOpt.value = ""; cmFilter.append(allCmOpt);
      tp.cabinets.forEach(cab => { const o = el("option", null, `CM${cab.number} · ${cab.name || cab.code}`); o.value = cab.code; cmFilter.append(o); });
      const counter = el("span", "muted"); counter.style.fontSize = "12px"; counter.style.alignSelf = "center";
      bar.append(search, cmFilter, counter);
      c.append(bar);

      const panel = el("div", "panel");
      const t = el("table");
      t.innerHTML = `<thead><tr><th>Nº</th><th>Calle</th><th>CM</th><th>Circuito</th><th>Fase</th><th>Fabricante</th><th>Modelo</th><th>W</th></tr></thead>`;
      const tb = el("tbody"); t.append(tb); panel.append(t);

      const draw = () => {
        const q = search.value.trim().toLowerCase();
        const cm = cmFilter.value;
        const items = rows.filter(({ pt, cab }) => {
          if (cm && cab.code !== cm) return false;
          if (!q) return true;
          return [pt.street, cab.code, cab.name, pt.manufacturer, pt.model, String(pt.number), pt.locality]
            .some(v => (v || "").toString().toLowerCase().includes(q));
        });
        counter.textContent = `${items.length} de ${rows.length} luminarias`;
        tb.innerHTML = "";
        const renderPage = (page) => {
          tb.innerHTML = "";
          page.forEach(({ pt, cab, circ }) => {
            const tr = el("tr"); tr.style.cursor = "pointer";
            const phaseCol = (tp.phase_colors || {})[pt.phase] || "#64748b";
            tr.innerHTML = `<td class="mono">${pt.number}</td>`
              + `<td>${pt.street || "<span class='muted'>—</span>"}${pt.street_number ? " " + pt.street_number : ""}</td>`
              + `<td><span style="display:inline-block;width:9px;height:9px;border-radius:50%;background:${cab.color};margin-right:5px"></span>CM${cab.number}</td>`
              + `<td>${circ ? "C" + circ.number : "—"}</td>`
              + `<td><span style="display:inline-block;width:9px;height:9px;border-radius:50%;background:${phaseCol};margin-right:5px"></span>${pt.phase}</td>`
              + `<td>${pt.manufacturer || "—"}</td><td>${pt.model || "—"}</td><td class="mono">${(pt.power_w || 0).toFixed(0)}</td>`;
            tr.onclick = () => openLightDetail(cab, pt);
            tb.append(tr);
          });
        };
        // Paginación reutilizando el helper genérico.
        const existingPager = panel.querySelector(".paginator");
        if (existingPager) existingPager.remove();
        if (items.length) panel.append(paginator(items, renderPage));
        else { tb.innerHTML = ""; tb.append(el("tr", null, `<td colspan="8" class="muted" style="text-align:center;padding:14px">Sin luminarias.</td>`)); }
      };
      search.oninput = draw; cmFilter.onchange = draw;
      draw();
      c.append(panel);
    } catch (e) { c.append(el("div", "empty", e.message)); }
  }

  // ============================ Topología (con editor) ============================
  async function loadTopologia() {
    const c = $("#content"); c.innerHTML = "";
    try {
      const tp = await api("/topology");
      window._topoCache = tp;  // usado por los formularios del editor
      const canEdit = has("cabinet:manage");
      const isOwner = isOwnerUser();

      // Barra: búsqueda + acciones de alta (solo cabinet:manage).
      const bar = el("div", "row between"); bar.style.marginBottom = "12px"; bar.style.gap = "10px"; bar.style.flexWrap = "wrap";
      const leftBar = el("div", "row"); leftBar.style.gap = "10px"; leftBar.style.flex = "1"; leftBar.style.flexWrap = "wrap";
      const search = el("input"); search.placeholder = "Buscar por código, nombre o zona…"; search.style.flex = "1"; search.style.minWidth = "220px";
      const counter = el("span", "muted"); counter.style.fontSize = "12px"; counter.style.alignSelf = "center";
      leftBar.append(search, counter);
      bar.append(leftBar);
      if (canEdit) {
        const tools = el("div", "row"); tools.style.gap = "8px";
        const addBtn = el("button", "btn sm", "➕ Nuevo CM");
        addBtn.onclick = () => openCabinetForm(null);
        tools.append(addBtn);
        if (isOwner && tp.cabinets.length) {
          const wipe = el("button", "btn ghost sm", "💣 Vaciar topología");
          wipe.style.color = "#ef4444";
          wipe.onclick = () => wipeTopology(tp.cabinets.length);
          tools.append(wipe);
        }
        bar.append(tools);
      }
      c.append(bar);

      const grid = el("div", "topo-grid"); c.append(grid);

      if (!tp.cabinets.length) {
        const empty = el("div", "empty");
        empty.innerHTML = canEdit
          ? "Sin topología todavía. Pulsa <strong>➕ Nuevo CM</strong> para dar de alta tu primer centro de mando."
          : "Sin topología todavía.";
        grid.append(empty);
        counter.textContent = "0 cuadros";
        return;
      }

      const draw = () => {
        const q = search.value.trim().toLowerCase();
        const items = tp.cabinets.filter(cab => {
          if (!q) return true;
          return (cab.code || "").toLowerCase().includes(q)
              || (cab.name || "").toLowerCase().includes(q)
              || (cab.zone || "").toLowerCase().includes(q);
        });
        counter.textContent = `${items.length} de ${tp.cabinets.length} cuadros`;
        grid.innerHTML = "";
        items.forEach(cab => grid.append(buildTopoCard(cab, tp, canEdit)));
        if (!items.length) grid.append(el("div", "empty", "Ningún cuadro coincide con la búsqueda."));
      };
      search.oninput = draw;
      draw();
    } catch (e) { c.append(el("div", "empty", e.message)); }
  }

  function buildTopoCard(cab, tp, canEdit) {
    const card = el("div", "topo-card");
    const cpts = cab.points;
    const phases = [...new Set(cpts.map(pt => pt.phase))].sort();
    const statusCls = !cab.online ? "off" : (cab.status === "critical" ? "bad" : (cab.status === "warning" ? "warn" : "ok"));
    card.innerHTML = `
      <div class="topo-head" style="border-left:3px solid ${cab.color}">
        <div class="topo-title">
          <span class="topo-dot ${statusCls}"></span>
          <strong>CM${cab.number}</strong>
          <span class="muted mono" style="font-size:11px">${cab.code}</span>
        </div>
        <div class="topo-name muted">${cab.name || ""}</div>
      </div>
      <div class="topo-stats">
        <div><span class="topo-num">${cab.circuits.length}</span><span class="muted">circuitos</span></div>
        <div><span class="topo-num">${cpts.length}</span><span class="muted">luminarias</span></div>
        <div><span class="topo-num">${phases.length || "—"}</span><span class="muted">fases ${phases.join(" ") || ""}</span></div>
      </div>`;
    card.onclick = () => openTopoDetail(cab, tp, canEdit);
    return card;
  }

  // --- Editor master-detail del CM (modal con 3 pestañas) ----------------
  function openTopoDetail(cab, tp, canEdit) {
    const modal = el("div", "modal");
    const card = el("div", "modal-card"); card.style.maxWidth = "720px";
    state.topoTab = state.topoTab || "cuadro";

    const head = el("div", "row between");
    head.innerHTML = `<h3 style="margin:0"><span style="display:inline-block;width:12px;height:12px;border-radius:50%;background:${cab.color};margin-right:8px"></span>CM${cab.number} · ${cab.name || cab.code}</h3>`;
    const closeX = el("button", "btn ghost sm", "✕"); closeX.onclick = () => modal.remove();
    head.append(closeX);
    card.append(head);
    card.append(el("div", "muted", `${cab.code} · ${cab.zone || "sin zona"} · ${cab.points.length} luminarias · ${cab.circuits.length} circuitos`));

    const tabs = el("div", "tabs"); tabs.style.marginTop = "12px";
    [["cuadro", "Cuadro"], ["circuitos", "Circuitos"], ["luminarias", "Luminarias"], ["dispositivo", "Dispositivo"]].forEach(([k, lbl]) => {
      const b = el("button", "tab" + (state.topoTab === k ? " active" : ""), lbl);
      b.onclick = () => { state.topoTab = k; modal.remove(); openTopoDetail(cab, tp, canEdit); };
      tabs.append(b);
    });
    card.append(tabs);

    const body = el("div"); body.style.marginTop = "14px"; card.append(body);
    if (state.topoTab === "cuadro") renderCabinetTab(body, cab, canEdit, modal);
    else if (state.topoTab === "circuitos") renderCircuitsTab(body, cab, canEdit);
    else if (state.topoTab === "dispositivo") renderDeviceTab(body, cab, canEdit);
    else renderLightsTab(body, cab, canEdit);

    modal.append(card); document.body.append(modal);
  }

  function renderCabinetTab(body, cab, canEdit, modal) {
    const grid = el("div"); grid.style.display = "grid"; grid.style.gridTemplateColumns = "1fr 1fr"; grid.style.gap = "10px";
    const rows = [
      ["Código", cab.code, "mono"],
      ["Nombre", cab.name || "—"],
      ["Número (CM)", cab.number],
      ["Zona", cab.zone || "—"],
      ["Color", `<span style="display:inline-block;width:11px;height:11px;border-radius:50%;background:${cab.color};margin-right:6px"></span><span class="mono">${cab.color}</span>`],
      ["Coordenadas", cab.latitude != null ? `${cab.latitude.toFixed(5)}, ${cab.longitude.toFixed(5)}` : "sin ubicar"],
    ];
    rows.forEach(([k, v, cls]) => {
      const cell = el("div");
      cell.innerHTML = `<div class="muted" style="font-size:11px">${k}</div><div class="${cls || ""}" style="font-size:14px">${v}</div>`;
      grid.append(cell);
    });
    body.append(grid);

    if (canEdit) {
      const actions = el("div", "perm-actions");
      const edit = el("button", "btn sm", "✏ Editar datos");
      edit.onclick = () => { modal.remove(); openCabinetForm(cab); };
      const del = el("button", "btn ghost sm", "🗑 Borrar cuadro"); del.style.color = "#ef4444";
      del.onclick = () => { modal.remove(); deleteCabinet(cab); };
      actions.append(edit, del);
      body.append(actions);
    }
  }

  function renderCircuitsTab(body, cab, canEdit) {
    const t = el("table");
    t.innerHTML = `<thead><tr><th>#</th><th>Nombre</th><th>Color</th><th>Fase</th><th>Nominal</th><th>Lumin.</th><th></th></tr></thead>`;
    const tb = el("tbody");
    cab.circuits.forEach(ci => {
      const list = cab.points.filter(pt => pt.circuit_id === ci.id);
      const tr = el("tr");
      tr.innerHTML = `<td class="mono">${ci.number}</td><td>${ci.name || "—"}</td>`
        + `<td><span style="display:inline-block;width:11px;height:11px;border-radius:50%;background:${ci.color};margin-right:6px"></span><span class="mono">${ci.color}</span></td>`
        + `<td>${ci.phase}</td><td class="mono">${(ci.expected_power_w || 0).toFixed(0)} W</td><td class="mono">${list.length}</td>`;
      const td = el("td");
      if (canEdit) {
        const e = el("button", "btn ghost sm", "✏"); e.onclick = () => openCircuitForm(cab, ci);
        const mv = el("button", "btn ghost sm", "⇄"); mv.title = "Mover a otro CM"; mv.style.marginLeft = "4px";
        mv.onclick = () => moveCircuitToCabinet(cab, ci, list.length);
        const d = el("button", "btn ghost sm", "🗑"); d.style.color = "#ef4444"; d.style.marginLeft = "4px";
        d.onclick = () => deleteCircuit(cab, ci, list.length);
        td.append(e, mv, d);
      }
      tr.append(td); tb.append(tr);
    });
    if (!cab.circuits.length) tb.append(el("tr", null, `<td colspan="7" class="muted" style="text-align:center; padding:10px">Sin circuitos.</td>`));
    t.append(tb); body.append(t);
    if (canEdit) {
      const add = el("button", "btn sm", "➕ Nuevo circuito"); add.style.marginTop = "12px";
      add.onclick = () => openCircuitForm(cab, null);
      body.append(add);
    }
  }

  function renderLightsTab(body, cab, canEdit) {
    const circById = Object.fromEntries(cab.circuits.map(c => [c.id, c]));
    const t = el("table");
    t.innerHTML = `<thead><tr><th>#</th><th>Etiqueta</th><th>Circuito</th><th>Fase</th><th>Potencia</th><th></th></tr></thead>`;
    const tb = el("tbody");
    cab.points.slice().sort((a, b) => a.number - b.number).forEach(pt => {
      const ci = circById[pt.circuit_id];
      const tr = el("tr");
      tr.innerHTML = `<td class="mono">${pt.number}</td><td>${pt.label || "—"}</td>`
        + `<td>${ci ? "Circuito " + ci.number : "<span class='muted'>?</span>"}</td>`
        + `<td>${pt.phase}</td><td class="mono">${(pt.power_w || 0).toFixed(0)} W</td>`;
      const td = el("td");
      if (canEdit) {
        const e = el("button", "btn ghost sm", "✏"); e.onclick = () => openLightForm(cab, pt);
        const d = el("button", "btn ghost sm", "🗑"); d.style.color = "#ef4444"; d.style.marginLeft = "4px";
        d.onclick = () => deleteLight(cab, pt);
        td.append(e, d);
      }
      tr.append(td); tb.append(tr);
    });
    if (!cab.points.length) tb.append(el("tr", null, `<td colspan="6" class="muted" style="text-align:center; padding:10px">Sin luminarias.</td>`));
    t.append(tb); body.append(t);
    if (canEdit) {
      const add = el("button", "btn sm", "➕ Nueva luminaria"); add.style.marginTop = "12px";
      if (!cab.circuits.length) { add.disabled = true; add.title = "Crea antes un circuito"; }
      add.onclick = () => openLightForm(cab, null);
      body.append(add);
    }
  }

  // Pestaña Dispositivo del editor del CM: vinculación tipo SICE (serial +
  // IMEI del controlador físico que publica la telemetría de este cuadro).
  async function renderDeviceTab(body, cab, canEdit) {
    body.innerHTML = `<div class="muted" style="font-size:12px; margin-bottom:12px">Controlador físico vinculado a este cuadro (estilo SICE). El bus sólo acepta telemetría cuyo serial coincida con el registrado.</div>`;
    try {
      const devices = await api(`/devices?cabinet_code=${encodeURIComponent(cab.code)}`);
      if (devices.length) {
        const t = el("table");
        t.innerHTML = `<thead><tr><th>Serial</th><th>IMEI</th><th>Modelo</th><th>Firmware</th><th>Último visto</th><th></th></tr></thead>`;
        const tb = el("tbody");
        devices.forEach(d => {
          const tr = el("tr");
          const last = d.last_seen_at ? fmtDateTime(d.last_seen_at) : "nunca";
          tr.innerHTML = `<td class="mono">${d.serial}</td><td class="mono">${d.imei || "—"}</td><td>${d.model || "—"}</td><td>${d.firmware || "—"}</td><td class="muted mono" style="font-size:12px">${last}</td>`;
          const td = el("td");
          if (canEdit) {
            const del = el("button", "btn ghost sm", "🗑"); del.style.color = "#ef4444";
            del.onclick = async () => { if (confirm(`¿Desvincular el dispositivo ${d.serial}?`)) { try { await api(`/devices/${d.id}`, { method: "DELETE" }); toast("Dispositivo desvinculado"); reopenTopoAfterChange(cab.code, "dispositivo"); } catch (e) { toast(e.message, true); } } };
            td.append(del);
          }
          tr.append(td); tb.append(tr);
        });
        t.append(tb); body.append(t);
      } else {
        body.append(el("div", "empty", "Sin controlador vinculado."));
      }
      if (canEdit) {
        const form = el("div"); form.style.display = "grid"; form.style.gap = "8px"; form.style.marginTop = "12px";
        form.append(el("div", "muted", "<strong>Vincular controlador</strong>"));
        const serial = el("input"); serial.placeholder = "Serial del controlador (obligatorio)";
        const imei = el("input"); imei.placeholder = "IMEI del módem 4G (opcional)";
        const model = el("input"); model.placeholder = "Modelo (p.ej. PLCnext AXC F 2152)";
        const fw = el("input"); fw.placeholder = "Firmware (opcional)";
        const add = el("button", "btn sm", "Vincular");
        add.onclick = async () => {
          if (serial.value.trim().length < 4) { toast("El serial debe tener al menos 4 caracteres.", true); return; }
          try {
            await api("/devices", { method: "POST", body: JSON.stringify({ cabinet_code: cab.code, serial: serial.value.trim(), imei: imei.value.trim() || null, model: model.value.trim() || null, firmware: fw.value.trim() || null }) });
            toast("Controlador vinculado");
            reopenTopoAfterChange(cab.code, "dispositivo");
          } catch (e) { toast(e.message, true); }
        };
        form.append(serial, imei, model, fw, add);
        body.append(form);
      }
    } catch (e) { body.append(el("div", "empty", e.message)); }
  }

  // --- Formularios de alta/edición ---------------------------------------
  function openCabinetForm(cab, prefill) {
    const editing = !!cab;
    const modal = el("div", "modal"); const card = el("div", "modal-card");
    card.innerHTML = `<h3 style="margin:0 0 12px">${editing ? "Editar cuadro" : "Nuevo centro de mando"}</h3>`;
    if (!editing && prefill) {
      const hint = el("div", "muted"); hint.style.fontSize = "12px"; hint.style.marginBottom = "10px";
      hint.innerHTML = `📍 Coordenadas captadas del mapa: <span class="mono">${prefill.latitude.toFixed(5)}, ${prefill.longitude.toFixed(5)}</span>`;
      card.append(hint);
    }
    const form = el("div"); form.style.display = "grid"; form.style.gap = "10px";
    const code = el("input"); code.placeholder = "Código (p.ej. CAB-005)"; code.value = cab?.code || "";
    if (editing) { code.disabled = true; code.style.opacity = ".6"; }
    const name = el("input"); name.placeholder = "Nombre"; name.value = cab?.name || "";
    const number = el("input"); number.type = "number"; number.placeholder = "Número de CM"; number.value = cab?.number ?? "";
    const zone = el("input"); zone.placeholder = "Zona (opcional)"; zone.value = cab?.zone || "";
    const color = el("input"); color.type = "color"; color.value = cab?.color || "#f97316";
    const colorWrap = el("div", "row"); colorWrap.style.gap = "8px"; colorWrap.style.alignItems = "center";
    colorWrap.append(el("span", "muted", "Color en el mapa"), color);
    const lat = el("input"); lat.placeholder = "Latitud (opcional)"; lat.value = cab?.latitude ?? prefill?.latitude ?? "";
    const lon = el("input"); lon.placeholder = "Longitud (opcional)"; lon.value = cab?.longitude ?? prefill?.longitude ?? "";
    const coords = el("div", "row"); coords.style.gap = "8px"; coords.append(lat, lon);
    // Perfil de uso de la vía — define el suelo de seguridad del modo IA del
    // dimming (una arteria nunca baja tanto como una residencial).
    const profile = el("select");
    [["residential", "Residencial (baja agresivo)"],
     ["arterial", "Vía principal (mantener alto)"],
     ["crossing", "Paso de peatones / glorieta (suelo alto)"]].forEach(([v, lbl]) => {
      const o = el("option", null, lbl); o.value = v;
      if ((cab?.street_profile || "residential") === v) o.selected = true; profile.append(o);
    });
    const profWrap = el("div"); profWrap.innerHTML = `<div class="muted" style="font-size:11px;margin-bottom:4px">Perfil de calle (modo IA)</div>`;
    profWrap.append(profile);
    // Ciudad / proyecto — solo el owner asigna (un director hereda el suyo).
    // Nuevo CM: preselecciona la ciudad activa del topbar. Editar: la del CM.
    let projSel = null;
    if (isOwnerUser()) {
      projSel = el("select");
      const none = el("option", null, "— Global (sin ciudad) —"); none.value = ""; projSel.append(none);
      const curPid = editing ? (cab?.project_id ?? null) : (state.activeProject ?? null);
      (state.projects || []).forEach(p => {
        const o = el("option", null, p.name); o.value = String(p.id);
        if (curPid === p.id) o.selected = true; projSel.append(o);
      });
      const pwrap = el("div"); pwrap.innerHTML = `<div class="muted" style="font-size:11px;margin-bottom:4px">Ciudad / proyecto</div>`;
      pwrap.append(projSel);
      form.append(code, name, number, zone, colorWrap, coords, profWrap, pwrap);
    } else {
      form.append(code, name, number, zone, colorWrap, coords, profWrap);
    }
    card.append(form);

    const actions = el("div", "perm-actions");
    const save = el("button", "btn sm", editing ? "Guardar" : "Crear");
    save.onclick = async () => {
      const payload = {
        name: name.value.trim(), number: parseInt(number.value, 10) || 0,
        zone: zone.value.trim() || null, color: color.value,
        latitude: lat.value ? parseFloat(lat.value) : null,
        longitude: lon.value ? parseFloat(lon.value) : null,
        street_profile: profile.value,
      };
      if (projSel) payload.project_id = projSel.value ? parseInt(projSel.value, 10) : null;
      try {
        if (editing) {
          await api(`/cabinets/registry/${encodeURIComponent(cab.code)}`, { method: "PATCH", body: JSON.stringify(payload) });
          toast("Cuadro actualizado");
        } else {
          if (code.value.trim().length < 2) { toast("El código debe tener al menos 2 caracteres.", true); return; }
          payload.code = code.value.trim();
          await api("/cabinets/registry", { method: "POST", body: JSON.stringify(payload) });
          toast("Cuadro creado: " + payload.code);
        }
        modal.remove();
        // Si estoy en Inicio (mapa), refresco topología y redibujo. En
        // Topología, recargo la rejilla.
        if (state.view === "inicio") {
          try { window._topology = await api("/topology"); drawTopology(); } catch (e) {}
          await refreshLive();
        } else {
          loadTopologia();
        }
      } catch (e) { toast(e.message, true); }
    };
    const cancel = el("button", "btn ghost sm", "Cancelar"); cancel.onclick = () => modal.remove();
    actions.append(save, cancel); card.append(actions);
    modal.append(card); document.body.append(modal);
  }

  function openCircuitForm(cab, circ) {
    const editing = !!circ;
    const modal = el("div", "modal"); const card = el("div", "modal-card");
    card.innerHTML = `<h3 style="margin:0 0 12px">${editing ? "Editar circuito" : "Nuevo circuito"} · ${cab.code}</h3>`;
    const form = el("div"); form.style.display = "grid"; form.style.gap = "10px";
    const number = el("input"); number.type = "number"; number.placeholder = "Número de circuito"; number.value = circ?.number ?? (cab.circuits.length + 1);
    const name = el("input"); name.placeholder = "Nombre (opcional)"; name.value = circ?.name || "";
    const phase = el("select"); ["L1", "L2", "L3", "III"].forEach(p => { const o = el("option", null, p); o.value = p; if ((circ?.phase || "L1") === p) o.selected = true; phase.append(o); });
    const phaseWrap = el("div", "row"); phaseWrap.style.gap = "8px"; phaseWrap.style.alignItems = "center"; phaseWrap.append(el("span", "muted", "Fase"), phase);
    const color = el("input"); color.type = "color"; color.value = circ?.color || "#38bdf8";
    const colorWrap = el("div", "row"); colorWrap.style.gap = "8px"; colorWrap.style.alignItems = "center"; colorWrap.append(el("span", "muted", "Color"), color);
    // Nominal AUTOMÁTICO: suma de las luminarias del circuito. Read-only — el
    // backend lo recalcula solo; ya no se teclea a mano.
    const ptSum = circ ? (cab.points || []).filter(pt => pt.circuit_id === circ.id).reduce((a, pt) => a + (pt.power_w || 0), 0) : 0;
    const power = el("input"); power.type = "number"; power.value = Math.round(ptSum); power.disabled = true; power.style.opacity = ".7";
    const powerWrap = el("div", "row"); powerWrap.style.gap = "8px"; powerWrap.style.alignItems = "center"; powerWrap.append(el("span", "muted", "Nominal (auto)"), power, el("span", "muted", "W"));
    const powerHint = el("div", "muted"); powerHint.style.fontSize = "11px";
    powerHint.textContent = "Se calcula solo sumando las luminarias del circuito. Sirve para detectar carga caída / sobrecarga (sin luminarias = sin comprobación).";
    form.append(number, name, phaseWrap, colorWrap, powerWrap, powerHint);
    card.append(form);

    const actions = el("div", "perm-actions");
    const save = el("button", "btn sm", editing ? "Guardar" : "Crear");
    save.onclick = async () => {
      const payload = {
        number: parseInt(number.value, 10) || 1, name: name.value.trim(),
        phase: phase.value, color: color.value,
        // expected_power_w ya no se envía: lo calcula el backend desde las luminarias.
      };
      try {
        if (editing) {
          await api(`/circuits/${circ.id}`, { method: "PATCH", body: JSON.stringify(payload) });
          toast("Circuito actualizado");
        } else {
          payload.cabinet_code = cab.code;
          await api("/circuits", { method: "POST", body: JSON.stringify(payload) });
          toast("Circuito creado");
        }
        modal.remove(); reopenTopoAfterChange(cab.code, "circuitos");
      } catch (e) { toast(e.message, true); }
    };
    const cancel = el("button", "btn ghost sm", "Cancelar"); cancel.onclick = () => modal.remove();
    actions.append(save, cancel); card.append(actions);
    modal.append(card); document.body.append(modal);
  }

  // Ficha de información de una luminaria (el "recuadro" que pidió el capitán,
  // equivalente al editor del CM pero para un punto de luz). Se abre al clicar
  // la luminaria en el mapa o desde la tabla de luminarias.
  function openLightDetail(cab, pt) {
    const canEdit = has("cabinet:manage");
    const circ = (cab.circuits || []).find(c => c.id === pt.circuit_id);
    const modal = el("div", "modal"); const card = el("div", "modal-card"); card.style.maxWidth = "460px";
    const phaseColor = (window._topoCache?.phase_colors || {})[pt.phase] || "#64748b";
    const head = el("div", "row between");
    const farolaName = `Farola ${String(pt.number).padStart(2, "0")}`;
    head.innerHTML = `<h3 style="margin:0">💡 ${farolaName}</h3>`;
    const closeX = el("button", "btn ghost sm", "✕"); closeX.onclick = () => modal.remove();
    head.append(closeX); card.append(head);
    if (pt.label && pt.label !== farolaName) card.append(el("div", "muted", pt.label));

    card.style.maxWidth = "560px"; card.style.maxHeight = "85vh"; card.style.overflowY = "auto";
    const cmColor = cab.color || "#f97316";
    const circColor = circ ? circ.color : "#64748b";
    const sec = (txt) => { const h = el("div", "muted"); h.style.cssText = "font-size:11px; font-weight:600; letter-spacing:.5px; text-transform:uppercase; margin-top:14px; margin-bottom:6px; border-top:1px solid var(--border); padding-top:10px"; h.textContent = txt; card.append(h); };
    const grid = () => { const g = el("div"); g.style.display = "grid"; g.style.gridTemplateColumns = "1fr 1fr"; g.style.gap = "10px"; return g; };
    const cell = (k, v) => { const d = el("div"); d.innerHTML = `<div class="muted" style="font-size:11px">${k}</div><div style="font-size:14px">${v || "<span class='muted'>—</span>"}</div>`; return d; };
    const has = (k) => pt[k] != null && pt[k] !== "" && pt[k] !== 0;

    // === 🔌 Eléctrico Phoenix (lo primero — qué desconectar) ===
    sec("🔌 Eléctrico Phoenix");
    const elec = grid(); elec.append(
      cell("Centro de mando", `<span style="display:inline-block;width:10px;height:10px;border-radius:50%;background:${cmColor};margin-right:6px"></span>CM${cab.number} · ${cab.code}`),
      cell("Circuito", circ ? `<span style="display:inline-block;width:10px;height:10px;border-radius:50%;background:${circColor};margin-right:6px"></span>Circuito ${circ.number}${circ.name ? " · " + circ.name : ""}` : "—"),
      cell("Fase", `<span style="display:inline-block;width:10px;height:10px;border-radius:50%;background:${phaseColor};margin-right:6px"></span>${pt.phase}`),
      cell("Estado CM", cab._online === false ? "🔴 offline" : "🟢 en línea"),
    );
    card.append(elec);

    // === 🏷 Identificación ===
    sec("🏷 Identificación");
    const ident = grid(); ident.append(
      cell("Nº de poste", pt.number),
      cell("Nº inventario", pt.inventory_code),
      cell("Tecnología", pt.technology),
      cell("Fabricante", pt.manufacturer),
      cell("Modelo", pt.model),
      cell("Consumo", pt.power_w ? `${pt.power_w.toFixed(0)} W` : ""),
    );
    card.append(ident);

    // === 🔬 Óptica (solo si algún campo) ===
    if (["photometric","regulation","serial_number","color_temp_k","network_id"].some(k => has(k))) {
      sec("🔬 Óptica");
      const opt = grid(); opt.append(
        cell("Distribución fotométrica", pt.photometric),
        cell("Regulación", pt.regulation),
        cell("Nº de serie", pt.serial_number),
        cell("Temperatura de color", pt.color_temp_k),
        cell("ID de red", pt.network_id),
      );
      card.append(opt);
    }

    // === 📍 Ubicación ===
    sec("📍 Ubicación");
    const addr = grid(); addr.append(
      cell("Provincia", pt.province),
      cell("Localidad", pt.locality),
      cell("CP", pt.postal_code),
      cell("Vía", pt.street),
      cell("Número", pt.street_number),
      cell("Posición", pt.latitude != null ? `<span class="mono" style="font-size:12px">${pt.latitude.toFixed(5)}, ${pt.longitude.toFixed(5)}</span>` : ""),
    );
    card.append(addr);
    if (has("notes")) card.append(cell("Observaciones", pt.notes));

    // === 🛠 Montaje (solo si algún campo) ===
    if (["support_type","layout_type","construction_type","light_source_type"].some(k => has(k))) {
      sec("🛠 Montaje");
      const mnt = grid(); mnt.append(
        cell("Soporte", pt.support_type),
        cell("Disposición", pt.layout_type),
        cell("Construcción", pt.construction_type),
        cell("Fuente de luz", pt.light_source_type),
      );
      card.append(mnt);
    }

    // === 🔁 Desmontaje (solo si existe la antigua) ===
    if (["old_manufacturer","old_model","old_power_w","old_light_source_type","old_notes"].some(k => has(k))) {
      sec("🔁 Desmontaje (luminaria antigua)");
      const old = grid(); old.append(
        cell("Fabricante", pt.old_manufacturer),
        cell("Modelo", pt.old_model),
        cell("Potencia", pt.old_power_w ? `${pt.old_power_w.toFixed(0)} W` : ""),
        cell("Fuente", pt.old_light_source_type),
      );
      card.append(old);
      if (has("old_notes")) card.append(cell("Observaciones", pt.old_notes));
    }

    const actions = el("div", "perm-actions");
    if (canEdit) {
      const edit = el("button", "btn sm", "✏ Editar");
      edit.onclick = () => { modal.remove(); openLightForm(cab, pt); };
      const del = el("button", "btn ghost sm", "🗑 Borrar"); del.style.color = "#ef4444";
      del.onclick = () => { modal.remove(); deleteLight(cab, pt); };
      actions.append(edit, del);
    }
    const close = el("button", "btn ghost sm", "Cerrar"); close.onclick = () => modal.remove();
    actions.append(close); card.append(actions);
    modal.append(card); document.body.append(modal);
  }

  // Formulario completo de luminaria estilo RF Light GEO de Hispaled, con
  // 6 secciones colapsables. Eléctrico Phoenix arriba destacado porque es la
  // ventaja sobre RF Light (CM/circuito/fase para saber qué desconectar).
  // Fabricante/modelo/tecnología con autocompletado del catálogo en BD.
  function openLightForm(cab, pt, opts = {}) {
    const editing = !!pt;
    const pickCabinet = !!opts.pickCabinet;
    const prefill = opts.prefill || {};
    // En modo "elegir CM" (alta desde el mapa) arranco con el primer CM si no
    // se pasó uno. La lista de CMs sale del cache de topología.
    const allCabs = (window._topoCache || window._topology || { cabinets: [] }).cabinets;
    let curCab = cab || allCabs[0];
    const modal = el("div", "modal"); const card = el("div", "modal-card");
    card.style.maxWidth = "640px"; card.style.maxHeight = "85vh"; card.style.overflowY = "auto";
    card.innerHTML = `<h3 style="margin:0 0 4px">${editing ? "Editar luminaria" : "Nueva luminaria"}${curCab ? " · " + curCab.code : ""}</h3>`
      + `<div class="muted" style="font-size:12px; margin-bottom:14px">Ficha completa estilo RF Light GEO. Sólo el bloque eléctrico es imprescindible; el resto rellena lo que tengas (la dirección se detecta sola).</div>`;

    // mk crea un input; valor inicial = pt[k] ?? prefill[k] ?? v.
    const inputs = {};
    const mk = (k, ph, v, o = {}) => {
      const i = el("input"); i.placeholder = ph;
      i.value = pt?.[k] ?? prefill[k] ?? v ?? "";
      if (o.type) i.type = o.type; if (o.maxlength) i.maxLength = o.maxlength;
      if (o.inputmode) i.inputMode = o.inputmode;
      if (o.list) i.setAttribute("list", o.list);
      inputs[k] = i; return i;
    };
    const sectionHeader = (txt) => { const h = el("div", "muted"); h.style.cssText = "font-size:11px; font-weight:600; letter-spacing:.5px; text-transform:uppercase; margin-top:14px; margin-bottom:6px"; h.textContent = txt; return h; };
    const grid2 = () => { const g = el("div"); g.style.display = "grid"; g.style.gridTemplateColumns = "1fr 1fr"; g.style.gap = "8px"; return g; };
    const labeled = (lbl, node) => { const w = el("div"); w.innerHTML = `<div class="muted" style="font-size:11px; margin-bottom:2px">${lbl}</div>`; w.append(node); return w; };

    // === 🔌 Eléctrico Phoenix (ventaja sobre RF Light) ===
    card.append(sectionHeader("🔌 Eléctrico Phoenix · qué desconectar en el CM"));
    const circuit = el("select");
    const phase = el("select"); ["L1", "L2", "L3"].forEach(p => { const o = el("option", null, p); o.value = p; if ((pt?.phase || "L1") === p) o.selected = true; phase.append(o); });
    // Rellena el selector de circuitos con los del CM actual.
    const fillCircuits = () => {
      circuit.innerHTML = "";
      (curCab?.circuits || []).forEach(ci => { const o = el("option", null, `Circuito ${ci.number}${ci.name ? " · " + ci.name : ""}`); o.value = ci.id; if (pt?.circuit_id === ci.id) o.selected = true; circuit.append(o); });
      if (!(curCab?.circuits || []).length) { const o = el("option", null, "(sin circuitos — crea uno antes)"); o.value = ""; circuit.append(o); }
    };
    const elec = grid2();
    let cmNode;
    if (pickCabinet) {
      // Selector de CM: al cambiar, recargo sus circuitos.
      const cmSel = el("select");
      allCabs.forEach(x => { const o = el("option", null, `CM${x.number} · ${x.name || x.code}`); o.value = x.code; if (curCab && x.code === curCab.code) o.selected = true; cmSel.append(o); });
      cmSel.onchange = () => { curCab = allCabs.find(x => x.code === cmSel.value); fillCircuits(); };
      cmNode = labeled("Centro de mando", cmSel);
    } else {
      const i = el("input"); i.value = `${curCab?.code || ""} · ${curCab?.name || ""}`; i.disabled = true; i.style.opacity = ".7";
      cmNode = labeled("Centro de mando", i);
    }
    fillCircuits();
    elec.append(cmNode, labeled("Circuito", circuit), labeled("Fase", phase));
    card.append(elec);

    // === 🏷 Identificación ===
    card.append(sectionHeader("🏷 Identificación"));
    const ident = grid2();
    ident.append(
      labeled("Nº de poste / punto", mk("number", "Ej. 17", pt?.number ?? ((curCab?.points?.length || 0) + 1), { type: "number" })),
      labeled("Nº de inventario", mk("inventory_code", "Ej. P-099")),
      labeled("Tecnología", mk("technology", "LED…", "LED", { list: "lf-tech" })),
      labeled("Fabricante / marca", mk("manufacturer", "Hispaled, Schréder…", "", { list: "lf-mfr" })),
      labeled("Modelo", mk("model", "RF Light…", "", { list: "lf-mdl" })),
      labeled("Consumo (W)", mk("power_w", "30", pt?.power_w ?? 100, { type: "number" })),
    );
    card.append(ident);
    const labelInp = mk("label", "Etiqueta interna (opcional)", pt?.label || "");
    card.append(labeled("Etiqueta", labelInp));

    // === 🔬 Óptica ===
    card.append(sectionHeader("🔬 Óptica · driver y regulación"));
    const opt = grid2();
    opt.append(
      labeled("Distribución fotométrica", mk("photometric", "Asimétrica vial…")),
      labeled("Tipo de regulación", mk("regulation", "1-10 V, DALI…", "", { list: "lf-reg" })),
      labeled("Nº de serie luminaria", mk("serial_number", "SN-12345")),
      labeled("Temperatura de color", mk("color_temp_k", "3000K", "", { list: "lf-tc" })),
      labeled("ID de red (RF/LoRa/DALI)", mk("network_id", "Nodo 0x1A2B")),
    );
    card.append(opt);

    // === 📍 Ubicación (auto desde GPS) ===
    card.append(sectionHeader("📍 Ubicación · detectar desde GPS"));
    const lat = mk("latitude", "Latitud", pt?.latitude ?? "", { type: "number" });
    const lon = mk("longitude", "Longitud", pt?.longitude ?? "", { type: "number" });
    const coords = grid2(); coords.append(labeled("Latitud", lat), labeled("Longitud", lon));
    card.append(coords);
    const geoBtn = el("button", "btn ghost sm", "📍 Detectar calle, CP, ciudad y provincia desde GPS");
    geoBtn.style.marginTop = "6px";
    geoBtn.onclick = async () => {
      if (!lat.value || !lon.value) { toast("Pon antes la latitud y longitud.", true); return; }
      geoBtn.textContent = "Buscando…"; geoBtn.disabled = true;
      const a = await reverseGeocode(parseFloat(lat.value), parseFloat(lon.value));
      geoBtn.textContent = "📍 Detectar calle, CP, ciudad y provincia desde GPS"; geoBtn.disabled = false;
      if (a) {
        if (a.street) inputs.street.value = a.street;
        if (a.street_number) inputs.street_number.value = a.street_number;
        if (a.postal_code) inputs.postal_code.value = a.postal_code;
        if (a.locality) inputs.locality.value = a.locality;
        if (a.province) inputs.province.value = a.province;
        toast("Dirección detectada");
      } else { toast("No se pudo detectar (sin red o sin datos).", true); }
    };
    card.append(geoBtn);
    const addr = grid2();
    addr.append(
      labeled("Provincia", mk("province", "Alicante")),
      labeled("Localidad / Ciudad", mk("locality", "Benidorm")),
      labeled("Código postal", mk("postal_code", "03501", "", { maxlength: 10 })),
      labeled("Vía / Calle", mk("street", "Av. Mediterráneo")),
    );
    card.append(addr);
    const num2 = mk("street_number", "12", "", { maxlength: 16 });
    card.append(labeled("Número de portal", num2));
    const notes = mk("notes", "Observaciones", "");
    card.append(labeled("Observaciones", notes));

    // === 🛠 Montaje ===
    card.append(sectionHeader("🛠 Montaje"));
    const mnt = grid2();
    mnt.append(
      labeled("Tipo de soporte", mk("support_type", "Columna, brazo mural…", "", { list: "lf-sup" })),
      labeled("Disposición en la vía", mk("layout_type", "Unilateral, tresbolillo…", "", { list: "lf-lay" })),
      labeled("Tipo de construcción", mk("construction_type", "Acero galvanizado…")),
      labeled("Tipo de fuente de luz", mk("light_source_type", "LED, VSAP…", "", { list: "lf-src" })),
    );
    card.append(mnt);

    // === 🔁 Desmontaje (colapsable, sólo si interesa) ===
    const oldDetails = el("details"); oldDetails.style.marginTop = "12px";
    const sum = el("summary", "muted", "🔁 Desmontaje · datos de la luminaria antigua (opcional)");
    sum.style.cssText = "cursor:pointer; font-size:12px; font-weight:600; padding:6px 0";
    oldDetails.append(sum);
    const oldGrid = grid2();
    oldGrid.append(
      labeled("Fabricante antiguo", mk("old_manufacturer", "")),
      labeled("Modelo antiguo", mk("old_model", "")),
      labeled("Potencia antigua (W)", mk("old_power_w", "150", pt?.old_power_w ?? 0, { type: "number" })),
      labeled("Fuente de luz antigua", mk("old_light_source_type", "VSAP")),
    );
    oldDetails.append(oldGrid);
    oldDetails.append(labeled("Observaciones del desmontaje", mk("old_notes", "")));
    card.append(oldDetails);

    // Datalists para autocompletado (se rellenan al cargar el catálogo).
    const dlBox = el("div"); dlBox.style.display = "none";
    [
      ["lf-tech", "technologies"], ["lf-mfr", "manufacturers"], ["lf-mdl", "models"],
      ["lf-reg", "regulations"], ["lf-tc", "color_temps"],
      ["lf-sup", "support_types"], ["lf-lay", "layout_types"], ["lf-src", "light_source_types"],
    ].forEach(([id]) => { const dl = el("datalist"); dl.id = id; dlBox.append(dl); });
    card.append(dlBox);

    (async () => {
      try {
        const cat = await api("/lightpoints/catalog");
        const fill = (id, arr) => { const dl = document.getElementById(id); if (!dl) return; dl.innerHTML = ""; (arr || []).forEach(v => { const o = el("option"); o.value = v; dl.append(o); }); };
        fill("lf-tech", cat.technologies); fill("lf-mfr", cat.manufacturers); fill("lf-mdl", cat.models);
        fill("lf-reg", cat.regulations); fill("lf-tc", cat.color_temps);
        fill("lf-sup", cat.support_types); fill("lf-lay", cat.layout_types); fill("lf-src", cat.light_source_types);
      } catch (e) { /* sin catálogo → sigue funcionando como texto libre */ }
    })();

    const actions = el("div", "perm-actions");
    const save = el("button", "btn sm", editing ? "Guardar" : "Crear");
    save.onclick = async () => {
      // Construyo el payload con todos los campos de texto (trim) y los numéricos.
      const val = (k) => (inputs[k]?.value ?? "").toString().trim();
      const num = (k, def = 0) => { const v = parseFloat(inputs[k]?.value); return isNaN(v) ? def : v; };
      const payload = {
        circuit_id: parseInt(circuit.value, 10),
        phase: phase.value,
        number: parseInt(val("number"), 10) || 1,
        label: val("label"),
        power_w: num("power_w", 0),
        inventory_code: val("inventory_code"),
        technology: val("technology"),
        manufacturer: val("manufacturer"),
        model: val("model"),
        photometric: val("photometric"),
        regulation: val("regulation"),
        serial_number: val("serial_number"),
        color_temp_k: val("color_temp_k"),
        network_id: val("network_id"),
        province: val("province"),
        locality: val("locality"),
        postal_code: val("postal_code"),
        street: val("street"),
        street_number: val("street_number"),
        notes: val("notes"),
        support_type: val("support_type"),
        layout_type: val("layout_type"),
        construction_type: val("construction_type"),
        light_source_type: val("light_source_type"),
        old_manufacturer: val("old_manufacturer"),
        old_model: val("old_model"),
        old_power_w: num("old_power_w", 0),
        old_light_source_type: val("old_light_source_type"),
        old_notes: val("old_notes"),
        latitude: val("latitude") ? parseFloat(val("latitude")) : null,
        longitude: val("longitude") ? parseFloat(val("longitude")) : null,
      };
      if (!payload.circuit_id) { toast("Ese CM no tiene circuitos. Crea uno antes de añadir luminarias.", true); return; }
      try {
        // Si hay coords y faltan datos administrativos, intento autorrellenar
        // antes de guardar (best-effort, no bloquea si falla).
        if (payload.latitude != null && !payload.street) {
          const a = await reverseGeocode(payload.latitude, payload.longitude);
          if (a) {
            payload.street = payload.street || a.street;
            payload.street_number = payload.street_number || a.street_number;
            payload.postal_code = payload.postal_code || a.postal_code;
            payload.locality = payload.locality || a.locality;
            payload.province = payload.province || a.province;
          }
        }
        if (editing) {
          await api(`/lightpoints/${pt.id}`, { method: "PATCH", body: JSON.stringify(payload) });
          toast("Luminaria actualizada");
        } else {
          payload.cabinet_code = curCab.code;
          await api("/lightpoints", { method: "POST", body: JSON.stringify(payload) });
          toast("Luminaria creada");
        }
        modal.remove(); reopenTopoAfterChange(curCab.code, "luminarias");
      } catch (e) { toast(e.message, true); }
    };
    const cancel = el("button", "btn ghost sm", "Cancelar"); cancel.onclick = () => modal.remove();
    actions.append(save, cancel); card.append(actions);
    modal.append(card); document.body.append(modal);
  }

  // Geocoding inverso (lat/lon → ficha de dirección completa) vía Nominatim
  // de OpenStreetMap. Best-effort: si no hay red devuelve null. Devuelve
  // {street, street_number, postal_code, locality, province} para rellenar
  // la ficha de RF Light GEO de un tirón.
  async function reverseGeocode(lat, lon) {
    try {
      const url = `https://nominatim.openstreetmap.org/reverse?format=json&zoom=18&addressdetails=1&lat=${lat}&lon=${lon}`;
      const r = await fetch(url, { headers: { "Accept-Language": "es" } });
      if (!r.ok) return null;
      const d = await r.json();
      const a = d.address || {};
      const road = a.road || a.pedestrian || a.footway || a.residential || a.cycleway || d.name || "";
      return {
        street: road,
        street_number: a.house_number || "",
        postal_code: a.postcode || "",
        // Nominatim usa city/town/village según tamaño. Cogemos el primero que haya.
        locality: a.city || a.town || a.village || a.hamlet || a.municipality || "",
        // Provincia: en España viene normalmente en "province" o "state".
        province: a.province || a.state || a.county || "",
      };
    } catch (e) { return null; }
  }

  // Geocoding directo (texto → ubicación): "Benidorm" o un CP devuelve la
  // ciudad/provincia. Para autocompletar el alta de proyecto. Best-effort.
  async function forwardGeocode(query) {
    try {
      const url = `https://nominatim.openstreetmap.org/search?format=json&addressdetails=1&limit=1&accept-language=es&q=${encodeURIComponent(query)}`;
      const r = await fetch(url, { headers: { "Accept-Language": "es" } });
      if (!r.ok) return null;
      const arr = await r.json();
      if (!arr || !arr[0]) return null;
      const a = arr[0].address || {};
      const city = a.city || a.town || a.village || a.municipality || a.county || arr[0].display_name.split(",")[0];
      return { city, province: a.province || a.state || "", postal_code: a.postcode || "" };
    } catch (e) { return null; }
  }

  // --- Borrados con confirmación -----------------------------------------
  async function deleteCabinet(cab) {
    if (!confirm(`¿Borrar el cuadro ${cab.code}?\n\nSe eliminarán también sus ${cab.circuits.length} circuitos y ${cab.points.length} luminarias. Esta acción no se puede deshacer.`)) return;
    try { await api(`/cabinets/registry/${encodeURIComponent(cab.code)}`, { method: "DELETE" }); toast("Cuadro borrado: " + cab.code); loadTopologia(); }
    catch (e) { toast(e.message, true); }
  }
  async function deleteCircuit(cab, ci, lightCount) {
    if (lightCount > 0) { toast(`Tiene ${lightCount} luminaria(s). Bórralas o muévelas primero.`, true); return; }
    if (!confirm(`¿Borrar el circuito ${ci.number} de ${cab.code}?`)) return;
    try { await api(`/circuits/${ci.id}`, { method: "DELETE" }); toast("Circuito borrado"); reopenTopoAfterChange(cab.code, "circuitos"); }
    catch (e) { toast(e.message, true); }
  }
  // Reasignar un circuito (con sus luminarias) a otro CM. Caso típico: tras
  // un retrofit LED se fusionan dos cuadros en uno.
  function moveCircuitToCabinet(cab, ci, lightCount) {
    const tp = window._topoCache;
    const targets = (tp?.cabinets || []).filter(x => x.code !== cab.code);
    if (!targets.length) { toast("No hay otro CM al que mover. Crea otro cuadro primero.", true); return; }
    const modal = el("div", "modal"); const card = el("div", "modal-card");
    card.innerHTML = `<h3 style="margin:0 0 6px">Mover circuito ${ci.number} a otro CM</h3>`
      + `<div class="muted" style="font-size:12px; margin-bottom:12px">Se moverán también sus ${lightCount} luminaria(s). El CM origen (${cab.code}) las pierde.</div>`;
    const sel = el("select"); sel.style.width = "100%";
    targets.forEach(t => { const o = el("option", null, `CM${t.number} · ${t.name || t.code} (${t.code})`); o.value = t.code; sel.append(o); });
    card.append(sel);
    const actions = el("div", "perm-actions");
    const ok = el("button", "btn sm", "Mover");
    ok.onclick = async () => {
      const dest = sel.value;
      try {
        await api(`/circuits/${ci.id}`, { method: "PATCH", body: JSON.stringify({ cabinet_code: dest }) });
        toast(`Circuito movido a ${dest}`);
        modal.remove();
        reopenTopoAfterChange(dest, "circuitos");
      } catch (e) { toast(e.message, true); }
    };
    const cancel = el("button", "btn ghost sm", "Cancelar"); cancel.onclick = () => modal.remove();
    actions.append(ok, cancel); card.append(actions);
    modal.append(card); document.body.append(modal);
  }
  async function deleteLight(cab, pt) {
    if (!confirm(`¿Borrar la luminaria ${pt.number}${pt.label ? " (" + pt.label + ")" : ""}?`)) return;
    try { await api(`/lightpoints/${pt.id}`, { method: "DELETE" }); toast("Luminaria borrada"); reopenTopoAfterChange(cab.code, "luminarias"); }
    catch (e) { toast(e.message, true); }
  }
  async function wipeTopology(count) {
    if (!confirm(`💣 VACIAR TODA LA TOPOLOGÍA\n\nSe borrarán los ${count} cuadros con TODOS sus circuitos y luminarias.\n\nEsto es irreversible. ¿Continuar?`)) return;
    if (!confirm("Última confirmación: ¿seguro que quieres empezar de cero?")) return;
    try { const r = await api("/cabinets/registry/wipe-all", { method: "POST" }); toast(`Topología vaciada: ${r.cabinets} cuadros, ${r.circuits} circuitos, ${r.points} luminarias`); loadTopologia(); }
    catch (e) { toast(e.message, true); }
  }

  // Tras un cambio en circuitos/luminarias, recargo la topología y reabro el
  // editor del mismo CM en la pestaña donde estaba, para no perder el foco.
  async function reopenTopoAfterChange(code, tab) {
    try {
      const tp = await api("/topology");
      window._topoCache = tp;
      window._topology = tp;
      const cab = tp.cabinets.find(x => x.code === code);
      // Cierro cualquier modal abierto (editor previo + formularios) para no
      // apilarlos al reabrir con los datos frescos.
      document.querySelectorAll(".modal").forEach(m => m.remove());
      if (state.view === "inicio") {
        // En Inicio el contexto es el mapa: refresco marcadores en vez de
        // abrir el editor del CM. Quito los marcadores actuales (ahora son
        // L.marker, no CircleMarker) y los recreo para reflejar altas/bajas.
        if (window._map) {
          [...Object.values(window._cmMarkers || {}), ...Object.values(window._ptMarkers || {})]
            .forEach(m => { try { window._map.removeLayer(m); } catch (e) {} });
        }
        window._cmMarkers = {}; window._ptMarkers = {};
        drawTopology();
        await refreshLive();
      } else {
        if (state.view === "topologia") loadTopologia();
        if (cab) { state.topoTab = tab; openTopoDetail(cab, tp, has("cabinet:manage")); }
      }
    } catch (e) { toast(e.message, true); }
  }

  // ============================ Usuarios ============================
  async function loadUsers() {
    const c = $("#content"); c.innerHTML = "";
    try {
      const users = await api(scopeQuery("/users"));
      // Alta de usuarios (solo admins). No hay auto-registro: el admin da el acceso.
      if (has("user:manage")) {
        const cp = el("div", "panel"); cp.style.marginBottom = "14px";
        cp.append(el("div", null, "<strong>Crear usuario</strong> <span class='muted' style='font-size:12px'>· define las 4 credenciales (PIN/patrón son opcionales, el propio usuario los podrá cambiar al entrar)</span>"));
        const grid = el("div"); grid.style.display = "grid"; grid.style.gridTemplateColumns = "1fr 1fr"; grid.style.gap = "12px"; grid.style.marginTop = "12px";

        // Columna izquierda: identidad + contraseña + PIN + rango.
        const left = el("div"); left.style.display = "grid"; left.style.gap = "8px";
        const u = el("input"); u.placeholder = "usuario";
        const pw = el("input"); pw.type = "password"; pw.placeholder = "contraseña (mín. 6)";
        const pin = el("input"); pin.type = "password"; pin.inputMode = "numeric"; pin.maxLength = 8; pin.placeholder = "PIN (4-8 dígitos, opcional)";
        const rk = el("select");
        const allowed = (state.ranksCatalog || []).filter(r => r.id !== "owner");
        allowed.forEach(r => { const o = el("option", null, r.label); o.value = r.id; if (r.id === "novato") o.selected = true; rk.append(o); });
        const hint = el("div", "muted"); hint.style.fontSize = "12px";
        const updateHint = () => { const r = allowed.find(x => x.id === rk.value); hint.textContent = r ? r.description : ""; };
        rk.onchange = updateHint; updateHint();
        left.append(u, pw, pin, rk, hint);

        // Columna derecha: widget de patrón inline.
        const right = el("div"); right.style.display = "grid"; right.style.justifyItems = "center"; right.style.gap = "6px";
        right.append(el("div", "muted", "Patrón (opcional)"));
        let pattern = "";
        const pad = makePatternPad(seq => { pattern = seq; });
        right.append(pad);
        const reset = el("button", "btn ghost sm", "Repetir patrón"); reset.onclick = () => { pad.reset(); pattern = ""; };
        right.append(reset);

        grid.append(left, right); cp.append(grid);

        const b = el("button", "btn", "Crear usuario"); b.style.marginTop = "12px";
        b.onclick = async () => {
          if (!u.value.trim()) { toast("Falta el usuario.", true); return; }
          if (pw.value.length < 6) { toast("La contraseña debe tener al menos 6 caracteres.", true); return; }
          if (pin.value && !/^\d{4,8}$/.test(pin.value)) { toast("PIN: 4-8 dígitos.", true); return; }
          if (pattern && pattern.length < 4) { toast("El patrón debe unir al menos 4 puntos.", true); return; }
          const body = { username: u.value.trim(), password: pw.value, rank: rk.value };
          if (pin.value) body.pin = pin.value;
          if (pattern) body.pattern = pattern;
          try {
            await api("/users", { method: "POST", body: JSON.stringify(body) });
            toast("Usuario creado: " + body.username);
            u.value = pw.value = pin.value = ""; pad.reset(); pattern = "";
            loadUsers();
          } catch (e) { toast(e.message, true); }
        };
        cp.append(b); c.append(cp);
      }
      const p = el("div", "panel");
      const t = el("table");
      t.innerHTML = `<thead><tr><th>ID</th><th>Usuario</th><th>Rango</th><th>Puntos</th><th>Activo</th><th></th></tr></thead>`;
      const tb = el("tbody");
      users.forEach(u => {
        const tr = el("tr");
        tr.innerHTML = `<td class="mono">${u.id}</td><td>${cap(u.username)}</td><td><span class="badge rank">${rankLabel(u.rank)}</span></td><td class="mono">${u.activity_points}</td><td>${u.is_active ? "sí" : "no"}</td>`;
        const td = el("td");
        if (has("user:manage")) {
          const sel = el("select"); sel.style.width = "150px";
          (state.ranksCatalog || []).forEach(r => { const o = el("option", null, r.label); o.value = r.id; o.title = r.description; if (r.id === u.rank) o.selected = true; sel.append(o); });
          sel.onchange = async () => { try { await api(`/users/${u.id}/rank`, { method: "POST", body: JSON.stringify({ rank: sel.value }) }); toast(`${cap(u.username)} → ${rankLabel(sel.value)}`); loadUsers(); } catch (e) { toast(e.message, true); } };
          td.append(sel);
          const pb = el("button", "btn sm ghost", "Clave");
          pb.style.marginLeft = "8px";
          pb.onclick = async () => {
            const np = prompt(`Nueva contraseña para ${cap(u.username)} (mín. 6):`);
            if (!np) return;
            try { await api(`/users/${u.id}/password`, { method: "POST", body: JSON.stringify({ password: np }) }); toast("Contraseña actualizada"); }
            catch (e) { toast(e.message, true); }
          };
          td.append(pb);
        }
        tr.append(td); tb.append(tr);
      });
      t.append(tb); p.append(t); c.append(p);
    } catch (e) { c.append(el("div", "empty", e.message)); }
  }

  // ============================ Auditoría ============================
  // ============================ Rangos / permisos ============================
  // Editor en vivo: cada card lista los permisos como checkboxes y se guarda
  // entero al pulsar "Guardar cambios". El backend audita y rechaza permisos
  // que el usuario actual no tiene él mismo (anti-escalado).
  // Editor de rangos · layout master-detail (estilo Hydra):
  // a la izquierda lista vertical de rangos; a la derecha, detalle con
  // checklist y acciones del rango seleccionado. Mucho más compacto.
  async function loadRoles() {
    const c = $("#content"); c.innerHTML = "";
    try {
      const [perms, roles] = await Promise.all([
        api("/roles/permissions"),
        api("/roles"),
      ]);
      const canEdit = has("role:manage");
      const sorted = roles.slice().sort((a, b) => b.level - a.level);
      // Selección persistente entre re-renders.
      if (state.selectedRole !== "__new__" && !sorted.find(r => r.id === state.selectedRole)) {
        state.selectedRole = sorted[0]?.id || null;
      }

      const wrap = el("div", "roles-layout");

      // ---- Columna izquierda: lista de rangos ----
      const aside = el("div", "roles-list");
      const head = el("div", "roles-list-head");
      head.innerHTML = `<strong>Rangos</strong><span class="muted" style="font-size:11px">${roles.length} en catálogo</span>`;
      aside.append(head);
      sorted.forEach(r => {
        const item = el("div", "role-item" + (r.id === state.selectedRole ? " active" : ""));
        const dotCls = r.is_owner ? "bad" : (r.is_builtin ? "ok" : "warn");
        item.innerHTML = `
          <span class="role-dot ${dotCls}"></span>
          <div class="role-meta">
            <div class="role-name">${r.label}</div>
            <div class="role-sub muted">nivel ${r.level} · ${r.is_owner ? "protegido" : (r.is_builtin ? "por defecto" : "custom")}</div>
          </div>
          <span class="muted mono" style="font-size:11px">${(r.permissions || []).length}</span>`;
        item.onclick = () => { state.selectedRole = r.id; loadRoles(); };
        aside.append(item);
      });
      if (canEdit) {
        const add = el("div", "role-item add");
        add.innerHTML = `<span class="role-dot" style="background:var(--dim)"></span><div class="role-meta"><div class="role-name">+ Nuevo rango</div><div class="role-sub muted">crear personalizado</div></div>`;
        add.onclick = () => { state.selectedRole = "__new__"; loadRoles(); };
        aside.append(add);
      }
      wrap.append(aside);

      // ---- Columna derecha: detalle ----
      const detail = el("div", "roles-detail panel");

      if (state.selectedRole === "__new__") {
        renderNewRoleForm(detail);
      } else {
        const role = sorted.find(r => r.id === state.selectedRole) || sorted[0];
        if (!role) {
          detail.append(el("div", "empty", "Selecciona un rango."));
        } else {
          renderRoleDetail(detail, role, perms, sorted, canEdit);
        }
      }
      wrap.append(detail);
      c.append(wrap);
    } catch (e) { c.append(el("div", "empty", e.message)); }
  }

  function renderRoleDetail(detail, role, perms, allRoles, canEdit) {
    const myRole = allRoles.find(r => r.id === state.me?.rank);
    const myLevel = myRole?.level ?? 0;
    const locked = role.is_owner || !canEdit || role.level >= myLevel;

    const head = el("div");
    const badges = [];
    if (role.is_owner) badges.push(`<span class="badge bad">protegido</span>`);
    else if (role.is_builtin) badges.push(`<span class="badge ok">por defecto</span>`);
    else badges.push(`<span class="badge warn">custom</span>`);
    if (locked && !role.is_owner) badges.push(`<span class="badge">solo lectura</span>`);
    head.innerHTML = `
      <div style="display:flex; align-items:baseline; gap:10px; flex-wrap:wrap">
        <h3 style="margin:0; font-size:18px">${role.label}</h3>
        <span class="muted mono" style="font-size:11px">id ${role.id} · nivel ${role.level}</span>
      </div>
      <div class="muted" style="font-size:12px; margin-top:4px">${role.description || ""}</div>
      <div style="margin-top:6px">${badges.join(" ")}</div>`;
    detail.append(head);

    detail.append(el("div", "perm-hr"));

    // Checklist de permisos (vertical).
    const list = el("div", "perm-list");
    const checkboxes = {};
    if (role.is_owner) {
      list.append(el("div", "muted", "El rango owner tiene todos los permisos (wildcard *) y no se puede editar."));
    } else {
      perms.forEach(p => {
        const row = el("label", "perm-row" + (locked ? " locked" : ""));
        const cb = el("input"); cb.type = "checkbox"; cb.checked = role.permissions.includes(p.id); cb.disabled = locked;
        checkboxes[p.id] = cb;
        const txt = el("div");
        txt.innerHTML = `<div class="perm-label">${p.label} <span class="mono muted" style="font-size:11px">${p.id}</span></div><div class="muted" style="font-size:11px">${p.description}</div>`;
        row.append(cb, txt); list.append(row);
      });
    }
    detail.append(list);

    if (!role.is_owner && !locked) {
      const actions = el("div", "perm-actions");
      const save = el("button", "btn sm", "Guardar cambios");
      save.onclick = async () => {
        const newPerms = Object.entries(checkboxes).filter(([, cb]) => cb.checked).map(([id]) => id);
        try { await api(`/roles/${role.id}`, { method: "PATCH", body: JSON.stringify({ permissions: newPerms }) }); toast("Rango actualizado"); loadRoles(); }
        catch (e) { toast(e.message, true); }
      };
      const rename = el("button", "btn ghost sm", "Renombrar / descripción");
      rename.onclick = async () => {
        const nl = prompt("Nombre visible:", role.label); if (nl === null) return;
        const nd = prompt("Descripción:", role.description || ""); if (nd === null) return;
        try { await api(`/roles/${role.id}`, { method: "PATCH", body: JSON.stringify({ label: nl, description: nd }) }); toast("Actualizado"); loadRoles(); }
        catch (e) { toast(e.message, true); }
      };
      actions.append(save, rename);
      if (!role.is_builtin) {
        const del = el("button", "btn ghost sm", "Borrar rango");
        del.onclick = async () => {
          if (!confirm(`¿Borrar el rango "${role.label}"? Solo si nadie lo tiene asignado.`)) return;
          try { await api(`/roles/${role.id}`, { method: "DELETE" }); toast("Rango borrado"); state.selectedRole = null; loadRoles(); }
          catch (e) { toast(e.message, true); }
        };
        actions.append(del);
      }
      detail.append(actions);
    }
  }

  function renderNewRoleForm(detail) {
    detail.innerHTML = `<h3 style="margin:0 0 4px">Nuevo rango</h3><div class="muted" style="font-size:12px; margin-bottom:14px">Crea un rango personalizado (auditor externo, ingeniero júnior, etc.)</div>`;
    const form = el("div"); form.style.display = "grid"; form.style.gap = "10px";
    const idIn = el("input"); idIn.placeholder = "id (minúsculas, sin espacios)";
    const lbIn = el("input"); lbIn.placeholder = "Nombre visible";
    const lvIn = el("input"); lvIn.type = "number"; lvIn.placeholder = "Nivel (0-99)"; lvIn.min = 0; lvIn.max = 99;
    const desc = el("input"); desc.placeholder = "Descripción (opcional)";
    form.append(idIn, lbIn, lvIn, desc);
    detail.append(form);
    const actions = el("div", "perm-actions");
    const create = el("button", "btn sm", "Crear rango");
    create.onclick = async () => {
      if (!idIn.value.trim() || !lbIn.value.trim() || !lvIn.value) { toast("Falta id, nombre o nivel.", true); return; }
      try {
        const r = await api("/roles", { method: "POST", body: JSON.stringify({
          id: idIn.value.trim(), label: lbIn.value.trim(),
          description: desc.value, level: parseInt(lvIn.value, 10), permissions: [],
        })});
        toast("Rango creado: " + r.label);
        state.selectedRole = r.id;
        loadRoles();
      } catch (e) { toast(e.message, true); }
    };
    const cancel = el("button", "btn ghost sm", "Cancelar");
    cancel.onclick = () => { state.selectedRole = null; loadRoles(); };
    actions.append(create, cancel);
    detail.append(actions);
  }

  // ============================ PERMISOS (vista unificada) ============================
  // Una sola pestaña que reemplaza Usuarios + Rangos. Layout:
  //   [Tab Usuarios | Tab Rangos]
  // - Usuarios: lista compacta expandible (acordeón). Cada usuario expandido
  //   muestra rol, permisos efectivos en chips, overrides individuales y
  //   acciones. Botón "+ Crear" arriba abre el formulario inline.
  // - Rangos: master-detail compacto (la función loadRoles existente).
  async function loadPermisos() {
    const c = $("#content"); c.innerHTML = "";
    state.permisosTab = state.permisosTab || "usuarios";

    // Proyectos ya es una sección propia del menú (no una pestaña aquí).
    const tabDefs = [["usuarios", "Usuarios"], ["rangos", "Rangos"]];
    if (state.permisosTab === "proyectos") state.permisosTab = "usuarios";

    const tabs = el("div", "tabs");
    tabDefs.forEach(([k, lbl]) => {
      const b = el("button", "tab" + (state.permisosTab === k ? " active" : ""), lbl);
      b.onclick = () => { state.permisosTab = k; loadPermisos(); };
      tabs.append(b);
    });
    c.append(tabs);

    const body = el("div", "tab-body");
    c.append(body);

    if (state.permisosTab === "usuarios") await renderPermisosUsuarios(body);
    else await renderPermisosRangos(body);
  }

  // Sección "Proyectos" del menú (solo Director/Phoenix por el data-perm).
  // El owner gestiona (crear/borrar/asignar); un director ve sus ciudades
  // en solo lectura (el backend ya exige owner para crear/borrar).
  async function loadProyectos() {
    const c = $("#content"); c.innerHTML = "";
    await renderProyectos(c);
  }

  async function renderProyectos(body) {
    try {
      const [projects, users, regs] = await Promise.all([
        api("/projects"),
        api("/users").catch(() => []),
        api("/cabinets/registry").catch(() => []),
      ]);
      const countUsers = (pid) => users.filter(u => u.project_id === pid).length;
      const countCabs = (pid) => regs.filter(r => r.project_id === pid).length;

      // Alta de proyecto.
      const cp = el("div", "panel"); cp.style.marginBottom = "14px";
      cp.append(el("div", null, "<strong>Crear proyecto / ciudad</strong> <span class='muted' style='font-size:12px'>· aísla cuadros y usuarios de cada cliente</span>"));
      const code = el("input"); code.placeholder = "código (p.ej. madrid)"; code.style.width = "180px";
      const name = el("input"); name.placeholder = "nombre (p.ej. Madrid Centro)"; name.style.flex = "1";

      // Fila de búsqueda: ciudad o CP → autocompleta nombre y sugiere código.
      const slugify = (s) => s.toLowerCase().normalize("NFD").replace(/[̀-ͯ]/g, "").replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "");
      const searchRow = el("div", "row"); searchRow.style.marginTop = "10px"; searchRow.style.gap = "8px"; searchRow.style.flexWrap = "wrap";
      const search = el("input"); search.placeholder = "🔍 buscar ciudad o CP (autocompleta)"; search.style.flex = "1";
      const find = el("button", "btn ghost sm", "Buscar");
      const doSearch = async () => {
        const q = search.value.trim(); if (!q) return;
        find.disabled = true; find.textContent = "Buscando…";
        const res = await forwardGeocode(q);
        find.disabled = false; find.textContent = "Buscar";
        if (!res || !res.city) { toast("No encontrado. Prueba otra búsqueda.", true); return; }
        name.value = res.province && res.province !== res.city ? `${res.city} (${res.province})` : res.city;
        if (!code.value.trim()) code.value = slugify(res.city);
        toast(`→ ${res.city}${res.postal_code ? " · CP " + res.postal_code : ""}`);
      };
      find.onclick = doSearch;
      search.onkeydown = (e) => { if (e.key === "Enter") doSearch(); };
      searchRow.append(search, find); cp.append(searchRow);

      const row = el("div", "row"); row.style.marginTop = "10px"; row.style.gap = "8px"; row.style.flexWrap = "wrap";
      const add = el("button", "btn sm", "Crear");
      add.onclick = async () => {
        if (!code.value.trim() || !name.value.trim()) { toast("Falta código o nombre.", true); return; }
        try { await api("/projects", { method: "POST", body: JSON.stringify({ code: code.value.trim(), name: name.value.trim() }) }); toast("Proyecto creado"); loadProjectsForChip(); loadProyectos(); }
        catch (e) { toast(e.message, true); }
      };
      row.append(code, name, add); cp.append(row);
      if (isOwnerUser()) body.append(cp);  // crear proyecto: solo el owner

      // Lista de proyectos.
      const panel = el("div", "panel");
      const t = el("table");
      t.innerHTML = `<thead><tr><th>ID</th><th>Código</th><th>Nombre</th><th>Usuarios</th><th>Cuadros</th><th></th></tr></thead>`;
      const tb = el("tbody");
      projects.forEach(p => {
        const nu = countUsers(p.id), nc = countCabs(p.id);
        const tr = el("tr");
        tr.innerHTML = `<td class="mono">${p.id}</td><td class="mono">${p.code}</td><td>${p.name}</td><td class="mono">${nu}</td><td class="mono">${nc}</td>`;
        const td = el("td");
        if (isOwnerUser()) {  // borrar proyecto: solo el owner
          const del = el("button", "btn ghost sm", "🗑"); del.style.color = "#ef4444";
          del.onclick = async () => {
            if (nu || nc) { toast(`No se puede borrar: ${nu} usuarios y ${nc} cuadros lo usan.`, true); return; }
            if (!confirm(`¿Borrar el proyecto "${p.name}"?`)) return;
            try { await api(`/projects/${p.id}`, { method: "DELETE" }); toast("Proyecto borrado"); loadProjectsForChip(); loadProyectos(); }
            catch (e) { toast(e.message, true); }
          };
          td.append(del);
        }
        tr.append(td); tb.append(tr);
      });
      if (!projects.length) tb.append(el("tr", null, `<td colspan="6" class="muted" style="text-align:center;padding:12px">Sin proyectos. Crea el primero arriba.</td>`));
      t.append(tb); panel.append(t); body.append(panel);
    } catch (e) { body.append(el("div", "empty", e.message)); }
  }

  async function renderPermisosUsuarios(body) {
    try {
      const [users, perms] = await Promise.all([
        api(scopeQuery("/users")),
        api("/roles/permissions").catch(() => []),
      ]);
      const permLabel = {}; perms.forEach(p => { permLabel[p.id] = p.label; });

      // Botón crear usuario (toggle inline).
      const tools = el("div", "row between"); tools.style.marginBottom = "10px";
      tools.innerHTML = `<div class="muted" style="font-size:12px">${users.length} usuario(s) en este alcance · pulsa una fila para ver permisos.</div>`;
      const addBtn = el("button", "btn sm", "+ Crear usuario");
      tools.append(addBtn);
      body.append(tools);

      const addPanel = el("div", "panel hidden"); addPanel.id = "new-user-panel";
      body.append(addPanel);
      addBtn.onclick = () => {
        addPanel.classList.toggle("hidden");
        if (!addPanel.classList.contains("hidden")) renderNewUserForm(addPanel);
      };

      const list = el("div", "user-list");
      users.forEach(u => list.append(buildUserRow(u, permLabel)));
      if (!users.length) list.append(el("div", "empty", "Sin usuarios."));
      body.append(list);
    } catch (e) { body.append(el("div", "empty", e.message)); }
  }

  function buildUserRow(u, permLabel) {
    const row = el("div", "user-row");
    const head = el("div", "user-head");
    const isOpen = state.expandedUser === u.id;
    const statusDot = `<span class="dot ${u.is_active ? "ok" : "bad"}"></span>`;
    head.innerHTML = `
      <span class="caret">${isOpen ? "▾" : "▸"}</span>
      ${statusDot}
      <div class="user-meta">
        <div class="user-name">${cap(u.username)}</div>
        <div class="user-sub muted">id ${u.id} · ${u.activity_points} pts</div>
      </div>
      <span class="badge rank">${rankLabel(u.rank)}</span>`;
    head.onclick = () => { state.expandedUser = isOpen ? null : u.id; loadPermisos(); };
    row.append(head);
    if (isOpen) {
      const detail = el("div", "user-detail");
      detail.innerHTML = `<div class="muted" style="font-size:12px">Cargando…</div>`;
      row.append(detail);
      fetchUserDetail(u.id).then(d => {
        detail.innerHTML = "";
        detail.append(buildUserDetail(d, permLabel));
      }).catch(e => { detail.innerHTML = `<div class="empty">${e.message}</div>`; });
    }
    return row;
  }

  async function fetchUserDetail(userId) {
    return await api(`/users/${userId}`);
  }

  function buildUserDetail(u, permLabel) {
    const wrap = el("div");

    // Línea 1: rango con selector y email.
    const top = el("div", "user-detail-row");
    const left = el("div");
    left.innerHTML = `<div class="muted" style="font-size:11px">Rango</div>`;
    const sel = el("select"); sel.style.minWidth = "160px";
    (state.ranksCatalog || []).forEach(r => {
      const o = el("option", null, r.label); o.value = r.id; o.title = r.description || "";
      if (r.id === u.rank) o.selected = true; sel.append(o);
    });
    sel.onchange = async () => {
      try { await api(`/users/${u.id}/rank`, { method: "POST", body: JSON.stringify({ rank: sel.value }) }); toast(`${cap(u.username)} → ${rankLabel(sel.value)}`); loadPermisos(); }
      catch (e) { toast(e.message, true); sel.value = u.rank; }
    };
    left.append(sel);
    const right = el("div");
    right.innerHTML = `<div class="muted" style="font-size:11px">Email · creado</div><div style="font-size:13px">${u.email || "—"} · <span class="mono muted">${fmtDate(u.created_at)}</span></div>`;
    top.append(left, right);
    wrap.append(top);

    // Proyectos / ciudades (multi-proyecto) — solo el owner puede reasignar.
    // Un usuario puede cubrir varias ciudades (director con su zona, ingeniero
    // con Benidorm + Terra Mítica + Finestrat). Aplica a CUALQUIER rango.
    if (isOwnerUser()) {
      const projRow = el("div"); projRow.style.marginTop = "10px";
      projRow.innerHTML = `<div class="muted" style="font-size:11px">Proyectos / ciudades <span style="opacity:.7">(marca las que cubre)</span></div>`;
      const projects = state.projects || [];
      const current = new Set((u.project_ids && u.project_ids.length) ? u.project_ids : (u.project_id ? [u.project_id] : []));
      const box = el("div"); box.style.display = "flex"; box.style.flexWrap = "wrap"; box.style.gap = "12px"; box.style.marginTop = "6px";
      const save = async () => {
        const ids = [...box.querySelectorAll("input:checked")].map(c => parseInt(c.value, 10));
        try {
          await api("/projects/assign-user", { method: "POST", body: JSON.stringify({ user_id: u.id, project_ids: ids }) });
          u.project_ids = ids; u.project_id = ids[0] || null;
          toast(ids.length ? `${cap(u.username)}: ${ids.length} ciudad(es)` : `${cap(u.username)}: global`);
        } catch (e) { toast(e.message, true); }
      };
      if (!projects.length) {
        box.append(el("span", "muted", "No hay proyectos. Crea alguno en la pestaña Proyectos."));
      }
      projects.forEach(p => {
        const lab = el("label"); lab.style.display = "inline-flex"; lab.style.alignItems = "center"; lab.style.gap = "5px"; lab.style.fontSize = "13px"; lab.style.cursor = "pointer";
        const ck = el("input"); ck.type = "checkbox"; ck.value = String(p.id); if (current.has(p.id)) ck.checked = true;
        ck.onchange = save;
        lab.append(ck, document.createTextNode(p.name)); box.append(lab);
      });
      projRow.append(box); wrap.append(projRow);
    }

    // Línea de seguridad: credenciales (sin revelar nunca) + estado 2FA.
    const sec = el("div", "user-detail-row"); sec.style.marginTop = "10px";
    const credCell = el("div");
    credCell.innerHTML = `<div class="muted" style="font-size:11px">Credenciales configuradas</div>`
      + `<div style="font-size:13px">Contraseña ✅`
      + ` · PIN ${u.has_pin ? "✅" : "—"} · Patrón ${u.has_pattern ? "✅" : "—"}</div>`
      + `<div class="muted" style="font-size:11px;margin-top:2px">Las credenciales se guardan cifradas y nunca son legibles, ni para el admin.</div>`;
    const totpCell = el("div");
    totpCell.innerHTML = `<div class="muted" style="font-size:11px">2FA (Google Authenticator)</div>`
      + `<div style="font-size:13px">${u.has_totp ? `✅ activo · 🔑 ${u.totp_recovery_remaining ?? 0} claves de recuperación` : "— sin activar"}</div>`;
    sec.append(credCell, totpCell);
    wrap.append(sec);

    // Ficha del trabajador (4 packs: laboral, contractual, auditoría, notas).
    wrap.append(fichaSection(u));

    // Permisos efectivos en chips.
    const eff = el("div"); eff.style.marginTop = "12px";
    eff.append(el("div", "muted", "Permisos efectivos"));
    const chipsRow = el("div", "perm-chips");
    if ((u.permissions || []).includes("*")) {
      const chip = el("span", "perm-chip ok"); chip.textContent = "Acceso total ★";
      chipsRow.append(chip);
    } else {
      (u.permissions || []).forEach(p => {
        const chip = el("span", "perm-chip"); chip.textContent = permLabel[p] || p; chip.title = p;
        chipsRow.append(chip);
      });
      if (!u.permissions?.length) chipsRow.append(el("span", "muted", "ninguno"));
    }
    eff.append(chipsRow);
    wrap.append(eff);

    // Acciones inferiores. El backend solo deja gestionar credenciales / borrar
    // a un usuario de rango ESTRICTAMENTE inferior; ocultamos los botones en el
    // resto (incluido uno mismo) para no mostrar acciones que darían 403.
    const acts = el("div", "user-actions"); acts.style.flexWrap = "wrap";
    const myLevel = (state.ranksCatalog || []).find(r => r.id === state.me?.rank)?.level ?? 0;
    const targetLevel = (state.ranksCatalog || []).find(r => r.id === u.rank)?.level ?? 0;
    const canManage = targetLevel < myLevel;
    const who = cap(u.username);

    if (canManage) {
      const pw = el("button", "btn ghost sm", "🔑 Contraseña");
      pw.onclick = async () => {
        const np = prompt(`Nueva contraseña para ${who} (mín. 6):`);
        if (!np || np.length < 6) { if (np !== null) toast("Mínimo 6 caracteres.", true); return; }
        try { await api(`/users/${u.id}/password`, { method: "POST", body: JSON.stringify({ password: np }) }); toast("Contraseña actualizada"); }
        catch (e) { toast(e.message, true); }
      };
      acts.append(pw);

      const pinSet = el("button", "btn ghost sm", "📌 PIN nuevo");
      pinSet.onclick = async () => {
        const v = prompt(`Nuevo PIN para ${who} (4-8 dígitos):`);
        if (!v) return;
        if (!/^\d{4,8}$/.test(v)) { toast("PIN: 4-8 dígitos.", true); return; }
        try { await api(`/users/${u.id}/pin`, { method: "POST", body: JSON.stringify({ pin: v }) }); toast("PIN actualizado"); loadPermisos(); }
        catch (e) { toast(e.message, true); }
      };
      acts.append(pinSet);
      if (u.has_pin) {
        const pinDel = el("button", "btn ghost sm", "📌✕ Quitar PIN");
        pinDel.onclick = async () => {
          if (!confirm(`¿Quitar el PIN de ${who}?`)) return;
          try { await api(`/users/${u.id}/pin`, { method: "DELETE" }); toast("PIN eliminado"); loadPermisos(); }
          catch (e) { toast(e.message, true); }
        };
        acts.append(pinDel);
      }

      const patSet = el("button", "btn ghost sm", "✏ Patrón nuevo");
      patSet.onclick = async () => {
        const v = prompt(`Nuevo patrón para ${who} — secuencia de 4-9 puntos (0-8), p.ej. 0125:`);
        if (!v) return;
        if (!/^[0-8]{4,9}$/.test(v)) { toast("Patrón: 4-9 dígitos del 0 al 8.", true); return; }
        try { await api(`/users/${u.id}/pattern`, { method: "POST", body: JSON.stringify({ pattern: v }) }); toast("Patrón actualizado"); loadPermisos(); }
        catch (e) { toast(e.message, true); }
      };
      acts.append(patSet);
      if (u.has_pattern) {
        const patDel = el("button", "btn ghost sm", "✏✕ Quitar patrón");
        patDel.onclick = async () => {
          if (!confirm(`¿Quitar el patrón de ${who}?`)) return;
          try { await api(`/users/${u.id}/pattern`, { method: "DELETE" }); toast("Patrón eliminado"); loadPermisos(); }
          catch (e) { toast(e.message, true); }
        };
        acts.append(patDel);
      }

      if (u.has_totp) {
        const rec = el("button", "btn ghost sm", "🔄 Claves 2FA");
        rec.title = "Regenera las claves de recuperación (no desactiva el 2FA)";
        rec.onclick = async () => {
          if (!confirm(`¿Regenerar las claves de recuperación 2FA de ${who}?\n\nLas anteriores dejarán de servir. El 2FA NO se desactiva.`)) return;
          try {
            const r = await api(`/users/${u.id}/totp/recovery`, { method: "POST" });
            alert(`Nuevas claves de recuperación de ${who}\n(apúntalas y entrégaselas — no se vuelven a mostrar):\n\n` + (r.recovery_codes || []).join("\n"));
            loadPermisos();
          } catch (e) { toast(e.message, true); }
        };
        acts.append(rec);
      }
    }

    if (canManage && u.id !== state.me?.id) {
      const del = el("button", "btn ghost sm", "🗑 Eliminar usuario"); del.style.color = "#ef4444";
      del.onclick = async () => {
        if (!confirm(`¿Eliminar al usuario "${who}"?\n\nEsta acción no se puede deshacer.`)) return;
        try {
          await api(`/users/${u.id}`, { method: "DELETE" });
          toast(`Usuario "${who}" eliminado`);
          state.expandedUser = null;
          loadPermisos();
        } catch (e) { toast(e.message, true); }
      };
      acts.append(del);
    }
    wrap.append(acts);
    return wrap;
  }

  // Ficha del trabajador. Solo lectura por defecto; con permiso user:manage
  // aparece "Editar ficha" y los campos se vuelven editables (PATCH /profile).
  // Turnos reales: dos turnos operativos + oficina (sin turno fijo).
  // Solo 2 turnos operativos + oficina. Las horas concretas las marca el
  // convenio/contrato (no se fijan en código).
  const FICHA_SHIFTS = [
    { v: "", label: "—" },
    { v: "mañana",  label: "Mañana" },
    { v: "tarde",   label: "Tarde / noche" },
    { v: "oficina", label: "Oficina" },
  ];
  const FICHA_LABORAL = [
    ["full_name",  "Nombre completo"],
    ["phone",      "Teléfono"],
    ["job_title",  "Cargo"],
    ["department", "Departamento"],
    ["site",       "Sede"],
    ["shift",      "Turno base"],
  ];
  const FICHA_CONTRACTUAL = [
    ["employee_id", "Nº de empleado"],
    ["national_id", "DNI / NIF"],
    ["company",     "Empresa"],
  ];

  function fichaSection(u) {
    const box = el("div"); box.style.marginTop = "12px";
    const canEdit = has("user:manage");

    // Adorno ✅/❌ — al lado del valor en modo lectura. Sin guion: si está
    // vacío, mostramos solo el ❌ (queda más limpio que "❌ —").
    const filled = (val) => val != null && String(val).trim() !== "";
    const valueWith = (val, formatted) => {
      const wrap = el("span");
      if (filled(val)) {
        const tick = el("span"); tick.textContent = "✅ "; tick.style.color = "#22c55e";
        wrap.append(tick);
        const txt = el("span"); txt.textContent = formatted ?? val; wrap.append(txt);
      } else {
        const cross = el("span"); cross.textContent = "❌"; cross.style.color = "#ef4444"; cross.style.opacity = ".75";
        wrap.append(cross);
      }
      return wrap;
    };

    const shiftLabel = (v) => (FICHA_SHIFTS.find(s => s.v === v) || {}).label || "";

    const render = (editing) => {
      box.innerHTML = "";
      box.append(el("div", "muted", "Ficha del trabajador"));
      const inputs = {};

      // Helper: una fila etiqueta + valor (o input en modo edición).
      const fieldRow = (key, label) => {
        const r = el("div"); r.style.margin = "6px 0";
        const lab = el("div", "muted"); lab.style.fontSize = "11px"; lab.textContent = label;
        r.append(lab);

        if (editing) {
          let inp;
          if (key === "shift") {
            inp = el("select");
            FICHA_SHIFTS.forEach(s => {
              const o = el("option", null, s.label); o.value = s.v;
              if ((u[key] || "") === s.v) o.selected = true;
              inp.append(o);
            });
          } else {
            inp = el("input"); inp.value = u[key] || ""; inp.style.width = "100%";
          }
          inputs[key] = inp; r.append(inp);
        } else {
          const v = el("div"); v.style.fontSize = "13px";
          if (key === "shift") {
            v.append(valueWith(u[key], shiftLabel(u[key])));
          } else {
            v.append(valueWith(u[key]));
          }
          r.append(v);
        }
        return r;
      };

      const pack = (title, fields) => {
        const col = el("div");
        const h = el("div", "muted"); h.style.fontSize = "11px"; h.style.textTransform = "uppercase"; h.style.letterSpacing = ".4px"; h.style.opacity = ".75"; h.textContent = title;
        col.append(h);
        fields.forEach(([k, l]) => col.append(fieldRow(k, l)));
        return col;
      };

      const grid = el("div"); grid.style.display = "grid"; grid.style.gridTemplateColumns = "1fr 1fr"; grid.style.gap = "14px"; grid.style.marginTop = "8px";
      grid.append(
        pack("Datos laborales", FICHA_LABORAL),
        pack("Datos contractuales", FICHA_CONTRACTUAL),
      );
      box.append(grid);

      // Resumen en lectura: chip del turno base (si tiene uno).
      if (!editing && filled(u.shift)) {
        const summary = el("div"); summary.style.marginTop = "8px"; summary.style.display = "flex"; summary.style.gap = "8px"; summary.style.flexWrap = "wrap";
        const t = el("span", "perm-chip"); t.textContent = "🕒 " + shiftLabel(u.shift);
        summary.append(t);
        box.append(summary);
      }

      // Auditoría: último acceso + IP (siempre solo lectura, lo fija el login).
      const audit = el("div"); audit.style.marginTop = "8px";
      const aLab = el("div", "muted"); aLab.style.fontSize = "11px"; aLab.textContent = "Último acceso"; audit.append(aLab);
      const aVal = el("div"); aVal.style.fontSize = "13px";
      aVal.textContent = u.last_login_at
        ? `${fmtDateTime(u.last_login_at)} · IP ${u.last_login_ip || "—"}`
        : "nunca";
      audit.append(aVal); box.append(audit);

      // Notas internas — solo admin (u.notes llega null si no autorizado).
      if (u.notes !== null && u.notes !== undefined) {
        const n = el("div"); n.style.marginTop = "8px";
        const nLab = el("div", "muted"); nLab.style.fontSize = "11px"; nLab.textContent = "Notas internas (solo admin)"; n.append(nLab);
        if (editing) {
          const ta = el("textarea"); ta.value = u.notes || ""; ta.rows = 2; ta.maxLength = 512; ta.style.width = "100%";
          inputs.notes = ta; n.append(ta);
        } else {
          const nVal = el("div"); nVal.style.fontSize = "13px"; nVal.style.whiteSpace = "pre-wrap";
          nVal.textContent = (u.notes && u.notes.trim()) ? u.notes : "—";
          n.append(nVal);
        }
        box.append(n);
      }

      if (canEdit) {
        const bar = el("div"); bar.style.marginTop = "10px"; bar.style.display = "flex"; bar.style.gap = "8px";
        if (!editing) {
          const edit = el("button", "btn ghost sm", "✎ Editar ficha");
          edit.onclick = () => render(true);
          bar.append(edit);
        } else {
          const save = el("button", "btn sm", "Guardar ficha");
          save.onclick = async () => {
            const body = {};
            Object.entries(inputs).forEach(([k, inp]) => { body[k] = inp.value; });
            try {
              const updated = await api(`/users/${u.id}/profile`, { method: "PATCH", body: JSON.stringify(body) });
              Object.assign(u, updated);  // refresca el objeto local con lo guardado
              toast("Ficha actualizada");
              render(false);
            } catch (e) { toast(e.message, true); }
          };
          const cancel = el("button", "btn ghost sm", "Cancelar");
          cancel.onclick = () => render(false);
          bar.append(save, cancel);
        }
        box.append(bar);
      }
    };

    render(false);
    return box;
  }

  function renderNewUserForm(panel) {
    panel.innerHTML = "";
    panel.append(el("div", null, "<strong>Crear usuario</strong> <span class='muted' style='font-size:12px'>· define las 4 credenciales (PIN/patrón opcionales)</span>"));
    const grid = el("div"); grid.style.display = "grid"; grid.style.gridTemplateColumns = "1fr 1fr"; grid.style.gap = "12px"; grid.style.marginTop = "12px";
    const left = el("div"); left.style.display = "grid"; left.style.gap = "8px";
    const u = el("input"); u.placeholder = "usuario";
    const pw = el("input"); pw.type = "password"; pw.placeholder = "contraseña (mín. 6)";
    const pin = el("input"); pin.type = "password"; pin.inputMode = "numeric"; pin.maxLength = 8; pin.placeholder = "PIN (4-8 dígitos, opcional)";
    const rk = el("select");
    const allowed = (state.ranksCatalog || []).filter(r => r.id !== "owner");
    allowed.forEach(r => { const o = el("option", null, r.label); o.value = r.id; if (r.id === "visualizador") o.selected = true; rk.append(o); });
    const hint = el("div", "muted"); hint.style.fontSize = "12px";
    const updateHint = () => { const r = allowed.find(x => x.id === rk.value); hint.textContent = r ? (r.description || "") : ""; };
    rk.onchange = updateHint; updateHint();
    left.append(u, pw, pin, rk, hint);

    const right = el("div"); right.style.display = "grid"; right.style.justifyItems = "center"; right.style.gap = "6px";
    right.append(el("div", "muted", "Patrón (opcional)"));
    let pattern = "";
    const pad = makePatternPad(seq => { pattern = seq; });
    right.append(pad);
    const reset = el("button", "btn ghost sm", "Repetir patrón"); reset.onclick = () => { pad.reset(); pattern = ""; };
    right.append(reset);
    grid.append(left, right); panel.append(grid);

    const actions = el("div", "row"); actions.style.marginTop = "12px"; actions.style.gap = "8px";
    const create = el("button", "btn", "Crear");
    create.onclick = async () => {
      if (!u.value.trim()) { toast("Falta el usuario.", true); return; }
      if (pw.value.length < 6) { toast("La contraseña debe tener al menos 6 caracteres.", true); return; }
      if (pin.value && !/^\d{4,8}$/.test(pin.value)) { toast("PIN: 4-8 dígitos.", true); return; }
      if (pattern && pattern.length < 4) { toast("El patrón debe unir al menos 4 puntos.", true); return; }
      const body = { username: u.value.trim(), password: pw.value, rank: rk.value };
      if (pin.value) body.pin = pin.value;
      if (pattern) body.pattern = pattern;
      try {
        await api("/users", { method: "POST", body: JSON.stringify(body) });
        toast("Usuario creado: " + body.username);
        $("#new-user-panel").classList.add("hidden");
        loadPermisos();
      } catch (e) { toast(e.message, true); }
    };
    const cancel = el("button", "btn ghost sm", "Cancelar");
    cancel.onclick = () => { $("#new-user-panel").classList.add("hidden"); };
    actions.append(create, cancel); panel.append(actions);
  }

  async function renderPermisosRangos(body) {
    // Reutilizamos la implementación de loadRoles, pintando dentro del tab.
    body.innerHTML = "";
    // Pequeño truco: rebindeamos #content temporalmente al body para que
    // loadRoles dibuje aquí sin duplicar lógica.
    const stash = $("#content");
    Object.defineProperty(document, "_origContent", { value: stash, configurable: true });
    body.id = "content-tab";
    const fakeContent = body;
    const realRoot = $("#content");
    // No hay forma elegante sin reescribir loadRoles → la replico aquí.
    await renderRolesEditorInto(fakeContent);
  }

  async function renderRolesEditorInto(c) {
    try {
      const [perms, roles] = await Promise.all([
        api("/roles/permissions"),
        api("/roles"),
      ]);
      const canEdit = has("role:manage");
      const sorted = roles.slice().sort((a, b) => b.level - a.level);
      if (state.selectedRole !== "__new__" && !sorted.find(r => r.id === state.selectedRole)) state.selectedRole = sorted[0]?.id || null;

      const wrap = el("div", "roles-layout");
      const aside = el("div", "roles-list");
      const head = el("div", "roles-list-head");
      head.innerHTML = `<strong>Rangos</strong><span class="muted" style="font-size:11px">${roles.length} en catálogo</span>`;
      aside.append(head);
      sorted.forEach(r => {
        const item = el("div", "role-item" + (r.id === state.selectedRole ? " active" : ""));
        const dotCls = r.is_owner ? "bad" : (r.is_builtin ? "ok" : "warn");
        item.innerHTML = `
          <span class="role-dot ${dotCls}"></span>
          <div class="role-meta">
            <div class="role-name">${r.label}</div>
            <div class="role-sub muted">nivel ${r.level} · ${r.is_owner ? "protegido" : (r.is_builtin ? "por defecto" : "custom")}</div>
          </div>
          <span class="muted mono" style="font-size:11px">${(r.permissions || []).length}</span>`;
        item.onclick = () => { state.selectedRole = r.id; loadPermisos(); };
        aside.append(item);
      });
      if (canEdit) {
        const add = el("div", "role-item add");
        add.innerHTML = `<span class="role-dot" style="background:var(--dim)"></span><div class="role-meta"><div class="role-name">+ Nuevo rango</div><div class="role-sub muted">crear personalizado</div></div>`;
        add.onclick = () => { state.selectedRole = "__new__"; loadPermisos(); };
        aside.append(add);
      }
      wrap.append(aside);

      const detail = el("div", "roles-detail panel");
      if (state.selectedRole === "__new__") renderNewRoleForm(detail);
      else {
        const role = sorted.find(r => r.id === state.selectedRole) || sorted[0];
        if (!role) detail.append(el("div", "empty", "Selecciona un rango."));
        else renderRoleDetailCompact(detail, role, perms, sorted, canEdit);
      }
      wrap.append(detail);
      c.append(wrap);
    } catch (e) { c.append(el("div", "empty", e.message)); }
  }

  // Detalle del rango ULTRA-COMPACTO: permisos en grid 2 columnas, sin
  // bloque de descripción por permiso (la descripción va en tooltip).
  function renderRoleDetailCompact(detail, role, perms, allRoles, canEdit) {
    const myRole = allRoles.find(r => r.id === state.me?.rank);
    const myLevel = myRole?.level ?? 0;
    const locked = role.is_owner || !canEdit || role.level >= myLevel;

    const head = el("div");
    const badges = [];
    if (role.is_owner) badges.push(`<span class="badge bad">protegido</span>`);
    else if (role.is_builtin) badges.push(`<span class="badge ok">por defecto</span>`);
    else badges.push(`<span class="badge warn">custom</span>`);
    if (locked && !role.is_owner) badges.push(`<span class="badge">solo lectura</span>`);
    head.innerHTML = `
      <div style="display:flex; align-items:baseline; gap:10px; flex-wrap:wrap">
        <h3 style="margin:0; font-size:16px">${role.label}</h3>
        <span class="muted mono" style="font-size:11px">${role.id} · nivel ${role.level}</span>
        ${badges.join(" ")}
      </div>
      <div class="muted" style="font-size:12px; margin-top:3px">${role.description || ""}</div>`;
    detail.append(head);

    detail.append(el("div", "perm-hr"));

    const list = el("div", "perm-grid");
    const checkboxes = {};
    if (role.is_owner) {
      list.append(el("div", "muted", "Acceso total (wildcard). No editable."));
    } else {
      perms.forEach(p => {
        const row = el("label", "perm-row-compact" + (locked ? " locked" : ""));
        row.title = `${p.id} — ${p.description}`;
        const cb = el("input"); cb.type = "checkbox"; cb.checked = role.permissions.includes(p.id); cb.disabled = locked;
        checkboxes[p.id] = cb;
        const txt = el("span"); txt.className = "perm-compact-label"; txt.textContent = p.label;
        row.append(cb, txt); list.append(row);
      });
    }
    detail.append(list);

    if (!role.is_owner && !locked) {
      const actions = el("div", "perm-actions");
      const save = el("button", "btn sm", "Guardar");
      save.onclick = async () => {
        const newPerms = Object.entries(checkboxes).filter(([, cb]) => cb.checked).map(([id]) => id);
        try { await api(`/roles/${role.id}`, { method: "PATCH", body: JSON.stringify({ permissions: newPerms }) }); toast("Rango actualizado"); loadPermisos(); }
        catch (e) { toast(e.message, true); }
      };
      const rename = el("button", "btn ghost sm", "Editar nombre / descripción");
      rename.onclick = async () => {
        const nl = prompt("Nombre visible:", role.label); if (nl === null) return;
        const nd = prompt("Descripción:", role.description || ""); if (nd === null) return;
        try { await api(`/roles/${role.id}`, { method: "PATCH", body: JSON.stringify({ label: nl, description: nd }) }); toast("Actualizado"); loadPermisos(); }
        catch (e) { toast(e.message, true); }
      };
      actions.append(save, rename);
      if (!role.is_builtin) {
        const del = el("button", "btn ghost sm", "Borrar rango");
        del.onclick = async () => {
          if (!confirm(`¿Borrar el rango "${role.label}"?`)) return;
          try { await api(`/roles/${role.id}`, { method: "DELETE" }); toast("Borrado"); state.selectedRole = null; loadPermisos(); }
          catch (e) { toast(e.message, true); }
        };
        actions.append(del);
      }
      detail.append(actions);
    }
  }

  async function loadAudit() {
    const c = $("#content"); c.innerHTML = "";
    try {
      const entries = await api("/audit?limit=500");
      const p = el("div", "panel");
      const tb = el("tbody");
      const t = el("table");
      t.innerHTML = `<thead><tr><th>Hora</th><th>Usuario</th><th>Acción</th><th>Objetivo</th><th>Detalle</th></tr></thead>`;
      t.append(tb); p.append(t);
      const renderPage = (rows) => {
        tb.innerHTML = "";
        rows.forEach(e => {
          const tr = el("tr");
          const when = fmtDateTime(e.timestamp);
          tr.innerHTML = `<td class="muted mono" style="font-size:12px">${when}</td><td>${e.username}</td><td><span class="badge">${e.action}</span></td><td class="mono">${e.target || "—"}</td><td class="muted" style="font-size:12px">${e.detail ? JSON.stringify(e.detail) : ""}</td>`;
          tb.append(tr);
        });
      };
      const pager = paginator(entries, renderPage);
      p.append(pager);
      if (!entries.length) p.append(el("div", "empty", "Sin registros."));
      c.append(p);
    } catch (e) { c.append(el("div", "empty", e.message)); }
  }

  // Paginador genérico para tablas largas (auditoría, seguridad…). Inyecta
  // controles "‹ ›" y un select de tamaño de página. Llama a renderPage(rows)
  // cada vez que el usuario cambia de página o de tamaño.
  function paginator(rows, renderPage, opts = {}) {
    const sizes = opts.sizes || [10, 25, 50, 100];
    const wrap = el("div", "paginator");
    let page = 0; let size = sizes[0];
    const update = () => {
      const total = rows.length;
      const pages = Math.max(1, Math.ceil(total / size));
      page = Math.min(page, pages - 1);
      const slice = rows.slice(page * size, (page + 1) * size);
      renderPage(slice);
      wrap.innerHTML = "";
      const left = el("div", "muted"); left.style.fontSize = "12px";
      left.textContent = `${total ? page * size + 1 : 0}–${Math.min((page + 1) * size, total)} de ${total}`;
      const center = el("div", "row");
      const prev = el("button", "btn ghost sm", "‹"); prev.disabled = page === 0;
      const next = el("button", "btn ghost sm", "›"); next.disabled = page >= pages - 1;
      const label = el("span", "muted"); label.style.fontSize = "12px"; label.textContent = `Página ${page + 1} / ${pages}`;
      prev.onclick = () => { page = Math.max(0, page - 1); update(); };
      next.onclick = () => { page = Math.min(pages - 1, page + 1); update(); };
      center.append(prev, label, next);
      const sizeSel = el("select"); sizeSel.style.fontSize = "12px";
      sizes.forEach(s => { const o = el("option", null, s + " / pág"); o.value = s; if (s === size) o.selected = true; sizeSel.append(o); });
      sizeSel.onchange = () => { size = parseInt(sizeSel.value, 10); page = 0; update(); };
      wrap.append(left, center, sizeSel);
    };
    update();
    return wrap;
  }

  // ============================ Seguridad (solo admins) ============================
  // Vista solo para 'user:manage'. Cuenta los logins fallidos / bloqueos del
  // último día y lista el feed de eventos auth.* y emergency.* con badges
  // codificados por color para distinguir lo bueno de lo sospechoso.
  const SEC_BADGE = {
    "auth.login": "ok", "auth.unlock": "ok", "auth.pin_set": "ok", "auth.pattern_set": "ok",
    "auth.pin_clear": "warn", "auth.pattern_clear": "warn", "auth.bootstrap": "ok",
    "auth.login_failed": "bad", "auth.unlock_failed": "bad", "auth.lockout": "bad",
    "auth.login_step1": "ok", "auth.password_set": "ok",
    "emergency.all_on": "warn",
    "security.ip_banned": "bad", "security.ip_unbanned": "warn",
    "security.siege_on": "bad", "security.siege_off": "warn",
    "security.new_device": "warn", "security.device_revoked": "warn",
    "security.device_unknown": "bad", "security.device_mismatch": "bad",
  };
  const SEC_LABEL = {
    "auth.login": "Inicio de sesión", "auth.login_failed": "Login fallido",
    "auth.login_step1": "Login paso 1 OK", "auth.password_set": "Contraseña cambiada",
    "auth.unlock": "Desbloqueo", "auth.unlock_failed": "Desbloqueo fallido",
    "auth.lockout": "Cuenta bloqueada", "auth.bootstrap": "Cuenta raíz creada",
    "auth.pin_set": "PIN definido", "auth.pin_clear": "PIN borrado",
    "auth.pattern_set": "Patrón definido", "auth.pattern_clear": "Patrón borrado",
    "emergency.all_on": "Modo emergencia",
    "security.ip_banned": "IP baneada", "security.ip_unbanned": "IP desbloqueada",
    "security.siege_on": "Modo siege ON", "security.siege_off": "Modo siege OFF",
    "security.new_device": "Dispositivo nuevo", "security.device_revoked": "Dispositivo revocado",
    "security.device_unknown": "Cuadro: dispositivo desconocido",
    "security.device_mismatch": "Cuadro: serial no coincide",
  };
  async function loadSecurity() {
    const c = $("#content"); c.innerHTML = "";
    try {
      // ----- KPIs (24 h) -----
      const entries = await api("/audit/security?limit=200");
      const dayAgo = Date.now() - 24 * 3600 * 1000;
      const recent = entries.filter(e => new Date(e.timestamp).getTime() >= dayAgo);
      const fails = recent.filter(e => e.action === "auth.login_failed").length;
      const ipBans = recent.filter(e => e.action === "security.ip_banned").length;
      const newDev = recent.filter(e => e.action === "security.new_device").length;
      const oks = recent.filter(e => e.action === "auth.login").length;
      const kpis = el("div", "grid kpis");
      kpis.append(
        kpi("Logins OK (24 h)", oks, false),
        kpi("Logins fallidos (24 h)", fails, fails > 0),
        kpi("IPs baneadas (24 h)", ipBans, ipBans > 0),
        kpi("Dispositivos nuevos (24 h)", newDev, newDev > 0),
      );
      c.append(kpis);

      // Las tres tarjetas de gestión van EN COLUMNAS (no apiladas) para
      // ahorrar espacio vertical. auto-fit las reparte según el ancho.
      const cols = el("div"); cols.style.display = "grid"; cols.style.gridTemplateColumns = "repeat(auto-fit, minmax(320px, 1fr))"; cols.style.gap = "16px"; cols.style.marginTop = "16px";

      // ----- Modo siege (solo Owner) -----
      if (state.me?.rank === "owner") {
        const sg = el("div", "panel");
        try {
          const siege = await api("/security/siege");
          const head = el("div", "row between");
          const desc = el("div"); desc.innerHTML = `<strong>Modo siege</strong> <span class="muted" style="font-size:12px">· cuando está activo, solo IPs whitelisted pueden entrar</span>`;
          const btn = el("button", "btn " + (siege.on ? "" : "ghost") + " sm", siege.on ? "⛨ Activo — desactivar" : "Activar modo siege");
          btn.onclick = async () => {
            if (siege.on || confirm("ATENCIÓN: el modo siege bloquea TODAS las IPs no whitelisted. Asegúrate de añadir tu IP primero. ¿Continuar?")) {
              try { await api("/security/siege", { method: "POST", body: JSON.stringify({ on: !siege.on }) }); loadSecurity(); }
              catch (e) { toast(e.message, true); }
            }
          };
          head.append(desc, btn); sg.append(head);
          if (siege.on && siege.whitelist.length) {
            const wl = el("div", "muted"); wl.style.fontSize = "12px"; wl.style.marginTop = "8px";
            wl.textContent = "Whitelist: " + siege.whitelist.join(", ");
            sg.append(wl);
          }
        } catch (e) { /* no admin → skip */ }
        cols.append(sg);
      }

      // ----- IP banlist (admin) -----
      const ban = el("div", "panel");
      ban.append(el("div", "row between", "<strong>IPs baneadas</strong> <span class='muted' style='font-size:12px'>auto-ban y manual</span>"));
      try {
        const bans = await api("/security/bans");
        if (bans.length) {
          const bt = el("table");
          bt.innerHTML = `<thead><tr><th>IP</th><th>Motivo</th><th>Banneada por</th><th>Caduca</th><th></th></tr></thead>`;
          const bb = el("tbody");
          bans.forEach(b => {
            const tr = el("tr");
            const exp = b.expires_at ? fmtDateTime(b.expires_at) : "permanente";
            tr.innerHTML = `<td class="mono">${b.ip}</td><td class="muted" style="font-size:12px">${b.reason || ""}</td><td>${b.banned_by}</td><td class="muted mono" style="font-size:12px">${exp}</td>`;
            const td = el("td");
            const rm = el("button", "btn ghost sm", "Quitar");
            rm.onclick = async () => { try { await api(`/security/bans/${encodeURIComponent(b.ip)}`, { method: "DELETE" }); toast("Ban quitado"); loadSecurity(); } catch (e) { toast(e.message, true); } };
            td.append(rm); tr.append(td); bb.append(tr);
          });
          bt.append(bb); ban.append(bt);
        } else {
          ban.append(el("div", "empty", "Sin IPs baneadas."));
        }
        // Form: banear a mano (vertical para caber en columna estrecha)
        const form = el("div"); form.style.marginTop = "10px"; form.style.display = "grid"; form.style.gap = "6px";
        const ipIn = el("input"); ipIn.placeholder = "IP a banear";
        const reIn = el("input"); reIn.placeholder = "motivo (opcional)";
        const minIn = el("input"); minIn.type = "number"; minIn.placeholder = "minutos (vacío = permanente)";
        const add = el("button", "btn sm", "Banear");
        add.onclick = async () => {
          if (!ipIn.value.trim()) return;
          const body = { ip: ipIn.value.trim(), reason: reIn.value || null };
          if (minIn.value) body.minutes = parseInt(minIn.value, 10);
          try { await api("/security/bans", { method: "POST", body: JSON.stringify(body) }); toast("IP baneada"); loadSecurity(); }
          catch (e) { toast(e.message, true); }
        };
        form.append(ipIn, reIn, minIn, add);
        ban.append(form);
      } catch (e) { ban.append(el("div", "empty", "Sin permisos para gestionar IPs.")); }
      cols.append(ban);

      // ----- Mis dispositivos (todos) -----
      const dev = el("div", "panel");
      dev.append(el("div", "row between", "<strong>Mis dispositivos</strong> <span class='muted' style='font-size:12px'>sesiones recientes de este usuario</span>"));
      try {
        const devs = await api("/security/devices");
        if (devs.length) {
          const dt = el("table");
          dt.innerHTML = `<thead><tr><th>Dispositivo</th><th>Última IP</th><th>Visto por última vez</th><th></th></tr></thead>`;
          const db = el("tbody");
          devs.forEach(d => {
            const tr = el("tr");
            const last = fmtDateTime(d.last_seen_at);
            tr.innerHTML = `<td>${d.label || "—"}<div class="muted" style="font-size:11px">${(d.user_agent || "").slice(0,80)}</div></td><td class="mono">${d.last_ip || "?"}</td><td class="muted mono" style="font-size:12px">${last}</td>`;
            const td = el("td");
            const rev = el("button", "btn ghost sm", "Revocar");
            rev.onclick = async () => { if (confirm("¿Revocar este dispositivo? La próxima sesión desde él contará como nueva.")) { try { await api(`/security/devices/${encodeURIComponent(d.device_id)}`, { method: "DELETE" }); toast("Dispositivo revocado"); loadSecurity(); } catch (e) { toast(e.message, true); } } };
            td.append(rev); tr.append(td); db.append(tr);
          });
          dt.append(db); dev.append(dt);
        } else { dev.append(el("div", "empty", "Sin dispositivos registrados.")); }
      } catch (e) { dev.append(el("div", "empty", e.message)); }
      cols.append(dev);
      c.append(cols);

      // ----- Feed de eventos (paginado, ancho completo) -----
      const p = el("div", "panel"); p.style.marginTop = "16px";
      p.append(el("div", "row between", "<strong>Historial de seguridad</strong> <span class='muted' style='font-size:12px'>append-only</span>"));
      const t = el("table");
      t.innerHTML = `<thead><tr><th>Hora</th><th>Usuario</th><th>Evento</th><th>Detalle</th></tr></thead>`;
      const tb = el("tbody"); t.append(tb); p.append(t);
      const renderPage = (rows) => {
        tb.innerHTML = "";
        rows.forEach(e => {
          const tr = el("tr");
          const when = fmtDateTime(e.timestamp);
          const cls = SEC_BADGE[e.action] || "";
          const label = SEC_LABEL[e.action] || e.action;
          const det = e.detail ? Object.entries(e.detail).map(([k, v]) => `${k}=${typeof v === "object" ? JSON.stringify(v) : v}`).join(" · ") : "";
          tr.innerHTML = `<td class="muted mono" style="font-size:12px">${when}</td><td>${e.username}</td><td><span class="badge ${cls}">${label}</span></td><td class="muted" style="font-size:12px">${det}</td>`;
          tb.append(tr);
        });
      };
      p.append(paginator(entries, renderPage));
      if (!entries.length) p.append(el("div", "empty", "Sin eventos de seguridad."));
      c.append(p);
    } catch (e) { c.append(el("div", "empty", e.message)); }
  }

  // ============================ Info / demo ============================
  async function loadInfo() {
    try {
      const r = await fetch(API + "/auth/info"); const d = await r.json();
      if (d.session_idle_minutes) state.idleMinutes = d.session_idle_minutes;
      if (d.timezone) state.tz = d.timezone;  // zona horaria del despliegue (reloj en hora local)
      // Versión/build: para saber de un vistazo si estás en la última.
      const tag = [d.version ? `v${d.version}` : "", d.build ? `build ${d.build}` : ""].filter(Boolean).join(" · ");
      const bt = $("#build-tag"); if (bt) bt.textContent = tag;
      const lb = $("#login-build"); if (lb && tag) lb.textContent = `PHOENIX LIGHT · ${tag}`;
      if (d.demo_mode && d.demo_username) {
        if (!$("#li-user").value) $("#li-user").value = d.demo_username;
        if (!$("#li-pass").value) $("#li-pass").value = d.demo_password || "";
        if (!$("#li-pin").value && d.demo_pin) $("#li-pin").value = d.demo_pin;
        state.demoPattern = d.demo_pattern || null;
        const pinTxt = d.demo_pin ? ` · PIN <span class="mono">${d.demo_pin}</span>` : "";
        const patTxt = d.demo_pattern ? ` · patrón <span class="mono">${d.demo_pattern}</span>` : "";
        $("#demo-hint").innerHTML = `Modo demo · <span class="mono">${d.demo_username} / ${d.demo_password}</span>${pinTxt}${patTxt}`;
      }
    } catch (e) {}
  }

  // ============================ Wiring ============================
  emblemAll();
  if (location.protocol === "file:") {
    $("#login-err").innerHTML = "⚠ Estás abriendo el archivo directamente (file://).<br>Arranca el backend y abre <b>http://localhost:8000/ui/</b>";
  } else {
    loadInfo();
  }
  // Monta la ventana 2 (patrón) con el challenge dado.
  function goLoginPattern(challenge) {
    state.loginChallenge = challenge;
    const host = $("#login-pattern-host"); host.innerHTML = "";
    const pad = makePatternPad(async seq => {
      if (seq.length < 4) return;
      try {
        const r = await loginStep2(state.loginChallenge, seq);
        if (!r.done && r.next === "totp") { goLoginTotp(r.challenge); }
      } catch (e) { $("#login-err").textContent = e.message; setTimeout(() => pad.reset(), 600); }
    });
    host.append(pad);
    state.loginPad = pad;
    showLoginStep(2);
  }
  // Monta la ventana 3 (código 2FA) con el challenge dado.
  function goLoginTotp(challenge) {
    state.loginChallenge = challenge;
    showLoginStep(3);
  }
  $("#btn-login").onclick = async () => {
    $("#login-err").textContent = "";
    const btn = $("#btn-login"); btn.disabled = true;
    try {
      const r = await loginStep1($("#li-user").value.trim(), $("#li-pass").value, $("#li-pin").value.trim());
      if (r.done) return;
      if (r.next === "pattern") goLoginPattern(r.challenge);
      else if (r.next === "totp") goLoginTotp(r.challenge);
    } catch (e) { $("#login-err").textContent = netMsg(e); }
    finally { btn.disabled = false; }
  };
  $("#btn-totp-confirm").onclick = async () => {
    // El código numérico puede venir como "123 456"; las claves de
    // recuperación se envían tal cual (el backend normaliza).
    const raw = $("#li-totp3").value.trim();
    const code = /[A-Za-z-]/.test(raw) ? raw : raw.replace(/\s/g, "");
    if (code.length < 6) { $("#login-err").textContent = "Introduce el código o una clave de recuperación."; return; }
    try { await loginStep3(state.loginChallenge, code); }
    catch (e) { $("#login-err").textContent = e.message; }
  };
  if ($("#li-totp3")) {
    attachTotpSpace($("#li-totp3"));
    $("#li-totp3").onkeydown = (e) => { if (e.key === "Enter") $("#btn-totp-confirm").click(); };
  }
  $("#btn-totp-back").onclick = () => { state.loginChallenge = null; showLoginStep(1); };
  $("#btn-pat-back").onclick = () => { state.loginChallenge = null; showLoginStep(1); };
  $("#btn-pat-reset").onclick = () => { if (state.loginPad) state.loginPad.reset(); $("#login-err").textContent = ""; };
  $("#btn-logout").onclick = logout;
  $("#btn-lock").onclick = showLockScreen;
  $("#btn-emergency").onclick = emergencyAllOn;
  $("#btn-pin").onclick = showSetPin;
  $("#btn-pattern").onclick = showSetPattern;
  $("#btn-totp").onclick = showSetTotp;
  // Menú de usuario (arriba derecha): abre/cierra el desplegable.
  $("#user-chip").onclick = (e) => {
    e.stopPropagation();
    const dd = $("#user-dropdown");
    const opening = dd.classList.contains("hidden");
    dd.classList.toggle("hidden");
    if (opening) setTimeout(() => document.addEventListener("click", closeUserMenu, { once: true }), 0);
  };
  document.querySelectorAll("#nav a").forEach(a => a.onclick = () => go(a.dataset.view));
  ["li-pass", "li-pin"].forEach(id => {
    $("#" + id).addEventListener("keydown", e => { if (e.key === "Enter") $("#btn-login").click(); });
  });

  if (state.token) boot().catch(() => logout());
  