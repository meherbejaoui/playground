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
    rows = []
    for position, puzzle in enumerate(puzzles):
        if daily:
            label = "Today" if position == 0 else puzzle["seed"]
        else:
            label = puzzle["title"] or puzzle["id"]
        grade = puzzle["difficulty"]["grade"]
        rows.append(
            f'<li><a href="p/{escape(puzzle["id"])}.html">'
            f"<strong>{escape(label)}</strong> "
            f'<span class="cb-index-meta">{puzzle["rows"]}×{puzzle["cols"]} · {escape(grade)}</span>'
            f"</a></li>"
        )
    return "\n".join(rows) if rows else "<li>None yet.</li>"


def _render_index(daily: list[dict[str, Any]], gallery: list[dict[str, Any]], site_title: str) -> str:
    daily_rows = _index_rows(daily, daily=True)
    gallery_rows = _index_rows(gallery, daily=False)

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
  --focus: #1a5c3a;
}}
@media (prefers-color-scheme: dark) {{
  :root {{
    --bg: #17181a;
    --surface: #201f22;
    --border: #777265;
    --text: #f4f3ef;
    --text-muted: #b7b3a8;
    --accent: #7fd4a6;
    --focus: #8fe0b3;
  }}
}}
* {{ box-sizing: border-box; }}
body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
        line-height: 1.5; max-width: 640px; margin: 2.5rem auto; padding: 0 1.15rem;
        color: var(--text); background: var(--bg); }}
:focus-visible {{ outline: 3px solid var(--focus); outline-offset: 2px; border-radius: 2px; }}
h1 {{ font-size: 1.55rem; font-weight: 700; letter-spacing: -0.01em; }}
h2 {{ font-size: 0.9rem; font-weight: 700; text-transform: uppercase; letter-spacing: 0.06em;
      color: var(--text-muted); margin-top: 2rem; }}
ul {{ list-style: none; padding: 0; }}
li {{ margin-bottom: 0.5rem; }}
a {{ display: flex; justify-content: space-between; align-items: baseline; gap: 0.75rem;
     padding: 0.7rem 0.9rem; border: 1px solid var(--border); border-radius: 0.55rem;
     text-decoration: none; color: inherit; background: var(--surface);
     transition: border-color 0.15s ease; }}
a:hover {{ border-color: var(--accent); }}
@media (prefers-reduced-motion: reduce) {{ a {{ transition: none; }} }}
.cb-index-meta {{ color: var(--text-muted); font-size: 0.85rem; font-variant-numeric: tabular-nums; }}
</style>
</head>
<body>
<h1>{escape(site_title)}</h1>
<h2>Daily</h2>
<ul>
{daily_rows}
</ul>
<h2>Gallery</h2>
<ul>
{gallery_rows}
</ul>
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
