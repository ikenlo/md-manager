# ruff: noqa: E501 — CSS з MDS Connect, рядки стилів не розбиваємо
"""Стилі сторінок MDS Manager — токени й компоненти MDS Connect (ikenlo/m-d, style.css).

Нові сторінки беруть CSS звідси, щоб дві системи виглядали однаково.
"""

from __future__ import annotations

from html import escape

FONTS = (
    "<link rel='preconnect' href='https://fonts.googleapis.com'>"
    "<link rel='stylesheet' href='https://fonts.googleapis.com/css2?family=Cormorant+Garamond:"
    "wght@500;600&family=Manrope:wght@400;500;600;700&display=swap'>"
)

_DARK = """
  --bg:#0b1a15;--surface:#11241d;--surface-2:#142b23;--surface-3:#1a352b;--ink:#eeeae0;--ink-2:#c4c0b5;
  --ink-3:#8c897f;--line:#234236;--line-strong:#2d5242;--gold:#d2ab5f;--gold-tint:rgba(210,171,95,.14);
  --ok:#6fd0a0;--ok-bg:rgba(31,138,91,.18);--warn:#e8b660;--warn-bg:rgba(183,121,31,.2);--danger:#ef8d84;
  --danger-bg:rgba(194,69,61,.2);--info:#8fc1f5;--info-bg:rgba(47,111,179,.2);--prog:#c3a6f5;
  --prog-bg:rgba(124,77,204,.22);--link:#d2ab5f;--btn-bg:#d2ab5f;--btn-ink:#17120a;color-scheme:dark;
"""

