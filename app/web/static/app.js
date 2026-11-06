"use strict";
// MDS Manager — веб-застосунок. Дизайн і базові компоненти — з MDS Connect (style.css, h(), icon()).
// DOM будуємо лише через h(): жодного innerHTML з даними.

const store = {
  get(k) { try { return localStorage.getItem(k); } catch (_) { return null; } },
  set(k, v) { try { localStorage.setItem(k, v); } catch (_) { } },
};

const ICONS = {
  link: '<path d="M10 13a5 5 0 0 0 7.5.5l3-3a5 5 0 0 0-7-7l-1.7 1.7"/><path d="M14 11a5 5 0 0 0-7.5-.5l-3 3a5 5 0 0 0 7 7l1.7-1.7"/>',
  ext: '<path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6M15 3h6v6M10 14L21 3"/>',
  spark: '<path d="M12 3l1.9 5.1L19 10l-5.1 1.9L12 17l-1.9-5.1L5 10l5.1-1.9z"/><path d="M19 15l.8 2.2L22 18l-2.2.8L19 21l-.8-2.2L16 18l2.2-.8z"/>',
  calendar: '<rect x="3" y="4" width="18" height="18" rx="2"/><path d="M16 2v4M8 2v4M3 10h18"/>',
  clock: '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
  chart: '<path d="M3 3v18h18"/><path d="M7 15v2M11 11v6M15 7v10M19 12v5"/>',
  wallet: '<path d="M20 7H5a2 2 0 0 1 0-4h13v4"/><path d="M3 5v14a2 2 0 0 0 2 2h15v-5"/><path d="M21 12h-4a2 2 0 0 0 0 4h4v-4z"/>',
  check: '<path d="M9 11l3 3L22 4"/><path d="M21 12v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11"/>',
  user: '<circle cx="12" cy="8" r="4"/><path d="M4 21a8 8 0 0 1 16 0"/>',
  users: '<circle cx="9" cy="8" r="4"/><path d="M2 21a7 7 0 0 1 14 0"/><path d="M16 4a4 4 0 0 1 0 8M22 21a7 7 0 0 0-4-6.3"/>',
  list: '<path d="M8 6h13M8 12h13M8 18h13M3 6h.01M3 12h.01M3 18h.01"/>',
  receipt: '<path d="M4 2v20l3-2 3 2 3-2 3 2 3-2 1 .7V2l-3 2-3-2-3 2-3-2-3 2z"/><path d="M8 8h8M8 12h8M8 16h5"/>',
  banknote: '<rect x="2" y="6" width="20" height="12" rx="2"/><circle cx="12" cy="12" r="2.5"/><path d="M6 12h.01M18 12h.01"/>',
  scissors: '<circle cx="6" cy="6" r="3"/><circle cx="6" cy="18" r="3"/><path d="M20 4L8.1 15.9M14.5 14.5L20 20M8.1 8.1L12 12"/>',
  settings: '<circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.7 1.7 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.7 1.7 0 0 0-1.8-.3 1.7 1.7 0 0 0-1 1.5V21a2 2 0 1 1-4 0v-.1a1.7 1.7 0 0 0-1.1-1.5 1.7 1.7 0 0 0-1.8.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.7 1.7 0 0 0 .3-1.8 1.7 1.7 0 0 0-1.5-1H3a2 2 0 1 1 0-4h.1a1.7 1.7 0 0 0 1.5-1.1 1.7 1.7 0 0 0-.3-1.8l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.7 1.7 0 0 0 1.8.3H9a1.7 1.7 0 0 0 1-1.5V3a2 2 0 1 1 4 0v.1a1.7 1.7 0 0 0 1 1.5 1.7 1.7 0 0 0 1.8-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.7 1.7 0 0 0-.3 1.8V9a1.7 1.7 0 0 0 1.5 1H21a2 2 0 1 1 0 4h-.1a1.7 1.7 0 0 0-1.5 1z"/>',
  book: '<path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20V3H6.5A2.5 2.5 0 0 0 4 5.5z"/><path d="M4 19.5A2.5 2.5 0 0 0 6.5 22H20v-5"/>',
  logout: '<path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4M16 17l5-5-5-5M21 12H9"/>',
  sun: '<circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/>',
  moon: '<path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z"/>',
  plus: '<path d="M12 5v14M5 12h14"/>',
  left: '<path d="M15 18l-6-6 6-6"/>',
  right: '<path d="M9 18l6-6-6-6"/>',
  phone: '<path d="M22 16.9v3a2 2 0 0 1-2.2 2 19.8 19.8 0 0 1-8.6-3.1 19.5 19.5 0 0 1-6-6A19.8 19.8 0 0 1 2.1 4.2 2 2 0 0 1 4.1 2h3a2 2 0 0 1 2 1.7c.1.9.3 1.8.6 2.7a2 2 0 0 1-.5 2.1L8 9.8a16 16 0 0 0 6 6l1.3-1.3a2 2 0 0 1 2.1-.4c.9.3 1.8.5 2.7.6a2 2 0 0 1 1.7 2z"/>',
  x: '<path d="M18 6L6 18M6 6l12 12"/>',
  search: '<circle cx="11" cy="11" r="7"/><path d="M21 21l-4.3-4.3"/>',
  down: '<path d="M6 9l6 6 6-6"/>',
  sliders: '<path d="M4 6h9M17 6h3M4 12h3M11 12h9M4 18h11M19 18h1"/><circle cx="15" cy="6" r="2"/><circle cx="9" cy="12" r="2"/><circle cx="17" cy="18" r="2"/>',
  more: '<circle cx="5" cy="12" r="1"/><circle cx="12" cy="12" r="1"/><circle cx="19" cy="12" r="1"/>',
  trend: '<path d="M23 6l-9.5 9.5-5-5L1 18"/><path d="M17 6h6v6"/>',
  card: '<rect x="2" y="5" width="20" height="14" rx="2"/><path d="M2 10h20"/>',
  transfer: '<path d="M17 3l4 4-4 4M3 7h18M7 21l-4-4 4-4M21 17H3"/>',
  send: '<path d="M22 2L11 13M22 2l-7 20-4-9-9-4z"/>',
  inbox: '<path d="M22 12h-6l-2 3h-4l-2-3H2"/><path d="M5.5 5.1L2 12v6a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2v-6l-3.5-6.9A2 2 0 0 0 16.8 4H7.2a2 2 0 0 0-1.7 1.1z"/>',
  box: '<path d="M21 16V8a2 2 0 0 0-1-1.7l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.7l7 4a2 2 0 0 0 2 0l7-4a2 2 0 0 0 1-1.7z"/><path d="M3.3 7L12 12l8.7-5M12 22V12"/>',
  percent: '<path d="M19 5L5 19"/><circle cx="6.5" cy="6.5" r="2.5"/><circle cx="17.5" cy="17.5" r="2.5"/>',
  home: '<path d="M3 21h18M5 21V7l7-4 7 4v14M9 21v-6h6v6"/>',
  megaphone: '<path d="M3 11l18-5v12L3 14v-3z"/><path d="M11.6 16.8a3 3 0 1 1-5.8-1.6"/>',
  zap: '<path d="M13 2L3 14h9l-1 8 10-12h-9l1-8z"/>',
  alert: '<circle cx="12" cy="12" r="9"/><path d="M12 8v4M12 16h.01"/>',
  ok: '<path d="M20 6L9 17l-5-5"/>',
  edit: '<path d="M12 20h9"/><path d="M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4z"/>',
  history: '<path d="M3 3v5h5"/><path d="M3.05 13A9 9 0 1 0 6 5.3L3 8"/><path d="M12 7v5l4 2"/>',
  cancel: '<circle cx="12" cy="12" r="9"/><path d="M15 9l-6 6M9 9l6 6"/>',
  noshow: '<circle cx="10" cy="8" r="4"/><path d="M3 21a7 7 0 0 1 12.5-4.3M17 14l5 5M22 14l-5 5"/>',
  play: '<path d="M6 4l14 8-14 8z"/>',
  move: '<path d="M5 9l-3 3 3 3M9 5l3-3 3 3M15 19l-3 3-3-3M19 9l3 3-3 3M2 12h20M12 2v20"/>',
  lock: '<rect x="4" y="11" width="16" height="10" rx="2"/><path d="M8 11V7a4 4 0 0 1 8 0v4"/>',
  trash: '<path d="M3 6h18M8 6V4h8v2M19 6l-1 14H6L5 6"/>',
  bug: '<rect x="8" y="6" width="8" height="14" rx="4"/><path d="M19 7l-3 2M5 7l3 2M19 19l-3-2M5 19l3-2M20 13h-4M4 13h4M10 4l1 2M14 4l-1 2"/>',
  image: '<rect x="3" y="3" width="18" height="18" rx="2"/><circle cx="9" cy="9" r="2"/><path d="M21 15l-5-5L5 21"/>',
  refresh: '<path d="M21 12a9 9 0 0 1-15.4 6.4L3 16"/><path d="M3 21v-5h5"/><path d="M3 12a9 9 0 0 1 15.4-6.4L21 8"/><path d="M21 3v5h-5"/>',
  calclock: '<path d="M21 10.5V6a2 2 0 0 0-2-2H5a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h6"/><path d="M16 2v4M8 2v4M3 10h18"/><circle cx="17.5" cy="17.5" r="4.5"/><path d="M17.5 15.5v2l1.3 1"/>',
  filetext: '<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><path d="M14 2v6h6M8 13h8M8 17h8M8 9h2"/>',
  landmark: '<path d="M3 22h18M6 18v-7M10 18v-7M14 18v-7M18 18v-7M12 2l9 5H3z"/>',
  usercog: '<circle cx="9" cy="7" r="4"/><path d="M2 21a7 7 0 0 1 10.5-6"/><circle cx="18" cy="17" r="2.5"/><path d="M18 13v1.5M18 19.5V21M14 17h1.5M20.5 17H22M15.2 14.2l1 1M19.8 18.8l1 1M15.2 19.8l1-1M19.8 15.2l1-1"/>',
  coins: '<circle cx="8" cy="8" r="6"/><path d="M18.1 10.4A6 6 0 1 1 10.3 18M7 6h1v4M16.7 13.9l.7.7-2.8 2.8"/>',
  grid: '<rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/><rect x="3" y="14" width="7" height="7" rx="1"/><rect x="14" y="14" width="7" height="7" rx="1"/>',
  rows: '<rect x="3" y="4" width="18" height="6" rx="1.5"/><rect x="3" y="14" width="18" height="6" rx="1.5"/>',
  eye: '<path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7S2 12 2 12z"/><circle cx="12" cy="12" r="3"/>',
  eyeoff: '<path d="M17.9 17.9A10.4 10.4 0 0 1 12 19c-6.5 0-10-7-10-7a18.4 18.4 0 0 1 5.1-5.9M9.9 5.2A9.6 9.6 0 0 1 12 5c6.5 0 10 7 10 7a18.5 18.5 0 0 1-2.2 3.2M14.1 14.1a3 3 0 1 1-4.2-4.2M2 2l20 20"/>',
  man: '<circle cx="12" cy="5" r="2.6"/><path d="M8.5 21v-6.5H7v-4a3 3 0 0 1 3-3h4a3 3 0 0 1 3 3v4h-1.5V21"/><path d="M12 14.5V21"/>',
  woman: '<circle cx="12" cy="5" r="2.6"/><path d="M9.5 21v-4H6.8L9.5 10a2.5 2.5 0 0 1 2.4-1.8h.2A2.5 2.5 0 0 1 14.5 10l2.7 7h-2.7v4"/>',
  dye: '<path d="M14.5 3.5l6 6-7.8 7.8a3 3 0 0 1-2.1.9H8.4l-2.6 2.6-2.1-2.1 2.6-2.6v-2.2a3 3 0 0 1 .9-2.1z"/><path d="M11 7l6 6"/><path d="M5 4.5c1.3 1.6 2 2.7 2 3.6a2 2 0 0 1-4 0c0-.9.7-2 2-3.6z"/>',
  gauge: '<path d="M12 14l4-4"/><path d="M3.3 19a10 10 0 1 1 17.4 0"/>',
};

