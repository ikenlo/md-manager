# Аудит дизайн-системи MDS Connect → MDs Manager

Дата: 12.11.2026 · Джерело: `ikenlo/m-d`, `main` @ `115be09` («Реліз 0.3.0 — канон») ·
Ціль: `MDsManager/frontend` (React 18 + Vite + Tailwind) на гілці `claude/mdsmanager-phase1`.

Документ лише описує стан. Код Manager у межах цього аудиту не змінювався.

---

## Tech Stack

| Що | MDS Connect | MDs Manager (Фаза 1) |
|---|---|---|
| Фреймворк | **Ванільний JS, без збірки.** Один файл `server/mds/web/static/app.js` (~4 800 рядків, 388 КБ) | React 18.3 + TypeScript 5.6 + Vite 5 |
| Стилі | Один `style.css` (~1 350 рядків, 98 КБ), CSS-змінні в `:root`, класи БЕМ-подібні (`.btn.primary`, `.kpi-tile.dark`) | Tailwind 3.4, токени в `tailwind.config.js` |
| Рендер DOM | Власна функція `h(tag, attrs, ...children)`, без `innerHTML` з даними (інваріант 12) | JSX |
| Маршрутизація | Hash-роутер: `location.hash` → `VIEWS[route](main)`, `window.onhashchange = renderApp` | `react-router-dom` 6 |
| Стан | Глобальний об'єкт `state = { user, services, masters, materials, settings }` + замикання у view | Zustand 5 (`useAuth`, `useInbox`) |
| HTTP | Власний `api` на `fetch`: таймаут, дедуплікація GET, обробка 401/403/409 | axios 1.7, лише інтерсептор для Bearer |
| Іконки | **Власний набір inline-SVG** (~65 шт., `ICONS` + `icon(name, cls)`), стиль Lucide/Feather: stroke 1.8, `round` | `lucide-react` 0.468 |
| Шрифти | Локальні `woff2`: Manrope 400–700, Cormorant Garamond 500–600 (кирилиця + латиниця окремо, `unicode-range`) | Google Fonts через `@import` в `index.css` |
| PWA | `manifest.webmanifest`, `sw.js` (network-first для статики, `/api/` не кешується), іконки 192/512 | Немає |
| Обгортки | `apps/windows` (Electron), `apps/android` (WebView) — лише оболонки над веб-панеллю | — |
| Тести UI | `ui-tests/smoke.js` (Playwright) у CI | — |
| Безпека фронту | Суворий CSP: `script-src 'self'; font-src 'self'; connect-src 'self'; frame-ancestors 'none'` | CSP не задано |

Висновок: **копіювати код компонентів Connect буквально не вийде** (там немає компонентів у React-розумінні),
але **CSS-токени, класи й поведінку можна перенести один до одного.**

---

## Folder Structure

```
m-d/
├── server/
│   ├── mds/
│   │   ├── api/            # FastAPI: app.py (CSP, middleware), deps.py, routers/*.py (auth, calendar, ext_api …)
│   │   ├── services/       # уся бізнес-логіка (finance, orders, bookings, notifications, ai/ …)
│   │   ├── bot/            # aiogram 3
│   │   ├── web/static/     # ← ВЕСЬ ФРОНТЕНД
│   │   │   ├── index.html  # порожній #root + style.css + app.js (?v=__V__ для кеш-бастингу)
│   │   │   ├── app.js      # h(), api, session, NAV, VIEWS.*, sheets, toast …
│   │   │   ├── style.css   # токени + усі компоненти
│   │   │   ├── sw.js, manifest.webmanifest, icon.svg, icon-192/512.png
│   │   │   ├── fonts/      # manrope-{cyr,lat}.woff2, cormorant-{cyr,lat}.woff2
│   │   │   └── vendor/     # mermaid.min.js (лише для екрана «Логіка системи»)
│   │   └── models.py, config.py, security.py, clock.py, money.py …
│   ├── migrations/         # Alembic
│   └── tests/
├── apps/{windows,android}/ # оболонки
├── ui-tests/               # Playwright smoke
└── docs/                   # CANON, FINANCE, API, SECURITY …
```

Усередині `app.js` порядок такий: утиліти (`store`, `session`, `api`, `h`, форматери) → примітиви UI
(`icon`, `avatar`, `toast`, `field`, `select`, `seg`, `kpi`, `emptyState`, `openSheet`) → `NAV` → `boot` /
`renderLogin` / `renderApp` → `VIEWS.<name>` по одному на екран.

---

## Auth Flow (step by step)

1. **Старт** — `boot()`: реєструє service worker, тягне версію з `/api/health`.
   Якщо в `localStorage["mds_token"]` немає токена → `renderLogin()`.
2. **Перевірка сесії** — `GET /api/auth/me`. Помилка → екран входу. Успіх → `loadRefs()` (послуги, персонал,
   матеріали, налаштування паралельно) → `renderApp()`.
3. **Екран входу** — поля «Логін» (не email!) і «Пароль». Останній логін запам'ятовується в `mds_last_user`
   і фокус одразу йде в пароль. Є кнопка «показати пароль» (`.pw-eye`), підказка «Увімкнено Caps Lock»,
   блок помилки з анімацією `shake` на картці, спінер у кнопці (`.btn.loading`).
4. **`POST /api/auth/login`** `{ username, password, device_token }`.
   Бекенд: блокування за IP (`check_ip` / `ip_failed`), журнал кожної спроби (`log_login`).
