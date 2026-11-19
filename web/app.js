"use strict";

const el = (tag, className, text) => {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
};

/* Sliders paint their own filled track through the --fill custom property. */
const paintRange = (input) => {
  const min = Number(input.min) || 0;
  const max = Number(input.max) || 100;
  const value = Number(input.value) || 0;
  const ratio = max > min ? (value - min) / (max - min) : 0;
  input.style.setProperty("--fill", `${Math.round(ratio * 100)}%`);
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
  lightFilter: document.getElementById("lightFilter"),
  lightsEmpty: document.getElementById("lightsEmpty"),
  targetSelect: document.getElementById("targetSelect"),
  targetPill: document.getElementById("targetPill"),
  controlNote: document.getElementById("controlNote"),
  powerToggle: document.getElementById("powerToggle"),
  powerState: document.getElementById("powerState"),
  controlBrightness: document.getElementById("controlBrightness"),
  controlBrightnessOut: document.getElementById("controlBrightnessOut"),
  controlTemp: document.getElementById("controlTemp"),
  controlTempOut: document.getElementById("controlTempOut"),
  controlColor: document.getElementById("controlColor"),
  controlHex: document.getElementById("controlHex"),
  applyColorBtn: document.getElementById("applyColorBtn"),
  sceneSelect: document.getElementById("sceneSelect"),
  applySceneBtn: document.getElementById("applySceneBtn"),
  controlSpeed: document.getElementById("controlSpeed"),
  controlSpeedOut: document.getElementById("controlSpeedOut"),
  lightsPill: document.getElementById("lightsPill"),
  lookPill: document.getElementById("lookPill"),
  logPill: document.getElementById("logPill"),
  networkNote: document.getElementById("networkNote"),
  sceneName: document.getElementById("sceneName"),
  saveSceneBtn: document.getElementById("saveSceneBtn"),
  sceneList: document.getElementById("sceneList"),
  scenePill: document.getElementById("scenePill"),
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
  styleSelect: document.getElementById("styleSelect"),
  samplingSelect: document.getElementById("samplingSelect"),
  sampleStage: document.getElementById("sampleStage"),
  colorStage: document.getElementById("colorStage"),
  sendStage: document.getElementById("sendStage"),
  samplingManual: document.getElementById("samplingManual"),
  samplingFps: document.getElementById("samplingFps"),
  samplingFpsOut: document.getElementById("samplingFpsOut"),
  samplingGrid: document.getElementById("samplingGrid"),
  samplingBlock: document.getElementById("samplingBlock"),
  samplingCapture: document.getElementById("samplingCapture"),
  layoutSelect: document.getElementById("layoutSelect"),
  layoutHint: document.getElementById("layoutHint"),
  brightness: document.getElementById("brightness"),
  brightnessOut: document.getElementById("brightnessOut"),
  dryRun: document.getElementById("dryRun"),
  controlCard: document.getElementById("controlCard"),
  log: document.getElementById("log"),
  logCard: document.getElementById("logCard"),
  clearLog: document.getElementById("clearLog"),
  configPath: document.getElementById("configPath"),
  perf: document.getElementById("perf"),
  perfMeta: document.getElementById("perfMeta"),
  perfLegend: document.getElementById("perfLegend"),
  perfSvg: document.getElementById("perfSvg"),
  rooms: document.getElementById("rooms"),
  newRoomBtn: document.getElementById("newRoomBtn"),
  roomList: document.getElementById("roomList"),
  roomEditor: document.getElementById("roomEditor"),
  roomName: document.getElementById("roomName"),
  roomMembers: document.getElementById("roomMembers"),
  roomSaveBtn: document.getElementById("roomSaveBtn"),
  roomCancelBtn: document.getElementById("roomCancelBtn"),
  saveColorBtn: document.getElementById("saveColorBtn"),
  colorChips: document.getElementById("colorChips"),
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
  scenesSignature: "",
  perfAt: 0,
  perf: { mpvCpu: [], wizCpu: [], mpvRam: [], wizRam: [], udp: [] },
  perfTimes: [],
  roomsSignature: "",
  roomArmed: null,
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
    if (data && data.warning) toast(data.warning, true);
    else if (message) toast(message);
    return data;
  } catch (error) {
    toast(error.message, true);
  } finally {
    state.busy = false;
    if (button) button.classList.remove("loading");
  }
}

function zoneLabel(zone) {
  const labels = {
    all: "whole frame",
    left: "left edge",
    right: "right edge",
    top: "top edge",
    bottom: "bottom edge",
    t1: "left third",
    t2: "middle third",
    t3: "right third",
  };
  return labels[zone] || zone;
}

function rgbCss(light) {
  const dim = Math.max(0.08, Math.min(1, (light.dimming || 100) / 100));
  const scale = 0.25 + 0.75 * dim;
  const channel = (value) => Math.round((Number(value) || 0) * scale);
  if (typeof light.r === "number" && typeof light.g === "number" && typeof light.b === "number") {
    return `rgb(${channel(light.r)}, ${channel(light.g)}, ${channel(light.b)})`;
  }
  // White bulbs report a temperature, not RGB; approximate it for the swatch.
  const value = Number.parseInt(kelvinToHex(light.temp || 3000).slice(1), 16);
  return `rgb(${channel((value >> 16) & 255)}, ${channel((value >> 8) & 255)}, ${channel(value & 255)})`;
}

const HEX_RE = /^#?[0-9a-fA-F]{6}$/;

function normalizeHex(value) {
  const text = String(value || "").trim();
  if (!HEX_RE.test(text)) return null;
  return (text.startsWith("#") ? text : `#${text}`).toLowerCase();
}

/* A warm-white bulb at 3000 K looks like #ffb16e on screen, not white. This
   follows Tanner Helland's fit so the hex field tracks the White slider; the
   bulb itself still receives the Kelvin number. */
function kelvinToHex(kelvin) {
  const temp = Math.max(1000, Math.min(40000, Number(kelvin) || 3000)) / 100;
  let r;
  let g;
  let b;
  if (temp <= 66) {
    r = 255;
    g = 99.4708025861 * Math.log(temp) - 161.1195681661;
    b = temp <= 19 ? 0 : 138.5177312231 * Math.log(temp - 10) - 305.0447927307;
  } else {
    r = 329.698727446 * (temp - 60) ** -0.1332047592;
    g = 288.1221695283 * (temp - 60) ** -0.0755148492;
    b = 255;
  }
  const channel = (value) =>
    Math.max(0, Math.min(255, Math.round(value))).toString(16).padStart(2, "0");
  return `#${channel(r)}${channel(g)}${channel(b)}`;
}

