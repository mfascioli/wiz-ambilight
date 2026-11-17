"use strict";

const el = (tag, className, text) => {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
};

const refs = {
  subtitle: document.getElementById("subtitle"),
  statusDot: document.getElementById("statusDot"),
  demoBadge: document.getElementById("demoBadge"),
  versionBadge: document.getElementById("versionBadge"),
  quitBtn: document.getElementById("quitBtn"),
  offlineBanner: document.getElementById("offlineBanner"),
  scanBtn: document.getElementById("scanBtn"),
  enableAllBtn: document.getElementById("enableAllBtn"),
  enableNoneBtn: document.getElementById("enableNoneBtn"),
  lights: document.getElementById("lights"),
  lightsEmpty: document.getElementById("lightsEmpty"),
  luaBanner: document.getElementById("luaBanner"),
  luaText: document.getElementById("luaText"),
  installBtn: document.getElementById("installBtn"),
  sessionPill: document.getElementById("sessionPill"),
  sessionDetail: document.getElementById("sessionDetail"),
  startBtn: document.getElementById("startBtn"),
  stopBtn: document.getElementById("stopBtn"),
  mediaField: document.getElementById("mediaField"),
  mediaInput: document.getElementById("mediaInput"),
  browseBtn: document.getElementById("browseBtn"),
  modeHint: document.getElementById("modeHint"),
  styleSelect: document.getElementById("styleSelect"),
  styleHint: document.getElementById("styleHint"),
  layoutSelect: document.getElementById("layoutSelect"),
  brightness: document.getElementById("brightness"),
  brightnessOut: document.getElementById("brightnessOut"),
  dryRun: document.getElementById("dryRun"),
  mapping: document.getElementById("mapping"),
  log: document.getElementById("log"),
  clearLog: document.getElementById("clearLog"),
  configPath: document.getElementById("configPath"),
  toast: document.getElementById("toast"),
};

const TOKEN = document.querySelector('meta[name="wiz-token"]')?.content || "";

const state = {
  snapshot: null,
  cards: new Map(),
  poll: null,
  logFrom: 0,
  busy: false,
  closed: false,
};

// --------------------------------------------------------------------- utils

function toast(message, isError) {
  refs.toast.textContent = message;
  refs.toast.classList.toggle("error", Boolean(isError));
  refs.toast.classList.remove("hidden");
  window.clearTimeout(toast.timer);
  toast.timer = window.setTimeout(() => refs.toast.classList.add("hidden"), 4200);
}

async function api(path, body) {
  const response = await fetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json", "X-Wiz-Token": TOKEN },
    body: JSON.stringify(body || {}),
  });
  const data = await response.json().catch(() => ({}));
  if (response.status === 403) {
    throw new Error("The panel was restarted or the request was blocked — reload the page.");
  }
  if (!response.ok || data.error) throw new Error(data.error || `HTTP ${response.status}`);
  return data;
}

async function action(path, body, message, button = null) {
  if (state.busy) return;
  state.busy = true;
  if (button) button.classList.add("loading");
  try {
    const data = await api(path, body);
    if (data && data.lights) apply(data);
    if (message) toast(message);
    return data;
  } catch (error) {
    toast(error.message, true);
  } finally {
    state.busy = false;
    if (button) button.classList.remove("loading");
  }
}

function zoneLabel(zone) {
  return zone === "t1" ? "top-left" : zone === "t2" ? "top-centre" : zone === "t3" ? "top-right" : zone;
}

function rgbCss(light) {
  const dim = Math.max(0.08, Math.min(1, (light.dimming || 100) / 100));
  const scale = 0.25 + 0.75 * dim;
  const channel = (value) => Math.round((Number(value) || 0) * scale);
  return `rgb(${channel(light.r)}, ${channel(light.g)}, ${channel(light.b)})`;
}

// --------------------------------------------------------------------- lights