5. **2FA (за потреби)** — відповідь `{ twofa: true, challenge_id, expires_in }` → другий крок у тій самій
   картці: 6 полів по одній цифрі (вставка з буфера розкладає код, Backspace/стрілки між полями,
   авто-сабміт на 6-й цифрі), таймер «Код дійсний ще 4:59», «Надіслати код ще раз», чекбокс
   «Запам'ятати цей пристрій на 30 днів». Код приходить у Telegram-бот. `POST /api/auth/login/verify`.
6. **Успіх** — `{ token, idle_minutes, user, device_token? }` → токен у `localStorage["mds_token"]`,
   `device_token` у `mds_device`, `location.hash = ""`, повторний `boot()`.
7. **Захищені маршрути** — окремого guard немає: `renderApp()` викликається лише з валідним `state.user`;
   маршрут, якого немає в `NAV[role]`, тихо підміняється першим пунктом меню ролі.
   Права перевіряє **сервер** (`actor.require`), UI лише ховає пункти.
8. **Продовження сесії** — `session.tick()` раз на хвилину: якщо токену > 10 хв і користувач активний
   (< 5 хв без дій) → `POST /api/auth/refresh` → новий токен. TTL токена — 12 год (`MDS_TOKEN_TTL_HOURS`).
9. **Автовихід за бездіяльністю** — 30 хв без `pointerdown/keydown/touchstart` (`MDS_IDLE_MINUTES`) →
   `logout()` + тост «Автовихід: 30 хвилин без дій».
10. **Протухла сесія** — будь-яка відповідь `401` (крім самого логіну) у `api.send` → `logout()` +
    помилка «Сесія завершилась».
11. **Вихід** — `logout()`: видаляє `mds_token` і фінансовий токен із `sessionStorage`, обнуляє `state.user`,
    малює екран входу. «Вийти на всіх пристроях» — `POST /api/auth/logout-all`.
12. **Додатковий бар'єр «Фінанси»** — `403 finance_pin_required` → шторка з PIN → `X-Finance-Token`
    у `sessionStorage` (до закриття вкладки), запит автоматично повторюється.

```js
// app.js — серце auth: один fetch-обгортник на всі запити
if (res.status === 401 && path !== "/api/auth/login") {
  logout();
  throw new Error("Сесія завершилась");
}
if (res.status === 403 && data && (data.error === "finance_pin_required" || data.error === "finance_pin_setup") && !retried) {
  if (await financePinPrompt(data.error === "finance_pin_setup")) return this.send(method, path, body, true);
}
if (res.status === 409 && data && data.error === "version_conflict") { /* … «Дані змінилися — оновіть» … */ }
```

**Порівняння з Manager:** у Manager вхід через email, немає обробки `401` (протухлий токен лишається
в `localStorage`, `ProtectedRoute` перевіряє лише наявність токена), немає idle-виходу й refresh,
немає 2FA. `user` дублюється в `localStorage["mds.user"]` замість `GET /api/auth/me` на старті.

---

## Layout Components (with code)

### App shell

Десктоп: `.app` = sidebar 240 px + `.main` (макс. 1360 px). ≤ 900 px: sidebar ховається, з'являються
липкий верхній `.mbar` і нижній `.tabbar` (4 вкладки + «+» посередині).

```css
.app { display: flex; min-height: 100vh; }
.main { flex: 1; min-width: 0; padding: 22px 28px 90px; max-width: 1360px; }
@media (max-width: 900px) {
  .sidebar { display: none; }
  .main { padding: 14px 16px 96px; }
  .tabbar { display: flex; position: fixed; bottom: 0; left: 0; right: 0; z-index: 20;
    background: var(--surface); border-top: 1px solid var(--line);
    padding: 6px max(4px, env(safe-area-inset-left, 0px)) calc(6px + env(safe-area-inset-bottom, 0px)) max(4px, env(safe-area-inset-right, 0px)); }
}
```

### Sidebar

Темно-зелена (`--brand`), лого-плашка з золотим градієнтом, групи навігації дрібними капсом,
активний пункт — напівпрозоре золото + **внутрішня золота смужка зліва**. Унизу — аватар, ім'я, роль,
кнопки «Повідомити про помилку», «Тема», «Вийти».

```js
const NAV = { director: [
  ["dashboard", "chart", "Фінанси", "Огляд"],     // [route, icon, label, group]
  ["calendar", "calendar", "Календар", "Робота"],
  /* … */
]};
// renderApp()
h("aside", { class: "sidebar" },
  h("div", { class: "brand" }, h("div", { class: "brand-mark" }, "M&D"),
    h("div", {}, h("div", { class: "brand-name" }, "MDS Connect"), h("div", { class: "brand-sub" }, "Салон M&D"))),
  h("nav", { class: "nav" }, navLinks),          // <a href="#/route" class="active">
  h("div", { class: "side-foot" }, avatar(user.full_name), /* who */, themeBtn, logoutBtn));
```