function targetIp() {
  return refs.targetSelect.value || "all";
}

function targetLights(snapshot) {
  const value = targetIp();
  const lights = snapshot?.lights || [];
  if (value === "all") return lights;
  if (value.startsWith("group:")) {
    const ips = snapshot?.config?.groups?.[value.slice(6)] || [];
    return lights.filter((light) => ips.includes(light.ip));
  }
  return lights.filter((light) => light.ip === value);
}

function targetLight(snapshot) {
  return targetLights(snapshot)[0] || null;
}

function targetName(snapshot) {
  const value = targetIp();
  if (value.startsWith("group:")) return value.slice(6);
  const light = targetLight(snapshot);
  if (light) return light.name || light.ip;
  return "all lights";
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
  ipLabel.tabIndex = 0;
  const modelLabel = el("span", "model");
  const hexChip = el("button", "hex-chip");
  hexChip.type = "button";
  hexChip.title = "Send this color to the target";
  hexChip.setAttribute("aria-label", "Use this light's color in direct control");
  hexChip.classList.add("hidden");
  const extraLabel = el("span", "extra");
  meta.append(online, ipLabel, modelLabel, hexChip, extraLabel);

  const main = el("div", "light-main");
  main.append(name, meta);

  const controls = el("div", "light-controls");
  const zonePick = el("div", "zone-pick");
  const zonePreview = el("span", "zone-preview");
  zonePreview.setAttribute("aria-hidden", "true");
  const zone = el("select", "zone");
  zone.setAttribute("aria-label", "Zone for this light");
  const auto = el("option", "", "Auto zone");
  auto.value = "";
  zone.append(auto);
  zonePick.append(zonePreview, zone);

  const identify = el("button", "icon-btn identify", "✦");
  identify.type = "button";
  identify.title = "Flash this bulb";
  identify.setAttribute("aria-label", "Identify light");

  const toggle = el("label", "switch");
  toggle.title = "Include this light in ambilight";
  const toggleInput = document.createElement("input");
  toggleInput.type = "checkbox";
  toggleInput.setAttribute("aria-label", "Include light");
  toggle.append(toggleInput, el("span"));

  controls.append(zonePick, identify, toggle);
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
  hexChip.addEventListener("click", () => {
    if (!card.light) return;
    const value = normalizeHex(card.light.hex) || "#ffffff";
    refs.targetSelect.value = card.light.ip;
    if (state.snapshot) renderControl(state.snapshot);
    if (document.activeElement !== refs.controlColor) refs.controlColor.value = value;
    refs.controlHex.value = value;
    refs.controlHex.focus();
    refs.controlHex.select();
    toast(`Target: ${card.light.name || card.light.ip}. Press Apply to send ${value}.`);
  });

  const card = {
    root,
    swatch,
    name,
    online,
    ipLabel,
    modelLabel,
    hexChip,
    extraLabel,
    zone,
    zonePreview,
    toggleInput,
    identify,
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
  card.ipLabel.dataset.hw = [light.model || "unknown model", light.firmware && `fw ${light.firmware}`]
    .filter(Boolean)
    .join(" · ");
  card.ipLabel.setAttribute("aria-label", `${light.ip} · ${card.ipLabel.dataset.hw}`);
  card.modelLabel.textContent = light.model || "unknown model";
  card.root.dataset.search = [light.name, light.ip, light.model].filter(Boolean).join(" ").toLowerCase();
  card.extraLabel.textContent = light.online
    ? (light.state ? `on · ${light.dimming ?? "?"}%` : "off")
    : "offline";
  card.zonePreview.dataset.zone = light.effective_zone;
  card.zonePreview.title = `Samples the ${zoneLabel(light.effective_zone)} of the video`;
  const hexValue = normalizeHex(light.hex);
  card.hexChip.classList.toggle("hidden", !hexValue || !light.online);
  if (hexValue) {
    card.hexChip.textContent = hexValue;
    card.hexChip.title = `Use ${hexValue} from ${light.name || light.ip} in direct control`;
  }

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
  const shown = light.state ? rgbCss(light) : "#24212d";
  card.swatch.style.background = shown;
  card.swatch.style.color = light.state ? shown : "transparent";
  card.swatch.classList.toggle("on", light.state && light.enabled);
  card.identify.disabled = !light.online;
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
  const online = lights.filter((light) => light.online).length;
  refs.lightsPill.textContent = lights.length ? `${online}/${lights.length}` : "0";
  refs.lightsPill.classList.toggle("warn", lights.length > 0 && online < lights.length);
  applyLightFilter();
}

/* Client-side only: the panel already knows every bulb it may talk to. */
function applyLightFilter() {
  const needle = (refs.lightFilter?.value || "").trim().toLowerCase();
  let shown = 0;
  for (const card of state.cards.values()) {
    const match = !needle || (card.root.dataset.search || "").includes(needle);
    card.root.classList.toggle("hidden", !match);
    if (match) shown += 1;
  }
  if (!refs.lightsEmpty) return;
  const empty = state.cards.size === 0;
  if (needle && !empty && shown === 0) {
    refs.lightsEmpty.textContent = `No light matches “${refs.lightFilter.value.trim()}”.`;
    refs.lightsEmpty.classList.remove("hidden");
  } else {
    refs.lightsEmpty.classList.toggle("hidden", !empty);
  }
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
  }
  refs.sessionDetail.classList.toggle("hidden", !running || !session.started);

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
  refs.startBtn.textContent = running ? "Restart" : "Start Ambilight";
  refs.startBtn.disabled = enabled === 0 || (mode === "launch" && !snapshot.config.media.trim());
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

const SAMPLING_OPTIONS = [
  ["auto", "Auto — follows the video size"],
  ["lean", "Lean — lightest read"],
  ["balanced", "Balanced — middle ground"],
  ["quality", "Quality — most detail"],
  ["manual", "Manual — pick every knob"],
];

/* Mirrors SAMPLING_PROFILES in mpv_ambilight.py, minus the numbers the panel
   shows in the spec strip: the strip explains what each preset actually reads. */
const SAMPLING_PROFILES = {
  lean: { grid: 48, block: 1, capture: "scaled", cap: 10 },
  balanced: { grid: 80, block: 2, capture: "scaled", cap: 15 },
  quality: { grid: 120, block: 3, capture: "source", cap: 30 },
};

/* Mirrors auto_sampling() in lua/wiz_ambilight.lua: the cap follows the
   height of the frame that was actually captured, not the video's height. */
function autoSampling(height) {
  if (!height) return null;
  if (height <= 1200) return { grid: 80, block: 1, capture: "scaled", cap: 30 };
  if (height <= 1600) return { grid: 96, block: 2, capture: "scaled", cap: 12 };
  return { grid: 112, block: 2, capture: "scaled", cap: 8 };
}

function renderStage(list, rows) {
  if (!list) return;
  while (list.children.length < rows.length) {
    const row = el("div", "kv-row");
    row.append(el("dt", "", ""), el("dd", "", ""));
    list.append(row);
  }
  while (list.children.length > rows.length) list.lastElementChild.remove();
  rows.forEach(([label, value, title], index) => {
    const row = list.children[index];
    const [term, detail] = row.children;
    if (term.textContent !== label) term.textContent = label;
    if (detail.textContent !== value) detail.textContent = value;
    row.title = title || "";
  });
}

function formatFps(value) {
  const rounded = Math.round(value * 10) / 10;
  return `${Number.isInteger(rounded) ? rounded : rounded.toFixed(1)} fps`;
}

function fillSamplingSelect() {
  if (refs.samplingSelect.options.length === SAMPLING_OPTIONS.length) return;
  refs.samplingSelect.replaceChildren();
  for (const [value, label] of SAMPLING_OPTIONS) {
    const option = el("option", "", label);
    option.value = value;
    refs.samplingSelect.append(option);
  }
}

function renderSettings(snapshot) {
  const config = snapshot.config;
  fillSelect(refs.styleSelect, snapshot.styles);
  fillSelect(refs.layoutSelect, snapshot.layouts);
  fillSamplingSelect();
  if (document.activeElement !== refs.styleSelect) refs.styleSelect.value = config.style;
  if (document.activeElement !== refs.layoutSelect) refs.layoutSelect.value = config.layout;
  if (document.activeElement !== refs.samplingSelect) refs.samplingSelect.value = config.sampling;
  if (document.activeElement !== refs.brightness) {
    refs.brightness.value = String(config.brightness);
    refs.brightnessOut.value = String(config.brightness);
    paintRange(refs.brightness);
  }
  refs.dryRun.checked = Boolean(config.dry_run);
  refs.lookPill.textContent = config.style;

  const details = snapshot.style_details?.[config.style] || {};
  const styleFps = Number(details.fps) || 0;
  const smooth = Number(details.smooth);
  const saturation = Number(details.saturation);
  const sendHz = Number(details.send_hz);
  const edge = Number(details.edge);

  const manual = config.sampling === "manual";
  const captureHeight = Number(snapshot.resources?.capture_h) || 0;
  const profile = manual
    ? {
        grid: Number(config.sampling_grid) || 0,
        block: Number(config.sampling_block) || 0,
        capture: config.sampling_capture === "source" ? "source" : "scaled",
        cap: styleFps,
      }
    : SAMPLING_PROFILES[config.sampling]
      || autoSampling(captureHeight)
      || { grid: 0, block: 0, capture: "scaled", cap: styleFps };
  const readFps = manual
    ? Number(config.sampling_fps) || styleFps
    : styleFps
      ? Math.min(styleFps, profile.cap || styleFps)
      : profile.cap;
  const autoSize = config.sampling === "auto" && !captureHeight;

  renderStage(refs.sampleStage, [
    ["Frame", profile.capture === "source" ? "Full" : "Scaled",
      "Scaled reads the mpv window; full reads the decoded source frame"],
    ["Columns", profile.grid ? String(profile.grid) : "auto",
      "Vertical slices read from each frame; auto picks 80, 96 or 112 from the captured height"],
    ["Avg pixels", profile.block ? `${profile.block}×${profile.block} px` : "auto",
      "Pixels averaged per sample; larger blocks are softer and cheaper"],
    ["Rate", !readFps ? "—" : autoSize ? `≤ ${formatFps(readFps)}` : formatFps(readFps),
      "Frames read per second; presets cap the style target, manual sets it directly"],
  ]);

  renderStage(refs.colorStage, [
    ["Fade", Number.isFinite(smooth) ? (smooth > 0 ? `${Math.round(smooth)} ms` : "off") : "—",
      "Time to blend from the previous color to the new one; off means instant jumps"],
    ["Saturation", Number.isFinite(saturation) ? `${saturation.toFixed(2)}×` : "—",
      "Color boost applied to each sample; 1× leaves it unchanged"],
  ]);

  renderStage(refs.sendStage, [
    ["Rate", Number.isFinite(sendHz) ? `${Number(sendHz.toFixed(1))}/s` : "—",
      "UDP datagrams sent to the bulbs per second"],
    ["Brightness", `${config.brightness}%`,
      "Cap applied to every bulb while the sync runs"],
  ]);

  refs.layoutHint.textContent = Number.isFinite(edge) && edge > 0
    ? `Edge band ${Math.round(edge * 100)}% for edge zones.`
    : "";
  refs.layoutHint.title =
    "Fraction of the frame read by left, right, top and bottom zones when the layout uses them";

  refs.samplingManual.classList.toggle("hidden", !manual);
  if (document.activeElement !== refs.samplingFps) {
    refs.samplingFps.value = String(config.sampling_fps);
    refs.samplingFpsOut.value = String(config.sampling_fps);
    paintRange(refs.samplingFps);
  }
  if (document.activeElement !== refs.samplingGrid) {
    refs.samplingGrid.value = String(config.sampling_grid);
  }
  if (document.activeElement !== refs.samplingBlock) {
    refs.samplingBlock.value = String(config.sampling_block);
  }
  if (document.activeElement !== refs.samplingCapture) {
    refs.samplingCapture.value = config.sampling_capture;
  }
}

function fillTargetOptions(snapshot) {
  const groups = snapshot.config.groups || {};
  const signature = JSON.stringify([
    snapshot.lights.map((light) => `${light.ip}:${light.name}`),
    Object.keys(groups).sort().map((name) => [name, groups[name]]),
  ]);
  if (refs.targetSelect.dataset.signature === signature) return;
  const wanted = refs.targetSelect.value || "all";
  refs.targetSelect.replaceChildren();
  const all = el("option", "", "All lights");
  all.value = "all";
  refs.targetSelect.append(all);
  for (const name of Object.keys(groups).sort((a, b) => a.localeCompare(b))) {
    const count = groups[name].length;
    const option = el("option", "", `${name} · ${count} ${count === 1 ? "light" : "lights"}`);
    option.value = `group:${name}`;
    refs.targetSelect.append(option);
  }
  for (const light of snapshot.lights) {
    const option = el("option", "", light.name ? `${light.name} · ${light.ip}` : light.ip);
    option.value = light.ip;
    refs.targetSelect.append(option);
  }
  refs.targetSelect.dataset.signature = signature;
  const known = [...refs.targetSelect.options].some((option) => option.value === wanted);
  refs.targetSelect.value = known ? wanted : "all";
}

function fillSceneOptions(snapshot) {
  const scenes = snapshot.wiz_scenes || [];
  const signature = scenes.map((scene) => `${scene.id}:${scene.name}`).join("|");
  if (refs.sceneSelect.dataset.signature === signature) return;
  const wanted = refs.sceneSelect.value;
  refs.sceneSelect.replaceChildren();
  for (const scene of scenes) {
    const option = el("option", "", `${scene.name} (${scene.id})`);
    option.value = String(scene.id);
    refs.sceneSelect.append(option);
  }
  refs.sceneSelect.dataset.signature = signature;
  if (wanted && [...refs.sceneSelect.options].some((option) => option.value === wanted)) {
    refs.sceneSelect.value = wanted;
  }
}

function ipInCidr(ip, cidr) {
  const [base, bitsText] = String(cidr).split("/");
  const bits = Number(bitsText);
  if (!base || !Number.isFinite(bits) || bits < 0 || bits > 32) return false;
  const toInt = (value) =>
    value.split(".").reduce((acc, part) => ((acc << 8) + Number(part)) >>> 0, 0);
  const mask = bits === 0 ? 0 : (0xffffffff << (32 - bits)) >>> 0;
  return (toInt(ip) & mask) === (toInt(base) & mask);
}

function renderNetwork(snapshot) {
  if (!refs.networkNote) return;
  const networks = snapshot.network || [];
  const lights = snapshot.lights || [];
  if (!networks.length) {
    refs.networkNote.textContent =
      "This computer has no active IPv4 network — bulbs cannot answer.";
    refs.networkNote.classList.add("warn");
    return;
  }
  const online = lights.filter((light) => light.online).length;
  const offline = lights.filter((light) => !light.online);
  const parts = [`Panel network: ${networks.join(", ")}`];
  if (lights.length) parts.push(`${online} of ${lights.length} bulbs reachable`);
  const outside = offline.filter((light) => !networks.some((cidr) => ipInCidr(light.ip, cidr)));
  if (outside.length) {
    parts.push(`${outside.map((light) => light.ip).join(", ")} outside this subnet`);
  }
  refs.networkNote.textContent = parts.join(" · ");
  refs.networkNote.classList.toggle("warn", lights.length > 0 && offline.length > 0);
}

function renderCrazy(snapshot) {
  const crazy = snapshot.crazy || {};
  const active = Boolean(crazy.active);
  refs.statusDot.classList.toggle("crazy", active);
  refs.statusDot.title = active ? "Crazy mode — click 3× to stop" : "";
}

function renderControl(snapshot) {
  fillTargetOptions(snapshot);
  fillSceneOptions(snapshot);

  const lights = targetLights(snapshot);
  const light = lights[0] || null;
  const isAll = targetIp() === "all";
  refs.targetPill.textContent = isAll ? "all lights" : targetName(snapshot);
  refs.controlNote.textContent = snapshot.session.running
    ? "Ambilight is syncing — direct changes last until the next frame."
    : "Control bulbs without starting Ambilight.";

  const hasLights = snapshot.lights.length > 0;
  const hasTarget = lights.length > 0;
  const anyOn = lights.some((row) => row.state);
  refs.applyColorBtn.disabled = !hasLights;
  refs.applySceneBtn.disabled = !hasLights || !refs.sceneSelect.options.length;
  refs.saveSceneBtn.disabled = !hasLights;
  refs.powerToggle.disabled = !hasTarget;
  if (document.activeElement !== refs.powerToggle) refs.powerToggle.checked = anyOn;
  refs.powerState.textContent = hasTarget ? (anyOn ? "On" : "Off") : "—";
  refs.powerState.classList.toggle("on", anyOn);

  if (!light) return;
  if (document.activeElement !== refs.controlBrightness) {
    const value = light.dimming ?? 100;
    refs.controlBrightness.value = String(value);
    refs.controlBrightnessOut.value = String(value);
    paintRange(refs.controlBrightness);
  }
  if (document.activeElement !== refs.controlTemp) {
    const value = light.temp ?? 3000;
    refs.controlTemp.value = String(value);
    refs.controlTempOut.value = `${value} K`;
    paintRange(refs.controlTemp);
  }
  if (document.activeElement !== refs.controlHex && document.activeElement !== refs.controlColor) {
    const value =
      document.activeElement === refs.controlTemp
        ? kelvinToHex(refs.controlTemp.value)
        : normalizeHex(light.hex) || (light.temp ? kelvinToHex(light.temp) : "#ffffff");
    refs.controlColor.value = value;
    refs.controlHex.value = value;
  }
}

function renderScenes(snapshot) {
  const scenes = snapshot.scenes || [];
  refs.scenePill.textContent = String(scenes.length);
  const signature = scenes.map((scene) => `${scene.name}:${scene.count}`).join("|");
  if (signature === state.scenesSignature) return;
  state.scenesSignature = signature;
  refs.sceneList.replaceChildren();
  if (!scenes.length) {
    refs.sceneList.append(el("p", "scene-empty", "No saved scenes yet."));
    return;
  }
  for (const scene of scenes) {
    const item = el("div", "scene-item");
    item.append(
      el("span", "scene-name", scene.name),
      el("span", "scene-count", `${scene.count} ${scene.count === 1 ? "light" : "lights"}`),
    );
    const applyBtn = el("button", "ghost small", "Apply");
    applyBtn.type = "button";
    applyBtn.addEventListener("click", () =>
      action("/api/scene/apply", { name: scene.name }, `Scene “${scene.name}” applied`, applyBtn),
    );
    const deleteBtn = el("button", "ghost small", "Delete");
    deleteBtn.type = "button";
    let armed = false;
    deleteBtn.addEventListener("click", () => {
      if (!armed) {
        armed = true;
        deleteBtn.textContent = "Sure?";
        deleteBtn.classList.add("danger");
        window.setTimeout(() => {
          armed = false;
          deleteBtn.textContent = "Delete";
          deleteBtn.classList.remove("danger");
        }, 3000);
        return;
      }
      action("/api/scene/delete", { name: scene.name }, `Deleted “${scene.name}”`, deleteBtn);
    });
    item.append(applyBtn, deleteBtn);
    refs.sceneList.append(item);
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
  refs.logPill.textContent = lines.length
    ? `${lines.length}`
    : snapshot.session.running
      ? "starting"
      : "idle";
  if (lines.length < state.logFrom) state.logFrom = 0;
  const visible = lines.slice(state.logFrom);
  const text = visible.join("\n");
  if (refs.log.textContent !== text) {
    refs.log.textContent = text || (snapshot.session.running ? "Starting…" : "No activity yet.");
    refs.log.scrollTop = refs.log.scrollHeight;
  }
}

const PERF_SAMPLES = 60;

/* One chart frame, three lanes by unit. CPU, MB and KB/s cannot share an
   honest axis, so each lane has its own scale; the colors tell the processes
   apart. These are chalk tones, not the amber accent: the accent stays for the
   chrome. */
const PERF_LANES = [
  {
    label: "CPU %",
    min: 5,
    format: (value) => `${value < 10 ? value.toFixed(1) : Math.round(value)}%`,
    series: [
      {
        key: "mpvCpu",
        label: "mpv CPU",
        color: "#e08c82",
        tip: "mpv's share of the whole processor",
      },
      {
        key: "wizCpu",
        label: "wiz CPU",
        color: "#9fcf9f",
        tip: "Panel and sync share of the whole processor",
      },
    ],
  },
  {
    label: "RAM MB",
    min: 10,
    format: (value) => `${Math.round(value)} MB`,
    series: [
      {
        key: "mpvRam",
        label: "mpv RAM",
        color: "#fcbe11",
        tip: "mpv's resident memory",
      },
      {
        key: "wizRam",
        label: "wiz RAM",
        color: "#8fb6db",
        tip: "Panel and sync resident memory",
      },
    ],
  },
  {
    label: "UDP KB/s",
    min: 1,
    format: (value) => `${value < 10 ? value.toFixed(1) : Math.round(value)} KB/s`,
    series: [
      {
        key: "udp",
        label: "WiZ UDP",
        color: "#b9a0d8",
        tip: "Datagrams the sync sends to the bulbs",
      },
    ],
  },
];

function svgNode(tag, attrs) {
  const node = document.createElementNS("http://www.w3.org/2000/svg", tag);
  for (const [name, value] of Object.entries(attrs || {})) node.setAttribute(name, String(value));
  return node;
}

/* Round a peak up to a readable maximum: 0.42 -> 0.5, 37 -> 40, 230 -> 250. */
function niceCeil(value) {
  if (!Number.isFinite(value) || value <= 0) return 1;
  const exponent = Math.floor(Math.log10(value));
  const base = 10 ** exponent;
  const fraction = value / base;
  const steps = [1, 1.5, 2, 2.5, 3, 4, 5, 6, 8, 10];
  const step = steps.find((candidate) => fraction <= candidate) || 10;
  return step * base;
}

function lastValue(values) {
  for (let index = values.length - 1; index >= 0; index -= 1) {
    const value = values[index];
    if (typeof value === "number" && Number.isFinite(value)) return value;
  }
  return null;
}

function formatMetric(key, value) {
  if (typeof value !== "number" || !Number.isFinite(value)) return "—";
  if (key.endsWith("Cpu")) return `${value < 1 ? value.toFixed(2) : value.toFixed(1)}%`;
  if (key.endsWith("Ram")) return `${Math.round(value)} MB`;
  return `${value < 10 ? value.toFixed(1) : Math.round(value)} KB/s`;
}

function pushPerf(res) {
  if (!res.at || res.at === state.perfAt) return;
  state.perfAt = res.at;
  const incoming = {
    mpvCpu: res.cpu_mpv,
    wizCpu: res.cpu_wiz,
    mpvRam: res.ram_mpv,
    wizRam: res.ram_wiz,
    udp: res.udp_kbps,
  };
  for (const [key, series] of Object.entries(state.perf)) {
    const value = incoming[key];
    series.push(typeof value === "number" && Number.isFinite(value) ? value : null);
    if (series.length > PERF_SAMPLES) series.splice(0, series.length - PERF_SAMPLES);
  }
  state.perfTimes.push(res.at);
  if (state.perfTimes.length > PERF_SAMPLES) {
    state.perfTimes.splice(0, state.perfTimes.length - PERF_SAMPLES);
  }
}

function renderPerfLegend(res) {
  refs.perfLegend.replaceChildren();
  const cores = Number(res.cores) || 0;
  for (const lane of PERF_LANES) {
    for (const series of lane.series) {
      const item = el("span", "legend-item");
      const swatch = el("span", "legend-swatch");
      swatch.style.setProperty("--c", series.color);
      item.append(
        swatch,
        el("span", "", series.label),
        el("span", "legend-value", formatMetric(series.key, lastValue(state.perf[series.key]))),
      );
      item.title = cores ? `${series.tip} · 100% = all ${cores} cores busy` : series.tip;
      refs.perfLegend.append(item);
    }
  }
}

function renderPerfChart(res) {
  const svg = refs.perfSvg;
  if (!svg) return;
  const width = Math.max(320, Math.round(svg.clientWidth || 720));
  const height = Math.max(140, Math.round(svg.clientHeight || 206));
  const left = 46;
  const right = 10;
  const top = 8;
  const bottom = 18;
  const plotW = width - left - right;
  const laneH = (height - top - bottom) / 3;
  const stepX = plotW / (PERF_SAMPLES - 1);
  svg.setAttribute("viewBox", `0 0 ${width} ${height}`);
  svg.replaceChildren();

  const mono = "ui-monospace, Menlo, Consolas, monospace";
  const time = (x, text, anchor) => {
    const node = svgNode("text", {
      x,
      y: height - 4,
      "text-anchor": anchor,
      fill: "#6f6b62",
      "font-family": mono,
      "font-size": 8,
    });
    node.textContent = text;
    return node;
  };
  const span = state.perfTimes.length >= 2
    ? Math.max(1, Math.round(state.perfTimes[state.perfTimes.length - 1] - state.perfTimes[0]))
    : PERF_SAMPLES;
  svg.append(time(left, `−${span} s`, "start"));
  svg.append(time(left + plotW / 2, `−${Math.round(span / 2)} s`, "middle"));
  svg.append(time(left + plotW, "now", "end"));

  [0, 0.5, 1].forEach((fraction) => {
    const x = left + plotW * fraction;
    svg.append(
      svgNode("line", {
        x1: x,
        y1: top,
        x2: x,
        y2: height - bottom,
        stroke: "rgba(255,255,255,0.045)",
        "stroke-width": 1,
      }),
    );
  });

  PERF_LANES.forEach((lane, laneIndex) => {
    const laneTop = top + laneIndex * laneH;
    const laneBottom = laneTop + laneH;
    if (laneIndex > 0) {
      svg.append(
        svgNode("line", {
          x1: 0,
          y1: laneTop,
          x2: width,
          y2: laneTop,
          stroke: "rgba(255,255,255,0.10)",
          "stroke-width": 1,
        }),
      );
    }

    const numbers = lane.series.flatMap((series) =>
      state.perf[series.key].filter((value) => Number.isFinite(value)),
    );
    const peak = numbers.length ? Math.max(...numbers) : 0;
    const max = niceCeil(Math.max(peak * 1.15, lane.min));
    const usable = laneH - 12;

    const label = svgNode("text", {
      x: left - 8,
      y: laneTop + 10,
      "text-anchor": "end",
      fill: "#8a857a",
      "font-family": mono,
      "font-size": 7.5,
      "letter-spacing": "0.06em",
    });
    label.textContent = lane.label;
    svg.append(label);

    const cap = svgNode("text", {
      x: width - right,
      y: laneTop + 10,
      "text-anchor": "end",
      fill: "#6f6b62",
      "font-family": mono,
      "font-size": 7,
    });
    cap.textContent = lane.format(max);
    svg.append(cap);

    [0.25, 0.5, 0.75].forEach((fraction) => {
      const y = laneBottom - 4 - fraction * usable;
      svg.append(
        svgNode("line", {
          x1: left,
          y1: y,
          x2: width - right,
          y2: y,
          stroke: "rgba(255,255,255,0.05)",
          "stroke-width": 1,
          "stroke-dasharray": "1 3",
        }),
      );
    });

    for (const series of lane.series) {
      const values = state.perf[series.key];
      let path = "";
      let pen = false;
      values.forEach((value, index) => {
        if (typeof value !== "number" || !Number.isFinite(value)) {
          pen = false;
          return;
        }
        const x = left + index * stepX;
        const y = laneBottom - 4 - Math.min(1, value / max) * usable;
        path += `${pen ? "L" : "M"}${x.toFixed(1)} ${y.toFixed(1)} `;
        pen = true;
      });
      if (!path) continue;
      svg.append(
        svgNode("path", {
          d: path.trim(),
          fill: "none",
          stroke: series.color,
          "stroke-width": 1.7,
          "stroke-linejoin": "round",
          "stroke-linecap": "round",
          "vector-effect": "non-scaling-stroke",
        }),
      );
    }
  });

  if (!res.available) {
    const note = svgNode("text", {
      x: width / 2,
      y: height / 2,
      "text-anchor": "middle",
      fill: "#6f6b62",
      "font-family": mono,
      "font-size": 9,
    });
    note.textContent = "CPU and RAM need /proc (Linux)";
    svg.append(note);
  }
}

function renderPerf(snapshot) {
  const res = snapshot.resources || {};
  pushPerf(res);
  renderPerfLegend(res);
  renderPerfChart(res);

  const bits = [];
  const videoW = typeof res.video_w === "number" ? Math.round(res.video_w) : null;
  const videoH = typeof res.video_h === "number" ? Math.round(res.video_h) : null;
  const captureW = typeof res.capture_w === "number" ? Math.round(res.capture_w) : null;
  const captureH = typeof res.capture_h === "number" ? Math.round(res.capture_h) : null;
  if (videoW && videoH) bits.push(`video ${videoW}×${videoH}`);
  if (captureW && captureH && (captureW !== videoW || captureH !== videoH)) {
    bits.push(`capture ${captureW}×${captureH}`);
  }
  if (typeof res.capture_fps === "number" && res.capture_fps > 0) {
    bits.push(`${res.capture_fps.toFixed(1)} fps`);
  }
  if (typeof res.processes === "number" && res.processes > 0) {
    bits.push(`${res.processes} process${res.processes === 1 ? "" : "es"}`);
  }
  if (typeof res.mpv_pid === "number") bits.push(`mpv pid ${res.mpv_pid}`);
  refs.perfMeta.replaceChildren();
  refs.perfMeta.classList.toggle("hidden", !bits.length);
  for (const bit of bits) refs.perfMeta.append(el("span", "", bit));
  refs.perf.title = res.available
    ? bits.join(" · ")
    : "CPU and RAM need Linux /proc; WiZ UDP still comes from the sync stats";
}

// ---------------------------------------------------------------------- rooms

function renderRooms(snapshot) {
  const groups = snapshot.config.groups || {};
  const lights = snapshot.lights || [];
  const names = Object.keys(groups).sort((a, b) => a.localeCompare(b));
  const signature = JSON.stringify([
    names.map((name) => [name, groups[name]]),
    lights.map((light) => [light.ip, light.state, light.online, light.name]),
    state.roomArmed,
  ]);
  if (signature === state.roomsSignature) return;
  state.roomsSignature = signature;
  refs.roomList.replaceChildren();

  if (!names.length) {
    refs.roomList.append(
      el("span", "room-empty", "No rooms yet — group lights to switch them together."),
    );
    return;
  }

  for (const name of names) {
    const members = lights.filter((light) => groups[name].includes(light.ip));
    const anyOn = members.some((light) => light.state);
    const row = el("div", "room");
    row.classList.toggle("on", anyOn);

    const text = el("button", "room-text");
    text.type = "button";
    text.title = "Target this room in Direct control";
    text.append(
      el("b", "", name),
      el("i", "", `${members.length} ${members.length === 1 ? "light" : "lights"}`),
    );
    text.addEventListener("click", () => {
      if (!state.snapshot) return;
      refs.targetSelect.value = `group:${name}`;
      if (refs.controlCard) {
        refs.controlCard.open = true;
        refs.controlCard.scrollIntoView({ block: "nearest", behavior: "smooth" });
      }
      renderControl(state.snapshot);
      toast(`Direct control: ${name}`);
    });

    const edit = el("button", "room-edit", "✎");
    edit.type = "button";
    edit.title = "Edit this room";
    edit.setAttribute("aria-label", `Edit ${name}`);
    edit.addEventListener("click", () => openRoomEditor(name));

    const remove = el("button", "room-delete", state.roomArmed === name ? "!" : "×");
    remove.type = "button";
    remove.title = state.roomArmed === name ? "Press again to delete" : "Delete this room";
    remove.classList.toggle("armed", state.roomArmed === name);
    remove.addEventListener("click", () => {
      if (state.roomArmed !== name) {
        state.roomArmed = name;
        renderRooms(state.snapshot);
        window.setTimeout(() => {
          if (state.roomArmed === name) {
            state.roomArmed = null;
            renderRooms(state.snapshot);
          }
        }, 3000);
        return;
      }
      state.roomArmed = null;
      action("/api/group", { name, delete: true }, `Deleted room “${name}”`);
    });

    row.append(el("span", "room-dot"), text, edit, remove);
    refs.roomList.append(row);
  }
}

function openRoomEditor(name) {
  const snapshot = state.snapshot;
  if (!snapshot) return;
  const selected = new Set(snapshot.config.groups?.[name] || []);
  refs.roomName.value = name || "";
  refs.roomMembers.replaceChildren();
  for (const light of snapshot.lights) {
    const label = el("label", "room-member");
    const box = document.createElement("input");
    box.type = "checkbox";
    box.value = light.ip;
    box.checked = selected.has(light.ip);
    label.append(box, el("span", "", light.name || light.ip));
    refs.roomMembers.append(label);
  }
  if (!snapshot.lights.length) {
    refs.roomMembers.append(el("span", "room-empty", "No lights known yet."));
  }
  refs.roomEditor.dataset.editing = name || "";
  refs.roomEditor.classList.remove("hidden");
  refs.roomName.focus();
  refs.roomName.select();
}

function closeRoomEditor() {
  refs.roomEditor.dataset.editing = "";
  refs.roomEditor.classList.add("hidden");
}

function saveRoom() {
  const name = refs.roomName.value.trim();
  if (!name) {
    toast("Give the room a name first.", true);
    refs.roomName.focus();
    return;
  }
  const ips = [...refs.roomMembers.querySelectorAll("input[type=checkbox]")]
    .filter((box) => box.checked)
    .map((box) => box.value);
  if (!ips.length) {
    toast("Pick at least one light for this room.", true);
    return;
  }
  const previous = refs.roomEditor.dataset.editing || "";
  action("/api/group", { name, ips, previous }, `Room “${name}” saved`).then((data) => {
    if (data) closeRoomEditor();
  });
}

// --------------------------------------------------------------------- colors

function savedColors(snapshot) {
  const raw = snapshot.config.colors || [];
  return raw
    .map((entry) => {
      if (typeof entry === "string") return { hex: normalizeHex(entry), brightness: 100 };
      if (!entry || typeof entry !== "object") return null;
      const brightness = Number(entry.brightness);
      return {
        hex: normalizeHex(entry.hex),
        brightness: Number.isFinite(brightness)
          ? Math.max(10, Math.min(100, Math.round(brightness)))
          : 100,
      };
    })
    .filter((entry) => entry && entry.hex);
}

function renderColors(snapshot) {
  const colors = savedColors(snapshot);
  refs.colorChips.replaceChildren();
  if (!colors.length) {
    refs.colorChips.append(el("span", "swatch-empty", "No saved colors."));
    return;
  }
  for (const { hex, brightness } of colors) {
    const chip = el("button", "color-chip");
    chip.type = "button";
    chip.style.setProperty("--c", hex);
    chip.title = `${hex} · ${brightness}% — click to apply, Shift+click to remove`;
    chip.setAttribute("aria-label", `Apply ${hex} at ${brightness}%`);
    chip.addEventListener("click", (event) => {
      if (event.shiftKey) {
        action("/api/color", { hex, remove: true }, `Removed ${hex}`);
        return;
      }
      refs.controlColor.value = hex;
      refs.controlHex.value = hex;
      refs.controlBrightness.value = String(brightness);
      refs.controlBrightnessOut.value = String(brightness);
      paintRange(refs.controlBrightness);
      sendControl({ hex, brightness }, `Color ${hex} · ${brightness}%`, chip);
    });
    refs.colorChips.append(chip);
  }
}

function apply(snapshot) {
  state.snapshot = snapshot;
  refs.versionBadge.textContent = `v${snapshot.version}`;
  refs.demoBadge.classList.toggle("hidden", !snapshot.demo);
  refs.configPath.textContent = `Config: ${snapshot.config_display || snapshot.config_path}`;
  refs.configPath.title = snapshot.config_path;
  renderLights(snapshot.lights, snapshot.zones);
  renderSession(snapshot);
  renderSettings(snapshot);
  renderControl(snapshot);
  renderNetwork(snapshot);
  renderCrazy(snapshot);
  renderScenes(snapshot);
  renderLua(snapshot);
  renderLog(snapshot);
  renderRooms(snapshot);
  renderColors(snapshot);
  renderPerf(snapshot);
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

function sendControl(payload, message, button) {
  return action("/api/control", { target: targetIp(), ...payload }, message, button);
}

function applyColor() {
  const value = normalizeHex(refs.controlHex.value);
  if (!value) {
    toast("Use a hex color like #ff8800.", true);
    refs.controlHex.focus();
    return;
  }
  refs.controlColor.value = value;
  refs.controlHex.value = value;
  sendControl({ hex: value }, `Color ${value}`, refs.applyColorBtn);
}

function applyWizScene(message) {
  const scene = Number(refs.sceneSelect.value);
  if (!scene) {
    toast("Pick a WiZ scene first.", true);
    return;
  }
  const speed = Number(refs.controlSpeed.value);
  const label = refs.sceneSelect.selectedOptions[0]?.textContent || `scene ${scene}`;
  sendControl({ scene, speed }, message || `${label} · speed ${speed}`, refs.applySceneBtn);
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
  if (data && !data.warning) {
    const reachable = data.lights.filter((light) => light.online).length;
    toast(`Scan finished · ${reachable} ${reachable === 1 ? "bulb" : "bulbs"} reachable`);
  }
});

refs.enableAllBtn.addEventListener("click", () => setAllEnabled(true));
refs.enableNoneBtn.addEventListener("click", () => setAllEnabled(false));
refs.lightFilter?.addEventListener("input", applyLightFilter);
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
refs.samplingSelect.addEventListener("change", () =>
  saveConfig({ sampling: refs.samplingSelect.value }),
);
refs.samplingFps.addEventListener("input", () => {
  refs.samplingFpsOut.value = refs.samplingFps.value;
});
refs.samplingFps.addEventListener("change", () => {
  const value = Number(refs.samplingFps.value);
  if (value !== state.snapshot?.config.sampling_fps) saveConfig({ sampling_fps: value });
});
refs.samplingGrid.addEventListener("change", () => {
  const value = Math.max(24, Math.min(240, Number(refs.samplingGrid.value) || 80));
  refs.samplingGrid.value = String(value);
  if (value !== state.snapshot?.config.sampling_grid) saveConfig({ sampling_grid: value });
});
refs.samplingBlock.addEventListener("change", () => {
  const value = Number(refs.samplingBlock.value);
  if (value !== state.snapshot?.config.sampling_block) saveConfig({ sampling_block: value });
});
refs.samplingCapture.addEventListener("change", () =>
  saveConfig({ sampling_capture: refs.samplingCapture.value }),
);
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

refs.targetSelect.addEventListener("change", () => {
  if (state.snapshot) renderControl(state.snapshot);
});
refs.powerToggle.addEventListener("change", () => {
  const on = refs.powerToggle.checked;
  sendControl({ power: on }, `${targetName(state.snapshot)} ${on ? "on" : "off"}`);
});
refs.newRoomBtn.addEventListener("click", () => openRoomEditor(""));
refs.roomSaveBtn.addEventListener("click", saveRoom);
refs.roomCancelBtn.addEventListener("click", closeRoomEditor);
refs.roomName.addEventListener("keydown", (event) => {
  if (event.key === "Enter") {
    event.preventDefault();
    saveRoom();
  }
  if (event.key === "Escape") closeRoomEditor();
});
refs.saveColorBtn.addEventListener("click", () => {
  const value = normalizeHex(refs.controlHex.value);
  if (!value) {
    toast("Use a hex color like #ff8800.", true);
    refs.controlHex.focus();
    return;
  }
  const brightness = Number(refs.controlBrightness.value) || 100;
  refs.controlColor.value = value;
  refs.controlHex.value = value;
  action(
    "/api/color",
    { hex: value, brightness },
    `Saved ${value} · ${brightness}%`,
    refs.saveColorBtn,
  );
});

// The chart is hidden while Activity is closed, so it is measured again when
// the card opens or the window changes size instead of waiting for a sample.
refs.logCard.addEventListener("toggle", () => {
  if (refs.logCard.open && state.snapshot) renderPerf(state.snapshot);
});
let perfResize = 0;
window.addEventListener("resize", () => {
  window.cancelAnimationFrame(perfResize);
  perfResize = window.requestAnimationFrame(() => {
    if (state.snapshot) renderPerfChart(state.snapshot.resources || {});
  });
});
let dotClicks = [];
const CRAZY_WINDOW = 3000;

function tapDot() {
  refs.statusDot.classList.remove("tap");
  void refs.statusDot.offsetWidth;
  refs.statusDot.classList.add("tap");
}

function crazyEasterEgg() {
  const now = Date.now();
  dotClicks = dotClicks.filter((stamp) => now - stamp < CRAZY_WINDOW);
  dotClicks.push(now);
  tapDot();
  if (dotClicks.length < 3) return;
  dotClicks = [];
  const active = Boolean(state.snapshot?.crazy?.active);
  const wasRunning = Boolean(state.snapshot?.session?.running);
  const message = active
    ? "Crazy mode stopped"
    : wasRunning
      ? "Crazy for 5 s — Ambilight resumes after"
      : "Crazy for 5 s";
  action("/api/crazy", { target: "all" }, message, refs.statusDot);
}

refs.statusDot.addEventListener("click", crazyEasterEgg);
refs.statusDot.addEventListener("keydown", (event) => {
  if (event.key === "Enter" || event.key === " ") {
    event.preventDefault();
    crazyEasterEgg();
  }
});
refs.controlBrightness.addEventListener("input", () => {
  refs.controlBrightnessOut.value = refs.controlBrightness.value;
});
refs.controlBrightness.addEventListener("change", () => {
  const value = Number(refs.controlBrightness.value);
  sendControl({ brightness: value }, `Brightness ${value}%`);
});
refs.controlTemp.addEventListener("input", () => {
  const value = Number(refs.controlTemp.value);
  refs.controlTempOut.value = `${value} K`;
  const hex = kelvinToHex(value);
  refs.controlHex.value = hex;
  refs.controlColor.value = hex;
});
refs.controlTemp.addEventListener("change", () => {
  const value = Number(refs.controlTemp.value);
  sendControl({ temp: value }, `White ${value} K`);
});
refs.controlColor.addEventListener("input", () => {
  refs.controlHex.value = refs.controlColor.value;
});
refs.controlHex.addEventListener("input", () => {
  const value = normalizeHex(refs.controlHex.value);
  if (value) refs.controlColor.value = value;
});
refs.controlHex.addEventListener("keydown", (event) => {
  if (event.key === "Enter") {
    event.preventDefault();
    applyColor();
  }
});
refs.applyColorBtn.addEventListener("click", applyColor);
refs.applySceneBtn.addEventListener("click", () => applyWizScene());
refs.controlSpeed.addEventListener("input", () => {
  refs.controlSpeedOut.value = refs.controlSpeed.value;
});
refs.controlSpeed.addEventListener("change", () => {
  if (refs.sceneSelect.options.length) applyWizScene(`Scene speed ${refs.controlSpeed.value}`);
});
refs.saveSceneBtn.addEventListener("click", async () => {
  const name = refs.sceneName.value.trim();
  if (!name) {
    toast("Give the scene a name first.", true);
    refs.sceneName.focus();
    return;
  }
  const data = await action("/api/scene/save", { name }, `Saved “${name}”`, refs.saveSceneBtn);
  if (data) refs.sceneName.value = "";
});
refs.sceneName.addEventListener("keydown", (event) => {
  if (event.key === "Enter") {
    event.preventDefault();
    refs.saveSceneBtn.click();
  }
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
  const sliders = [
    refs.brightness,
    refs.controlBrightness,
    refs.controlTemp,
    refs.controlSpeed,
    refs.samplingFps,
  ];
  for (const input of sliders) {
    paintRange(input);
    input.addEventListener("input", () => paintRange(input));
  }
  await refresh();
  state.poll = window.setInterval(() => {
    if (!document.hidden && !state.closed) refresh();
  }, 1200);
}

boot();
