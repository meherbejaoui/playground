"""The puzzle model: bitmaps, clue derivation, bit-packing, and the JSON
contract (PLAN.md 3.1, 3.3).

This module is the boundary between the generator/solver and everything
downstream. Nothing here knows how a grid gets filled or solved; it only
describes a finished puzzle.
"""

from __future__ import annotations

import base64
import json
from dataclasses import dataclass
from typing import Any, Sequence

FORMAT_VERSION = 1
FILLED = "#"
EMPTY = "."

DAILY = "daily"
GALLERY = "gallery"

MIN_SIZE = 5
MAX_SIZE = 15

Bitmap = tuple[tuple[bool, ...], ...]
Clues = tuple[tuple[int, ...], ...]


class BitmapError(ValueError):
    """A bitmap's text form is malformed."""


class PuzzleError(ValueError):
    """A puzzle payload is structurally invalid."""


def _bitmap_from_rows(rows: Sequence[str]) -> Bitmap:
    if not rows:
        raise BitmapError("bitmap has no rows")
    width = len(rows[0])
    if width == 0:
        raise BitmapError("bitmap rows are empty")
    grid: list[tuple[bool, ...]] = []
    for index, row in enumerate(rows):
        if len(row) != width:
            raise BitmapError(
                f"row {index} has length {len(row)}, expected {width} (ragged bitmap)"
            )
        cells: list[bool] = []
        for col, char in enumerate(row):
            if char == FILLED:
                cells.append(True)
            elif char == EMPTY:
                cells.append(False)
            else:
                raise BitmapError(
                    f"row {index}, col {col}: {char!r} is not {FILLED!r} or {EMPTY!r}"
                )
        grid.append(tuple(cells))
    return tuple(grid)


def parse_bitmap(text: str) -> Bitmap:
    """Parse a multi-line ``#``/``.`` block into a :data:`Bitmap`."""
    rows = [line for line in text.splitlines() if line != ""]
    return _bitmap_from_rows(rows)


def format_bitmap(grid: Bitmap) -> str:
    """The inverse of :func:`parse_bitmap`."""
    return "\n".join(
        "".join(FILLED if cell else EMPTY for cell in row) for row in grid
    )


def _line_clues(line: Sequence[bool]) -> tuple[int, ...]:
    clues: list[int] = []
    run = 0
    for cell in line:
        if cell:
            run += 1
        else:
            if run:
                clues.append(run)
            run = 0
    if run:
        clues.append(run)
    return tuple(clues)


def derive_clues(grid: Bitmap) -> tuple[Clues, Clues]:
    """Standard nonogram run-length clues: ``(rowClues, colClues)``.

    An all-empty line's clue is ``()`` (serialized as ``[]``), never ``(0,)``.
    """
    rows = len(grid)
    cols = len(grid[0]) if rows else 0
    row_clues = tuple(_line_clues(row) for row in grid)
    col_clues = tuple(
        _line_clues(tuple(grid[r][c] for r in range(rows))) for c in range(cols)
    )
    return row_clues, col_clues


def pack_solution(grid: Bitmap) -> str:
    """Pack a bitmap to base64 (PLAN.md 3.3): row-major, each row padded to a
    whole number of bytes, MSB-first within a byte.
    """
    rows = len(grid)
    cols = len(grid[0]) if rows else 0
    bytes_per_row = (cols + 7) // 8
    data = bytearray(rows * bytes_per_row)
    for r, row in enumerate(grid):
        for c, cell in enumerate(row):
            if cell:
                byte_index = r * bytes_per_row + c // 8
                bit_index = 7 - (c % 8)
                data[byte_index] |= 1 << bit_index
    return base64.b64encode(bytes(data)).decode("ascii")


def unpack_solution(encoded: str, rows: int, cols: int) -> Bitmap:
    """The inverse of :func:`pack_solution`."""
    bytes_per_row = (cols + 7) // 8
    data = base64.b64decode(encoded.encode("ascii"))
    expected = rows * bytes_per_row
    if len(data) != expected:
        raise BitmapError(
            f"packed solution has {len(data)} bytes, expected {expected} for a "
            f"{rows}x{cols} grid"
        )
    grid: list[tuple[bool, ...]] = []
    for r in range(rows):
        row: list[bool] = []
        for c in range(cols):
            byte_index = r * bytes_per_row + c // 8
            bit_index = 7 - (c % 8)
            row.append(bool(data[byte_index] & (1 << bit_index)))
        grid.append(tuple(row))
    return tuple(grid)


@dataclass(frozen=True)
class Difficulty:
    passes: int
    grade: str


@dataclass(frozen=True)
class Puzzle:
    id: str
    kind: str
    rows: int
    cols: int
    row_clues: Clues
    col_clues: Clues
    solution: str
    difficulty: Difficulty
    generated_at: str
    title: str | None = None
    seed: str | None = None
    slug: str | None = None
    format: int = FORMAT_VERSION

    def bitmap(self) -> Bitmap:
        return unpack_solution(self.solution, self.rows, self.cols)


def to_dict(puzzle: Puzzle) -> dict[str, Any]:
    return {
        "format": puzzle.format,
        "id": puzzle.id,
        "kind": puzzle.kind,
        "title": puzzle.title,
        "rows": puzzle.rows,
        "cols": puzzle.cols,
        "rowClues": [list(c) for c in puzzle.row_clues],
        "colClues": [list(c) for c in puzzle.col_clues],
        "solution": puzzle.solution,
        "difficulty": {
            "passes": puzzle.difficulty.passes,
            "grade": puzzle.difficulty.grade,
        },
        "seed": puzzle.seed,
        "generatedAt": puzzle.generated_at,
        "slug": puzzle.slug,
    }


def from_dict(payload: dict[str, Any]) -> Puzzle:
    try:
        difficulty = Difficulty(
            passes=int(payload["difficulty"]["passes"]),
            grade=str(payload["difficulty"]["grade"]),
        )
        return Puzzle(
            format=int(payload.get("format", FORMAT_VERSION)),
            id=str(payload["id"]),
            kind=str(payload["kind"]),
            title=payload.get("title"),
            rows=int(payload["rows"]),
            cols=int(payload["cols"]),
            row_clues=tuple(tuple(int(n) for n in run) for run in payload["rowClues"]),
            col_clues=tuple(tuple(int(n) for n in run) for run in payload["colClues"]),
            solution=str(payload["solution"]),
            difficulty=difficulty,
            generated_at=str(payload["generatedAt"]),
            seed=payload.get("seed"),
            slug=payload.get("slug"),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise PuzzleError(f"invalid puzzle payload: {exc}") from exc


def to_json(puzzle: Puzzle) -> str:
    return json.dumps(to_dict(puzzle), indent=2, ensure_ascii=False) + "\n"


def from_json(text: str) -> Puzzle:
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise PuzzleError(f"invalid puzzle JSON: {exc}") from exc
    if not isinstance(payload, dict):
        raise PuzzleError("puzzle JSON must be an object")
    return from_dict(payload)