function h(tag, attrs, ...children) {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v === null || v === undefined || v === false) continue;
    if (k === "class") el.className = v;
    else if (k === "style" && typeof v === "object") Object.assign(el.style, v);
    else if (k.startsWith("on")) el.addEventListener(k.slice(2), v);
    else if (k === "value") el.value = v;
    else if (k === "checked") el.checked = !!v;
    else el.setAttribute(k, v === true ? "" : v);
  }
  for (const c of children.flat(Infinity)) {
    if (c === null || c === undefined || c === false) continue;
    el.append(c instanceof Node ? c : document.createTextNode(String(c)));
  }
  return el;
}
function icon(name, cls = "") {
  const s = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  s.setAttribute("viewBox", "0 0 24 24");
  s.setAttribute("class", "i " + cls);
  s.setAttribute("aria-hidden", "true");
  s.innerHTML = ICONS[name] || ""; // лише статичні іконки з цього файлу
  return s;
}

// ---------- API ----------
const api = {
  async send(method, path, body, isForm = false) {
    const opts = { method, headers: {}, credentials: "same-origin" };
    if (body !== undefined) {
      if (isForm) opts.body = body;
      else { opts.headers["Content-Type"] = "application/json"; opts.body = JSON.stringify(body); }
    }
    let res;
    try { res = await fetch(path, opts); } catch (_) { throw new Error("Немає з'єднання з сервером"); }
    const data = res.status === 204 ? null : await res.json().catch(() => null);
    if (res.status === 401 && !path.startsWith("/api/auth/")) { state.me = null; renderLogin(); throw new Error("Сесія завершилась"); }
    if (!res.ok) throw new Error((data && data.detail) || "Помилка " + res.status);
    return data;
  },
  get(p) { return this.send("GET", p); },
  post(p, b) { return this.send("POST", p, b === undefined ? {} : b); },
  del(p) { return this.send("DELETE", p); },
  form(p, fd) { return this.send("POST", p, fd, true); },
};

