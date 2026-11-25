"use strict";

const el = (tag, className, text) => {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
};

/* Sliders paint their own filled track through the --fill custom property.
   Knob inputs are invisible, so they expose the same ratio as --turn on the
   round dial instead. `max="0"` is a real bound, so it must not fall through
   a truthiness default. */
const rangeBounds = (input) => {
  const min = input.min === "" ? 0 : Number(input.min);
  const max = input.max === "" ? 100 : Number(input.max);
  return {
    min: Number.isFinite(min) ? min : 0,
    max: Number.isFinite(max) ? max : 100,
  };
};

const paintRange = (input) => {
  const { min, max } = rangeBounds(input);
  const value = Number(input.value) || 0;
  const ratio = max > min ? (value - min) / (max - min) : 0;
  input.style.setProperty("--fill", `${Math.round(ratio * 100)}%`);
  const knob = input.closest?.(".knob");
  if (knob) {
    /* The threshold knob's dial shares the wider −60…0 side-chain ring with
       the live-input dot, so its amber arc and gate tick stay aligned even
       though the threshold itself stops at −36 dB. */
    const scaleMin = Number(knob.dataset.scaleMin);
    const turnMin = Number.isFinite(scaleMin) ? scaleMin : min;
    const turn = max > turnMin ? (value - turnMin) / (max - turnMin) : 0;
    knob.style.setProperty("--turn", String(Math.max(0, Math.min(1, turn))));
  }
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
  reactSelect: document.getElementById("reactSelect"),
  reactHint: document.getElementById("reactHint"),
  reactAmount: document.getElementById("reactAmount"),
  reactAmountOut: document.getElementById("reactAmountOut"),
  reactProfile: document.getElementById("reactProfile"),
  reactProfileField: document.getElementById("reactProfileField"),
  reactProfileHint: document.getElementById("reactProfileHint"),
  reactDynamics: document.getElementById("reactDynamics"),
  reactDynamicsHint: document.getElementById("reactDynamicsHint"),
  reactThreshold: document.getElementById("reactThreshold"),
  reactThresholdOut: document.getElementById("reactThresholdOut"),
  reactAttack: document.getElementById("reactAttack"),
  reactAttackOut: document.getElementById("reactAttackOut"),
  reactRelease: document.getElementById("reactRelease"),
  reactReleaseOut: document.getElementById("reactReleaseOut"),
  reactPunch: document.getElementById("reactPunch"),
  reactPunchOut: document.getElementById("reactPunchOut"),
  thresholdKnob: document.getElementById("thresholdKnob"),
  dynamicsPanel: document.getElementById("dynamicsPanel"),
  vuMeter: document.getElementById("vuMeter"),
  vuDbOut: document.getElementById("vuDbOut"),
  vuOverOut: document.getElementById("vuOverOut"),
  reactTarget: document.getElementById("reactTarget"),
  reactTargetField: document.getElementById("reactTargetField"),
  reactTargetOut: document.getElementById("reactTargetOut"),
  autoLux: document.getElementById("autoLux"),
  autoLuxHint: document.getElementById("autoLuxHint"),
  luxField: document.getElementById("luxField"),
  luxTarget: document.getElementById("luxTarget"),
  luxTargetOut: document.getElementById("luxTargetOut"),
  luxReadout: document.getElementById("luxReadout"),
  reactBands: document.getElementById("reactBands"),
  reactBandsField: document.getElementById("reactBandsField"),
  reactColorMode: document.getElementById("reactColorMode"),
  reactColorPair: document.getElementById("reactColorPair"),
  reactColorA: document.getElementById("reactColorA"),
  reactColorB: document.getElementById("reactColorB"),
  reactColorASlot: document.getElementById("reactColorASlot"),
  reactColorBSlot: document.getElementById("reactColorBSlot"),
  reactColorALabel: document.getElementById("reactColorALabel"),
  reactColorBLabel: document.getElementById("reactColorBLabel"),
  reactColorHint: document.getElementById("reactColorHint"),
  eqPanel: document.getElementById("eqPanel"),
  eqBandCount: document.getElementById("eqBandCount"),
  eqSummary: document.getElementById("eqSummary"),
  eqCanvas: document.getElementById("eqCanvas"),
  eqFaders: document.getElementById("eqFaders"),
  eqDetail: document.getElementById("eqDetail"),
  eqDetailTitle: document.getElementById("eqDetailTitle"),
  eqType: document.getElementById("eqType"),
  eqSlopeField: document.getElementById("eqSlopeField"),
  eqSlope: document.getElementById("eqSlope"),
  eqSlopeOut: document.getElementById("eqSlopeOut"),
  eqSolo: document.getElementById("eqSolo"),
  eqFreq: document.getElementById("eqFreq"),
  eqFreqOut: document.getElementById("eqFreqOut"),
  eqQ: document.getElementById("eqQ"),
  eqQOut: document.getElementById("eqQOut"),
  eqQField: document.getElementById("eqQField"),
  eqGain: document.getElementById("eqGain"),
  eqGainOut: document.getElementById("eqGainOut"),
  eqLamp: document.getElementById("eqLamp"),
  reactAuto: document.getElementById("reactAuto"),
  reactActiveBands: document.getElementById("reactActiveBands"),
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
  vibrance: document.getElementById("vibrance"),
  vibranceOut: document.getElementById("vibranceOut"),
  whiteLeds: document.getElementById("whiteLeds"),
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
  eq: {
    bands: [],
    lamps: [],
    limits: null,
    selected: 0,
    signature: "",
    dragging: null,
  },
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

  const forget = el("button", "icon-btn forget", "×");
  forget.type = "button";
  forget.title = "Forget this light";
  forget.setAttribute("aria-label", "Forget light");
  let forgetArmed = false;
  let forgetTimer = null;
  const disarmForget = () => {
    forgetArmed = false;
    forget.textContent = "×";
    forget.classList.remove("armed");
    forget.title = "Forget this light";
    if (forgetTimer) {
      window.clearTimeout(forgetTimer);
      forgetTimer = null;
    }
  };
  forget.addEventListener("click", () => {
    if (!forgetArmed) {
      forgetArmed = true;
      forget.textContent = "!";
      forget.classList.add("armed");
      forget.title = "Press again to forget this light";
      forgetTimer = window.setTimeout(disarmForget, 3000);
      return;
    }
    const label = card.light?.name || card.light?.ip || "light";
    disarmForget();
    action(
      "/api/light/delete",
      { ip: light.ip },
      `Forgot ${label}. A scan can add a reachable bulb back.`,
      forget,
    );
  });

  const toggle = el("label", "switch");
  toggle.title = "Include this light in ambilight";
  const toggleInput = document.createElement("input");
  toggleInput.type = "checkbox";
  toggleInput.setAttribute("aria-label", "Include light");
  toggle.append(toggleInput, el("span"));

  controls.append(zonePick, identify, toggle, forget);
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
    forget,
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
  card.forget.setAttribute("aria-label", `Forget ${light.name || light.ip}`);
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

/* The reaction list arrives from the core so the panel and the CLI can never
   disagree about the modes. Video and audio stay in separate optgroups: the
   same control says how the lights react and what they react to. */
function fillReactionSelect(snapshot) {
  const reactions = snapshot.reactions || [];
  const groups = snapshot.reaction_groups || [];
  const signature = JSON.stringify([
    reactions.map((reaction) => [
      reaction.id,
      reaction.label,
      reaction.group,
      reaction.hint,
      reaction.detail,
      reaction.audio,
      reaction.profiles?.map((profile) => [
        profile.id,
        profile.label,
        profile.hint,
      ]),
    ]),
    groups.map((group) => [group.id, group.label]),
  ]);
  if (refs.reactSelect.dataset.signature === signature) return;
  refs.reactSelect.replaceChildren();
  for (const group of groups) {
    const members = reactions.filter((reaction) => reaction.group === group.id);
    if (!members.length) continue;
    const optgroup = el("optgroup");
    optgroup.label = group.label;
    for (const reaction of members) {
      const option = el("option", "", reaction.label);
      option.value = reaction.id;
      option.title = reaction.hint || "";
      optgroup.append(option);
    }
    refs.reactSelect.append(optgroup);
  }
  refs.reactSelect.dataset.signature = signature;
  refs.reactSelect.dataset.hints = JSON.stringify(
    Object.fromEntries(
      reactions.map((reaction) => [reaction.id, reaction.hint || ""]),
    ),
  );
  refs.reactSelect.dataset.details = JSON.stringify(
    Object.fromEntries(
      reactions.map((reaction) => [
        reaction.id,
        reaction.detail || reaction.hint || "",
      ]),
    ),
  );
}

function reactionById(snapshot, id) {
  return (snapshot?.reactions || []).find((reaction) => reaction.id === id) || null;
}

function renderReactionHint(reaction) {
  let details = {};
  try {
    details = JSON.parse(refs.reactSelect.dataset.details || "{}");
  } catch {
    details = {};
  }
  refs.reactHint.textContent = details[reaction] || "";
  refs.reactHint.title =
    "Reactions scale with the strength slider and the style; audio modes " +
    "add a dynamic EQ analyser only while selected";
}

function fillProfileSelect(reaction) {
  const profiles = reaction?.profiles || [];
  refs.reactProfileField.classList.toggle("hidden", profiles.length === 0);
  if (!profiles.length) return;
  const signature = JSON.stringify(
    profiles.map((profile) => [profile.id, profile.label, profile.hint]),
  );
  if (refs.reactProfile.dataset.signature !== signature) {
    refs.reactProfile.replaceChildren();
    for (const profile of profiles) {
      const option = el("option", "", profile.label);
      option.value = profile.id;
      option.title = profile.hint || "";
      refs.reactProfile.append(option);
    }
    refs.reactProfile.dataset.signature = signature;
    refs.reactProfile.dataset.hints = JSON.stringify(
      Object.fromEntries(
        profiles.map((profile) => [profile.id, profile.hint || ""]),
      ),
    );
  }
}

function renderProfileHint() {
  let hints = {};
  try {
    hints = JSON.parse(refs.reactProfile.dataset.hints || "{}");
  } catch {
    hints = {};
  }
  refs.reactProfileHint.textContent = hints[refs.reactProfile.value] || "";
}

function fillDynamicsSelect(snapshot) {
  const presets = snapshot.dynamics || [];
  const signature = JSON.stringify(
    presets.map((preset) => [
      preset.id,
      preset.label,
      preset.hint,
      preset.threshold,
      preset.attack,
      preset.release,
      preset.punch,
    ]),
  );
  if (refs.reactDynamics.dataset.signature === signature) return;
  refs.reactDynamics.replaceChildren();
  for (const preset of presets) {
    const option = el("option", "", preset.label);
    option.value = preset.id;
    option.title = preset.hint || "";
    refs.reactDynamics.append(option);
  }
  const custom = el("option", "", "Custom");
  custom.value = "custom";
  refs.reactDynamics.append(custom);
  refs.reactDynamics.dataset.signature = signature;
  refs.reactDynamics.dataset.hints = JSON.stringify(
    Object.fromEntries(presets.map((preset) => [preset.id, preset.hint || ""])),
  );
  refs.reactDynamics.dataset.presets = JSON.stringify(
    Object.fromEntries(
      presets.map((preset) => [
        preset.id,
        {
          threshold: preset.threshold,
          attack: preset.attack,
          release: preset.release,
          punch: preset.punch,
        },
      ]),
    ),
  );
}

function renderDynamicsHint() {
  let hints = {};
  try {
    hints = JSON.parse(refs.reactDynamics.dataset.hints || "{}");
  } catch {
    hints = {};
  }
  refs.reactDynamicsHint.textContent =
    refs.reactDynamics.value === "custom"
      ? "Your own four values; pick a preset for a starting point."
      : hints[refs.reactDynamics.value] ||
        "A starting point for the four knobs; adjust any of them freely.";
}

function setRangeOutput(input, output, value, label) {
  if (document.activeElement !== input) {
    input.value = String(value);
    paintRange(input);
  }
  output.value = label(value);
}

function matchingDynamics(config) {
  let presets = {};
  try {
    presets = JSON.parse(refs.reactDynamics.dataset.presets || "{}");
  } catch {
    presets = {};
  }
  const values = {
    threshold: Number(config.react_threshold),
    attack: Number(config.react_attack),
    release: Number(config.react_release),
    punch: Number(config.react_punch),
  };
  for (const [id, preset] of Object.entries(presets)) {
    const close = Object.keys(values).every(
      (key) => Math.abs(values[key] - Number(preset[key])) < 0.51,
    );
    if (close) return id;
  }
  return "custom";
}

function syncDynamicsFields(snapshot, config, reaction) {
  const audio = Boolean(reaction?.audio);
  refs.dynamicsPanel.classList.toggle("hidden", !audio);
  // Audio modes use the dynamics preset; video modes keep the profile.
  refs.reactProfileField.classList.toggle(
    "hidden",
    audio || !(reaction?.profiles || []).length,
  );
  if (!audio) {
    stopMeter();
    return;
  }
  fillDynamicsSelect(snapshot);
  if (document.activeElement !== refs.reactDynamics) {
    refs.reactDynamics.value = matchingDynamics(config);
  }
  renderDynamicsHint();
  const threshold = Number(config.react_threshold);
  const attack = Number(config.react_attack);
  const release = Number(config.react_release);
  const punch = Number(config.react_punch);
  setRangeOutput(
    refs.reactThreshold,
    refs.reactThresholdOut,
    Number.isFinite(threshold) ? threshold : -18,
    (value) => `${Math.round(value)} dB`,
  );
  setRangeOutput(
    refs.reactAttack,
    refs.reactAttackOut,
    Number.isFinite(attack) ? attack : 1,
    (value) => `${Math.round(value)} ms`,
  );
  setRangeOutput(
    refs.reactRelease,
    refs.reactReleaseOut,
    Number.isFinite(release) ? release : 55,
    (value) => `${Math.round(value)} ms`,
  );
  setRangeOutput(
    refs.reactPunch,
    refs.reactPunchOut,
    Math.round((Number.isFinite(punch) ? punch : 3) * 100),
    (value) => `${(value / 100).toFixed(1)}×`,
  );
  startMeter();
}

/* The timeline matches the Pro-C 2 style: a −36 dBFS floor, an amber input
   trace, and a red area that hangs from the top for the light drive. The
   threshold knob's ring uses the plugin's wider −60…0 dB side-chain scale. */
const SCOPE_MIN_DB = -36;
const SCOPE_MAX_DB = 0;
const KNOB_MIN_DB = -60;
const SCOPE_WINDOW_MS = 5000;
const SCOPE_POLL_MS = 40;
const SCOPE_COLORS = {
  amber: "#fcbe11",
  drive: "#ff6b5e",
  grid: "#1c1c1c",
  time: "rgba(255, 255, 255, .035)",
  label: "#6f6b62",
};

const vu = {
  timer: null,
  busy: false,
  history: [],
  lastDb: null,
  ceiling: -6,
  window: 12,
  plot: null,
  dragging: false,
};

function thresholdValue() {
  const value = Number(refs.reactThreshold?.value);
  return Number.isFinite(value) ? value : -18;
}

function punchValue() {
  const value = Number(refs.reactPunch?.value) / 100;
  return Number.isFinite(value) && value >= 1 ? value : 3;
}

function ceilingValue() {
  const value = Number(vu.ceiling);
  return Number.isFinite(value) ? value : -6;
}

function windowValue() {
  const value = Number(vu.window);
  return Number.isFinite(value) && value > 0 ? value : 12;
}

/* Mirrors pulse_level() in mpv_ambilight.py: gate at the threshold, full
   brightness once the level reaches the profile ceiling, with a minimum
   window so a high threshold keeps a usable range. Punch then raises the
   middle of that window. The result is the bulb brightness the song asks
   for. */
function activationLevel(db, threshold = thresholdValue()) {
  if (db === null || !Number.isFinite(db)) return 0;
  const low = threshold;
  const high = Math.max(low + windowValue(), ceilingValue());
  const raw = (db - low) / (high - low);
  const clamped = Math.max(0, Math.min(1, raw));
  return clamped ** (1 / Math.max(1, punchValue()));
}

function dbToY(db, top, height) {
  const clamped = Math.max(SCOPE_MIN_DB, Math.min(SCOPE_MAX_DB, db));
  return top + ((SCOPE_MAX_DB - clamped) / -SCOPE_MIN_DB) * height;
}

function meterDb() {
  const value = Number(vu.lastDb);
  return Number.isFinite(value) ? value : null;
}

function renderLightReadout(db, threshold) {
  const output = refs.vuOverOut;
  if (!output) return;
  const percent = Math.round(activationLevel(db, threshold) * 100);
  output.textContent = `LIGHT ${percent}%`;
  output.classList.toggle("over", percent > 0);
}

/* The threshold knob carries the live input on an outer ring, red once the
   input is above the gate, the way Pro-C 2 tracks its side-chain level. The
   ring spans −60…0 dB, so the dot walks toward 0 as the song gets louder;
   the amber tick marks the threshold on the same scale. */
function updateThresholdRing(db, threshold) {
  const knob = refs.thresholdKnob;
  if (!knob) return;
  const value = Number.isFinite(db) ? db : KNOB_MIN_DB;
  const ratio = Math.max(
    0,
    Math.min(1, (value - KNOB_MIN_DB) / (SCOPE_MAX_DB - KNOB_MIN_DB)),
  );
  knob.style.setProperty("--level", ratio.toFixed(4));
  knob.classList.toggle("hot", db !== null && Number.isFinite(db) && db > threshold);
}

function sizeScope(canvas) {
  const rect = canvas.getBoundingClientRect();
  const width = Math.max(1, Math.round(rect.width));
  const height = Math.max(1, Math.round(rect.height));
  const dpr = Math.min(window.devicePixelRatio || 1, 2);
  const pixelWidth = Math.round(width * dpr);
  const pixelHeight = Math.round(height * dpr);
  if (canvas.width !== pixelWidth || canvas.height !== pixelHeight) {
    canvas.width = pixelWidth;
    canvas.height = pixelHeight;
  }
  const ctx = canvas.getContext("2d");
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  ctx.clearRect(0, 0, width, height);
  return { ctx, width, height };
}

function drawTimeline(db = meterDb()) {
  const canvas = refs.vuMeter;
  if (!canvas || !canvas.getContext) return;
  const { ctx, width, height } = sizeScope(canvas);
  if (width < 40 || height < 40) return;

  const left = width < 340 ? 26 : 30;
  const right = width - 8;
  const top = 1;
  const bottom = height - 15;
  const plotWidth = Math.max(1, right - left);
  const plotHeight = Math.max(1, bottom - top);
  const threshold = thresholdValue();
  const now = performance.now();

  ctx.fillStyle = "#090909";
  ctx.fillRect(0, 0, width, height);
  ctx.textBaseline = "middle";
  ctx.font = "8.5px ui-monospace, Menlo, Consolas, monospace";

  // dBFS grid: 6 dB steps across the −36…0 window, like a compressor meter.
  ctx.textAlign = "right";
  for (const mark of [0, -6, -12, -18, -24, -30, -36]) {
    const y = dbToY(mark, top, plotHeight);
    ctx.strokeStyle = SCOPE_COLORS.grid;
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.moveTo(left, y + 0.5);
    ctx.lineTo(right, y + 0.5);
    ctx.stroke();
    ctx.fillStyle = mark === 0 ? "#8a857b" : SCOPE_COLORS.label;
    ctx.fillText(String(mark), left - 5, Math.max(5, y));
  }

  // Time grid: one line per second across the five-second window.
  ctx.textAlign = "center";
  for (let second = 1; second <= 4; second += 1) {
    const x = right - (second * 1000 * plotWidth) / SCOPE_WINDOW_MS;
    ctx.strokeStyle = SCOPE_COLORS.time;
    ctx.beginPath();
    ctx.moveTo(x + 0.5, top);
    ctx.lineTo(x + 0.5, bottom);
    ctx.stroke();
    ctx.fillStyle = SCOPE_COLORS.label;
    ctx.fillText(`−${second}s`, x, bottom + 8);
  }
  ctx.fillStyle = SCOPE_COLORS.label;
  ctx.textAlign = "right";
  ctx.fillText("now", right, bottom + 8);

  const points = vu.history.filter((point) => now - point.t <= SCOPE_WINDOW_MS);
  ctx.save();
  ctx.beginPath();
  ctx.rect(left, top, plotWidth, plotHeight);
  ctx.clip();

  if (points.length >= 2) {
    const xFor = (point) =>
      right - Math.min(1, (now - point.t) / SCOPE_WINDOW_MS) * plotWidth;

    // Soft body under the input trace so level reads at a glance.
    ctx.beginPath();
    ctx.moveTo(xFor(points[0]), bottom);
    for (const point of points) {
      ctx.lineTo(xFor(point), dbToY(point.db, top, plotHeight));
    }
    ctx.lineTo(xFor(points[points.length - 1]), bottom);
    ctx.closePath();
    const fill = ctx.createLinearGradient(0, top, 0, bottom);
    fill.addColorStop(0, "rgba(252, 190, 17, .20)");
    fill.addColorStop(1, "rgba(252, 190, 17, .02)");
    ctx.fillStyle = fill;
    ctx.fill();

    // Red light drive, inverted from the top: the curtain is attached to the
    // top border and hangs down by the drive amount, so its depth is the
    // brightness percentage the bulbs receive, not another level.
    ctx.beginPath();
    ctx.moveTo(xFor(points[0]), top);
    for (const point of points) {
      const drive = activationLevel(point.db, threshold);
      ctx.lineTo(xFor(point), top + drive * plotHeight);
    }
    ctx.lineTo(xFor(points[points.length - 1]), top);
    ctx.closePath();
    const driveFill = ctx.createLinearGradient(0, top, 0, bottom);
    driveFill.addColorStop(0, "rgba(255, 107, 94, .42)");
    driveFill.addColorStop(0.5, "rgba(255, 107, 94, .22)");
    driveFill.addColorStop(1, "rgba(255, 107, 94, .06)");
    ctx.fillStyle = driveFill;
    ctx.fill();

    // A solid hairline on the top border makes the attachment explicit: the
    // red area is a curtain hanging from the top, never a floating trace.
    ctx.strokeStyle = "rgba(255, 107, 94, .55)";
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.moveTo(left, top + 0.5);
    ctx.lineTo(right, top + 0.5);
    ctx.stroke();

    // Redraw the amber input on top so red stays the drive, never the level.
    ctx.lineJoin = "round";
    ctx.lineWidth = 1.5;
    ctx.strokeStyle = SCOPE_COLORS.amber;
    ctx.beginPath();
    for (let index = 0; index < points.length; index += 1) {
      const point = points[index];
      const x = xFor(point);
      const y = dbToY(point.db, top, plotHeight);
      if (index === 0) ctx.moveTo(x, y);
      else ctx.lineTo(x, y);
    }
    ctx.stroke();

    // A crisp edge on the drive curtain so the percentage is easy to read.
    ctx.strokeStyle = "rgba(255, 107, 94, .95)";
    ctx.lineWidth = 1.4;
    ctx.beginPath();
    for (let index = 0; index < points.length; index += 1) {
      const point = points[index];
      const x = xFor(point);
      const y = top + activationLevel(point.db, threshold) * plotHeight;
      if (index === 0) ctx.moveTo(x, y);
      else ctx.lineTo(x, y);
    }
    ctx.stroke();
  }
  ctx.restore();

  // The live edge: an amber dot on the input plus a red tick on the drive.
  const fresh = points.length && now - points[points.length - 1].t < 400;
  if (fresh) {
    const level = points[points.length - 1].db;
    const x = right;
    const y = dbToY(level, top, plotHeight);
    ctx.fillStyle = SCOPE_COLORS.amber;
    ctx.beginPath();
    ctx.arc(x, y, 2.6, 0, 2 * Math.PI);
    ctx.fill();
    ctx.strokeStyle = "rgba(252, 190, 17, .3)";
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.arc(x, y, 5.5, 0, 2 * Math.PI);
    ctx.stroke();

    const driveY = top + activationLevel(level, threshold) * plotHeight;
    ctx.strokeStyle = "rgba(255, 107, 94, .5)";
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.moveTo(right - 0.5, top);
    ctx.lineTo(right - 0.5, driveY);
    ctx.stroke();
    ctx.strokeStyle = SCOPE_COLORS.drive;
    ctx.lineWidth = 1.6;
    ctx.beginPath();
    ctx.moveTo(right - 10, driveY + 0.5);
    ctx.lineTo(right, driveY + 0.5);
    ctx.stroke();
  } else {
    ctx.fillStyle = SCOPE_COLORS.label;
    ctx.font = "10px ui-monospace, Menlo, Consolas, monospace";
    ctx.textAlign = "center";
    ctx.fillText("waiting for audio", left + plotWidth / 2, top + plotHeight / 2);
  }

  // Draggable threshold line and handle.
  const thresholdY = dbToY(threshold, top, plotHeight);
  ctx.strokeStyle = "rgba(252, 190, 17, .92)";
  ctx.lineWidth = 1.2;
  ctx.setLineDash([5, 3]);
  ctx.beginPath();
  ctx.moveTo(left, thresholdY + 0.5);
  ctx.lineTo(right, thresholdY + 0.5);
  ctx.stroke();
  ctx.setLineDash([]);

  ctx.fillStyle = SCOPE_COLORS.amber;
  ctx.beginPath();
  ctx.moveTo(right - 7, thresholdY - 5);
  ctx.lineTo(right, thresholdY);
  ctx.lineTo(right - 7, thresholdY + 5);
  ctx.closePath();
  ctx.fill();

  const label = `${Math.round(threshold)} dB`;
  ctx.font = "9px ui-monospace, Menlo, Consolas, monospace";
  const labelWidth = ctx.measureText(label).width;
  const labelY = Math.max(top + 9, Math.min(bottom - 2, thresholdY - 5));
  ctx.fillStyle = "rgba(8, 8, 8, .88)";
  ctx.fillRect(right - labelWidth - 11, labelY - 10, labelWidth + 6, 11);
  ctx.fillStyle = SCOPE_COLORS.amber;
  ctx.textAlign = "right";
  ctx.textBaseline = "middle";
  ctx.fillText(label, right - 8, labelY - 4);

  vu.plot = { left, right, top, bottom, plotHeight };
  renderLightReadout(db, threshold);
  updateThresholdRing(db, threshold);
}

function capturePointer(node, pointerId) {
  try {
    node.setPointerCapture?.(pointerId);
  } catch {
    // Synthetic or already-released pointers can still drive the math.
  }
}

function releasePointer(node, pointerId) {
  try {
    if (node.hasPointerCapture?.(pointerId)) node.releasePointerCapture(pointerId);
  } catch {
    // The pointer may already be gone; dragging state is what matters.
  }
}

function thresholdFromPointer(event) {
  if (!vu.plot) return;
  const rect = refs.vuMeter.getBoundingClientRect();
  const y = Math.max(
    vu.plot.top,
    Math.min(vu.plot.bottom, event.clientY - rect.top),
  );
  const ratio = (y - vu.plot.top) / vu.plot.plotHeight;
  const value = SCOPE_MAX_DB + ratio * SCOPE_MIN_DB;
  const bounds = rangeBounds(refs.reactThreshold);
  const min = Math.max(SCOPE_MIN_DB, bounds.min);
  const max = Math.min(SCOPE_MAX_DB, bounds.max);
  const step = Number(refs.reactThreshold.step) || 1;
  const raw = Math.max(min, Math.min(max, value));
  const snapped = Math.round(raw / step) * step;
  refs.reactThreshold.value = String(snapped);
  refs.reactThreshold.dispatchEvent(new Event("input", { bubbles: true }));
  drawTimeline();
}

function endThresholdDrag(event) {
  if (!vu.dragging) return;
  vu.dragging = false;
  refs.vuMeter.classList.remove("dragging");
  releasePointer(refs.vuMeter, event.pointerId);
  refs.reactThreshold.dispatchEvent(new Event("change", { bubbles: true }));
}

function bindScope() {
  const canvas = refs.vuMeter;
  if (!canvas) return;
  canvas.addEventListener("pointerdown", (event) => {
    if (event.button !== undefined && event.button !== 0) return;
    if (!vu.plot) return;
    refs.reactThreshold.focus({ preventScroll: true });
    vu.dragging = true;
    canvas.classList.add("dragging");
    capturePointer(canvas, event.pointerId);
    thresholdFromPointer(event);
    event.preventDefault();
  });
  canvas.addEventListener("pointermove", (event) => {
    if (!vu.dragging) return;
    thresholdFromPointer(event);
    event.preventDefault();
  });
  canvas.addEventListener("pointerup", endThresholdDrag);
  canvas.addEventListener("pointercancel", endThresholdDrag);
}

function bindKnobs() {
  document.querySelectorAll(".knob").forEach((knob) => {
    const input = knob.querySelector(".knob-input");
    if (!input) return;
    let drag = null;

    knob.addEventListener("pointerdown", (event) => {
      if (event.button !== undefined && event.button !== 0) return;
      const start = Number(input.value) || 0;
      drag = { y: event.clientY, value: start, pointerId: event.pointerId };
      input.focus({ preventScroll: true });
      knob.classList.add("dragging");
      capturePointer(knob, event.pointerId);
      event.preventDefault();
    });

    knob.addEventListener("pointermove", (event) => {
      if (!drag) return;
      const { min, max } = rangeBounds(input);
      const step = Number(input.step) || 1;
      const fine = event.shiftKey ? 0.2 : 1;
      const delta = ((drag.y - event.clientY) / 150) * (max - min) * fine;
      const raw = Math.max(min, Math.min(max, drag.value + delta));
      const snapped = Math.round((raw - min) / step) * step + min;
      if (Number(input.value) !== snapped) {
        input.value = String(Number(snapped.toFixed(4)));
        input.dispatchEvent(new Event("input", { bubbles: true }));
      }
      event.preventDefault();
    });

    const end = (event) => {
      if (!drag) return;
      drag = null;
      knob.classList.remove("dragging");
      releasePointer(knob, event.pointerId);
      input.dispatchEvent(new Event("change", { bubbles: true }));
    };
    knob.addEventListener("pointerup", end);
    knob.addEventListener("pointercancel", end);
  });
}

async function pollMeter() {
  if (state.closed || document.hidden || vu.busy) return;
  vu.busy = true;
  try {
    const response = await fetch("/api/meter", { cache: "no-store" });
    if (!response.ok) return;
    const data = await response.json();
    const ceiling = Number(data.ceiling);
    if (Number.isFinite(ceiling)) vu.ceiling = ceiling;
    const windowSize = Number(data.window);
    if (Number.isFinite(windowSize) && windowSize > 0) vu.window = windowSize;
    const rawDb = data.db;
    const numericDb = rawDb === null || rawDb === undefined ? NaN : Number(rawDb);
    const db = Number.isFinite(numericDb) ? numericDb : null;
    vu.lastDb = db;
    if (db !== null) {
      const now = performance.now();
      vu.history.push({ t: now, db });
      while (vu.history.length && vu.history[0].t < now - SCOPE_WINDOW_MS - 1000) {
        vu.history.shift();
      }
    }
    drawTimeline(db);
    refs.vuDbOut.value = db === null ? "−∞ dB" : `${db.toFixed(1)} dB`;
  } catch {
    // The next tick retries; a closed or sleeping player is not an error.
  } finally {
    vu.busy = false;
  }
}

function startMeter() {
  if (vu.timer) return;
  drawTimeline(null);
  vu.timer = window.setInterval(pollMeter, SCOPE_POLL_MS);
  pollMeter();
}

function stopMeter() {
  if (vu.timer) {
    window.clearInterval(vu.timer);
    vu.timer = null;
  }
  vu.history = [];
  vu.lastDb = null;
  vu.ceiling = -6;
  vu.window = 12;
  drawTimeline(null);
  refs.vuDbOut.value = "−∞ dB";
  updateThresholdRing(null, thresholdValue());
}

function buildBandInputs(snapshot) {
  const bands = snapshot.bands || [];
  const signature = JSON.stringify(bands.map((band) => [band.id, band.label]));
  if (refs.reactBands.dataset.signature === signature) return;
  refs.reactBands.replaceChildren();
  // Eight swatches fit the Look column; wider EQ layouts wrap onto a second
  // row instead of shrinking each swatch into a sliver.
  const columns = Math.max(1, Math.min(8, bands.length));
  refs.reactBands.style.gridTemplateColumns = `repeat(${columns}, minmax(0, 1fr))`;
  for (const band of bands) {
    const label = el("label", "band-color");
    const input = document.createElement("input");
    input.type = "color";
    input.value = band.color;
    input.dataset.band = band.id;
    input.setAttribute("aria-label", `${band.label} band color`);
    label.append(input, el("span", "", band.label));
    refs.reactBands.append(label);
  }
  refs.reactBands.dataset.signature = signature;
}

function eqShortFreq(value) {
  const freq = Number(value) || 0;
  if (freq >= 1000) {
    return `${(freq / 1000).toFixed(1).replace(/\.0$/, "")}k`;
  }
  return String(Math.round(freq));
}

function eqLogToFreq(value) {
  const ratio = Math.log(20000 / 20);
  return 20 * Math.exp(ratio * (Number(value) / 1000));
}

function eqFreqToLog(freq) {
  const ratio = Math.log(20000 / 20);
  return (Math.log(Math.max(20, Math.min(20000, Number(freq) || 1000)) / 20) / ratio) * 1000;
}

function eqClone(bands) {
  return (bands || []).map((band) => ({ ...band }));
}

function eqDefaultFreqs(count) {
  const total = Math.max(2, Math.min(16, Number(count) || 8));
  const ratio = (16000 / 32) ** (1 / (total - 1));
  return Array.from({ length: total }, (_, index) => 32 * ratio ** index);
}

function eqRemapBands(bands, count) {
  const freqs = eqDefaultFreqs(count);
  const source = bands || [];
  return freqs.map((freq) => {
    let best = null;
    let bestDistance = Infinity;
    for (const band of source) {
      const distance = Math.abs(Math.log2(Number(band.freq) / freq));
      if (distance < bestDistance) {
        bestDistance = distance;
        best = band;
      }
    }
    return {
      freq: Math.round(freq * 100) / 100,
      type: best?.type || "bell",
      gain: best ? Number(best.gain) || 0 : 0,
      q: best ? Number(best.q) || 1.4 : 1.4,
      slope: best ? Number(best.slope) || 24 : 24,
      lamp: best ? Number(best.lamp ?? -1) : -1,
      solo: Boolean(best?.solo),
    };
  });
}

function buildEqCount(snapshot) {
  const limits = snapshot.eq_limits || { min: 2, max: 16 };
  const signature = `${limits.min}:${limits.max}`;
  if (refs.eqBandCount.dataset.signature === signature) return;
  refs.eqBandCount.replaceChildren();
  for (let count = limits.min; count <= limits.max; count += 1) {
    const option = document.createElement("option");
    option.value = String(count);
    option.textContent = String(count);
    refs.eqBandCount.append(option);
  }
  refs.eqBandCount.dataset.signature = signature;
}

function buildEqAuto(snapshot) {
  const modes = snapshot.auto_modes || [];
  const signature = JSON.stringify(modes.map((mode) => mode.id));
  if (refs.reactAuto.dataset.signature === signature) return;
  refs.reactAuto.replaceChildren();
  for (const mode of modes) {
    const option = document.createElement("option");
    option.value = mode.id;
    option.textContent = mode.label;
    refs.reactAuto.append(option);
  }
  refs.reactAuto.dataset.signature = signature;
}

function eqTypes(snapshot) {
  return snapshot?.eq_limits?.types || [
    { id: "bell", label: "Bell" },
    { id: "bandpass", label: "Band pass" },
    { id: "lowpass", label: "Low cut" },
    { id: "highpass", label: "High cut" },
    { id: "notch", label: "Notch" },
    { id: "flat", label: "Flat" },
  ];
}

function eqSlopes(snapshot) {
  return snapshot?.eq_limits?.slopes || [12, 24, 48];
}

function buildEqType(snapshot) {
  const types = eqTypes(snapshot);
  const signature = JSON.stringify(types.map((type) => [type.id, type.label]));
  if (refs.eqType.dataset.signature === signature) return;
  refs.eqType.replaceChildren();
  for (const type of types) {
    const option = document.createElement("option");
    option.value = type.id;
    option.textContent = type.label;
    refs.eqType.append(option);
  }
  refs.eqType.dataset.signature = signature;
}

function buildEqSlope(snapshot) {
  const slopes = eqSlopes(snapshot);
  const signature = JSON.stringify(slopes);
  if (refs.eqSlope.dataset.signature === signature) return;
  refs.eqSlope.replaceChildren();
  for (const slope of slopes) {
    const option = document.createElement("option");
    option.value = String(slope);
    option.textContent = `${slope} dB/oct`;
    refs.eqSlope.append(option);
  }
  refs.eqSlope.dataset.signature = signature;
}

function eqTypeShort(type) {
  return {
    bell: "BELL",
    bandpass: "BPASS",
    lowpass: "LOCUT",
    highpass: "HICUT",
    notch: "NOTCH",
    flat: "FLAT",
  }[type] || "BELL";
}

function eqUsesSlope(type) {
  return type === "lowpass" || type === "highpass" || type === "bandpass";
}

function eqFill(fader, gain) {
  const pct = ((Math.max(-18, Math.min(18, Number(gain) || 0)) + 18) / 36) * 100;
  fader.style.setProperty("--fill", `${pct.toFixed(1)}%`);
}

function fillEqLampSelect(select, lamps, selected) {
  const signature = JSON.stringify(lamps.map((lamp) => [lamp.index, lamp.name]));
  if (select.dataset.signature !== signature) {
    select.replaceChildren();
    const auto = document.createElement("option");
    auto.value = "-1";
    auto.textContent = "Auto";
    select.append(auto);
    for (const lamp of lamps) {
      const option = document.createElement("option");
      option.value = String(lamp.index);
      option.textContent = lamp.name;
      select.append(option);
    }
    select.dataset.signature = signature;
  }
  select.value = String(selected);
}

function buildEqFaders(snapshot) {
  const bands = state.eq.bands;
  const lamps = state.eq.lamps;
  const signature = JSON.stringify([
    bands.length,
    lamps.map((lamp) => [lamp.index, lamp.name]),
  ]);
  if (refs.eqFaders.dataset.signature !== signature) {
    refs.eqFaders.replaceChildren();
    bands.forEach((band, index) => {
      const column = el("div", "eq-band");
      column.dataset.index = String(index);
      const gain = el("span", "eq-band-gain", "0.0");
      const fader = document.createElement("input");
      fader.type = "range";
      fader.min = "-18";
      fader.max = "18";
      fader.step = "0.5";
      fader.value = String(band.gain || 0);
      eqFill(fader, band.gain);
      fader.dataset.index = String(index);
      fader.setAttribute("aria-label", `Band ${index + 1} gain`);
      const freq = el("span", "eq-band-freq", eqShortFreq(band.freq));
      const tags = el("div", "eq-band-tags");
      const shape = el("span", "eq-band-shape", eqTypeShort(band.type));
      shape.title = eqTypes(state.snapshot).find((type) => type.id === band.type)?.label
        || "Bell";
      const solo = document.createElement("button");
      solo.type = "button";
      solo.className = "eq-band-solo";
      solo.textContent = "S";
      solo.title = `Solo band ${index + 1}`;
      solo.dataset.index = String(index);
      solo.setAttribute("aria-label", `Solo band ${index + 1}`);
      tags.append(shape, solo);
      const lamp = document.createElement("select");
      lamp.className = "eq-band-lamp";
      lamp.dataset.index = String(index);
      lamp.setAttribute("aria-label", `Band ${index + 1} lamp`);
      fillEqLampSelect(lamp, lamps, band.lamp ?? -1);
      column.append(gain, fader, freq, tags, lamp);
      refs.eqFaders.append(column);
    });
    refs.eqFaders.dataset.signature = signature;
  }
  refs.eqFaders.querySelectorAll(".eq-band").forEach((column, index) => {
    const band = bands[index];
    if (!band) return;
    column.classList.toggle("selected", index === state.eq.selected);
    const gain = column.querySelector(".eq-band-gain");
    const fader = column.querySelector('input[type="range"]');
    const freq = column.querySelector(".eq-band-freq");
    const shape = column.querySelector(".eq-band-shape");
    const solo = column.querySelector(".eq-band-solo");
    const lamp = column.querySelector("select");
    if (gain) gain.textContent = Number(band.gain).toFixed(1);
    if (fader && document.activeElement !== fader) {
      fader.value = String(band.gain || 0);
    }
    if (fader) eqFill(fader, band.gain);
    if (freq) freq.textContent = eqShortFreq(band.freq);
    if (shape) {
      shape.textContent = eqTypeShort(band.type);
      shape.title = eqTypes(state.snapshot || {}).find(
        (type) => type.id === band.type,
      )?.label || "Bell";
    }
    if (solo) {
      solo.classList.toggle("active", Boolean(band.solo));
      solo.setAttribute("aria-pressed", String(Boolean(band.solo)));
    }
    if (lamp) fillEqLampSelect(lamp, lamps, band.lamp ?? -1);
  });
}

function eqPlot() {
  return state.eq.plot;
}

function eqFreqBounds(index) {
  const bands = state.eq.bands;
  const low = index > 0 ? Number(bands[index - 1]?.freq) * 1.001 : 20;
  const high =
    index < bands.length - 1
      ? Number(bands[index + 1]?.freq) * 0.999
      : 20000;
  return [low, high];
}

function eqX(freq, plot) {
  const min = 20;
  const max = 20000;
  return plot.left
    + (Math.log(Math.max(min, Math.min(max, freq)) / min) / Math.log(max / min))
      * (plot.right - plot.left);
}

function eqY(gain, plot) {
  const limit = 18;
  const ratio = Math.max(-1, Math.min(1, gain / limit));
  const mid = (plot.top + plot.bottom) / 2;
  return mid - ratio * ((plot.bottom - plot.top) / 2);
}

function eqBandGain(freq, band) {
  const centre = Math.max(20, Number(band.freq) || 1000);
  const gain = Number(band.gain || 0);
  const q = Math.max(0.4, Number(band.q) || 1.4);
  const kind = band.type || "bell";
  const octaves = Math.log2(freq / centre);
  const sigma = Math.max(0.07, 0.60 / q);
  if (kind === "lowpass") {
    const order = Math.max(1, Number(band.slope || 24) / 6);
    return gain - 18 * (1 - 1 / (1 + (freq / centre) ** order));
  }
  if (kind === "highpass") {
    const order = Math.max(1, Number(band.slope || 24) / 6);
    return gain - 18 * (1 - 1 / (1 + (centre / freq) ** order));
  }
  if (kind === "notch") {
    return gain - 18 * Math.exp(-0.5 * (octaves / sigma) ** 2);
  }
  if (kind === "flat") {
    return gain;
  }
  if (kind === "bandpass") {
    const order = Math.max(1, Number(band.slope || 24) / 6);
    const edge = 2 ** (0.5 / q);
    const low = centre / edge;
    const high = centre * edge;
    const below = 1 / (1 + (low / freq) ** order);
    const above = 1 / (1 + (freq / high) ** order);
    return gain - 18 * (1 - below * above);
  }
  return gain * Math.exp(-0.5 * (octaves / sigma) ** 2);
}

function eqCurveGain(freq, bands) {
  let total = 0;
  for (const band of bands) {
    total += eqBandGain(freq, band);
  }
  return Math.max(-18, Math.min(18, total));
}

function drawEq() {
  const canvas = refs.eqCanvas;
  if (!canvas || !canvas.getContext) return;
  const { ctx, width, height } = sizeScope(canvas);
  if (width < 80 || height < 60) return;
  const plot = {
    left: 28,
    right: width - 9,
    top: 9,
    bottom: height - 17,
  };
  state.eq.plot = plot;
  const bands = state.eq.bands;
  const palette = SCOPE_COLORS;

  ctx.font = "8px ui-monospace, Menlo, Consolas, monospace";
  ctx.textBaseline = "middle";
  ctx.fillStyle = "rgba(255, 255, 255, .035)";
  for (const gain of [-12, -6, 6, 12]) {
    const y = eqY(gain, plot);
    ctx.fillRect(plot.left, y, plot.right - plot.left, 1);
  }
  ctx.fillStyle = "rgba(255, 255, 255, .10)";
  ctx.fillRect(plot.left, eqY(0, plot), plot.right - plot.left, 1);
  ctx.fillStyle = "#6f6b62";
  ctx.textAlign = "right";
  for (const gain of [-18, -12, -6, 0, 6, 12, 18]) {
    ctx.fillText(`${gain}`, plot.left - 3, eqY(gain, plot));
  }
  const marks = [20, 50, 100, 200, 500, 1000, 2000, 5000, 10000, 20000];
  ctx.textAlign = "center";
  for (const freq of marks) {
    const x = eqX(freq, plot);
    ctx.fillStyle = "rgba(255, 255, 255, .035)";
    ctx.fillRect(x, plot.top, 1, plot.bottom - plot.top);
    ctx.fillStyle = "#6f6b62";
    ctx.fillText(freq >= 1000 ? `${freq / 1000}k` : `${freq}`, x, height - 7);
  }

  const curve = [];
  for (let x = plot.left; x <= plot.right; x += 1) {
    const ratio = (x - plot.left) / Math.max(1, plot.right - plot.left);
    const freq = 20 * (20000 / 20) ** ratio;
    curve.push([x, eqY(eqCurveGain(freq, bands), plot)]);
  }
  if (curve.length) {
    ctx.beginPath();
    ctx.moveTo(curve[0][0], eqY(0, plot));
    for (const [x, y] of curve) ctx.lineTo(x, y);
    ctx.lineTo(curve[curve.length - 1][0], eqY(0, plot));
    ctx.closePath();
    ctx.fillStyle = "rgba(252, 190, 17, .13)";
    ctx.fill();
    ctx.beginPath();
    ctx.moveTo(curve[0][0], curve[0][1]);
    for (const [x, y] of curve) ctx.lineTo(x, y);
    ctx.strokeStyle = palette.amber;
    ctx.lineWidth = 1.4;
    ctx.stroke();
  }
  bands.forEach((band, index) => {
    const x = eqX(Number(band.freq), plot);
    const y = eqY(Number(band.gain), plot);
    const color = state.snapshot?.bands?.[index]?.color || palette.amber;
    ctx.beginPath();
    ctx.arc(x, y, index === state.eq.selected ? 5 : 3.4, 0, Math.PI * 2);
    ctx.fillStyle = color;
    ctx.fill();
    if (band.solo) {
      ctx.beginPath();
      ctx.arc(x, y, 9, 0, Math.PI * 2);
      ctx.strokeStyle = "rgba(252, 190, 17, .9)";
      ctx.setLineDash([2, 2]);
      ctx.lineWidth = 1;
      ctx.stroke();
      ctx.setLineDash([]);
    }
    if (index === state.eq.selected) {
      ctx.beginPath();
      ctx.arc(x, y, 7, 0, Math.PI * 2);
      ctx.strokeStyle = "rgba(255, 255, 255, .75)";
      ctx.lineWidth = 1;
      ctx.stroke();
    }
  });
  const assigned = bands.filter((band) => Number(band.lamp) >= 0).length;
  const soloed = bands.filter((band) => band.solo).length;
  refs.eqSummary.textContent = `${bands.length} bands · ${assigned} assigned${
    soloed ? ` · ${soloed} solo` : ""
  }`;
}

function syncEqDetail() {
  const band = state.eq.bands[state.eq.selected];
  if (!band) return;
  const kind = band.type || "bell";
  refs.eqDetailTitle.textContent = `Band ${state.eq.selected + 1}`;
  if (document.activeElement !== refs.eqType) refs.eqType.value = kind;
  const usesSlope = eqUsesSlope(kind);
  refs.eqSlopeField.classList.toggle("hidden", !usesSlope);
  refs.eqSlopeOut.value = String(band.slope || 24);
  if (document.activeElement !== refs.eqSlope) {
    refs.eqSlope.value = String(band.slope || 24);
  }
  refs.eqQField.classList.toggle(
    "hidden",
    kind === "lowpass" || kind === "highpass" || kind === "flat",
  );
  refs.eqSolo.checked = Boolean(band.solo);
  refs.eqFreqOut.value = `${eqShortFreq(band.freq)} Hz`;
  if (document.activeElement !== refs.eqFreq) {
    refs.eqFreq.value = String(Math.round(eqFreqToLog(band.freq)));
  }
  refs.eqQOut.value = Number(band.q).toFixed(1);
  if (document.activeElement !== refs.eqQ) refs.eqQ.value = String(band.q);
  refs.eqGainOut.value = `${Number(band.gain).toFixed(1)} dB`;
  if (document.activeElement !== refs.eqGain) refs.eqGain.value = String(band.gain);
  fillEqLampSelect(refs.eqLamp, state.eq.lamps, band.lamp ?? -1);
}

function paintEqBand(column, band) {
  const gain = column.querySelector(".eq-band-gain");
  const fader = column.querySelector('input[type="range"]');
  const freq = column.querySelector(".eq-band-freq");
  const shape = column.querySelector(".eq-band-shape");
  const solo = column.querySelector(".eq-band-solo");
  const lamp = column.querySelector("select");
  if (gain) gain.textContent = Number(band.gain).toFixed(1);
  if (fader && document.activeElement !== fader) fader.value = String(band.gain);
  if (fader) eqFill(fader, band.gain);
  if (freq) freq.textContent = eqShortFreq(band.freq);
  if (shape) {
    shape.textContent = eqTypeShort(band.type);
    shape.title = eqTypes(state.snapshot || {}).find(
      (type) => type.id === band.type,
    )?.label || "Bell";
  }
  if (solo) {
    solo.classList.toggle("active", Boolean(band.solo));
    solo.setAttribute("aria-pressed", String(Boolean(band.solo)));
  }
  if (lamp && document.activeElement !== lamp) {
    lamp.value = String(band.lamp ?? -1);
  }
}

function refreshEqBands() {
  refs.eqFaders.querySelectorAll(".eq-band").forEach((column, index) => {
    column.classList.toggle("selected", index === state.eq.selected);
    const band = state.eq.bands[index];
    if (band) paintEqBand(column, band);
  });
}

function updateEqBandDom(index) {
  const column = refs.eqFaders.querySelector(`.eq-band[data-index="${index}"]`);
  const band = state.eq.bands[index];
  if (!column || !band) return;
  refreshEqBands();
  syncEqDetail();
  drawEq();
}

function syncEqFields(snapshot, config, reaction) {
  refs.eqPanel.classList.toggle("hidden", !reaction?.audio);
  if (!reaction?.audio) return;
  buildEqCount(snapshot);
  buildEqAuto(snapshot);
  buildEqType(snapshot);
  buildEqSlope(snapshot);
  const next = Array.isArray(config.react_eq) ? config.react_eq : [];
  // A count change always wins over a focused control: the server just gave us
  // the new band list. Otherwise keep local values while a fader is in use so
  // a poll cannot snap the handle back mid-drag.
  const countChanged = state.eq.bands.length !== next.length;
  const editing =
    state.eq.dragging || refs.eqPanel.contains(document.activeElement);
  if (countChanged || !editing) state.eq.bands = eqClone(next);
  state.eq.lamps = snapshot.lamps || [];
  state.eq.limits = snapshot.eq_limits || state.eq.limits;
  state.eq.selected = Math.max(0, Math.min(state.eq.bands.length - 1, state.eq.selected));

  if (document.activeElement !== refs.eqBandCount) {
    refs.eqBandCount.value = String(config.react_eq_bands || state.eq.bands.length);
  }
  if (document.activeElement !== refs.reactAuto) {
    refs.reactAuto.value = config.react_auto || "off";
  }
  const auto = (snapshot.auto_modes || []).find(
    (mode) => mode.id === (config.react_auto || "off"),
  );
  refs.reactAuto.title = auto?.hint || "";
  refs.reactActiveBands.checked = Boolean(config.react_active_bands);
  buildEqFaders(snapshot);
  refreshEqBands();
  syncEqDetail();
  drawEq();
}

function buildColorModeSelect(snapshot) {
  const modes = snapshot.color_modes || [];
  const signature = JSON.stringify(modes.map((mode) => [mode.id, mode.label]));
  if (refs.reactColorMode.dataset.signature === signature) return;
  refs.reactColorMode.replaceChildren();
  for (const mode of modes) {
    const option = document.createElement("option");
    option.value = mode.id;
    option.textContent = mode.label;
    refs.reactColorMode.append(option);
  }
  refs.reactColorMode.dataset.signature = signature;
}

function syncReactionFields(snapshot, config) {
  const reaction = reactionById(snapshot, config.react);
  const profiles = reaction?.profiles || [];
  const autoLux = Boolean(config.auto_lux);
  fillProfileSelect(reaction);
  refs.autoLux.checked = autoLux;
  refs.reactTargetField.classList.toggle("hidden", config.react !== "equalize");
  refs.luxField.classList.toggle("hidden", !autoLux);
  refs.reactBandsField.classList.toggle("hidden", !reaction?.audio);
  const colorModes = snapshot.color_modes || [];
  const colorMode = colorModes.some((mode) => mode.id === config.react_color_mode)
    ? config.react_color_mode
    : "bands";
  if (document.activeElement !== refs.reactColorMode) {
    refs.reactColorMode.value = colorMode;
  }
  refs.reactBands.classList.toggle("hidden", colorMode !== "bands");
  const pair = ["range", "level", "single"].includes(colorMode);
  refs.reactColorPair.classList.toggle("hidden", !pair);
  refs.reactColorPair.classList.toggle("single", colorMode === "single");
  refs.reactColorBSlot.classList.toggle("hidden", colorMode === "single");
  refs.reactColorALabel.textContent = colorMode === "single"
    ? "Color" : colorMode === "level" ? "Soft" : "Low";
  refs.reactColorBLabel.textContent = colorMode === "level" ? "Loud" : "High";
  const modeHint = colorModes.find((mode) => mode.id === colorMode)?.hint;
  if (modeHint) refs.reactColorHint.textContent = modeHint;
  if (document.activeElement !== refs.reactColorA) {
    refs.reactColorA.value = config.react_color_a || "#fcbe11";
  }
  if (document.activeElement !== refs.reactColorB) {
    refs.reactColorB.value = config.react_color_b || "#38bdf8";
  }
  if (profiles.length && document.activeElement !== refs.reactProfile) {
    const valid = profiles.some((profile) => profile.id === config.react_profile);
    refs.reactProfile.value = valid ? config.react_profile : profiles[0].id;
  }
  renderProfileHint();
  if (document.activeElement !== refs.reactAmount) {
    const amount = Math.round((Number(config.react_amount) || 0) * 100);
    refs.reactAmount.value = String(amount);
    refs.reactAmountOut.value = String(amount);
    paintRange(refs.reactAmount);
  }
  if (document.activeElement !== refs.reactTarget) {
    const target = Math.round((Number(config.react_target) || 0.45) * 100);
    refs.reactTarget.value = String(target);
    refs.reactTargetOut.value = String(target);
    paintRange(refs.reactTarget);
  }
  if (document.activeElement !== refs.luxTarget) {
    const target = Math.round(Number(config.lux_target) || 50);
    refs.luxTarget.value = String(target);
    refs.luxTargetOut.value = String(target);
  }
  const lux = snapshot.lux;
  const value = Number(lux?.value);
  const target = Math.round(Number(config.lux_target) || 50);
  refs.luxReadout.hidden = !autoLux;
  if (autoLux) {
    if (!lux || !Number.isFinite(value)) {
      refs.luxReadout.textContent =
        config.react === "equalize"
          ? "No sensor reading; Equalize uses video luma."
          : "No sensor reading; brightness unchanged.";
    } else {
      const age = Math.max(0, Math.round(lux.age));
      const fallback = config.react === "equalize" ? "video luma" : "no correction";
      refs.luxReadout.textContent = lux.fresh
        ? `Sensor ${value.toFixed(1)} lx, target ${target} lx`
        : `Sensor ${value.toFixed(1)} lx (stale ${age} s), ${fallback}`;
    }
  }
  if (!refs.reactBands.contains(document.activeElement)) {
    const colors = Array.isArray(config.react_bands) ? config.react_bands : [];
    refs.reactBands.querySelectorAll('input[type="color"]').forEach((input, index) => {
      if (colors[index]) input.value = colors[index];
    });
  }
  syncDynamicsFields(snapshot, config, reaction);
  syncEqFields(snapshot, config, reaction);
}

function renderSettings(snapshot) {
  const config = snapshot.config;
  const vibrance = Number.isFinite(Number(config.vibrance))
    ? Number(config.vibrance) : 1;
  fillSelect(refs.styleSelect, snapshot.styles);
  fillSelect(refs.layoutSelect, snapshot.layouts);
  fillSamplingSelect();
  fillReactionSelect(snapshot);
  buildBandInputs(snapshot);
  buildColorModeSelect(snapshot);
  if (document.activeElement !== refs.styleSelect) refs.styleSelect.value = config.style;
  if (document.activeElement !== refs.reactSelect) {
    refs.reactSelect.value = config.react;
  }
  if (document.activeElement !== refs.layoutSelect) refs.layoutSelect.value = config.layout;
  if (document.activeElement !== refs.samplingSelect) refs.samplingSelect.value = config.sampling;
  if (document.activeElement !== refs.brightness) {
    refs.brightness.value = String(config.brightness);
    refs.brightnessOut.value = String(config.brightness);
    paintRange(refs.brightness);
  }
  if (document.activeElement !== refs.vibrance) {
    const percent = Math.round(vibrance * 100);
    refs.vibrance.value = String(percent);
    refs.vibranceOut.value = String(percent);
    paintRange(refs.vibrance);
  }
  refs.dryRun.checked = Boolean(config.dry_run);
  refs.whiteLeds.checked = Boolean(config.white_leds);
  refs.lookPill.textContent = config.style;
  renderReactionHint(config.react);
  syncReactionFields(snapshot, config);

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
    ["Saturation", Number.isFinite(saturation)
      ? `${(saturation * vibrance).toFixed(2)}×` : "—",
      "Style saturation times the Vibrance slider; 1× leaves colors unchanged"],
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
  const metered = lights.filter((row) => Number.isFinite(row.power));
  const watts = metered.reduce((sum, row) => sum + row.power, 0);
  let powerText = hasTarget ? (anyOn ? "On" : "Off") : "—";
  if (anyOn && metered.length) {
    const partial = metered.length < lights.length ? ` (${metered.length}/${lights.length})` : "";
    powerText += ` · ${formatWatts(watts)}${partial}`;
  }
  refs.powerState.textContent = powerText;
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
    // Whole-processor shares are small next to a 12-core box: a busy mpv can
    // read 2-4 %. A 5 % floor pinned those lines to the axis, so start lower
    // and let the peak set the top of the lane.
    min: 0.5,
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
  if (typeof value !== "number" || !Number.isFinite(value)) return "-";
  if (key.endsWith("Cpu")) return `${value < 1 ? value.toFixed(2) : value.toFixed(1)}%`;
  if (key.endsWith("Ram")) return `${Math.round(value)} MB`;
  return `${value < 10 ? value.toFixed(1) : Math.round(value)} KB/s`;
}

function formatWatts(value) {
  if (typeof value !== "number" || !Number.isFinite(value)) return null;
  return `${value < 10 ? value.toFixed(1) : Math.round(value)} W`;
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
  const running = Boolean(state.snapshot?.session?.running);
  const dry = running && Boolean(state.snapshot?.config?.dry_run);
  for (const lane of PERF_LANES) {
    for (const series of lane.series) {
      const item = el("span", "legend-item");
      const swatch = el("span", "legend-swatch");
      swatch.style.setProperty("--c", series.color);
      const value = formatMetric(series.key, lastValue(state.perf[series.key]));
      const shown = series.key === "udp" && dry ? "dry run" : value;
      item.append(
        swatch,
        el("span", "", series.label),
        el("span", "legend-value", shown),
      );
      let tip = series.tip;
      if (lane.label === "CPU %" && cores) {
        tip += ` · 100% = all ${cores} cores busy`;
      }
      if (series.key === "udp" && dry) {
        tip = "Dry run is on, so the sync logs colors instead of sending UDP";
      } else if (
        running
        && value === "-"
        && (series.key === "mpvCpu" || series.key === "mpvRam")
      ) {
        tip = "No mpv process found yet — start playback or check the Lua script";
      }
      item.title = tip;
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
      let end = null;
      values.forEach((value, index) => {
        if (typeof value !== "number" || !Number.isFinite(value)) {
          pen = false;
          return;
        }
        const x = left + index * stepX;
        const y = laneBottom - 4 - Math.min(1, value / max) * usable;
        path += `${pen ? "L" : "M"}${x.toFixed(1)} ${y.toFixed(1)} `;
        pen = true;
        end = { x, y };
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
      // A flat low line would otherwise hide on the axis; the dot marks the
      // newest sample and matches the value in the legend.
      if (end) {
        svg.append(
          svgNode("circle", {
            cx: end.x.toFixed(1),
            cy: end.y.toFixed(1),
            r: 2.2,
            fill: series.color,
          }),
        );
      }
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
  if (snapshot.session?.running && snapshot.config?.dry_run) bits.push("dry run · no UDP");
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
refs.reactSelect.addEventListener("change", () => {
  const reaction = refs.reactSelect.value;
  renderReactionHint(reaction);
  if (state.snapshot) {
    syncReactionFields(state.snapshot, {
      ...state.snapshot.config,
      react: reaction,
    });
  }
  saveConfig({ react: reaction });
});
refs.reactAmount.addEventListener("input", () => {
  refs.reactAmountOut.value = refs.reactAmount.value;
  paintRange(refs.reactAmount);
});
refs.reactAmount.addEventListener("change", () => {
  saveConfig({ react_amount: Number(refs.reactAmount.value) / 100 });
});
refs.reactDynamics.addEventListener("change", () => {
  renderDynamicsHint();
  let presets = {};
  try {
    presets = JSON.parse(refs.reactDynamics.dataset.presets || "{}");
  } catch {
    presets = {};
  }
  const preset = presets[refs.reactDynamics.value];
  if (preset) {
    // The dataset uses short keys for matching; the config needs the four
    // react_* names, or the preset looks applied but the server never sees it.
    saveConfig({
      react_threshold: preset.threshold,
      react_attack: preset.attack,
      react_release: preset.release,
      react_punch: preset.punch,
    });
  }
});
refs.reactThreshold.addEventListener("input", () => {
  refs.reactThresholdOut.value = `${Math.round(Number(refs.reactThreshold.value))} dB`;
  paintRange(refs.reactThreshold);
  drawTimeline();
});
refs.reactThreshold.addEventListener("change", () => {
  saveConfig({ react_threshold: Number(refs.reactThreshold.value) });
});
refs.reactAttack.addEventListener("input", () => {
  refs.reactAttackOut.value = `${Math.round(Number(refs.reactAttack.value))} ms`;
  paintRange(refs.reactAttack);
});
refs.reactAttack.addEventListener("change", () => {
  saveConfig({ react_attack: Number(refs.reactAttack.value) });
});
refs.reactRelease.addEventListener("input", () => {
  refs.reactReleaseOut.value = `${Math.round(Number(refs.reactRelease.value))} ms`;
  paintRange(refs.reactRelease);
});
refs.reactRelease.addEventListener("change", () => {
  saveConfig({ react_release: Number(refs.reactRelease.value) });
});
refs.reactPunch.addEventListener("input", () => {
  refs.reactPunchOut.value = `${(Number(refs.reactPunch.value) / 100).toFixed(1)}×`;
  paintRange(refs.reactPunch);
});
refs.reactPunch.addEventListener("change", () => {
  saveConfig({ react_punch: Number(refs.reactPunch.value) / 100 });
});
refs.reactProfile.addEventListener("change", () => {
  renderProfileHint();
  saveConfig({ react_profile: refs.reactProfile.value });
});
refs.autoLux.addEventListener("change", () => {
  saveConfig({ auto_lux: refs.autoLux.checked });
});
refs.reactTarget.addEventListener("input", () => {
  refs.reactTargetOut.value = refs.reactTarget.value;
  paintRange(refs.reactTarget);
});
refs.reactTarget.addEventListener("change", () => {
  saveConfig({ react_target: Number(refs.reactTarget.value) / 100 });
});
refs.luxTarget.addEventListener("input", () => {
  refs.luxTargetOut.value = refs.luxTarget.value;
});
refs.luxTarget.addEventListener("change", () => {
  saveConfig({ lux_target: Number(refs.luxTarget.value) });
});
refs.reactBands.addEventListener("change", (event) => {
  const input = event.target.closest('input[type="color"]');
  if (!input) return;
  const colors = [...refs.reactBands.querySelectorAll('input[type="color"]')].map(
    (swatch) => swatch.value,
  );
  saveConfig({ react_bands: colors });
});
refs.reactColorMode.addEventListener("change", () => {
  saveConfig({ react_color_mode: refs.reactColorMode.value });
  if (state.snapshot) {
    syncReactionFields(state.snapshot, {
      ...state.snapshot.config,
      react_color_mode: refs.reactColorMode.value,
    });
  }
});
refs.reactColorA.addEventListener("change", () =>
  saveConfig({ react_color_a: refs.reactColorA.value }),
);
refs.reactColorB.addEventListener("change", () =>
  saveConfig({ react_color_b: refs.reactColorB.value }),
);
function saveEq() {
  saveConfig({ react_eq: state.eq.bands });
}
refs.eqBandCount.addEventListener("change", () => {
  const count = Number(refs.eqBandCount.value);
  state.eq.bands = eqRemapBands(state.eq.bands, count);
  state.eq.selected = Math.max(
    0,
    Math.min(state.eq.bands.length - 1, state.eq.selected),
  );
  // Send the full plan with the count so the server never extends the old
  // centres positionally (which would duplicate the top band).
  saveConfig({ react_eq_bands: count, react_eq: state.eq.bands });
});
refs.reactAuto.addEventListener("change", () => {
  const mode = (state.snapshot?.auto_modes || []).find(
    (item) => item.id === refs.reactAuto.value,
  );
  refs.reactAuto.title = mode?.hint || "";
  saveConfig({ react_auto: refs.reactAuto.value });
});
refs.reactActiveBands.addEventListener("change", () =>
  saveConfig({ react_active_bands: refs.reactActiveBands.checked }),
);
refs.eqFaders.addEventListener("click", (event) => {
  const solo = event.target.closest(".eq-band-solo");
  if (solo) {
    const index = Number(solo.dataset.index);
    const band = state.eq.bands[index];
    if (band) {
      state.eq.selected = index;
      band.solo = !band.solo;
      updateEqBandDom(index);
      saveEq();
    }
    return;
  }
  const column = event.target.closest(".eq-band");
  if (!column) return;
  state.eq.selected = Number(column.dataset.index);
  updateEqBandDom(state.eq.selected);
});
refs.eqFaders.addEventListener("input", (event) => {
  const fader = event.target.closest('input[type="range"]');
  if (!fader) return;
  const index = Number(fader.dataset.index);
  const band = state.eq.bands[index];
  if (!band) return;
  state.eq.selected = index;
  band.gain = Number(fader.value);
  updateEqBandDom(index);
});
refs.eqFaders.addEventListener("change", (event) => {
  const fader = event.target.closest('input[type="range"]');
  if (fader) {
    const band = state.eq.bands[Number(fader.dataset.index)];
    if (band) {
      band.gain = Number(fader.value);
      saveEq();
    }
    return;
  }
  const lamp = event.target.closest("select.eq-band-lamp");
  if (!lamp) return;
  const band = state.eq.bands[Number(lamp.dataset.index)];
  if (!band) return;
  band.lamp = Number(lamp.value);
  saveEq();
});
refs.eqFreq.addEventListener("input", () => {
  const band = state.eq.bands[state.eq.selected];
  if (!band) return;
  const [low, high] = eqFreqBounds(state.eq.selected);
  band.freq =
    Math.round(
      Math.max(low, Math.min(high, eqLogToFreq(refs.eqFreq.value))) * 10,
    ) / 10;
  refs.eqFreqOut.value = `${eqShortFreq(band.freq)} Hz`;
  updateEqBandDom(state.eq.selected);
});
refs.eqFreq.addEventListener("change", saveEq);
refs.eqQ.addEventListener("input", () => {
  const band = state.eq.bands[state.eq.selected];
  if (!band) return;
  band.q = Number(refs.eqQ.value);
  refs.eqQOut.value = Number(band.q).toFixed(1);
  drawEq();
});
refs.eqQ.addEventListener("change", saveEq);
refs.eqType.addEventListener("change", () => {
  const band = state.eq.bands[state.eq.selected];
  if (!band) return;
  band.type = refs.eqType.value;
  updateEqBandDom(state.eq.selected);
  saveEq();
});
refs.eqSlope.addEventListener("change", () => {
  const band = state.eq.bands[state.eq.selected];
  if (!band) return;
  band.slope = Number(refs.eqSlope.value) || 24;
  refs.eqSlopeOut.value = String(band.slope);
  updateEqBandDom(state.eq.selected);
  saveEq();
});
refs.eqSolo.addEventListener("change", () => {
  const band = state.eq.bands[state.eq.selected];
  if (!band) return;
  band.solo = refs.eqSolo.checked;
  updateEqBandDom(state.eq.selected);
  saveEq();
});
refs.eqGain.addEventListener("input", () => {
  const band = state.eq.bands[state.eq.selected];
  if (!band) return;
  band.gain = Number(refs.eqGain.value);
  refs.eqGainOut.value = `${Number(band.gain).toFixed(1)} dB`;
  updateEqBandDom(state.eq.selected);
});
refs.eqGain.addEventListener("change", saveEq);
refs.eqLamp.addEventListener("change", () => {
  const band = state.eq.bands[state.eq.selected];
  if (!band) return;
  band.lamp = Number(refs.eqLamp.value);
  updateEqBandDom(state.eq.selected);
  saveEq();
});

function eqNodeAt(event) {
  const plot = state.eq.plot;
  if (!plot) return -1;
  const rect = refs.eqCanvas.getBoundingClientRect();
  const x = event.clientX - rect.left;
  const y = event.clientY - rect.top;
  let best = -1;
  let bestDistance = 24;
  state.eq.bands.forEach((band, index) => {
    const distance = Math.hypot(
      x - eqX(Number(band.freq), plot),
      y - eqY(Number(band.gain), plot),
    );
    if (distance < bestDistance) {
      bestDistance = distance;
      best = index;
    }
  });
  return best;
}

function eqPointerUpdate(event) {
  const drag = state.eq.dragging;
  const plot = state.eq.plot;
  if (!drag || !plot) return;
  const rect = refs.eqCanvas.getBoundingClientRect();
  const x = Math.max(plot.left, Math.min(plot.right, event.clientX - rect.left));
  const y = Math.max(plot.top, Math.min(plot.bottom, event.clientY - rect.top));
  const frequency = 20 * (20000 / 20) ** ((x - plot.left) / (plot.right - plot.left));
  const gain = Math.round(
    (1 - ((y - plot.top) / (plot.bottom - plot.top)) * 2) * 18 * 2,
  ) / 2;
  const band = state.eq.bands[drag.index];
  if (!band) return;
  const [low, high] = eqFreqBounds(drag.index);
  // Keep the bands in frequency order so a drag never re-sorts the list and
  // changes which lamp and colour the selected band owns.
  band.freq = Math.round(Math.max(low, Math.min(high, frequency)) * 10) / 10;
  band.gain = Math.max(-18, Math.min(18, gain));
  updateEqBandDom(drag.index);
}

refs.eqCanvas.addEventListener("pointerdown", (event) => {
  const index = eqNodeAt(event);
  if (index < 0) return;
  state.eq.selected = index;
  state.eq.dragging = { index, pointerId: event.pointerId };
  capturePointer(refs.eqCanvas, event.pointerId);
  updateEqBandDom(index);
  eqPointerUpdate(event);
});
refs.eqCanvas.addEventListener("pointermove", (event) => {
  if (!state.eq.dragging) return;
  eqPointerUpdate(event);
});
const endEqDrag = (event) => {
  if (!state.eq.dragging) return;
  releasePointer(refs.eqCanvas, event.pointerId);
  state.eq.dragging = null;
  saveEq();
};
refs.eqCanvas.addEventListener("pointerup", endEqDrag);
refs.eqCanvas.addEventListener("pointercancel", endEqDrag);
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
refs.vibrance.addEventListener("input", () => {
  refs.vibranceOut.value = refs.vibrance.value;
});
refs.vibrance.addEventListener("change", () => {
  const value = Number(refs.vibrance.value) / 100;
  if (value !== state.snapshot?.config.vibrance) saveConfig({ vibrance: value });
});
refs.whiteLeds.addEventListener("change", () => {
  if (refs.whiteLeds.checked !== Boolean(state.snapshot?.config.white_leds)) {
    saveConfig({ white_leds: refs.whiteLeds.checked });
  }
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
    drawEq();
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
  stopMeter();
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
    refs.vibrance,
    refs.reactThreshold,
    refs.reactAttack,
    refs.reactRelease,
    refs.reactPunch,
    refs.controlBrightness,
    refs.controlTemp,
    refs.controlSpeed,
    refs.samplingFps,
  ];
  for (const input of sliders) {
    paintRange(input);
    input.addEventListener("input", () => paintRange(input));
  }
  bindScope();
  bindKnobs();
  await refresh();
  state.poll = window.setInterval(() => {
    if (!document.hidden && !state.closed) refresh();
  }, 1200);
}

boot();