```css
.sidebar { width: 240px; background: var(--brand); color: var(--brand-ink); padding: 18px 12px;
  position: sticky; top: 0; height: 100vh; overflow-y: auto; display: flex; flex-direction: column; }
.brand-mark { width: 38px; height: 38px; border-radius: var(--r-md); display: grid; place-items: center;
  background: linear-gradient(145deg, #d8b46a, #a9823b); color: #1a1408; font: 700 var(--fs-sm) var(--sans); }
.brand-name { font: 600 var(--fs-xl)/1 var(--serif); color: #f3e6c4; }
.nav-group { font-size: var(--fs-2xs); letter-spacing: 1.4px; text-transform: uppercase; color: rgba(245,241,230,.42); padding: 14px 12px 6px; }
.nav a { display: flex; align-items: center; gap: 12px; padding: 8px 12px; border-radius: var(--r-sm);
  color: rgba(245,241,230,.78); font-weight: 600; font-size: var(--fs-sm); }
.nav a:hover  { background: rgba(255,255,255,.06); color: #fff; }
.nav a.active { background: rgba(232,212,166,.14); color: #f3e6c4; box-shadow: inset 2px 0 0 var(--gold-soft); }
```

### Topbar (заголовок сторінки)

```js
function topbar(title, ...actions) {      // перший рядковий action = підзаголовок
  return h("div", { class: "topbar" },
    h("div", {}, h("h1", {}, title), sub ? h("div", { class: "sub" }, sub) : null),
    h("div", { class: "row" }, actions, bellButton(), refreshBtn));
}
```
```css
.topbar { display: flex; align-items: center; justify-content: space-between; gap: 12px; margin-bottom: 18px; flex-wrap: wrap; }
.topbar .sub { color: var(--ink-3); font-size: var(--fs-sm); margin-top: 2px; }
@media (max-width: 900px) { .topbar h1 { display: none; } }   /* на мобільному заголовок у .mbar */
```

### Card / KPI tile / grids

```css
.card { background: var(--surface); border: 1px solid var(--line); border-radius: var(--r-xl);
  padding: var(--sp-4); box-shadow: var(--shadow-sm); }
.card-head { display: flex; align-items: center; justify-content: space-between; margin-bottom: 10px; }
.grid.kpi { grid-template-columns: repeat(auto-fill, minmax(190px, 1fr)); }
.grid.two { grid-template-columns: repeat(auto-fit, minmax(320px, 1fr)); }
.kpi-value { font-size: var(--fs-2xl); font-weight: 700; letter-spacing: -.02em; font-variant-numeric: tabular-nums; }
.kpi-tile.dark   { background: var(--brand); color: var(--brand-ink); }                       /* головна цифра */
.kpi-tile.accent { border-color: rgba(180,138,62,.45); background: linear-gradient(180deg, var(--gold-tint), var(--surface) 70%); }
@media (hover: hover) { .card.click:hover { transform: translateY(-2px); box-shadow: var(--shadow); } }
```

### Mobile bar, FAB

`.mbar` — липкий хедер на `var(--bg)` з лого або «‹ Назад», назвою екрана, «Оновити» і «Баг».
`.fab` (десктоп) / `.tab-plus` (мобільний) — круглі кнопки «Швидкий запис», зелена з золотим кільцем
`0 0 0 4px var(--gold-tint)`.

---

## UI Components (Button, Input, Modal, Table, Badge — with code)

### Button

Варіанти: базова (біла з рамкою), `primary`/`gold` (зелений градієнт; у темній темі — золото), `accent`
(золото), `ghost`, `danger` (контурна червона), розміри `sm` (32 px) / базова (40 px) / `big` (48 px, на всю
ширину), стан `loading` (спінер замість тексту), натискання `scale(.97)`.

```css
.btn { display: inline-flex; align-items: center; justify-content: center; gap: 8px;
  border: 1px solid var(--line-strong); background: var(--surface); color: var(--ink);
  padding: 8px 16px; border-radius: var(--r-md); font-weight: 600; min-height: 40px; box-shadow: var(--shadow-sm);
  transition: background var(--dur-1) var(--ease), border-color var(--dur-1) var(--ease), box-shadow var(--dur-2) var(--ease), transform var(--dur-1) var(--ease); }
.btn.primary { background: linear-gradient(180deg, var(--brand-2), var(--brand)); border-color: var(--brand); color: #fff;
  box-shadow: inset 0 1px 0 rgba(255,255,255,.1), 0 1px 2px rgba(20,57,44,.25), 0 2px 8px rgba(20,57,44,.12); }
.btn.ghost  { background: transparent; border-color: transparent; box-shadow: none; }
.btn.danger { background: transparent; color: var(--danger); border-color: rgba(194,69,61,.35); box-shadow: none; }
.btn.sm  { min-height: 32px; padding: 4px 12px; font-size: var(--fs-sm); border-radius: var(--r-sm); }
.btn.big { width: 100%; min-height: 48px; font-size: var(--fs-md); border-radius: var(--r-lg); }
.btn:disabled { opacity: .45; cursor: not-allowed; box-shadow: none; }
.btn:focus-visible { outline: none; box-shadow: var(--ring); }        /* золоте кільце 3px */
.btn.loading { position: relative; color: transparent !important; pointer-events: none; }
.btn.loading::after { content: ""; position: absolute; width: 18px; height: 18px; border-radius: 50%;
  border: 2px solid rgba(255,255,255,.35); border-top-color: #fff; animation: spin .7s linear infinite; }
.icon-btn { border: 0; background: transparent; width: 34px; height: 34px; border-radius: var(--r-sm); display: grid; place-items: center; }
```

Обгортка дій — `run(fn, okMsg)`: виконує, показує зелений тост або червоний з `e.message`.

### Input / Field / Select / Segmented