function buildCard(light) {
  const root = el("article", "light");
  const swatch = el("div", "swatch");
  const name = el("input", "name-input");
  name.type = "text";
  name.placeholder = "Unnamed light";
  name.maxLength = 40;
  name.spellcheck = false;
  name.setAttribute("aria-label", "Light name");

  const meta = el("div", "meta");
  const online = el("span", "online-dot");
  const ipLabel = el("span", "ip");
  const modelLabel = el("span", "model");
  const zoneChip = el("span", "zone-chip");
  const extraLabel = el("span", "extra");
  meta.append(online, ipLabel, modelLabel, zoneChip, extraLabel);

  const main = el("div", "light-main");
  main.append(name, meta);

  const controls = el("div", "light-controls");
  const zone = el("select", "zone");
  zone.setAttribute("aria-label", "Zone for this light");
  const auto = el("option", "", "Auto zone");
  auto.value = "";
  zone.append(auto);

  const identify = el("button", "icon-btn identify", "✦");
  identify.type = "button";
  identify.title = "Flash this bulb";
  identify.setAttribute("aria-label", "Identify light");

  const power = el("button", "icon-btn power", "⏻");
  power.type = "button";
  power.title = "Turn the bulb on or off";
  power.setAttribute("aria-label", "Toggle light power");

  const toggle = el("label", "switch");
  toggle.title = "Include this light in ambilight";
  const toggleInput = document.createElement("input");
  toggleInput.type = "checkbox";
  toggleInput.setAttribute("aria-label", "Include light");
  toggle.append(toggleInput, el("span"));

  controls.append(zone, identify, power, toggle);
  root.append(swatch, main, controls);

  name.addEventListener("change", () => {
    const value = name.value.trim();
    if (value === (card.light?.name || "")) return;
    action("/api/light", { ip: light.ip, name: value });
  });
  name.addEventListener("keydown", (event) => {
    if (event.key === "Enter") name.blur();
    if (event.key === "Escape") {
      name.value = card.light?.name || "";
      name.blur();
    }
  });
  toggleInput.addEventListener("change", () => {
    if (toggleInput.checked === Boolean(card.light?.enabled)) return;
    action("/api/light", { ip: light.ip, enabled: toggleInput.checked });
  });
  zone.addEventListener("change", () => {
    if (zone.value === (card.light?.zone || "")) return;
    action("/api/light", { ip: light.ip, zone: zone.value });
  });
  identify.addEventListener("click", () => {
    action("/api/identify", { ip: light.ip }, "Flashing the bulb…", identify);
  });
  power.addEventListener("click", () => {
    action(
      "/api/power",
      { ip: light.ip, on: !(card.light?.state) },
      card.light?.state ? "Turning the bulb off…" : "Turning the bulb on…",
      power,
    );
  });

  const card = {
    root,
    swatch,
    name,
    online,
    ipLabel,
    modelLabel,
    zoneChip,
    extraLabel,
    zone,
    toggleInput,
    identify,
    power,
    light: null,
  };
  return card;
}

function updateCard(card, light) {
  card.light = light;
  card.root.classList.toggle("on", light.state);
  card.root.classList.toggle("enabled", light.enabled);
  card.root.classList.toggle("offline", !light.online);
  if (document.activeElement !== card.name) card.name.value = light.name;

  card.online.className = `online-dot ${light.online ? "up" : "down"}`;
  card.online.title = light.online ? "Online" : "Offline";
  card.ipLabel.textContent = light.ip;
  card.modelLabel.textContent = light.model || "unknown model";
  card.extraLabel.textContent = light.online
    ? [light.firmware && `fw ${light.firmware}`, light.state ? `on · ${light.dimming ?? "?"}%` : "off"]
        .filter(Boolean)
        .join(" · ")
    : "offline";
  card.zoneChip.classList.toggle("hidden", !light.enabled || !light.online);
  card.zoneChip.textContent = `→ ${zoneLabel(light.effective_zone)}`;
  card.zoneChip.title = `This bulb shows the ${zoneLabel(light.effective_zone)} zone`;

  if (document.activeElement !== card.zone) {
    const known = new Set(["", ...card.zone.dataset.zones.split(",")]);
    if (!known.has(light.zone)) {
      const fallback = el("option", "", zoneLabel(light.zone));
      fallback.value = light.zone;
      card.zone.append(fallback);
      card.zone.dataset.zones += `,${light.zone}`;
    }
    card.zone.value = light.zone;
  }
  if (document.activeElement !== card.toggleInput) card.toggleInput.checked = light.enabled;
  card.swatch.style.background = light.state ? rgbCss(light) : "#24212d";
  card.swatch.style.color = light.state ? rgbCss(light) : "transparent";
  card.swatch.classList.toggle("on", light.state && light.enabled);
  card.identify.disabled = !light.online;
  card.power.disabled = !light.online;
  card.power.title = light.state ? "Turn this bulb off" : "Turn this bulb on";
  card.power.setAttribute("aria-label", card.power.title);
}

