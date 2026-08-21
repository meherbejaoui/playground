"""Static site assembly (PLAN.md 5 `build` row).

Reads every puzzle in ``puzzles/`` and writes a self-contained static site:
one player page per puzzle, plus an archive index with separate Daily and
Gallery sections. No template engine — pages are assembled with plain
string replacement over the ``web/page.html`` skeleton's ``%%PLACEHOLDER%%``
markers.

Unlike the sister project's crossword grid, a Cellblock puzzle's JSON never
contains a plaintext solution (only the packed base64 form), so there is no
solution-stripping step here — the puzzle dict is inlined as-is.
"""

from __future__ import annotations

import json
import re
import shutil
from html import escape
from pathlib import Path
from typing import Any

from .generate import today_seed
from .model import DAILY, GALLERY, PuzzleError, from_json, to_dict

MARKER_NAME = ".cellblock-site"

# player-core.js declares only `export function NAME(...)` and one trailing
# `export { isComplete };`; player-ui.js additionally has a single-line
# `import { ... } from "./player-core.js";`. Stripping these turns both
# files into plain top-level declarations that share one scope once
# concatenated into a single inline <script type="module"> block.
_EXPORT_DECL_RE = re.compile(r"^export (function|const|class) ", re.MULTILINE)
_EXPORT_LIST_RE = re.compile(r"^export\s*\{[^}]*\}\s*;?\s*$\n?", re.MULTILINE)
_IMPORT_RE = re.compile(
    r'^import\s*\{[^}]*\}\s*from\s*["\']\./player-core\.js["\'];?\s*$\n?', re.MULTILINE
)


class BuildError(RuntimeError):
    """The site could not be built (bad output dir, unreadable puzzle, ...)."""


def _web_dir() -> Path:
    return Path(__file__).resolve().parents[2] / "web"


def _inline_core_js(source: str) -> str:
    source = _EXPORT_LIST_RE.sub("", source)
    return _EXPORT_DECL_RE.sub(r"\1 ", source)


def _inline_ui_js(source: str) -> str:
    source = _IMPORT_RE.sub("", source)
    return _EXPORT_DECL_RE.sub(r"\1 ", source)


def _prepare_output_dir(out_dir: Path) -> None:
    """Refuse to wipe a directory that doesn't look like a previous build."""
    if out_dir.exists():
        contents = list(out_dir.iterdir())
        if contents and not (out_dir / MARKER_NAME).is_file():
            raise BuildError(
                f"{out_dir} is not empty and has no {MARKER_NAME} marker from a "
                f"previous build; refusing to overwrite a directory that might "
                f"contain something else"
            )
        if contents:
            shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)


