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
        rows.append(
            f'<li><a href="p/{escape(puzzle["id"])}.html">'
            f"<strong>{escape(label)}</strong> "
            f'<span class="gl-index-id">{escape(puzzle["id"])}</span></a></li>'
        )
    list_html = "\n".join(rows) if rows else "<li>No puzzles yet.</li>"

    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{escape(site_title)}</title>
<style>
body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
        max-width: 640px; margin: 2rem auto; padding: 0 1rem; }}
h1 {{ font-size: 1.4rem; }}
ul {{ list-style: none; padding: 0; }}
li {{ margin-bottom: 0.4rem; }}
a {{ display: block; padding: 0.6rem 0.8rem; border: 1px solid #ccc; border-radius: 0.4rem;
     text-decoration: none; color: inherit; }}
a:hover {{ background: #f4f3ee; }}
.gl-index-id {{ color: #6b675e; font-size: 0.85rem; }}
</style>
</head>
<body>
<h1>{escape(site_title)}</h1>
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