```js
function field(label, input) { return h("label", { class: "f" }, h("span", {}, label), input); }
function seg(options, value, onChange) { /* .seg > button.on — перемикач-«таблетка» */ }
```
```css
label.f > span { display: block; font-size: var(--fs-xs); font-weight: 500; color: var(--ink-2); margin-bottom: 6px; }
input, select, textarea { width: 100%; background: var(--surface); border: 1px solid var(--line-strong);
  border-radius: var(--r-md); padding: 8px 12px; min-height: 40px; }
input:hover:not(:focus) { border-color: var(--ink-3); }
input:focus { border-color: var(--gold); box-shadow: var(--ring); }
input:disabled { background: var(--surface-2); color: var(--ink-3); }
@media (max-width: 900px) { input, select, textarea { font-size: var(--fs-input); } }  /* 16px — без зуму на iOS */
.seg { display: inline-flex; background: var(--surface-3); border-radius: var(--r-md); padding: 3px; gap: 2px; }
.seg button.on { background: var(--surface); color: var(--ink); box-shadow: 0 1px 2px rgba(20,30,25,.1), 0 0 0 1px rgba(20,30,25,.04); }
.search svg { position: absolute; left: 11px; top: 50%; transform: translateY(-50%); color: var(--ink-3); }
.search input { padding-left: 36px; }
```

### Modal = Sheet (бокова шторка)

Класичних центрованих модалок у Connect **немає**. Усі діалоги — `openSheet(title, ...content)`:
справа панель 520 px, на ≤ 600 px — нижня шторка з закругленням зверху і safe-area.
Закриття: клік по оверлею або «×». Підтвердження — `confirmSheet(title, text, okText, onOk, { danger, withReason })`.

```js
function openSheet(title, ...content) {
  closeSheet();
  const ov = h("div", { class: "overlay", id: "overlay", onclick: (e) => { if (e.target === ov) closeSheet(); } },
    h("div", { class: "sheet", role: "dialog", "aria-modal": "true" },
      h("div", { class: "sheet-head" }, h("h2", {}, title),
        h("button", { class: "x", onclick: closeSheet, "aria-label": "Закрити" }, icon("x"))),
      ...content));
  document.body.append(ov);
  unfitSheet = fitToKeyboard(ov);      // підлаштування під екранну клавіатуру
  return ov;
}
```
```css
.overlay { position: fixed; inset: 0; background: rgba(15,22,19,.38); z-index: 50; display: flex; justify-content: flex-end;
  animation: fade var(--dur-2) var(--ease); backdrop-filter: blur(2px); }
.sheet { background: var(--surface); width: 100%; max-width: 520px; height: 100%; overflow-y: auto;
  padding: 0 24px 28px; box-shadow: var(--shadow-lg); animation: slide var(--dur-3) var(--ease); }
.sheet-head { position: sticky; top: 0; background: var(--surface); padding: 18px 0 14px; border-bottom: 1px solid var(--line);
  display: flex; justify-content: space-between; align-items: center; }
@media (max-width: 600px) {
  .overlay { align-items: flex-end; }
  .sheet { height: auto; max-height: 90%; border-radius: var(--r-xl) var(--r-xl) 0 0;
    padding-bottom: calc(32px + env(safe-area-inset-bottom, 0px)); animation: rise .2s ease-out; }
}
```

### Table

Таблиця всередині `.card.table-wrap`; липкі заголовки капсом; клікабельні рядки `tr.click`.
**На ≤ 640 px таблиця автоматично стає списком карток**: глобальний `MutationObserver` викликає
`labelTables()`, яка проставляє `data-label` з `<th>` у кожну `<td>`, а CSS виводить підпис через `::before`.

```css
th, td { padding: 10px 14px; border-bottom: 1px solid var(--line); text-align: left; }
th { font-size: var(--fs-2xs); color: var(--ink-3); font-weight: 700; text-transform: uppercase;
  letter-spacing: .06em; background: var(--surface-2); position: sticky; top: 0; }
td.num, th.num { text-align: right; white-space: nowrap; font-variant-numeric: tabular-nums; }
tr.click:hover td { background: var(--surface-2); }
@media (max-width: 640px) {
  table.resp tr:has(th) { display: none; }
  table.resp tr { display: block; padding: 12px 16px; border-bottom: 1px solid var(--line); }
  table.resp td { display: flex; justify-content: space-between; gap: 12px; padding: 3px 0; border: 0; text-align: right; }
  table.resp td::before { content: attr(data-label); color: var(--ink-3); font-size: var(--fs-sm); }
}
```

### Badge = Chip

Таблетка з **крапкою кольору статусу** (`::before`), фон — `*-bg`, текст — основний колір статусу.

```js
const chip = (st, map = STATUS) => h("span", { class: "chip st-" + st }, map[st] || st);
```
```css
.chip { display: inline-flex; align-items: center; gap: 6px; padding: 2px 9px; min-height: 22px;
  border-radius: var(--r-pill); font-size: var(--fs-xs); font-weight: 700; background: var(--muted-bg); color: var(--ink-2); }
.chip::before { content: ""; width: 6px; height: 6px; border-radius: 50%; background: currentColor; opacity: .85; }
.st-pending     { background: var(--warn-bg); color: var(--warn); }   /* Очікує */
.st-confirmed   { background: var(--info-bg); color: var(--info); }   /* Підтверджено */
.st-in_progress { background: var(--prog-bg); color: var(--prog); }   /* Триває */
.st-completed   { background: var(--ok-bg);   color: var(--ok); }     /* Завершено */
.st-cancelled, .st-no_show { background: var(--muted-bg); color: var(--ink-3); }
```

