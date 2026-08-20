"""Static site assembly (PLAN.md 5 `build` row).

Reads every puzzle in ``puzzles/``, strips solutions, and writes a
self-contained static site: one player page per puzzle plus a
reverse-chronological archive index. No template engine — pages are
assembled with plain string replacement over the ``web/page.html``
skeleton's ``%%PLACEHOLDER%%`` markers.
"""

from __future__ import annotations

import json
import re
import shutil
from html import escape
from pathlib import Path
from typing import Any

from .puzzle import PuzzleError, from_json, strip_solution, to_dict

MARKER_NAME = ".gridlock-site"

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


def load_puzzles(puzzles_dir: str | Path) -> list[dict[str, Any]]:
    """Every puzzle in ``puzzles_dir``, newest first by generation time."""
    directory = Path(puzzles_dir)
    if not directory.is_dir():
        raise BuildError(f"no puzzles directory at {directory}")

    puzzles: list[dict[str, Any]] = []
    for path in sorted(directory.glob("*.json")):
        try:
            puzzle = from_json(path.read_text(encoding="utf-8"))
        except PuzzleError as exc:
            raise BuildError(f"{path}: {exc}") from exc
        puzzles.append(to_dict(puzzle))

    puzzles.sort(key=lambda p: (p["generatedAt"], p["id"]), reverse=True)
    return puzzles


def _render_page(
    template: str, puzzle: dict[str, Any], css: str, core_js: str, ui_js: str, site_title: str
) -> str:
    stripped = strip_solution(puzzle)
    puzzle_json = json.dumps(stripped, ensure_ascii=False).replace("</", "<\\/")
    page_title = f"{site_title} — {puzzle['id']}"

    html = template
    html = html.replace("%%TITLE%%", escape(page_title))
    html = html.replace("%%PUZZLE_JSON%%", puzzle_json)
    html = html.replace("%%CSS%%", css)
    html = html.replace("%%CORE_JS%%", core_js)
    html = html.replace("%%UI_JS%%", ui_js)
    return html


def _render_index(puzzles: list[dict[str, Any]], site_title: str) -> str:
    rows = []
    for position, puzzle in enumerate(puzzles):
        label = "Today" if position == 0 else puzzle["seed"]
        badge = ' class="idx-badge"' if position == 0 else ""
        rows.append(
            f'<li><a class="idx-row" href="p/{escape(puzzle["id"])}.html">'
            f'<span class="idx-row-main"><strong{badge}>{escape(label)}</strong> '
            f'<span class="idx-row-id">{escape(puzzle["id"])}</span></span>'
            f'<span class="idx-row-arrow" aria-hidden="true">&rarr;</span>'
            f"</a></li>"
        )
    list_html = "\n".join(rows) if rows else "<li class=\"idx-empty\">No puzzles yet.</li>"

    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
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
</style>
</head>
<body>
<nav class="idx-breadcrumb" aria-label="Breadcrumb"><a href="../index.html">Puzzle Factories</a></nav>
<h1>{escape(site_title)}</h1>
<p class="lede">A fresh 5&times;5 mini crossword every day, plus the full archive to replay.</p>
<ul>
{list_html}
</ul>
</body>
</html>
"""


def build_site(
    puzzles_dir: str | Path = "puzzles",
    out_dir: str | Path = "site",
    title: str = "Gridlock",
) -> list[dict[str, Any]]:
    """Build the static site into ``out_dir``. Returns the puzzles it built."""
    out_path = Path(out_dir)
    _prepare_output_dir(out_path)

    puzzles = load_puzzles(puzzles_dir)

    web = _web_dir()
    template = (web / "page.html").read_text(encoding="utf-8")
    css = (web / "player.css").read_text(encoding="utf-8")
    core_js = _inline_core_js((web / "player-core.js").read_text(encoding="utf-8"))
    ui_js = _inline_ui_js((web / "player-ui.js").read_text(encoding="utf-8"))

    pages_dir = out_path / "p"
    pages_dir.mkdir(parents=True, exist_ok=True)
    for puzzle in puzzles:
        page = _render_page(template, puzzle, css, core_js, ui_js, title)
        (pages_dir / f"{puzzle['id']}.html").write_text(page, encoding="utf-8")

    (out_path / "index.html").write_text(_render_index(puzzles, title), encoding="utf-8")
    (out_path / MARKER_NAME).write_text(
        "Generated by `python -m gridlock build`. Safe to delete this whole directory.\n",
        encoding="utf-8",
    )

    return puzzles
