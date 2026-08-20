"""Terminal rendering of a puzzle: clued grid previews and stuck-solve diagnostics."""

from __future__ import annotations

from typing import Sequence

from .model import Bitmap, Clues, Puzzle

FILLED_GLYPH = "#"
EMPTY_GLYPH = "·"  # middle dot — visually distinct from a blank cell
UNKNOWN_GLYPH = "?"


def _clue_column_width(clues: Clues) -> int:
    return max((len(run) for run in clues), default=1)


def _format_clue(run: Sequence[int]) -> str:
    return " ".join(str(n) for n in run) if run else "0"


def _render_grid_lines(cells: Sequence[Sequence[str]], row_clues: Clues, col_clues: Clues) -> str:
    """Shared rendering core for both a solved grid and a stuck-solve grid."""
    rows = len(cells)
    cols = len(cells[0]) if rows else 0

    row_label_width = max((len(_format_clue(run)) for run in row_clues), default=1)
    col_header_height = _clue_column_width(col_clues)
    col_labels = [_format_clue(run).split(" ") for run in col_clues]

    lines: list[str] = []

    for header_row in range(col_header_height):
        prefix = " " * row_label_width + " "
        cells_text = []
        for c in range(cols):
            labels = col_labels[c]
            offset = col_header_height - len(labels)
            if header_row >= offset:
                cells_text.append(labels[header_row - offset].rjust(2))
            else:
                cells_text.append("  ")
            if (c + 1) % 5 == 0 and c + 1 != cols:
                cells_text.append("|")
        lines.append(prefix + "".join(cells_text))

    lines.append(" " * row_label_width + " " + "--" * cols)

    for r in range(rows):
        label = _format_clue(row_clues[r]).rjust(row_label_width)
        row_text = []
        for c in range(cols):
            row_text.append(f" {cells[r][c]}")
            if (c + 1) % 5 == 0 and c + 1 != cols:
                row_text.append("|")
        lines.append(f"{label} |{''.join(row_text)}")
        if (r + 1) % 5 == 0 and r + 1 != rows:
            lines.append(" " * row_label_width + " " + "--" * cols)

    return "\n".join(lines)


def render_puzzle(puzzle: Puzzle, solved: bool = True) -> str:
    """A clued grid preview: column clues stacked above, row clues to the left."""
    row_clues = puzzle.row_clues
    col_clues = puzzle.col_clues
    if solved:
        grid = puzzle.bitmap()
        cells = [[FILLED_GLYPH if cell else EMPTY_GLYPH for cell in row] for row in grid]
    else:
        cells = [[UNKNOWN_GLYPH for _ in range(puzzle.cols)] for _ in range(puzzle.rows)]
    header = f"{puzzle.id}  ({puzzle.rows}x{puzzle.cols}, {puzzle.difficulty.grade})"
    return header + "\n\n" + _render_grid_lines(cells, row_clues, col_clues)


def render_bitmap(grid: Bitmap, row_clues: Clues, col_clues: Clues) -> str:
    """A clued grid preview built directly from a bitmap (no Puzzle needed)."""
    cells = [[FILLED_GLYPH if cell else EMPTY_GLYPH for cell in row] for row in grid]
    return _render_grid_lines(cells, row_clues, col_clues)


def render_stuck(
    grid: Sequence[Sequence[bool | None]], row_clues: Clues, col_clues: Clues
) -> str:
    """A partially-solved grid: ``True`` filled, ``False`` empty, ``None`` unknown.

    Deliberately independent of solver.py's cell-state representation (that
    module doesn't exist yet when this one is first written) — callers
    convert whatever internal state they use to this plain ``bool | None``
    convention. Used by the gallery validator to show artists exactly where
    single-line deduction gets stuck.
    """
    cells = [
        [FILLED_GLYPH if cell is True else EMPTY_GLYPH if cell is False else UNKNOWN_GLYPH for cell in row]
        for row in grid
    ]
    return _render_grid_lines(cells, row_clues, col_clues)