### Toast

Один тост за раз, темний (`--ink`) або червоний; зверху праворуч, на ≤ 600 px — знизу над таббаром.
Успіх 2,6 с, помилка 4,5 с.

```js
function toast(msg, err = false, ms = null) {
  document.querySelectorAll(".toast").forEach((t) => t.remove());
  const t = h("div", { class: "toast" + (err ? " err" : ""), role: "status" }, icon(err ? "alert" : "ok", "sm"), msg);
  document.body.append(t);
  setTimeout(() => t.remove(), ms || (err ? 4500 : 2600));
}
```
```css
.toast { position: fixed; right: 20px; top: 18px; z-index: 99; display: flex; align-items: center; gap: 10px;
  background: var(--ink); color: var(--surface); padding: 12px 16px; border-radius: var(--r-lg);
  box-shadow: var(--shadow-lg); max-width: min(420px, calc(100vw - 32px)); animation: toast-in var(--dur-3) var(--ease); font-weight: 600; }
.toast.err { background: var(--danger); color: #fff; }
@media (max-width: 600px) { .toast { left: 16px; right: 16px; top: auto; bottom: 86px; } }
```

### Skeleton

Смужки 58 px із shimmer. `renderApp()` одразу ставить 4 смужки в `.main`, view прибирає їх після завантаження.

```js
h("div", { class: "skeleton" }, h("i"), h("i"), h("i"))
```
```css
.skeleton { display: grid; gap: 10px; }
.skeleton i { display: block; height: 58px; border-radius: var(--r-lg);
  background: linear-gradient(90deg, var(--surface-2) 25%, var(--surface-3) 50%, var(--surface-2) 75%);
  background-size: 200% 100%; animation: shimmer 1.2s linear infinite; }
```

### Empty state

Іконка в сірому колі 52 px + текст. Тексти розрізняють «нічого немає» і «нічого не знайдено за фільтром».

```js
function emptyState(text, ico = "inbox") { return h("div", { class: "empty" }, icon(ico), h("div", {}, text)); }
// використання: emptyState(list.length ? "Нічого не знайдено — змініть пошук чи фільтр" : "Немає замовлень за період", "receipt")
```
```css
.empty { text-align: center; color: var(--ink-3); padding: var(--sp-8) var(--sp-3); display: flex; flex-direction: column; align-items: center; gap: var(--sp-3); }
.empty svg { width: 52px; height: 52px; padding: 13px; border-radius: 50%; background: var(--surface-2); box-shadow: inset 0 0 0 1px var(--line); stroke-width: 1.6; }
```

### Avatar

Колір фону — детермінований хеш імені з 8 приглушених кольорів; ініціали з 2 слів.

```js
const AV_COLORS = ["#1d4d3b", "#8a6a2f", "#3f5a7a", "#7a4a5c", "#4f6b3a", "#5b4a7a", "#2f6b6b", "#7a5a3a"];
function avatar(name, cls = "") {
  let hsh = 0;
  for (const c of name || "") hsh = (hsh * 31 + c.charCodeAt(0)) >>> 0;
  return h("span", { class: "avatar " + cls, style: { background: AV_COLORS[hsh % AV_COLORS.length] } }, initials(name));
}
```
Розміри: `.avatar.sm` 26 px, базовий 34 px, `.avatar.lg` 46 px.

### Login card

Центрована картка 400 px на фоні `--bg` з двома радіальними «сяйвами» (золото справа зверху, зелень знизу
зліва) і повільним conic-glow. Зверху картки — смужка 3 px `linear-gradient(90deg, brand, gold, brand)`.
Лого-плашка 66 px із золотим градієнтом і кільцем, назва — Cormorant 30 px кольору `--brand`.
Поява: `rise-in` із затримками 0 / 80 / 140 / 200 / 300 мс для лого, назви, підпису, форми, футера.

---

## Design Tokens (exact values)

### Кольори — світла тема (`:root`)

| Токен | Значення | Призначення |
|---|---|---|
| `--brand` | `#14392c` | головний темно-зелений (sidebar, primary) |
| `--brand-2` | `#1d4d3b` | hover / посилання / градієнт кнопки |
| `--brand-ink` | `#f5f1e6` | текст на зеленому |
| `--gold` | `#b48a3e` | акцент, фокус |
| `--gold-soft` | `#e8d4a6` | смужка активного пункту меню |
| `--gold-tint` | `#f7efdc` | світлий золотий фон |
| `--bg` | `#f4f3ee` | фон сторінки (і `theme-color`) |
| `--surface` | `#ffffff` | картки |
| `--surface-2` | `#f8f7f3` | заголовки таблиць, hover |
| `--surface-3` | `#efede6` | фон `.seg`, іконок KPI |
| `--ink` | `#23262b` | основний текст |
| `--ink-2` | `#4b5058` | вторинний |
| `--ink-3` | `#868b93` | приглушений, плейсхолдери |
| `--line` | `#e4e1d8` | рамки |
| `--line-strong` | `#d3cfc3` | рамки інпутів і кнопок |
| `--focus` | `rgba(180,138,62,.35)` | кільце фокусу |
| `--ok` / `--ok-bg` | `#1f8a5b` / `#e5f4ec` | успіх, «завершено» |
| `--warn` / `--warn-bg` | `#b7791f` / `#fbf0dc` | «очікує» |
| `--danger` / `--danger-bg` | `#c2453d` / `#fbe7e5` | помилки |
| `--info` / `--info-bg` | `#2f6fb3` / `#e6eef8` | «підтверджено» |
| `--prog` / `--prog-bg` | `#7c4dcc` / `#f0eafb` | «триває» |
| `--muted-bg` | `#eeede8` | нейтральна таблетка |