function renderLights(lights, zones) {
  const seen = new Set();
  for (const light of lights) {
    seen.add(light.ip);
    let card = state.cards.get(light.ip);
    if (!card) {
      card = buildCard(light);
      card.zone.dataset.zones = zones.join(",");
      for (const name of zones) {
        const option = el("option", "", zoneLabel(name));
        option.value = name;
        card.zone.append(option);
      }
      state.cards.set(light.ip, card);
      refs.lights.append(card.root);
    }
    updateCard(card, light);
  }
  for (const [ip, card] of state.cards) {
    if (!seen.has(ip)) {
      card.root.remove();
      state.cards.delete(ip);
    }
  }
  refs.lightsEmpty.classList.toggle("hidden", lights.length > 0);
}

// --------------------------------------------------------------------- panels

function renderSession(snapshot) {
  const session = snapshot.session;
  const running = session.running;
  refs.statusDot.classList.toggle("live", running);
  refs.sessionPill.textContent = running
    ? `running · ${session.adopted ? "adopted " : ""}pid ${session.pid}`
    : "stopped";
  refs.sessionPill.classList.toggle("live", running);
  refs.stopBtn.disabled = !running;

  if (running && session.started) {
    const when = new Date(session.started * 1000).toLocaleTimeString([], {
      hour: "2-digit",
      minute: "2-digit",
    });
    refs.sessionDetail.textContent = `Started at ${when} · changing settings restarts the sync.`;
  } else {
    refs.sessionDetail.textContent = "No sync running.";
  }

  const enabled = snapshot.lights.filter((light) => light.enabled).length;
  const online = snapshot.lights.filter((light) => light.online).length;
  refs.subtitle.textContent = snapshot.demo
    ? "Demo mode — no packets are sent"
    : `${online} of ${snapshot.lights.length} lights online · ${enabled} in the show`;

  refs.enableAllBtn.disabled = snapshot.lights.length === 0 || enabled === snapshot.lights.length;
  refs.enableNoneBtn.disabled = enabled === 0;

  const mode = snapshot.config.mode;
  for (const button of document.querySelectorAll(".mode")) {
    button.classList.toggle("active", button.dataset.mode === mode);
  }
  refs.mediaField.classList.toggle("hidden", mode !== "launch");
  if (document.activeElement !== refs.mediaInput) refs.mediaInput.value = snapshot.config.media || "";
  refs.startBtn.textContent = running ? "Restart" : "Start ambilight";
  refs.startBtn.disabled = enabled === 0 || (mode === "launch" && !snapshot.config.media.trim());
  refs.modeHint.textContent =
    mode === "attach"
      ? "Attach follows any mpv window that loaded the Lua script. Install it once, then restart mpv."
      : "Launch starts mpv with the chosen file and syncs its frames. Settings are saved for next time.";
}

function fillSelect(select, values) {
  if (select.options.length === values.length) return;
  select.replaceChildren();
  for (const value of values) {
    const label = value === "auto" ? "Auto (by bulb count)" : zoneLabel(value).replace(/-/g, " / ");
    const option = el("option", "", label.charAt(0).toUpperCase() + label.slice(1));
    option.value = value;
    select.append(option);
  }
}

