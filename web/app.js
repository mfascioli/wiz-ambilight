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
  powerOnBtn: document.getElementById("powerOnBtn"),
  powerOffBtn: document.getElementById("powerOffBtn"),
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
  modeHint: document.getElementById("modeHint"),
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
  mapping: document.getElementById("mapping"),
  log: document.getElementById("log"),
  clearLog: document.getElementById("clearLog"),
  configPath: document.getElementById("configPath"),
  resources: document.getElementById("resources"),
  resCpu: document.getElementById("resCpu"),
  resRam: document.getElementById("resRam"),
  resNet: document.getElementById("resNet"),
  resNote: document.getElementById("resNote"),
  sparkCpu: document.getElementById("sparkCpu"),
  sparkRam: document.getElementById("sparkRam"),
  sparkNet: document.getElementById("sparkNet"),
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
  resourceAt: 0,
  resourceHistory: { cpu: [], ram: [], net: [] },
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
  return `rgb(${channel(light.r)}, ${channel(light.g)}, ${channel(light.b)})`;
}

const HEX_RE = /^#?[0-9a-fA-F]{6}$/;

function normalizeHex(value) {
  const text = String(value || "").trim();
  if (!HEX_RE.test(text)) return null;
  return (text.startsWith("#") ? text : `#${text}`).toLowerCase();
}

function targetIp() {
  return refs.targetSelect.value || "all";
}

function targetLight(snapshot) {
  const ip = targetIp();
  return (snapshot?.lights || []).find((light) => light.ip === ip) || null;
}

function targetName(snapshot) {
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

  controls.append(zonePick, identify, power, toggle);
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
  refs.startBtn.textContent = running ? "Restart" : "Start Ambilight";
  refs.startBtn.disabled = enabled === 0 || (mode === "launch" && !snapshot.config.media.trim());
  refs.modeHint.textContent =
    mode === "attach"
      ? "Attach follows any mpv window that loaded the Lua script."
      : "Launch starts mpv with the chosen file.";
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
    const row = el("div", "stage-row");
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
    const preview = el("span", "zone-preview");
    preview.dataset.zone = light.effective_zone;
    preview.setAttribute("aria-hidden", "true");
    chip.append(
      preview,
      el("strong", "", light.name || light.ip),
      el("span", "map-zone", zoneLabel(light.effective_zone)),
    );
    chip.title = `${light.name || light.ip} samples the ${zoneLabel(light.effective_zone)} of the video`;
    refs.mapping.append(chip);
  }
}

