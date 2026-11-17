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
  scanBtn: document.getElementById("scanBtn"),
  lights: document.getElementById("lights"),
  lightsEmpty: document.getElementById("lightsEmpty"),
  luaBanner: document.getElementById("luaBanner"),
  luaText: document.getElementById("luaText"),
  installBtn: document.getElementById("installBtn"),
  sessionPill: document.getElementById("sessionPill"),
  startBtn: document.getElementById("startBtn"),
  stopBtn: document.getElementById("stopBtn"),
  mediaField: document.getElementById("mediaField"),
  mediaInput: document.getElementById("mediaInput"),
  browseBtn: document.getElementById("browseBtn"),
  modeHint: document.getElementById("modeHint"),
  styleSelect: document.getElementById("styleSelect"),
  layoutSelect: document.getElementById("layoutSelect"),
  brightness: document.getElementById("brightness"),
  brightnessOut: document.getElementById("brightnessOut"),
  dryRun: document.getElementById("dryRun"),
  log: document.getElementById("log"),
  clearLog: document.getElementById("clearLog"),
  toast: document.getElementById("toast"),
};

const state = { snapshot: null, cards: new Map(), poll: null, logFrom: 0, busy: false };

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
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body || {}),
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok || data.error) throw new Error(data.error || `HTTP ${response.status}`);
  return data;
}

async function action(path, body, message) {
  if (state.busy) return;
  state.busy = true;
  try {
    const data = await api(path, body);
    if (data && data.lights) apply(data);
    if (message) toast(message);
    return data;
  } catch (error) {
    toast(error.message, true);
  } finally {
    state.busy = false;
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
  const ipLabel = el("span", "ip");
  const modelLabel = el("span", "model");
  const extraLabel = el("span", "extra");
  meta.append(ipLabel, modelLabel, extraLabel);

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
    action("/api/light", { ip: light.ip, name: name.value.trim() });
  });
  name.addEventListener("keydown", (event) => {
    if (event.key === "Enter") name.blur();
  });
  toggleInput.addEventListener("change", () => {
    action("/api/light", { ip: light.ip, enabled: toggleInput.checked });
  });
  zone.addEventListener("change", () => {
    action("/api/light", { ip: light.ip, zone: zone.value });
  });
  identify.addEventListener("click", () => {
    action("/api/identify", { ip: light.ip }, "Flashing the bulb…");
  });
  power.addEventListener("click", () => {
    action("/api/power", { ip: light.ip, on: !light.state });
  });

  return { root, swatch, name, ipLabel, modelLabel, extraLabel, zone, toggleInput, identify, power };
}

function updateCard(card, light) {
  card.root.classList.toggle("on", light.state);
  card.root.classList.toggle("enabled", light.enabled);
  card.root.classList.toggle("offline", !light.online);
  if (document.activeElement !== card.name) card.name.value = light.name;
  card.ipLabel.textContent = light.ip;
  card.modelLabel.textContent = light.model || "unknown model";
  card.extraLabel.textContent = light.online
    ? [light.firmware && `fw ${light.firmware}`, light.state ? `on · ${light.dimming ?? "?"}%` : "off"]
        .filter(Boolean)
        .join(" · ")
    : "offline";
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

  const enabled = snapshot.lights.filter((light) => light.enabled).length;
  const online = snapshot.lights.filter((light) => light.online).length;
  refs.subtitle.textContent = snapshot.demo
    ? "Demo mode — no packets are sent"
    : `${online} of ${snapshot.lights.length} lights online · ${enabled} in the show`;

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
  if (document.activeElement !== refs.brightness) refs.brightness.value = String(config.brightness);
  refs.brightnessOut.value = String(config.brightness);
  refs.dryRun.checked = Boolean(config.dry_run);
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
  renderLights(snapshot.lights, snapshot.zones);
  renderSession(snapshot);
  renderSettings(snapshot);
  renderLua(snapshot);
  renderLog(snapshot);
}

// --------------------------------------------------------------------- events

function saveConfig(patch, message) {
  return action("/api/config", patch, message);
}

for (const button of document.querySelectorAll(".mode")) {
  button.addEventListener("click", () => saveConfig({ mode: button.dataset.mode }));
}

refs.scanBtn.addEventListener("click", () => action("/api/scan", {}, "Network scan finished"));
refs.startBtn.addEventListener("click", () => action("/api/start", {}, "Ambilight started"));
refs.stopBtn.addEventListener("click", () => action("/api/stop", {}, "Ambilight stopped"));
refs.installBtn.addEventListener("click", () =>
  action("/api/install-script", {}, "Lua script installed — restart mpv"),
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
refs.mediaInput.addEventListener("change", () => saveConfig({ media: refs.mediaInput.value.trim() }));
refs.styleSelect.addEventListener("change", () => saveConfig({ style: refs.styleSelect.value }));
refs.layoutSelect.addEventListener("change", () => saveConfig({ layout: refs.layoutSelect.value }));
refs.brightness.addEventListener("input", () => {
  refs.brightnessOut.value = refs.brightness.value;
});
refs.brightness.addEventListener("change", () =>
  saveConfig({ brightness: Number(refs.brightness.value) }),
);
refs.dryRun.addEventListener("change", () => saveConfig({ dry_run: refs.dryRun.checked }));
refs.clearLog.addEventListener("click", () => {
  state.logFrom = state.snapshot ? state.snapshot.session.log.length : 0;
  refs.log.textContent = "No activity yet.";
});
refs.quitBtn.addEventListener("click", async () => {
  try {
    await api("/api/quit");
  } catch (_) {
    /* server may close the socket before answering */
  }
  window.clearInterval(state.poll);
  refs.statusDot.classList.remove("live");
  refs.sessionPill.textContent = "closed";
  refs.sessionPill.classList.remove("live");
  toast("Panel closed. Your lights keep running until you stop mpv.");
});

document.addEventListener("visibilitychange", () => {
  if (!document.hidden) refresh();
});

async function refresh() {
  try {
    const response = await fetch("/api/state", { cache: "no-store" });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    apply(await response.json());
  } catch (error) {
    refs.statusDot.classList.remove("live");
    refs.subtitle.textContent = "Panel connection lost";
  }
}

async function boot() {
  await refresh();
  state.poll = window.setInterval(() => {
    if (!document.hidden) refresh();
  }, 1200);
}

boot();