function renderSettings(snapshot) {
  const config = snapshot.config;
  fillSelect(refs.styleSelect, snapshot.styles);
  fillSelect(refs.layoutSelect, snapshot.layouts);
  if (document.activeElement !== refs.styleSelect) refs.styleSelect.value = config.style;
  if (document.activeElement !== refs.layoutSelect) refs.layoutSelect.value = config.layout;
  if (document.activeElement !== refs.brightness) {
    refs.brightness.value = String(config.brightness);
    refs.brightnessOut.value = String(config.brightness);
  }
  refs.dryRun.checked = Boolean(config.dry_run);

  const details = snapshot.style_details?.[config.style];
  refs.styleHint.textContent = details
    ? `${details.fps} fps capture · ${details.smooth ? `${details.smooth} ms fade` : "no fade"} · ` +
      `${details.send_hz} Hz output · ${Math.round(details.edge * 100)}% edge`
    : "";
}

function renderMapping(snapshot) {
  refs.mapping.replaceChildren();
  const enabled = snapshot.lights.filter((light) => light.enabled);
  if (!enabled.length) {
    refs.mapping.append(el("span", "mapping-empty", "No lights enabled."));
    return;
  }
  for (const light of enabled) {
    const chip = el("span", "map-chip");
    if (!light.online) chip.classList.add("offline");
    chip.append(
      el("strong", "", light.name || light.ip),
      el("span", "map-zone", `→ ${zoneLabel(light.effective_zone)}`),
    );
    chip.title = `${light.name || light.ip} shows the ${zoneLabel(light.effective_zone)} zone`;
    refs.mapping.append(chip);
  }
}

function renderLua(snapshot) {
  const lua = snapshot.lua;
  const needsInstall = !lua.installed;
  const stale = lua.installed && lua.stale;
  refs.luaBanner.classList.toggle("hidden", !needsInstall && !stale);
  refs.luaBanner.classList.toggle("stale", stale);
  refs.luaText.textContent = needsInstall
    ? "The Lua script is not installed, so attach mode cannot see mpv yet."
    : stale
      ? "The installed Lua script is outdated. Reinstall it and restart mpv."
      : "";
}

function renderLog(snapshot) {
  const lines = snapshot.session.log;
  if (lines.length < state.logFrom) state.logFrom = 0;
  const visible = lines.slice(state.logFrom);
  const text = visible.join("\n");
  if (refs.log.textContent !== text) {
    refs.log.textContent = text || (snapshot.session.running ? "Starting…" : "No activity yet.");
    refs.log.scrollTop = refs.log.scrollHeight;
  }
}

function apply(snapshot) {
  state.snapshot = snapshot;
  refs.versionBadge.textContent = `v${snapshot.version}`;
  refs.demoBadge.classList.toggle("hidden", !snapshot.demo);
  refs.configPath.textContent = `Config: ${snapshot.config_path}`;
  refs.configPath.title = snapshot.config_path;
  renderLights(snapshot.lights, snapshot.zones);
  renderSession(snapshot);
  renderSettings(snapshot);
  renderMapping(snapshot);
  renderLua(snapshot);
  renderLog(snapshot);
}

// --------------------------------------------------------------------- events

function saveConfig(patch, message) {
  const running = Boolean(state.snapshot?.session.running);
  return action(
    "/api/config",
    patch,
    message || (running ? "Saved — restarting the sync…" : null),
  );
}

function setAllEnabled(enabled) {
  if (!state.snapshot) return;
  const lights = {};
  for (const light of state.snapshot.lights) lights[light.ip] = { enabled };
  saveConfig({ lights }, enabled ? "All lights included" : "No lights included");
}

for (const button of document.querySelectorAll(".mode")) {
  button.addEventListener("click", () => saveConfig({ mode: button.dataset.mode }));
}