// ---------- утиліти ----------
const pad = (n) => String(n).padStart(2, "0");
const money = (k) => Math.round((k || 0) / 100).toLocaleString("uk-UA") + " ₴";
const num = (v) => (v === null || v === undefined ? "—" : Math.abs(v) >= 10 || Number.isInteger(v) ? Math.round(v).toLocaleString("uk-UA") : v.toFixed(1).replace(".", ","));
const plural = (n, one, few, many) => { const a = n % 10, b = n % 100; return a === 1 && b !== 11 ? one : a >= 2 && a <= 4 && (b < 12 || b > 14) ? few : many; };
const WD = ["нд", "пн", "вт", "ср", "чт", "пт", "сб"];
const WD_GEN = ["неділі", "понеділка", "вівторка", "середи", "четверга", "пʼятниці", "суботи"];
const MONTHS = ["січень", "лютий", "березень", "квітень", "травень", "червень", "липень", "серпень", "вересень", "жовтень", "листопад", "грудень"];
const dayLabel = (iso) => { const d = new Date(iso + "T12:00"); return `${WD[d.getDay()]} ${pad(d.getDate())}.${pad(d.getMonth() + 1)}`; };
const monthName = (ym) => { const [y, m] = ym.split("-").map(Number); return `${MONTHS[m - 1]} ${y}`; };
const shiftMonth = (ym, d) => { const [y, m] = ym.split("-").map(Number); const t = new Date(y, m - 1 + d, 1); return `${t.getFullYear()}-${pad(t.getMonth() + 1)}`; };
const fmtTime = (iso) => { const d = new Date(iso); return `${pad(d.getDate())}.${pad(d.getMonth() + 1)} ${pad(d.getHours())}:${pad(d.getMinutes())}`; };

function toast(msg, err = false) {
  document.querySelectorAll(".toast").forEach((t) => t.remove());
  const t = h("div", { class: "toast" + (err ? " err" : ""), role: "status" }, icon(err ? "alert" : "ok", "sm"), msg);
  document.body.append(t);
  setTimeout(() => t.remove(), err ? 4500 : 2600);
}
async function run(btn, fn, okMsg) {
  if (btn) btn.disabled = true;
  try { const r = await fn(); if (okMsg) toast(okMsg); return r; }
  catch (e) { toast(e.message, true); throw e; }
  finally { if (btn) btn.disabled = false; }
}
// Element.append(null) вставляє текст «null» — пропускаємо порожні вузли
const add = (el, ...nodes) => el.append(...nodes.flat().filter((x) => x !== null && x !== undefined && x !== false));
function copyBtn(getText) {
  const b = h("button", { type: "button", class: "btn sm ghost", onclick: () => {
    const done = () => { b.textContent = "Скопійовано"; setTimeout(() => { b.textContent = "Копіювати"; }, 1500); };
    try { navigator.clipboard.writeText(getText()).then(done, () => toast("Не вдалося скопіювати — виділіть текст вручну", true)); }
    catch (_) { toast("Не вдалося скопіювати — виділіть текст вручну", true); }
  } }, "Копіювати");
  return b;
}
const empty = (text, ico = "inbox") => h("div", { class: "empty" }, icon(ico), h("div", {}, text));
function topbar(title, sub, ...actions) {
  return h("div", { class: "topbar" }, h("div", {}, h("h1", {}, title), sub ? h("div", { class: "sub" }, sub) : null), h("div", { class: "row" }, actions));
}
function kpi(label, value, ico, cls = "", foot = null) {
  return h("div", { class: "card kpi-tile " + cls }, h("div", { class: "kpi-top" }, h("div", { class: "kpi-ico" }, icon(ico, "sm")), h("span", { class: "kpi-label" }, label)),
    h("div", { class: "kpi-value" }, value), foot);
}
function delta(d, inverse) {
  if (d === null || d === undefined || Math.abs(d) < 0.005) return h("span", { class: "delta flat" }, "—");
  const up = d > 0;
  return h("span", { class: `delta ${up ? "up" : "down"}${inverse ? " inv" : ""}` }, `${up ? "▲" : "▼"} ${Math.round(Math.abs(d) * 100)}%`);
}