function fillTargetOptions(snapshot) {
  const signature = snapshot.lights.map((light) => `${light.ip}:${light.name}`).join("|");
  if (refs.targetSelect.dataset.signature === signature) return;
  const wanted = refs.targetSelect.value || "all";
  refs.targetSelect.replaceChildren();
  const all = el("option", "", "All lights");
  all.value = "all";
  refs.targetSelect.append(all);
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

  const light = targetLight(snapshot);
  const isAll = targetIp() === "all";
  refs.targetPill.textContent = isAll ? "all lights" : targetName(snapshot);
  refs.controlNote.textContent = snapshot.session.running
    ? "Ambilight is syncing — direct changes last until the next frame."
    : "Control bulbs without starting Ambilight.";

  const hasLights = snapshot.lights.length > 0;
  refs.powerOnBtn.disabled = !hasLights;
  refs.powerOffBtn.disabled = !hasLights;
  refs.applyColorBtn.disabled = !hasLights;
  refs.applySceneBtn.disabled = !hasLights || !refs.sceneSelect.options.length;
  refs.saveSceneBtn.disabled = !hasLights;

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
    const value = normalizeHex(light.hex) || "#ffffff";
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

const SPARK_W = 110;
const SPARK_H = 20;
const RESOURCE_HISTORY = 36;

function pushResource(kind, value) {
  const series = state.resourceHistory[kind];
  series.push(typeof value === "number" && Number.isFinite(value) ? value : null);
  if (series.length > RESOURCE_HISTORY) series.splice(0, series.length - RESOURCE_HISTORY);
}

function sparkPath(values, zeroBased) {
  const numbers = values.filter((value) => typeof value === "number" && Number.isFinite(value));
  if (numbers.length < 2) return "";
  const max = Math.max(...numbers);
  const min = zeroBased ? 0 : Math.min(...numbers);
  const span = max - min;
  const step = SPARK_W / Math.max(1, values.length - 1);
  let path = "";
  let pen = false;
  values.forEach((value, index) => {
    if (typeof value !== "number" || !Number.isFinite(value)) {
      pen = false;
      return;
    }
    const x = index * step;
    const y = span ? SPARK_H - 2 - ((value - min) / span) * (SPARK_H - 4) : (zeroBased ? SPARK_H - 2 : SPARK_H / 2);
    path += `${pen ? "L" : "M"}${x.toFixed(1)} ${y.toFixed(1)} `;
    pen = true;
  });
  return path.trim();
}

function formatRate(bps) {
  if (typeof bps !== "number" || !Number.isFinite(bps)) return "—";
  if (bps < 1024) return `${Math.round(bps)} B/s`;
  if (bps < 1024 * 1024) return `${(bps / 1024).toFixed(1)} KB/s`;
  return `${(bps / (1024 * 1024)).toFixed(2)} MB/s`;
}

function renderResources(snapshot) {
  const res = snapshot.resources || {};
  if (res.at && res.at !== state.resourceAt) {
    state.resourceAt = res.at;
    pushResource("cpu", res.available ? res.cpu : null);
    pushResource("ram", res.available ? res.ram_mb : null);
    pushResource("net", res.network_bps);
  }

  refs.resCpu.textContent = res.available
    ? (typeof res.cpu === "number" ? `${res.cpu >= 10 ? Math.round(res.cpu) : res.cpu.toFixed(1)}%` : "—")
    : "n/a";
  refs.resRam.textContent = res.available && typeof res.ram_mb === "number"
    ? `${Math.round(res.ram_mb)} MB`
    : (res.available ? "—" : "n/a");
  refs.resNet.textContent = formatRate(res.network_bps);

  refs.sparkCpu.setAttribute("d", sparkPath(state.resourceHistory.cpu, true));
  refs.sparkRam.setAttribute("d", sparkPath(state.resourceHistory.ram, false));
  refs.sparkNet.setAttribute("d", sparkPath(state.resourceHistory.net, true));

  const bits = [snapshot.session.running ? "panel + sync" : "panel only"];
  const capW = typeof res.capture_w === "number" ? Math.round(res.capture_w) : null;
  const capH = typeof res.capture_h === "number" ? Math.round(res.capture_h) : null;
  const srcW = typeof res.video_w === "number" ? Math.round(res.video_w) : null;
  const srcH = typeof res.video_h === "number" ? Math.round(res.video_h) : null;
  if (srcW && srcH) {
    bits.push(`${srcW}×${srcH}`);
    if (capW && capH && (capW !== srcW || capH !== srcH)) bits.push(`cap ${capW}×${capH}`);
  } else if (capW && capH) {
    bits.push(`${capW}×${capH}`);
  }
  if (typeof res.capture_fps === "number" && res.capture_fps > 0) {
    bits.push(`${res.capture_fps.toFixed(1)} fps`);
  }
  refs.resNote.textContent = bits.join(" · ");
  refs.resources.title = res.available
    ? `Panel and sync tree · ${res.processes} process${res.processes === 1 ? "" : "es"} · ` +
      `WiZ UDP ${formatRate(res.network_bps)}`
    : "CPU and RAM need Linux /proc; the network counter still works";
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
  renderMapping(snapshot);
  renderLua(snapshot);
  renderLog(snapshot);
  renderResources(snapshot);
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
refs.powerOnBtn.addEventListener("click", () =>
  sendControl({ power: true }, `${targetName(state.snapshot)} on`, refs.powerOnBtn),
);
refs.powerOffBtn.addEventListener("click", () =>
  sendControl({ power: false }, `${targetName(state.snapshot)} off`, refs.powerOffBtn),
);
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
  refs.controlTempOut.value = `${refs.controlTemp.value} K`;
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