Додатково (поза змінними): золото лого `linear-gradient(145deg, #d8b46a, #a9823b)`, текст на ньому `#1a1408`,
назва в sidebar `#f3e6c4`.

### Кольори — темна тема (`:root[data-theme="dark"]`, перемикач у sidebar, `localStorage["mds_theme"]`)

`--bg #0b1a15`, `--surface #11241d`, `--surface-2 #142b23`, `--surface-3 #1a352b`, `--ink #eeeae0`,
`--ink-2 #c4c0b5`, `--ink-3 #8c897f`, `--line #234236`, `--line-strong #2d5242`, `--gold #d2ab5f`,
`--gold-tint rgba(210,171,95,.14)`; статуси — світліші кольори на `rgba(..., .18–.22)`.
У темній темі primary-кнопка стає **золотою** (`--gold`, текст `#17120a`).

### Типографіка

| Токен | Значення |
|---|---|
| `--sans` | `"Manrope", system-ui, -apple-system, "Segoe UI", Roboto, sans-serif` (400–700) |
| `--serif` | `"Cormorant Garamond", Georgia, serif` (500–600) — лише лого/назви |
| `--fs-micro` · `2xs` · `xs` · `sm` | 9.5 · 11 · 12 · 13 px |
| `--fs-base` · `md` · `input` | 14 · 15 · 16 px |
| `--fs-lg` · `xl` · `2xl` · `3xl` · `4xl` | 18 · 20 · 24 · 30 · 34 px |
| `--lh-tight` / `--lh-base` | 1.2 / 1.45 |
| Заголовки | `h1` 24 px (20 px на мобільному), `h2` 18, `h3` 15; `font-weight: 700; letter-spacing: -.01em; text-wrap: balance` |
| Цифри | `font-variant-numeric: tabular-nums` для `.num`, `.kpi-value`, `td.num` |

### Відступи, радіуси, тіні, рух

| Група | Значення |
|---|---|
| Spacing | `--sp-1 4` · `2 8` · `3 12` · `4 16` · `5 20` · `6 24` · `8 32` · `10 40` px |
| Radius | `--r-xs 6` · `sm 8` · `md 10` · `lg 12` · `xl 16` · `pill 999` px |
| `--shadow-sm` | `0 1px 2px rgba(20,30,25,.06)` |
| `--shadow` | `0 1px 2px rgba(20,30,25,.04), 0 4px 18px rgba(20,30,25,.07)` |
| `--shadow-lg` | `0 18px 50px rgba(15,25,20,.18)` |
| `--ring` | `0 0 0 3px var(--focus)` |
| `--ease` | `cubic-bezier(.2, .7, .2, 1)` |
| Тривалості | `--dur-1 120ms` · `--dur-2 200ms` · `--dur-3 320ms` |

### Анімації (`@keyframes`)

`fade`, `slide` (шторка справа), `rise` (шторка знизу), `toast-in`, `rise-in` (поява контенту, каскад
0,03 с на дочірній елемент у `.main` і `.grid.kpi`), `pop` (активна іконка меню, цифра коду), `spin`,
`shimmer` (skeleton), `shake` (помилка входу), `mark-in` (лого входу), `pulse` / `now-pulse`
(лінія «зараз» у календарі), `grow-x` / `grow-y` (бари графіків). Усе вимикається через
`@media (prefers-reduced-motion: reduce)`.

### Брейкпоінти (лише `max-width`, desktop-first)

| px | Що відбувається |
|---|---|
| **900** | головний: sidebar → tabbar + mbar, інпути 16 px, ховається `h1` у topbar |
| **760** | `isPhone()` у JS; 15 правил: компактні KPI, свайп-«колоди» карток, вертикальні дії |
| **640** | таблиці → картки (`table.resp`) |
| **600** | шторка знизу, тост знизу, кнопки дій на всю ширину |
| 520 / 480 / 380 | точкові правки (код 2FA, сегменти в шторці) |
| `(hover: hover)` | hover-ефекти лише для миші |

### Іконки

Власні SVG (~65): `calendar clock chart wallet check user users list receipt banknote scissors settings
book logout sun moon plus left right phone x search down sliders more trend card transfer send inbox box
percent home megaphone zap alert ok edit history cancel noshow play move lock trash bug image refresh
calclock filetext landmark usercog coins grid rows eye eyeoff man woman dye gauge bell shield flow`.
Геометрія — як у Lucide (viewBox 24, `stroke-width: 1.8`, round caps/joins). Розміри: `.i` 18 px,
`.i.sm` 15 px, `.i.lg` 22 px.

---

## Patterns to Adopt

Беремо в Manager без змін за змістом:

1. **Токени один до одного.** Повний набір змінних із `:root` і `:root[data-theme="dark"]`
   (у Manager зараз лише частина: немає `surface-3`, `line-strong`, статусних кольорів, шкал fs/sp/r,
   тіней, ease/dur; `line` відрізняється — `#e7e4da` замість `#e4e1d8`; тінь `card` власна).