// ---------- стан, меню ----------
const state = { me: null, poll: null };
const can = (perm) => !!state.me && state.me.user.perms.includes(perm);
// [id, іконка, назва, група, право, етап роадмапу (якщо ще не готово)]
const NAV = [
  ["overview", "chart", "Огляд", "Огляд", "overview"],
  ["dialogs", "inbox", "Діалоги", "Клієнти", "dialogs", 1],
  ["content", "calendar", "Контент-план", "Маркетинг", "content"],
  ["scenarios", "send", "Сценарії", "Маркетинг", "marketing", 4],
  ["ads", "megaphone", "Реклама й статистика", "Маркетинг", "marketing", 5],
  ["assistant", "spark", "Помічник", "AI", "overview", 7],
  ["approvals", "check", "Погодження", "Система", "approvals"],
  ["journal", "book", "Журнал дій", "Система", "audit"],
  ["settings", "settings", "Налаштування", "Система", "settings"],
];
const SOON = {
  1: "Усі розмови з Instagram, Telegram, Facebook, Viber, TikTok і сайту в одній стрічці: статуси, хто чекає відповіді, відповідь з сайту, картка клієнта з MDS Connect.",
  4: "Сценарії, де система пише першою: відгук після візиту, повернення клієнтів, неявки — з лімітами й відпискою. Канали: Instagram і SMS.",
  5: "Ланцюг «реклама → діалог → запис → гроші», оцінка якості діалогів, нові оголошення на паузі до вашого підтвердження.",
  7: "Чат з AI-помічником: «скільки записів на тиждень?», «напиши пост про…» — з доступом до всіх розділів.",
};
const TABS = ["overview", "content", "dialogs", "more"];
const navItems = () => NAV.filter((n) => can(n[4]));
const route = () => (location.hash.replace(/^#\/?/, "") || "").split("?")[0];

function stopPoll() { if (state.poll) { clearTimeout(state.poll); state.poll = null; } }

function applyTheme(t) { if (t === "dark") document.documentElement.setAttribute("data-theme", "dark"); else document.documentElement.removeAttribute("data-theme"); }
applyTheme(store.get("mdsm_theme") || "light");

// ---------- вхід ----------
function renderLogin(message) {
  stopPoll();
  window.onhashchange = null;
  const root = document.getElementById("root");
  const user = h("input", { id: "login-user", autocomplete: "username", autocapitalize: "none", spellcheck: "false", placeholder: "Логін MDS Connect", value: store.get("mdsm_last_user") || "" });
  const pass = h("input", { id: "login-pass", type: "password", autocomplete: "current-password", placeholder: "Пароль" });
  const err = h("div", { class: "login-err" + (message ? "" : " hidden"), role: "alert" }, message || "");
  const showErr = (m) => { err.textContent = m; err.classList.remove("hidden"); };
  const btn = h("button", { class: "btn login-btn big", type: "submit" }, h("span", {}, "Увійти"), icon("right", "sm"));
  const done = async (r) => {
    if (r.device_token) store.set("mdsm_device", r.device_token);
    store.set("mdsm_last_user", user.value.trim());
    await boot();
  };
  const body = h("div", { class: "login-body" });
  const form = h("form", { class: "stack login-form", onsubmit: async (e) => {
    e.preventDefault();
    err.classList.add("hidden");
    if (!pass.value) return showErr("Введіть пароль");
    btn.disabled = true;
    try {
      const r = await api.post("/api/auth/login", { username: user.value.trim(), password: pass.value, device_token: store.get("mdsm_device") });
      if (r.twofa) return codeStep(r);
      await done(r);
    } catch (x) { showErr(x.message); } finally { btn.disabled = false; }
  } },
    h("label", { class: "f" }, h("span", {}, "Логін"), user),
    h("label", { class: "f" }, h("span", {}, "Пароль"), pass), err, btn);
  function codeStep(r) {
    const code = h("input", { inputmode: "numeric", autocomplete: "one-time-code", maxlength: 6, placeholder: "6 цифр", "aria-label": "Код з Telegram" });
    const remember = h("input", { type: "checkbox", checked: true });
    const cerr = h("div", { class: "login-err hidden", role: "alert" });
    const vbtn = h("button", { class: "btn login-btn big", type: "submit" }, h("span", {}, "Підтвердити"), icon("ok", "sm"));
    body.replaceChildren(h("form", { class: "stack login-form", onsubmit: async (e) => {
      e.preventDefault();
      vbtn.disabled = true;
      try {
        await done(await api.post("/api/auth/verify", { challenge_id: r.challenge_id, code: code.value.trim(), remember: remember.checked, device_label: "MDS Manager" }));
      } catch (x) { cerr.textContent = x.message; cerr.classList.remove("hidden"); } finally { vbtn.disabled = false; }
    } },
      h("div", { class: "code-head" }, h("span", { class: "code-ico" }, icon("lock")),
        h("div", {}, h("b", {}, "Підтвердження входу"), h("div", {}, "Код надіслано в Telegram-бот салону."))),
      code, cerr, h("label", { class: "row remember" }, remember, "Запамʼятати цей пристрій на 30 днів"), vbtn));
    code.focus();
  }
  body.append(form);
  root.replaceChildren(h("div", { class: "login" }, h("div", { class: "login-glow" }),
    h("div", { class: "login-card" }, h("div", { class: "login-mark" }, "M&D"), h("div", { class: "login-name" }, "MDS Manager"),
      h("div", { class: "login-sub" }, "AI-адміністратор салону M&D"), body),
    h("div", { class: "login-foot" }, icon("lock", "sm"), "Вхід тим самим логіном, що в MDS Connect")));
  (user.value ? pass : user).focus();
}

// ---------- оболонка ----------
function renderApp() {
  stopPoll();
  const items = navItems();
  let r = route();
  if (r !== "more" && !items.find((i) => i[0] === r)) r = items[0][0];
  const links = [];
  let group = null;
  for (const [id, ico, label, grp, , soon] of items) {
    if (grp !== group) { links.push(h("div", { class: "nav-group" }, grp)); group = grp; }
    const cnt = id === "approvals" && state.me.approvals_pending ? h("span", { class: "cnt" }, state.me.approvals_pending) : null;
    links.push(h("a", { href: "#/" + id, class: (id === r ? "active " : "") + (soon ? "soon-item" : "") }, icon(ico), label, soon ? h("span", { class: "soon-tag" }, "скоро") : cnt));
  }
  if (state.me.mds_url) links.push(h("div", { class: "nav-group" }, "Салон"), h("a", { href: state.me.mds_url, target: "_blank", rel: "noopener" }, icon("ext"), "MDS Connect"));
  const dark = document.documentElement.getAttribute("data-theme") === "dark";
  const u = state.me.user;
  const sidebar = h("aside", { class: "sidebar" },
    h("div", { class: "brand" }, h("div", { class: "brand-mark" }, "M&D"), h("div", {}, h("div", { class: "brand-name" }, "MDS Manager"), h("div", { class: "brand-sub" }, "AI-адміністратор"))),
    h("nav", { class: "nav" }, links),
    h("div", { class: "side-foot" }, h("span", { class: "avatar", style: { background: "#8a6a2f" } }, (u.name || "?").slice(0, 1).toUpperCase()),
      h("div", { class: "who" }, h("b", {}, u.name), h("span", {}, u.role_name)),
      h("button", { class: "icon-btn", "aria-label": "Змінити тему", title: dark ? "Світла тема" : "Темна тема", onclick: () => { const t = dark ? "light" : "dark"; applyTheme(t); store.set("mdsm_theme", t); renderApp(); } }, icon(dark ? "sun" : "moon")),
      h("button", { class: "icon-btn", "aria-label": "Вийти", title: "Вийти", onclick: async () => { await api.post("/api/auth/logout").catch(() => {}); state.me = null; renderLogin(); } }, icon("logout"))));
  const tabs = TABS.filter((t) => t === "more" || items.find((i) => i[0] === t)).map((id) => {
    const it = items.find((i) => i[0] === id) || ["more", "more", "Ще"];
    const active = id === r || (id === "more" && !TABS.includes(r));
    return h("a", { href: "#/" + id, class: active ? "active" : "", "aria-label": it[2] }, icon(it[1]), h("span", { class: "tab-label" }, it[2]));
  });
  const main = h("main", { class: "main" });
  const title = r === "more" ? "Меню" : (items.find((i) => i[0] === r) || [])[2] || "";
  main.append(h("header", { class: "mbar" }, h("div", { class: "brand-mark" }, "M&D"), h("b", { class: "grow" }, title)));
  const content = h("div", {});
  main.append(content);
  document.getElementById("root").replaceChildren(h("div", { class: "app" }, sidebar, main), h("nav", { class: "tabbar" }, tabs));
  const it = items.find((i) => i[0] === r);
  const view = r === "more" ? viewMore : it && it[5] ? () => viewSoon(it) : VIEWS[r];
  content.append(h("div", { class: "skeleton" }, h("i"), h("i"), h("i")));
  Promise.resolve(view(content)).catch((e) => content.replaceChildren(empty(e.message, "alert")));
}

function viewMore(el) {
  el.replaceChildren(topbar("Меню", state.me.user.name + " · " + state.me.user.role_name),
    h("div", { class: "card" }, navItems().map(([id, ico, label, , , soon]) => h("a", { href: "#/" + id, class: "row", style: { padding: "12px 4px", borderBottom: "1px solid var(--line)", color: "inherit" } },
      icon(ico), h("span", { class: "grow" }, label), soon ? h("span", { class: "chip plain" }, "скоро") : icon("right", "sm")))));
}
function viewSoon(it) {
  const el = document.querySelector(".main > div");
  el.replaceChildren(topbar(it[2], `Етап ${it[5]} роадмапу`),
    h("div", { class: "card soon-card" }, icon(it[1], "lg"), h("h2", {}, "Скоро"), h("p", {}, SOON[it[5]])));
}

// ---------- огляд ----------
async function viewOverview(el) {
  const d = await api.get("/api/overview");
  const out = [];
  const reportBtn = can("marketing") && d.ai_enabled
    ? h("button", { class: "btn", disabled: d.report_running, onclick: (e) => run(e.currentTarget, () => api.post("/api/overview/report"), "Аналіз запущено — оновиться за хвилину").then(() => setTimeout(renderApp, 1500)) },
      icon("refresh", "sm"), d.report_running ? "Готується…" : "Оновити аналіз") : null;
  out.push(topbar("Огляд", d.day ? "Дані за " + dayLabel(d.day.day) + " проти середнього за 7 днів" : "", reportBtn));
  if (d.approvals_pending) out.push(h("a", { href: "#/approvals", class: "callout", style: { color: "inherit" } }, icon("check"), h("div", {}, h("b", {}, `Чекають погодження: ${d.approvals_pending}`), h("div", { class: "muted-note" }, "AI нічого не робить без вашого «Підтвердити»."))));
  if (d.period) {
    const p = d.period;
    out.push(h("div", { class: "grid kpi" },
      kpi("Записів за " + p.days + " днів", num(p.bookings), "calendar", "dark"),
      kpi("Прийшли", `${num(p.came)}${p.bookings ? " · " + Math.round((p.came / p.bookings) * 100) + "%" : ""}`, "check"),
      kpi("Виручка", money(p.revenue_kop), "coins"),
      kpi("Реклама", money(p.ad_spend_minor), "megaphone"),
      kpi("Реклама на візит", p.cost_per_visit_minor === null ? "—" : money(p.cost_per_visit_minor), "trend", "accent"),
      kpi("Підписники Instagram", p.followers === null ? "—" : num(p.followers), "users")));
    p.notes.forEach((n) => out.push(h("p", { class: "muted-note" }, n)));
  }
  const grid = h("div", { class: "grid two section" });
  if (d.day) {
    const card = h("div", { class: "card" }, h("div", { class: "card-head" }, h("h3", {}, "Вчора, " + dayLabel(d.day.day))));
    if (!d.day.groups.length) add(card, empty("Даних за день ще немає — підключіть MDS Connect, Meta чи Google Ads.", "chart"));
    d.day.groups.forEach((g) => add(card, h("div", { class: "table-wrap" }, h("table", {},
      h("thead", {}, h("tr", {}, h("th", {}, g.name), h("th", { class: "num" }, "Вчора"), h("th", { class: "num" }, "Сер. 7 дн"), h("th", { class: "num" }, "Зміна"))),
      h("tbody", {}, g.rows.map((x) => h("tr", {}, h("td", {}, x.label), h("td", { class: "num" }, h("b", {}, x.money ? money(x.value) : num(x.value))),
        h("td", { class: "num muted" }, x.money ? money(x.avg) : num(x.avg)), h("td", { class: "num" }, delta(x.delta, x.inverse)))))))));
    d.day.notes.forEach((n) => add(card, h("p", { class: "muted-note" }, n)));
    grid.append(card);
  }
  if ("report" in d) {
    const card = h("div", { class: "card" }, h("div", { class: "card-head" }, h("h3", {}, "AI-аналітик"), d.report ? h("span", { class: "muted small" }, `за ${dayLabel(d.report.day)} · $${d.report.cost_usd.toFixed(2)}`) : null));
    if (d.report_error) add(card, h("div", { class: "callout" }, icon("alert"), d.report_error));
    if (!d.report) add(card, empty(d.ai_enabled ? "Звіту ще немає. Він зʼявляється щоранку о 07:05." : "Потрібен ANTHROPIC_API_KEY.", "spark"));
    else {
      const rp = d.report;
      add(card, h("p", {}, rp.summary));
      if ((rp.highlights || []).length) add(card, h("ul", { class: "hl-list" }, rp.highlights.map((x) => h("li", {}, (x.tone === "good" ? "✅ " : x.tone === "warn" ? "⚠️ " : ""), x.text))));
      const pri = { high: "Сьогодні", medium: "Цього тижня", low: "За нагоди" };
      if ((rp.actions || []).length) add(card, h("h3", { class: "section" }, "Що зробити"), h("div", {}, rp.actions.map((a) => h("div", { class: "act" },
        h("div", { class: "pri " + a.priority }, pri[a.priority] || ""), h("b", {}, a.title), h("div", { class: "muted small" }, a.why), h("div", { class: "small" }, a.how)))));
      (rp.ad_ideas || []).forEach((a) => {
        const text = `${a.headline}\n\n${a.primary_text}\n\n${a.cta}`;
        add(card, h("div", { class: "act" }, h("div", { class: "row" }, h("span", { class: "chip plain" }, a.service), h("span", { class: "muted small" }, a.audience + " · " + a.budget_hint)),
          h("b", {}, a.headline), h("div", { class: "row-between" }, h("span", { class: "muted small" }, "Текст оголошення"), copyBtn(() => text)), h("div", { class: "text-box" }, text),
          h("div", { class: "row-between" }, h("span", { class: "muted small" }, "Промпт для зображення"), copyBtn(() => a.image_prompt)), h("div", { class: "text-box small" }, a.image_prompt)));
      });
    }
    grid.append(card);
  }
  out.push(grid);
  if (d.ads) out.push(h("div", { class: "card section" }, h("div", { class: "card-head" }, h("h3", {}, "Реклама: що окупається")),
    d.ads.length ? h("div", { class: "table-wrap" }, h("table", {}, h("thead", {}, h("tr", {}, ["Оголошення", "Витрати", "Кліки", "Звернення", "Записи", "Прийшли", "Ціна візиту"].map((t, i) => h("th", { class: i ? "num" : "" }, t)))),
      h("tbody", {}, d.ads.map((a) => h("tr", {}, h("td", {}, h("b", {}, a.name), h("div", { class: "muted small" }, a.platform === "google" ? "Google Ads" : a.campaign)),
        h("td", { class: "num" }, money(a.spend_minor)), h("td", { class: "num" }, num(a.clicks)), h("td", { class: "num" }, num(a.conversations)),
        h("td", { class: "num" }, num(a.bookings)), h("td", { class: "num" }, num(a.came)),
        h("td", { class: "num" }, a.cost_per_visit_minor === null ? h("span", { class: "chip st-pending" }, "без візитів") : h("b", {}, money(a.cost_per_visit_minor)))))))) : empty("Даних реклами ще немає.", "megaphone")));
  if (d.posts && d.posts.length) out.push(h("div", { class: "card section" }, h("div", { class: "card-head" }, h("h3", {}, "Пости за 30 днів: що заходить")),
    h("div", { class: "table-wrap" }, h("table", {}, h("thead", {}, h("tr", {}, ["Дата", "Пост", "Охоплення", "Перегляди", "Лайки", "Збереження"].map((t, i) => h("th", { class: i > 1 ? "num" : "" }, t)))),
      h("tbody", {}, d.posts.map((x) => h("tr", {}, h("td", {}, dayLabel(x.date)), h("td", {}, x.permalink && x.permalink.startsWith("https://") ? h("a", { href: x.permalink, target: "_blank", rel: "noopener" }, x.caption || "без підпису") : x.caption),
        h("td", { class: "num" }, num(x.reach)), h("td", { class: "num" }, num(x.views)), h("td", { class: "num" }, num(x.likes)), h("td", { class: "num" }, num(x.saved)))))))));
  if (d.sources && d.sources.length) out.push(h("div", { class: "card section" }, h("div", { class: "card-head" }, h("h3", {}, "Звідки записи")),
    h("div", { class: "table-wrap" }, h("table", {}, h("thead", {}, h("tr", {}, ["Джерело", "Записи", "Прийшли", "Неявки", "Виручка"].map((t, i) => h("th", { class: i ? "num" : "" }, t)))),
      h("tbody", {}, d.sources.map((x) => h("tr", {}, h("td", {}, x.source), h("td", { class: "num" }, x.bookings), h("td", { class: "num" }, x.came), h("td", { class: "num" }, x.no_show || ""), h("td", { class: "num" }, x.revenue_kop ? money(x.revenue_kop) : ""))))))));
  if (d.ai_month) out.push(h("div", { class: "card section" }, h("div", { class: "card-head" }, h("h3", {}, `AI цього місяця: $${d.ai_month.total.toFixed(2)}${d.ai_month.budget ? " з $" + d.ai_month.budget.toFixed(0) : ""}`)),
    d.ai_month.rows.length ? h("div", { class: "table-wrap" }, h("table", {}, h("tbody", {}, d.ai_month.rows.map((x) => h("tr", {}, h("td", {}, `${x.provider} / ${x.kind}`), h("td", { class: "num" }, x.calls), h("td", { class: "num" }, "$" + x.cost.toFixed(2))))))) : h("p", { class: "muted-note" }, "Витрат ще немає.")));
  el.replaceChildren(...out);
}

// ---------- контент-план ----------
const STATUS = { idea: "На розгляді", approved: "Підтверджено · фото", ready: "Готово до публікації", published: "Опубліковано" };
const FILTERS = [["all", "Усі"], ["idea", "На розгляді"], ["approved", "Чекають фото"], ["ready", "Готові"], ["published", "Опубліковані"]];
const content = { month: null, filter: "all" };
const media = (name, thumb) => `/api/content/media/${encodeURIComponent(name)}${thumb ? "?thumb=1" : ""}`;

function uploadButton(label, itemId, onDone) {
  const input = h("input", { type: "file", accept: "image/jpeg,image/png,image/webp", class: "hidden-file", multiple: !itemId, "aria-label": label });
  const btn = h("button", { type: "button", class: "btn sm", onclick: () => input.click() }, icon("image", "sm"), label);
  input.addEventListener("change", async () => {
    if (!input.files.length) return;
    const fd = new FormData();
    [...input.files].forEach((f) => fd.append("files", f));
    if (itemId) fd.append("item_id", itemId);
    const r = await run(btn, () => api.form("/api/content/photos", fd));
    if (r.errors.length) toast(r.errors.join("; "), true); else toast(`Додано фото: ${r.added.length}`);
    onDone();
  });
  return h("span", {}, btn, input);
}

function itemCard(it, d, photos, reload) {
  const isPost = it.kind === "post";
  const act = (action, body, okMsg) => (e) => run(e.currentTarget, () => api.post(`/api/content/items/${it.id}/${action}`, body || {}), okMsg).then(reload);
  const head = h("div", { class: "row-between" }, h("b", {}, `${dayLabel(it.date)} · ${isPost ? d.post_time : d.story_time}`),
    h("span", { class: "row" }, h("span", { class: "chip plain k-" + it.kind }, isPost ? "Пост" : "Сторіс"), h("span", { class: "chip s-" + it.status }, STATUS[it.status])));
  if (it.busy_text) return h("div", { class: "card post-card" }, head, h("div", { class: "callout section" }, icon("spark"), "AI готує новий варіант — сторінка оновиться сама."));
  const text = it.caption + (it.hashtags.length ? "\n\n" + it.hashtags.map((t) => "#" + t).join(" ") : "");
  const card = h("div", { class: "card post-card", id: "item-" + it.id }, head,
    h("h3", { class: "topic" }, it.topic), it.topics_tried > 1 ? h("div", { class: "muted small" }, "Тема №" + it.topics_tried) : null,
    h("div", { class: "row-between section" }, h("span", { class: "muted small" }, isPost ? "Підпис і хештеги" : "Текст на сторіс"), copyBtn(() => text)),
    h("div", { class: "text-box" }, text),
    h("p", { class: "small" }, h("span", { class: "muted" }, isPost ? "Заклик: " : "Наліпка: "), it.cta));
  const src = photos.find((p) => p.id === it.photo_id);
  if (src) {
    const pics = h("div", { class: "pics" }, h("div", { class: "pic" }, h("a", { href: media(src.file), target: "_blank" }, h("img", { src: media(src.file, true), alt: "Фото салону", loading: "lazy" })), h("div", { class: "cap" }, "Ваше фото")));
    if (it.image) pics.append(h("div", { class: "pic" }, h("a", { href: media(it.image), target: "_blank" }, h("img", { src: media(it.image, true), alt: "Оброблене фото", loading: "lazy" })), h("div", { class: "cap" }, "Після обробки AI")));
    else if (it.busy_image) pics.append(h("div", { class: "pic wait" }, "AI підправляє фото…"));
    add(card, pics);
  } else {
    const sel = h("select", { "aria-label": "Фото з бібліотеки" }, photos.map((p) => h("option", { value: p.id }, `#${p.id} · ${p.category_name}${p.description ? " — " + p.description.slice(0, 50) : ""}`)));
    add(card, h("div", { class: "callout section" }, icon("image"), h("div", {}, h("b", {}, "Потрібне фото. "), it.photo_note || "Оберіть або завантажте фото.")),
      h("div", { class: "row" }, uploadButton("Завантажити своє", it.id, reload)),
      photos.length ? h("div", { class: "inline-form" }, sel, h("button", { class: "btn sm", onclick: (e) => run(e.currentTarget, () => api.post(`/api/content/items/${it.id}/photo`, { photo_id: Number(sel.value) })).then(reload) }, "Взяти це фото")) : null);
  }
  if (it.error) add(card, h("div", { class: "callout section" }, icon("alert"), it.error));
  const counter = (n, what, then) => (n ? h("p", { class: "muted-note" }, `Відхилень ${what}: ${n} з ${d.max_rejections}. Після ${d.max_rejections}-го ${then}.`) : null);
  if (it.status === "idea") {
    const reason = h("input", { maxlength: 500, placeholder: "Що не так? (необовʼязково)", "aria-label": "Причина відхилення" });
    add(card, h("div", { class: "row section" }, h("button", { class: "btn primary", onclick: act("approve", null, "Підтверджено") }, icon("ok", "sm"), "Підтвердити")),
      h("div", { class: "inline-form" }, reason, h("button", { class: "btn danger", onclick: (e) => act("reject", { reason: reason.value }, "AI переробляє")(e) }, "Відхилити")),
      counter(it.rejections, "цієї теми", "AI придумає нову тему з нуля"));
  } else if (it.status === "approved" && src && !it.busy_image) {
    if (it.image_status === "ready") {
      const reason = h("input", { maxlength: 500, placeholder: "Що змінити на фото?", "aria-label": "Що змінити на фото" });
      add(card, h("div", { class: "row section" }, h("button", { class: "btn primary", onclick: act("image-approve", null, "Фото підтверджено") }, icon("ok", "sm"), "Фото підходить")),
        h("div", { class: "inline-form" }, reason, h("button", { class: "btn danger", onclick: (e) => act("image-reject", { reason: reason.value })(e) }, "Переробити")),
        counter(it.image_rejections, "фото", "треба буде обрати інше фото"));
    } else {
      add(card, h("div", { class: "row section" }, d.can_edit_photos ? h("button", { class: "btn primary", onclick: act("image-retry") }, "Обробити фото") : null,
        h("button", { class: "btn", onclick: act("image-original", null, "Готово") }, "Взяти без обробки")));
    }
  } else if (it.status === "ready") {
    const img = it.image || (src && src.file);
    add(card, h("div", { class: "row section" }, img ? h("a", { class: "btn primary", href: media(img) + "?download=1" }, icon("image", "sm"), "Завантажити фото") : null,
      copyBtn(() => text), h("button", { class: "btn ghost", onclick: act("published", null, "Позначено як опубліковане") }, "Опубліковано ✓")));
  }
  return card;
}

async function viewContent(el) {
  stopPoll();
  const ym = content.month || "";
  const d = await api.get("/api/content" + (ym ? "?month=" + ym : ""));
  content.month = d.month;
  const reload = () => { if (route() === "content") viewContent(el); };
  const by = {};
  d.items.forEach((i) => { by[i.status] = (by[i.status] || 0) + 1; });
  const go = (delta) => () => { content.month = shiftMonth(d.month, delta); viewContent(el); };
  const genBtn = d.can_write && d.missing && !d.generating
    ? h("button", { class: "btn primary", onclick: (e) => run(e.currentTarget, () => api.post("/api/content/generate", { month: d.month }), "AI придумує ідеї (1–2 хв)").then(reload) }, icon("spark", "sm"), `Згенерувати ідеї · ${d.missing}`) : null;
  const out = [topbar("Контент-план",
    `Instagram і Facebook · ${monthName(d.month)} · ${d.posts} ${plural(d.posts, "пост", "пости", "постів")} (що${WD_GEN[(d.post_weekday + 1) % 7]}) і ${d.stories} сторіс (раз на ${d.story_every} ${plural(d.story_every, "день", "дні", "днів")})`,
    h("button", { class: "btn ghost", onclick: go(-1) }, icon("left", "sm"), MONTHS[Number(shiftMonth(d.month, -1).slice(5)) - 1]),
    h("button", { class: "btn ghost", onclick: go(1) }, MONTHS[Number(shiftMonth(d.month, 1).slice(5)) - 1], icon("right", "sm")), genBtn)];
  if (!d.can_write) out.push(h("div", { class: "callout" }, icon("alert"), "Щоб AI пропонував ідеї, потрібен ANTHROPIC_API_KEY."));
  if (!d.can_edit_photos) out.push(h("div", { class: "callout" }, icon("image"), "Обробка фото вимкнена (немає GEMINI_API_KEY або оплати в Google AI Studio) — фото можна брати без обробки."));
  if (d.generating) out.push(h("div", { class: "callout" }, icon("spark"), "AI придумує ідеї на місяць. Сторінка оновиться сама."));
  if (d.error) out.push(h("div", { class: "callout" }, icon("alert"), d.error));
  out.push(h("div", { class: "grid kpi" }, kpi("Чекають вашого рішення", by.idea || 0, "alert", "dark"), kpi("Підтверджено, готуємо фото", by.approved || 0, "image"),
    kpi("Готово до публікації", by.ready || 0, "check", "accent"), kpi("Опубліковано", by.published || 0, "send")));
  const photosCard = h("div", { class: "card section" }, h("div", { class: "card-head" }, h("h3", {}, `Фото салону · ${d.photos.length}`), uploadButton("Завантажити фото", null, reload)),
    h("p", { class: "muted-note" }, "Лише фото, на публікацію яких клієнтка погодилась. Геолокація й дані камери видаляються автоматично."));
  photosCard.append(d.photos.length ? h("div", { class: "photo-grid section" }, d.photos.map((p) => h("div", { class: "photo" },
    h("a", { href: media(p.file), target: "_blank" }, h("img", { src: media(p.file, true), alt: p.description || "Фото салону", loading: "lazy" })),
    h("div", { class: "cap" }, `#${p.id} · ${p.category_name}`), h("div", { class: "small muted" }, p.busy ? "AI описує фото…" : (p.description || "Без опису").slice(0, 140)),
    h("button", { class: "btn sm ghost", style: { color: "var(--danger)", paddingLeft: 0 }, onclick: (e) => run(e.currentTarget, () => api.del("/api/content/photos/" + p.id), "Видалено").then(reload) }, "Видалити"))))
    : h("p", { class: "muted-note" }, "Фото ще немає. Завантажте 10–20 фото: роботи майстрів, інтерʼєр, процес — AI підбере їх до постів."));
  out.push(photosCard);
  out.push(h("div", { class: "seg section", role: "tablist" }, FILTERS.map(([k, l]) => h("button", { class: content.filter === k ? "on" : "", onclick: () => { content.filter = k; viewContent(el); } }, l + (by[k] ? " · " + by[k] : "")))));
  const shown = d.items.filter((i) => content.filter === "all" || i.status === content.filter);
  if (!d.items.length) out.push(h("div", { class: "card section" }, h("h3", {}, "Як це працює"), h("ol", { class: "hl-list section" },
    h("li", {}, "Завантажте фото салону — AI сам опише, що на них."),
    h("li", {}, "Натисніть «Згенерувати ідеї»: AI розпише пости й сторіс на місяць."),
    h("li", {}, `Кожну ідею підтвердіть або відхиліть. Після ${d.max_rejections}-го відхилення AI придумує іншу тему.`),
    h("li", {}, "AI трохи підправляє ваше фото під стиль стрічки, не змінюючи результат роботи."),
    h("li", {}, "Завантажте готове фото, скопіюйте текст — і публікуйте."))));
  else out.push(shown.length ? h("div", { class: "items-grid section" }, shown.map((i) => itemCard(i, d, d.photos, reload))) : empty("У цьому фільтрі порожньо.", "calendar"));
  if (by.idea && !d.busy) out.push(h("details", { class: "section" }, h("summary", { class: "muted small" }, "Почати ідеї місяця заново"),
    h("div", { class: "card section" }, h("p", { class: "small" }, "Усі непідтверджені ідеї буде видалено, підтверджені й готові лишаться."),
      h("button", { class: "btn danger", onclick: (e) => run(e.currentTarget, () => api.post("/api/content/reset", { month: d.month }), "Ідеї видалено").then(reload) }, `Видалити ${by.idea} ідей`))));
  el.replaceChildren(...out);
  if (d.busy) state.poll = setTimeout(reload, 8000);
}

// ---------- погодження, журнал, налаштування ----------
async function viewApprovals(el) {
  const rows = await api.get("/api/approvals");
  const reload = () => viewApprovals(el).then(refreshMe);
  el.replaceChildren(topbar("Погодження", "Критичні дії AI виконує лише після вашого «Підтвердити»"),
    rows.length ? h("div", { class: "grid" }, rows.map((a) => {
      const reason = h("input", { maxlength: 500, placeholder: "Коментар (необовʼязково)", "aria-label": "Коментар" });
      return h("div", { class: "card" }, h("div", { class: "row-between" }, h("span", { class: "chip st-pending" }, a.kind_name), h("span", { class: "muted small" }, fmtTime(a.created_at) + " · " + a.requested_by)),
        h("h3", { class: "section" }, a.title),
        h("div", { class: "inline-form" }, reason,
          h("button", { class: "btn primary", onclick: (e) => run(e.currentTarget, () => api.post("/api/approvals/" + a.id, { approve: true, reason: reason.value }), "Підтверджено").then(reload) }, "Підтвердити"),
          h("button", { class: "btn danger", onclick: (e) => run(e.currentTarget, () => api.post("/api/approvals/" + a.id, { approve: false, reason: reason.value }), "Відхилено").then(reload) }, "Відхилити")));
    })) : h("div", { class: "card" }, empty("Нічого не чекає погодження. Тут зʼявлятимуться публікації, розсилки й реклама, які підготував AI.", "check")));
}
async function viewJournal(el) {
  const rows = await api.get("/api/audit?limit=200");
  el.replaceChildren(topbar("Журнал дій", "Хто що робив у MDS Manager — люди й AI"),
    h("div", { class: "card" }, rows.length ? h("div", { class: "table-wrap" }, h("table", { class: "journal" }, h("thead", {}, h("tr", {}, h("th", {}, "Коли"), h("th", {}, "Хто"), h("th", {}, "Дія"), h("th", {}, "Деталі"))),
      h("tbody", {}, rows.map((x) => h("tr", {}, h("td", {}, fmtTime(x.at)), h("td", {}, x.actor), h("td", {}, x.action), h("td", { class: "muted" }, [x.target, x.details].filter(Boolean).join(" · "))))))) : empty("Записів ще немає.", "book")));
}
async function viewSettings(el) {
  const s = await api.get("/api/settings");
  el.replaceChildren(topbar("Налаштування", "Підключення, ліміти AI, розклад контенту"),
    h("div", { class: "grid two" },
      h("div", { class: "card" }, h("div", { class: "card-head" }, h("h3", {}, "Підключення")), s.connections.map((c) => h("div", { class: "row-between act" },
        h("div", {}, h("b", {}, c.name), h("div", { class: "muted small" }, c.what)), h("span", { class: "chip " + (c.ok ? "st-completed" : "st-pending") }, c.ok ? "Працює" : "Не підключено")))),
      h("div", { class: "card" }, h("div", { class: "card-head" }, h("h3", {}, "AI і контент")),
        h("div", { class: "act" }, h("b", {}, s.ai_budget > 0 ? `Ліміт на AI: $${s.ai_spent.toFixed(2)} з $${s.ai_budget.toFixed(0)} цього місяця` : `AI цього місяця: $${s.ai_spent.toFixed(2)} · без ліміту`), h("div", { class: "muted small" }, "Змінюється в .env на сервері (AI_MONTHLY_BUDGET_USD).")),
        h("div", { class: "act" }, h("b", {}, `Пост що${WD_GEN[(s.content.post_weekday + 1) % 7]}, сторіс раз на ${s.content.story_every} ${plural(s.content.story_every, "день", "дні", "днів")}`),
          h("div", { class: "muted small" }, s.content.auto_day ? `Ідеї на наступний місяць — ${s.content.auto_day}-го числа.` : "Автогенерація ідей вимкнена.")),
        h("div", { class: "act" }, h("b", {}, s.analyst_daily ? "Щоденний AI-звіт о 07:05 увімкнено" : "Щоденний AI-звіт вимкнено")),
        h("p", { class: "muted-note" }, "Редагування цих налаштувань на сайті — на етапі 2 (база знань і налаштування агента)."))));
}

const VIEWS = { overview: viewOverview, content: viewContent, approvals: viewApprovals, journal: viewJournal, settings: viewSettings };

async function refreshMe() {
  try { state.me = await api.get("/api/me"); } catch (_) { }
}
async function boot() {
  try { state.me = await api.get("/api/me"); } catch (_) { return renderLogin(); }
  window.onhashchange = renderApp;
  renderApp();
}
boot();