refs.scanBtn.addEventListener("click", async () => {
  const original = refs.scanBtn.textContent;
  refs.scanBtn.textContent = "Scanning…";
  refs.scanBtn.disabled = true;
  const data = await action("/api/scan", {}, null, refs.scanBtn);
  refs.scanBtn.textContent = original;
  refs.scanBtn.disabled = false;
  if (data) toast(`Scan finished · ${data.lights.length} lights known`);
});

refs.enableAllBtn.addEventListener("click", () => setAllEnabled(true));
refs.enableNoneBtn.addEventListener("click", () => setAllEnabled(false));
refs.startBtn.addEventListener("click", () => action("/api/start", {}, "Ambilight started", refs.startBtn));
refs.stopBtn.addEventListener("click", () => action("/api/stop", {}, "Ambilight stopped", refs.stopBtn));
refs.installBtn.addEventListener("click", () =>
  action("/api/install-script", {}, "Lua script installed — restart mpv", refs.installBtn),
);
refs.browseBtn.addEventListener("click", async () => {
  try {
    const result = await api("/api/pick-file");
    if (result.path) {
      refs.mediaInput.value = result.path;
      await saveConfig({ media: result.path });
    }
  } catch (error) {
    toast(error.message, true);
  }
});
refs.mediaInput.addEventListener("change", () => {
  const value = refs.mediaInput.value.trim();
  if (value !== (state.snapshot?.config.media || "")) saveConfig({ media: value });
});
refs.styleSelect.addEventListener("change", () => saveConfig({ style: refs.styleSelect.value }));
refs.layoutSelect.addEventListener("change", () => saveConfig({ layout: refs.layoutSelect.value }));
refs.brightness.addEventListener("input", () => {
  refs.brightnessOut.value = refs.brightness.value;
});
refs.brightness.addEventListener("change", () => {
  const value = Number(refs.brightness.value);
  if (value !== state.snapshot?.config.brightness) saveConfig({ brightness: value });
});
refs.dryRun.addEventListener("change", () => {
  if (refs.dryRun.checked !== Boolean(state.snapshot?.config.dry_run)) {
    saveConfig({ dry_run: refs.dryRun.checked });
  }
});
refs.clearLog.addEventListener("click", () => {
  state.logFrom = state.snapshot ? state.snapshot.session.log.length : 0;
  refs.log.textContent = "No activity yet.";
});

let quitArmed = false;
let quitTimer = null;
refs.quitBtn.addEventListener("click", async () => {
  if (!quitArmed) {
    quitArmed = true;
    refs.quitBtn.textContent = "Confirm quit";
    refs.quitBtn.classList.add("danger");
    toast("Press Quit again to stop the sync and close the panel.");
    quitTimer = window.setTimeout(() => {
      quitArmed = false;
      refs.quitBtn.textContent = "Quit";
      refs.quitBtn.classList.remove("danger");
    }, 5000);
    return;
  }
  window.clearTimeout(quitTimer);
  state.closed = true;
  try {
    await api("/api/quit");
  } catch (_) {
    /* the server may close the socket before answering */
  }
  window.clearInterval(state.poll);
  refs.statusDot.classList.remove("live");
  refs.sessionPill.textContent = "closed";
  refs.sessionPill.classList.remove("live");
  refs.sessionDetail.textContent = "Panel closed.";
  refs.offlineBanner.classList.add("hidden");
  toast("Panel closed. Lights stop when the sync child exits.");
});

document.addEventListener("visibilitychange", () => {
  if (!document.hidden && !state.closed) refresh();
});

async function refresh() {
  try {
    const response = await fetch("/api/state", { cache: "no-store" });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    apply(await response.json());
    refs.offlineBanner.classList.add("hidden");
  } catch (error) {
    if (state.closed) return;
    refs.statusDot.classList.remove("live");
    refs.subtitle.textContent = "Panel connection lost";
    refs.offlineBanner.classList.remove("hidden");
  }
}

async function boot() {
  await refresh();
  state.poll = window.setInterval(() => {
    if (!document.hidden && !state.closed) refresh();
  }, 1200);
}

boot();