2. **Локальні шрифти `woff2` з `unicode-range`** замість Google Fonts — швидше, працює офлайн
   і сумісно з CSP `font-src 'self'`. Файли вже лежать у корені репозиторію: `app/web/static/fonts/`.
3. **Кнопки:** варіанти `primary/ghost/danger/accent`, розміри `sm/md/big`, `loading`-спінер,
   `:active scale(.97)`, золоте `focus-visible` кільце.
4. **Поля:** `label.f` з підписом над полем, `min-height: 40px`, `font-size: 16px` на мобільному,
   золотий фокус, `.seg` для фільтрів (у Manager фільтри статусів — ідеальний кандидат).
5. **Chip зі статусною крапкою** і семантичними кольорами `ok/warn/info/prog/danger/muted`.
6. **Toast** — один за раз, 2,6 / 4,5 с, `role="status"`, і обгортка `run(fn, okMsg)` для дій.
7. **Sheet замість модалок**: справа на десктопі, знизу на телефоні, `confirmSheet` для
   незворотних дій (у Manager: «Передати людині», «Позначити втраченим»).
8. **Skeleton + Empty state** з різним текстом для «порожньо» і «не знайдено».
9. **Auth-поведінка:** глобальна обробка `401` → вихід; idle-логаут 30 хв; тихий refresh токена;
   `GET /api/auth/me` на старті замість кешованого `user`; «показати пароль», Caps Lock, `shake` на помилці,
   запам'ятовування останнього логіну.
10. **Мобільна схема ≤ 900 px**: таббар знизу + липкий хедер, safe-area-інсети, `100dvh`.
11. **Аватар із хеш-кольором** (8 приглушених тонів) — однакові кольори клієнтів між Connect і Manager.
12. **`prefers-reduced-motion`** для всіх анімацій; `tabular-nums` для часу й сум.
13. **Суворий CSP** із Connect (`script-src 'self'`, `font-src 'self'`, `frame-ancestors 'none'`).

---

## Patterns to Adapt (Manager-specific)

1. **Формат коду.** У Connect усе — функції `h()` і класи. У Manager — React. Рекомендація:
   перенести `style.css`-токени в `tailwind.config.js` (`theme.extend` через `var(--…)`, щоб працювала
   темна тема) і зробити тонкі React-компоненти `Button`, `Field`, `Chip`, `Sheet`, `Toast`, `Skeleton`,
   `EmptyState`, `Avatar`, які віддають ті самі класи / утиліти. Альтернатива — підключити класи Connect
   як `@layer components` у `index.css` і писати `className="btn primary"`.
2. **Sidebar.** Connect: 240 px з текстом і групами. Manager: вузька 96 px-рейка з бейджами
   непрочитаних — для інбоксу з трьома колонками (рейка + список + чат) це виправдано. Залишити вузьку
   рейку, але взяти кольори, активний стан (`inset 2px 0 0 var(--gold-soft)` + `rgba(232,212,166,.14)`),
   `brand-mark`-плашку і футер з аватаром / темою / виходом. Пункти мають бути `<NavLink>`, а не `<button>`.
3. **Inbox — нового типу екран**, якого в Connect немає. Брати: `.card`, `.search`, `.seg` для фільтрів,
   `.chip` для статусів, `avatar()`, `emptyState`. Бульбашки чату — власні, але в палітрі:
   клієнт — `--surface`, AI-агент — `--gold-tint`, людина — `--brand` / `--brand-ink`, системні — `--muted-bg`.
4. **Статуси діалогів** ≠ статуси записів Connect. Пропоноване зіставлення на існуючі кольори:
   `new` → `info`, `in_progress` → `prog`, `ordered` → `ok`, `lost` → `muted`.
   (Зараз у `StatusTag.tsx` власні кольори: `new` — суцільний `--brand`, `ordered` — хардкод `#e3ece7`.)
5. **Іконки.** Лишити `lucide-react` (той самий візуальний стиль), але виставити `strokeWidth={1.8}`
   і розміри 18 / 15 / 22 px, як у Connect. Кольори каналів (`#c13584`, `#2aa3df`, `#1877f2`) — лише
   у маленьких іконках, не в фонах.
6. **Вхід.** Connect — `username` + 2FA через Telegram; Manager зараз — `email`. За планом сесія Manager
   іде через логін MDS Connect (див. CLAUDE.md кореня: director → owner, admin → admin) — тож форму
   варто вирівняти на «Логін», а 2FA-крок робити, лише коли бекенд Manager його підтримає.
   Демо-вхід (`MOCK_USER`) лишити тільки для `npm run dev`, як зараз.
7. **Ролі.** Connect: `director`, `master`. Manager: `owner` / `admin` (майстрам доступу немає).
   `NAV` за ролями — той самий підхід, адмін не бачить «Реклама» і грошей.
8. **Фінансовий PIN** — у Manager не потрібен, поки немає грошових екранів.
9. **PWA/service worker** — відкласти: Manager — десктоп-диспетчер на Windows (`D:/MDsManager/`).
   Мобільний брейкпоінт 900 px усе одно потрібен для перегляду з телефона через Cloudflare Tunnel.
10. **Таблиці → картки на ≤ 640 px.** У React замість глобального `MutationObserver` — компонент
    `<Table>`, який сам рендерить `data-label` у `<td>`.