def load_puzzles(puzzles_dir: str | Path) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Every puzzle in ``puzzles_dir``, split into ``(daily, gallery)``.

    ``daily`` is newest-first by generation time; ``gallery`` is sorted by
    title.
    """
    directory = Path(puzzles_dir)
    if not directory.is_dir():
        raise BuildError(f"no puzzles directory at {directory}")

    daily: list[dict[str, Any]] = []
    gallery: list[dict[str, Any]] = []
    for path in sorted(directory.glob("*.json")):
        try:
            puzzle = from_json(path.read_text(encoding="utf-8"))
        except PuzzleError as exc:
            raise BuildError(f"{path}: {exc}") from exc
        payload = to_dict(puzzle)
        (daily if puzzle.kind == DAILY else gallery).append(payload)

    daily.sort(key=lambda p: (p["generatedAt"], p["id"]), reverse=True)
    gallery.sort(key=lambda p: (p["title"] or "", p["id"]))
    return daily, gallery


def _page_title(puzzle: dict[str, Any], site_title: str) -> str:
    if puzzle["kind"] == GALLERY:
        # Never bake the gallery title into the static <title> tag either —
        # it should stay a surprise until the puzzle is solved, same as the
        # on-page heading (PLAN.md 6.6).
        return f"{site_title} — Gallery puzzle"
    return f"{site_title} — {puzzle['id']}"


def _render_page(template: str, puzzle: dict[str, Any], css: str, core_js: str, ui_js: str, site_title: str) -> str:
    puzzle_json = json.dumps(puzzle, ensure_ascii=False).replace("</", "<\\/")

    html = template
    html = html.replace("%%TITLE%%", escape(_page_title(puzzle, site_title)))
    html = html.replace("%%PUZZLE_JSON%%", puzzle_json)
    html = html.replace("%%CSS%%", css)
    html = html.replace("%%CORE_JS%%", core_js)
    html = html.replace("%%UI_JS%%", ui_js)
    return html


def _index_rows(puzzles: list[dict[str, Any]], daily: bool) -> str:
    today = today_seed()
    rows = []
    for puzzle in puzzles:
        if daily:
            # Compare against the real current-UTC-date seed, not sort
            # position: the newest puzzle by generatedAt isn't necessarily
            # today's if `build` runs without a fresh `generate` first (a
            # missed cron, or a manual/local rebuild off a stale puzzles/
            # dir).
            is_today = puzzle["seed"] == today
            label = "Today" if is_today else puzzle["seed"]
            badge = ' class="idx-badge"' if is_today else ""
        else:
            label = puzzle["title"] or puzzle["id"]
            badge = ""
        grade = puzzle["difficulty"]["grade"]
        rows.append(
            f'<li><a class="idx-row" href="p/{escape(puzzle["id"])}.html">'
            f'<span class="idx-row-main"><strong{badge}>{escape(label)}</strong> '
            f'<span class="idx-row-id">{puzzle["rows"]}&times;{puzzle["cols"]} &middot; {escape(grade)}</span></span>'
            f'<span class="idx-row-arrow" aria-hidden="true">&rarr;</span>'
            f"</a></li>"
        )
    return "\n".join(rows) if rows else "<li class=\"idx-empty\">None yet.</li>"


def _render_index(daily: list[dict[str, Any]], gallery: list[dict[str, Any]], site_title: str) -> str:
    daily_rows = _index_rows(daily, daily=True)
    gallery_rows = _index_rows(gallery, daily=False)

    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="referrer" content="strict-origin-when-cross-origin">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; script-src 'self' 'unsafe-inline' https://ko-fi.com https://*.ko-fi.com; style-src 'self' 'unsafe-inline' https://ko-fi.com https://*.ko-fi.com; font-src https://ko-fi.com https://*.ko-fi.com; img-src 'self' data: https://ko-fi.com https://*.ko-fi.com; frame-src https://ko-fi.com https://*.ko-fi.com; connect-src https://ko-fi.com https://*.ko-fi.com; base-uri 'none'; form-action 'none';">
<title>{escape(site_title)}</title>
<style>
:root {{
  color-scheme: light dark;
  --bg: #f4f3ee;
  --surface: #ffffff;
  --border: #847d6c;
  --text: #1c1b18;
  --text-muted: #6b675e;
  --accent: #2f6f4f;
  --accent-contrast: #ffffff;
  --focus: #1a5c3a;
  --shadow: 0 1px 2px rgba(28, 27, 24, 0.06), 0 4px 12px rgba(28, 27, 24, 0.07);
}}
@media (prefers-color-scheme: dark) {{
  :root {{
    --bg: #17181a;
    --surface: #201f22;
    --border: #777265;
    --text: #f4f3ef;
    --text-muted: #b7b3a8;
    --accent: #7fd4a6;
    --accent-contrast: #08130d;
    --focus: #8fe0b3;
    --shadow: 0 1px 2px rgba(0, 0, 0, 0.4), 0 4px 16px rgba(0, 0, 0, 0.35);
  }}
}}
* {{ box-sizing: border-box; }}
body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
        line-height: 1.5; max-width: 640px; margin: 2.5rem auto; padding: 0 1.15rem 3rem;
        color: var(--text); background: var(--bg); }}
:focus-visible {{ outline: 3px solid var(--focus); outline-offset: 2px; border-radius: 2px; }}
.idx-breadcrumb {{ font-size: 0.85rem; margin-bottom: 1.1rem; }}
.idx-breadcrumb a {{ color: var(--text-muted); text-decoration: none; padding: 0.2rem 0.3rem;
                      margin: -0.2rem -0.3rem; border-radius: 0.3rem; }}
.idx-breadcrumb a:hover {{ text-decoration: underline; }}
h1 {{ font-size: 1.65rem; font-weight: 700; letter-spacing: -0.01em; margin: 0 0 0.3rem; }}
p.lede {{ color: var(--text-muted); margin: 0 0 1.75rem; font-size: 0.98rem; }}
h2 {{ font-size: 0.85rem; font-weight: 700; text-transform: uppercase; letter-spacing: 0.06em;
      color: var(--text-muted); margin: 2rem 0 0.6rem; }}
ul {{ list-style: none; padding: 0; margin: 0; }}
li {{ margin-bottom: 0.6rem; }}
.idx-row {{ display: flex; justify-content: space-between; align-items: center; gap: 0.75rem;
     padding: 0.85rem 1.1rem; border: 1px solid var(--border); border-radius: 0.65rem;
     text-decoration: none; color: inherit; background: var(--surface); box-shadow: var(--shadow);
     transition: border-color 0.15s ease, transform 0.15s ease; }}
.idx-row:hover {{ border-color: var(--accent); transform: translateY(-1px); }}
.idx-row:hover .idx-row-arrow {{ transform: translateX(3px); }}
@media (prefers-reduced-motion: reduce) {{
  .idx-row, .idx-row-arrow {{ transition: none; }}
  .idx-row:hover {{ transform: none; }}
}}
.idx-row-main {{ display: flex; align-items: baseline; gap: 0.6rem; flex-wrap: wrap; }}
.idx-row-id {{ color: var(--text-muted); font-size: 0.85rem; font-variant-numeric: tabular-nums; }}
.idx-row-arrow {{ color: var(--accent); font-size: 1.1rem; transition: transform 0.15s ease; flex: 0 0 auto; }}
.idx-badge {{ background: var(--accent); color: var(--accent-contrast); padding: 0.15rem 0.55rem;
              border-radius: 999px; font-size: 0.78rem; font-weight: 700; }}
.idx-empty {{ color: var(--text-muted); padding: 0.85rem 1.1rem; }}
.idx-footer {{ margin-top: 3rem; padding-top: 1.25rem; border-top: 1px solid var(--border);
               font-size: 0.85rem; color: var(--text-muted); }}
.idx-footer a {{ color: var(--text-muted); text-decoration: underline; }}
.idx-footer a:hover {{ color: var(--accent); }}
</style>
</head>
<body>
<nav class="idx-breadcrumb" aria-label="Breadcrumb">
  <a href="https://www.meherbejaoui.com/">meherbejaoui.com</a>
  <span aria-hidden="true">/</span>
  <a href="../index.html">Puzzle Factories</a>
</nav>
<h1>{escape(site_title)}</h1>
<p class="lede">A new nonogram every day, certified solvable by logic alone &mdash; plus a hand-drawn picture gallery.</p>
<h2>Daily</h2>
<ul>
{daily_rows}
</ul>
<h2>Gallery</h2>
<ul>
{gallery_rows}
</ul>
<footer class="idx-footer">
  Built and maintained by <a href="https://www.meherbejaoui.com/">Meher Bejaoui</a>.
  <a href="https://github.com/meherbejaoui/puzzlefactory">Source on GitHub</a>.
</footer>
<script>
(function () {{
  // Click-to-load "Tip Me" Ko-fi button, matching the one on meherbejaoui.com
  // and its other sub-sites. Nothing from Ko-fi loads until this placeholder
  // is clicked -- it is ours, costs nothing, and sets no cookie. On click it
  // injects Ko-fi's real overlay-widget.js and calls kofiWidgetOverlay.draw(),
  // which renders Ko-fi's own floating button in roughly the same spot; this
  // placeholder then removes itself.
  var KOFI_RESERVED_HEIGHT = 76;

  function init() {{
    var btn = document.createElement("button");
    btn.type = "button";
    btn.id = "kofi-float-trigger";
    btn.setAttribute("aria-label", "Support me on Ko-fi");
    btn.style.position = "fixed";
    btn.style.left = "16px";
    btn.style.bottom = "24px";
    btn.style.zIndex = "40";
    btn.style.display = "flex";
    btn.style.alignItems = "center";
    btn.style.gap = "8px";
    btn.style.borderRadius = "999px";
    btn.style.border = "none";
    btn.style.padding = "12px 16px";
    btn.style.fontFamily = "-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif";
    btn.style.fontSize = "14px";
    btn.style.fontWeight = "500";
    // Dark navy on the #00b9fe brand blue: ~6.7:1 contrast, passes WCAG AA.
    btn.style.color = "#0a2a33";
    btn.style.background = "#00b9fe";
    btn.style.boxShadow = "0 8px 20px rgba(0,0,0,.25)";
    btn.style.cursor = "pointer";

    var icon = document.createElement("span");
    icon.setAttribute("aria-hidden", "true");
    icon.textContent = "☕";
    var label = document.createElement("span");
    label.textContent = "Tip Me";
    btn.appendChild(icon);
    btn.appendChild(label);

    var spacer = document.createElement("div");
    spacer.setAttribute("aria-hidden", "true");
    spacer.style.height = KOFI_RESERVED_HEIGHT + "px";

    var loading = false;
    btn.addEventListener("click", function () {{
      if (loading) return;
      loading = true;
      btn.disabled = true;
      btn.style.cursor = "wait";

      var script = document.createElement("script");
      script.src = "https://storage.ko-fi.com/cdn/scripts/overlay-widget.js";
      script.referrerPolicy = "strict-origin-when-cross-origin";
      script.onload = function () {{
        var overlay = window.kofiWidgetOverlay;
        var drew = false;
        if (overlay && typeof overlay.draw === "function") {{
          try {{
            overlay.draw("meherbejaoui", {{
              type: "floating-chat",
              "floating-chat.donateButton.text": "Tip Me",
              "floating-chat.donateButton.background-color": "#00b9fe",
              "floating-chat.donateButton.text-color": "#fff"
            }});
            drew = true;
          }} catch (err) {{
            drew = false;
          }}
        }}
        if (drew) {{
          btn.remove();
        }} else {{
          // Ko-fi's script loaded but never exposed a usable overlay API
          // (e.g. an ad/tracker blocker stripped or stubbed it out), or
          // draw() itself threw. Leave the trigger clickable instead of
          // getting stuck disabled or silently vanishing.
          loading = false;
          btn.disabled = false;
          btn.style.cursor = "pointer";
        }}
        script.remove();
      }};
      script.onerror = function () {{
        loading = false;
        btn.disabled = false;
        btn.style.cursor = "pointer";
        script.remove();
      }};
      document.body.appendChild(script);
    }});

    document.body.appendChild(btn);
    document.body.appendChild(spacer);
  }}

  if (document.readyState === "loading") {{
    document.addEventListener("DOMContentLoaded", init);
  }} else {{
    init();
  }}
}})();
</script>
</body>
</html>
"""