CSS = (
    """
:root{--brand:#14392c;--brand-2:#1d4d3b;--brand-ink:#f5f1e6;--gold:#b48a3e;--gold-soft:#e8d4a6;--gold-tint:#f7efdc;
--bg:#f4f3ee;--surface:#fff;--surface-2:#f8f7f3;--surface-3:#efede6;--ink:#23262b;--ink-2:#4b5058;--ink-3:#868b93;
--line:#e4e1d8;--line-strong:#d3cfc3;--focus:rgba(180,138,62,.35);--ok:#1f8a5b;--ok-bg:#e5f4ec;--warn:#b7791f;
--warn-bg:#fbf0dc;--danger:#c2453d;--danger-bg:#fbe7e5;--info:#2f6fb3;--info-bg:#e6eef8;--prog:#7c4dcc;
--prog-bg:#f0eafb;--link:#1d4d3b;--btn-bg:#14392c;--btn-ink:#fff;--shadow-sm:0 1px 2px rgba(20,30,25,.06);
--sans:"Manrope",system-ui,-apple-system,"Segoe UI",Roboto,sans-serif;--serif:"Cormorant Garamond",Georgia,serif}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){"""
    + _DARK
    + """}}
:root[data-theme="dark"]{"""
    + _DARK
    + """}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:14px/1.45 var(--sans);
-webkit-font-smoothing:antialiased;overflow-x:hidden}
button,input,select,textarea{font:inherit;color:inherit}a{color:var(--link);text-decoration:none}
h1,h2,h3{margin:0;font-weight:700;letter-spacing:-.01em;text-wrap:balance}h1{font-size:24px}h2{font-size:18px}h3{font-size:15px}
.serif{font-family:var(--serif);font-weight:600}.muted{color:var(--ink-3)}.small{font-size:13px}
.bar{background:var(--brand);color:var(--brand-ink);padding-block:10px}
.bar .in{max-width:1240px;margin:0 auto;display:flex;align-items:center;gap:14px;flex-wrap:wrap;
padding-left:max(16px,env(safe-area-inset-left,0px));padding-right:max(16px,env(safe-area-inset-right,0px))}
.mark{width:34px;height:34px;border-radius:10px;display:grid;place-items:center;
background:linear-gradient(145deg,#d8b46a,#a9823b);color:#1a1408;font:700 12px var(--sans)}
.bname{font:600 19px/1 var(--serif);color:#f3e6c4}.bar nav{display:flex;gap:4px;margin-left:auto;flex-wrap:wrap}
.bar nav a{color:rgba(245,241,230,.78);font-weight:600;font-size:13px;padding:7px 12px;border-radius:8px}
.bar nav a.on{background:rgba(232,212,166,.14);color:#f3e6c4}
.main{max-width:1240px;margin:0 auto;padding-block:22px 80px;
padding-left:max(16px,env(safe-area-inset-left,0px));padding-right:max(16px,env(safe-area-inset-right,0px))}
.topbar{display:flex;align-items:flex-end;justify-content:space-between;gap:12px;margin-bottom:16px;flex-wrap:wrap}
.topbar .sub{color:var(--ink-3);font-size:13px;margin-top:3px}
.card{background:var(--surface);border:1px solid var(--line);border-radius:16px;padding:16px;box-shadow:var(--shadow-sm);min-width:0}
.card-head{display:flex;align-items:center;justify-content:space-between;gap:6px 10px;margin-bottom:12px;flex-wrap:wrap}
.grid{display:grid;gap:12px}.grid.kpi{grid-template-columns:repeat(auto-fill,minmax(170px,1fr))}
.grid.two{grid-template-columns:repeat(auto-fit,minmax(min(100%,420px),1fr));align-items:start}
.section{margin-top:20px}
.kpi-tile{padding:14px 16px;display:flex;flex-direction:column;gap:4px}
.kpi-label{font-size:12px;font-weight:600;color:var(--ink-3)}
.kpi-value{font-size:24px;font-weight:700;letter-spacing:-.02em;font-variant-numeric:tabular-nums}
.kpi-tile.dark{background:var(--brand);border-color:var(--brand);color:var(--brand-ink)}
.kpi-tile.dark .kpi-label{color:rgba(245,241,230,.7)}
.kpi-tile.accent{border-color:rgba(180,138,62,.45);background:linear-gradient(180deg,var(--gold-tint),var(--surface) 70%)}
.btn{display:inline-flex;align-items:center;justify-content:center;gap:8px;border:1px solid var(--line-strong);
background:var(--surface);color:var(--ink);padding:8px 16px;border-radius:10px;cursor:pointer;font-weight:600;
min-height:40px;white-space:nowrap;box-shadow:var(--shadow-sm)}
.btn:hover{background:var(--surface-2)}.btn:disabled{opacity:.45;cursor:not-allowed}
.btn.primary{background:var(--btn-bg);border-color:var(--btn-bg);color:var(--btn-ink)}
.btn.ok{background:var(--ok);border-color:var(--ok);color:#fff}
.btn.danger{background:transparent;color:var(--danger);border-color:rgba(194,69,61,.4);box-shadow:none}
.btn.danger:hover{background:var(--danger-bg)}
.btn.sm{min-height:34px;padding:4px 12px;font-size:13px;border-radius:8px}
.btn.ghost{background:transparent;border-color:transparent;box-shadow:none}
.btn:focus-visible,a:focus-visible,input:focus-visible,select:focus-visible,textarea:focus-visible{outline:none;box-shadow:0 0 0 3px var(--focus)}
.seg{display:inline-flex;background:var(--surface-3);border-radius:10px;padding:3px;gap:2px;flex-wrap:wrap}
.seg a{color:var(--ink-2);padding:6px 12px;border-radius:8px;font-weight:600;font-size:13px}
.seg a.on{background:var(--surface);color:var(--ink);box-shadow:0 1px 2px rgba(20,30,25,.1)}
.row{display:flex;gap:8px;align-items:center;flex-wrap:wrap}.grow{flex:1;min-width:0}
.chip{display:inline-flex;align-items:center;gap:5px;font-size:12px;font-weight:600;padding:2px 9px;
border-radius:999px;background:var(--surface-3);color:var(--ink-2);white-space:nowrap}
.chip.ok{background:var(--ok-bg);color:var(--ok)}.chip.warn{background:var(--warn-bg);color:var(--warn)}
.chip.danger{background:var(--danger-bg);color:var(--danger)}.chip.info{background:var(--info-bg);color:var(--info)}
.chip.prog{background:var(--prog-bg);color:var(--prog)}.chip.gold{background:var(--gold-tint);color:var(--gold)}
input,select,textarea{width:100%;background:var(--surface);border:1px solid var(--line-strong);border-radius:10px;
padding:8px 12px;min-height:40px}
.callout{border-radius:12px;padding:10px 14px;background:var(--gold-tint);font-size:13px;color:var(--ink-2);margin:0}
.callout.danger{background:var(--danger-bg);color:var(--danger)}.callout.ok{background:var(--ok-bg);color:var(--ok)}
pre.p{white-space:pre-wrap;word-break:break-word;margin:0;font:14px/1.55 var(--sans);background:var(--surface-2);
border:1px solid var(--line);border-radius:10px;padding:10px 12px}
"""
)


def page(
    title: str, body: str, *, active: str = "", refresh: bool = False, script: str = ""
) -> str:
    nav = "".join(
        f"<a href='{href}' class='{'on' if key == active else ''}'>{label}</a>"
        for key, href, label in (("panel", "/panel", "Огляд"), ("content", "/panel/content",
                                 "Контент-план"))
    )  # fmt: skip
    meta = "<meta http-equiv='refresh' content='15'>" if refresh else ""
    return (
        "<!doctype html><html lang='uk'><head><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width,initial-scale=1,viewport-fit=cover'>"
        f"<meta name='robots' content='noindex'>{meta}<title>{escape(title)}</title>{FONTS}"
        f"<style>{CSS}</style></head><body>"
        "<header class='bar'><div class='in'><div class='mark'>M&amp;D</div>"
        f"<div class='bname'>MDS Manager</div><nav>{nav}</nav></div></header>"
        f"<main class='main'>{body}</main><script>{script}</script></body></html>"
    )