11. **Тема.** Перемикач світла/темна є в Connect і поширюється на `theme-color`. У Manager — додати
    разом із токенами через `var(--…)`; без цього Tailwind-кольори жорстко світлі.

---

## Component Reuse Matrix

| Component | Copy as-is? | Needs adaptation? | Why |
|---|---|---|---|
| Design tokens (`:root`, dark) | ✅ Так | — | Ідентична айдентика; лише перенести в CSS-змінні + `tailwind.config.js` |
| Шрифти Manrope / Cormorant (`woff2`) | ✅ Так | — | Файли вже є в `app/web/static/fonts/`; прибрати Google Fonts `@import` |
| `@keyframes` + `prefers-reduced-motion` | ✅ Так | — | Чистий CSS, без залежностей |
| Button (`.btn` + варіанти, `loading`) | ✅ CSS | 🔶 React-обгортка | Класи переносяться; потрібен `<Button variant size loading>` |
| Icon button (`.icon-btn`, `.x`) | ✅ CSS | 🔶 React-обгортка | Те саме |
| Field / Input / Select / Textarea | ✅ CSS | 🔶 React-обгортка | `<Field label>`; 16 px на мобільному обов'язково |
| Segmented (`.seg`) | ✅ CSS | 🔶 React-обгортка | Для фільтрів інбоксу замість власних кнопок |
| Search (`.search`) | ✅ CSS | 🔶 Іконка lucide | Іконка з `lucide-react` |
| Card / card-head / grid | ✅ Так | — | Базовий контейнер |
| KPI tile (`dark`/`accent`, delta, sparkline) | ✅ CSS | 🔶 React + дані | Знадобиться для «Аналітики» Manager; `sparkline()` переписати на JSX-SVG |
| Chip / status badge | ✅ CSS | 🔶 Мапа статусів | Нові статуси діалогів → існуючі кольори (`info/prog/ok/muted`) |
| Avatar (хеш-колір) | ✅ Логіка | 🔶 React | Той самий алгоритм → однакові кольори клієнтів в обох системах |
| Toast + `run()` | ✅ CSS | 🔶 Zustand-стор / хук | `useToast()`; поведінка (один за раз, 2,6/4,5 с) та сама |
| Sheet / overlay / confirmSheet | ✅ CSS | 🔶 React-портал | Портал + фокус-трап + Esc; `fitToKeyboard` для мобільного |
| Skeleton | ✅ Так | — | Готовий CSS, `<Skeleton rows={3} />` |
| Empty state | ✅ Так | — | `<EmptyState icon text />` |
| Table + `table.resp` | ✅ CSS | 🔶 React `<Table>` | `data-label` ставити в JSX, без `MutationObserver` |
| Sidebar | ❌ Ні | 🔶 Так | Manager: вузька рейка з бейджами для інбоксу; беремо лише кольори/активний стан/футер |
| Topbar / mbar / tabbar | ✅ CSS | 🔶 Так | Мобільна навігація з іншим набором вкладок (Чати, Записи, Клієнти, Ще) |
| FAB «Швидкий запис» | ❌ Ні | — | У Manager запис створює AI/оператор із чату; FAB не потрібен |
| Login card (анімації, Caps Lock, eye) | ✅ CSS | 🔶 Так | Поле «Логін» замість email; 2FA-крок — пізніше |
| 2FA code boxes | ❌ Поки ні | 🔶 Пізніше | Немає бекенду 2FA в Manager |
| `api` wrapper (401/409/timeout) | ❌ Код ні | 🔶 Логіку так | Перенести в axios-інтерсептори: 401 → logout, 409 → «дані змінилися», таймаут з українським текстом |
| `session` (idle 30 хв + refresh) | ❌ Код ні | 🔶 Логіку так | Хук `useIdleLogout` + refresh-ендпоінт у бекенді Manager |
| Finance PIN | ❌ Ні | — | Немає грошових екранів |
| Daystrip / Calendar grid | ❌ Ні | 🔶 Пізніше | Можливе для екрана «Записи» (Фаза 2), записи читаються з Connect через `/api/ext/v1` |
| Service worker / manifest | ❌ Ні | — | Десктоп-застосунок; відкласти |
| Mermaid (`vendor/`) | ❌ Ні | — | Лише для екрана «Логіка системи» Connect |
| Власний набір SVG-іконок | ❌ Ні | — | У Manager `lucide-react` того самого стилю; лише вирівняти `strokeWidth=1.8` |

**Підсумок:** 29 позицій. Копіюються повністю — 6 (токени, шрифти, анімації, Card, Skeleton, Empty state);
CSS береться як є, але потрібна React-обгортка — 13; береться лише логіка або відкладено — 5
(Sidebar, 2FA, `api`-обгортка, `session`, календар); не потрібні — 5 (FAB, PIN, service worker, Mermaid,
власні SVG-іконки).

---

## Додатково: що помічено в Manager під час аудиту

- У корені репозиторію вже є старий SPA `app/web/static/` з **копією** `style.css` Connect (1 343 рядки
  проти 1 354 в актуальному Connect 0.3.0 — версії розійшлися) і шрифтами. Під час переходу на React
  варто брати токени з актуального Connect, а не з цієї копії.
- `MDsManager/frontend/src/index.css` тягне шрифти з `fonts.googleapis.com` — це конфліктує
  з CSP рівня Connect і з офлайн-роботою.
- `ProtectedRoute` перевіряє лише наявність токена; протухлий токен не веде на вхід (немає 401-інтерсептора).