def build_site(
    puzzles_dir: str | Path = "puzzles",
    out_dir: str | Path = "site",
    title: str = "Cellblock",
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Build the static site into ``out_dir``. Returns ``(daily, gallery)``."""
    out_path = Path(out_dir)
    _prepare_output_dir(out_path)

    daily, gallery = load_puzzles(puzzles_dir)
    all_puzzles = daily + gallery

    web = _web_dir()
    template = (web / "page.html").read_text(encoding="utf-8")
    css = (web / "player.css").read_text(encoding="utf-8")
    core_js = _inline_core_js((web / "player-core.js").read_text(encoding="utf-8"))
    ui_js = _inline_ui_js((web / "player-ui.js").read_text(encoding="utf-8"))

    pages_dir = out_path / "p"
    pages_dir.mkdir(parents=True, exist_ok=True)
    for puzzle in all_puzzles:
        page = _render_page(template, puzzle, css, core_js, ui_js, title)
        (pages_dir / f"{puzzle['id']}.html").write_text(page, encoding="utf-8")

    (out_path / "index.html").write_text(_render_index(daily, gallery, title), encoding="utf-8")
    (out_path / MARKER_NAME).write_text(
        "Generated by `python -m cellblock build`. Safe to delete this whole directory.\n",
        encoding="utf-8",
    )

    return daily, gallery
