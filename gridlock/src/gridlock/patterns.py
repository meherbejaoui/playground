"""Block patterns: loading, validation, slot extraction, crossing maps.

A *pattern* is the black-square layout of a grid, independent of any letters.
Patterns are data (``data/patterns/<size>.json``), not code, so new layouts
need no Python changes — but every pattern is validated against the rules in
PLAN.md 3.2 before it is ever used.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path

ACROSS = "across"
DOWN = "down"

MIN_SLOT_LENGTH = 3
MAX_BLOCKS_5 = 8


class PatternError(ValueError):
    """A pattern violates one of the structural rules in PLAN.md 3.2."""


def data_dir() -> Path:
    """Locate the project's ``data/`` directory.

    Resolution order: ``GRIDLOCK_DATA_DIR`` env var, the directory shipped
    alongside the source tree, then ``./data`` relative to the working
    directory.
    """
    env = os.environ.get("GRIDLOCK_DATA_DIR")
    if env:
        return Path(env)
    packaged = Path(__file__).resolve().parents[2] / "data"
    if packaged.is_dir():
        return packaged
    return Path("data")


@dataclass(frozen=True)
class Pattern:
    name: str
    size: int
    blocks: frozenset[tuple[int, int]]

    def is_block(self, row: int, col: int) -> bool:
        return (row, col) in self.blocks

    def white_cells(self) -> list[tuple[int, int]]:
        return [
            (r, c)
            for r in range(self.size)
            for c in range(self.size)
            if (r, c) not in self.blocks
        ]


@dataclass(frozen=True)
class Slot:
    row: int
    col: int
    direction: str
    length: int
    cells: tuple[tuple[int, int], ...]


def _runs(pattern: Pattern, direction: str) -> list[Slot]:
    """Maximal runs of white cells in one direction, in reading order."""
    slots: list[Slot] = []
    size = pattern.size
    for outer in range(size):
        run: list[tuple[int, int]] = []
        for inner in range(size):
            cell = (outer, inner) if direction == ACROSS else (inner, outer)
            if pattern.is_block(*cell):
                if run:
                    slots.append(_slot_from_run(run, direction))
                    run = []
            else:
                run.append(cell)
        if run:
            slots.append(_slot_from_run(run, direction))
    return slots


def _slot_from_run(run: list[tuple[int, int]], direction: str) -> Slot:
    start = run[0]
    return Slot(
        row=start[0],
        col=start[1],
        direction=direction,
        length=len(run),
        cells=tuple(run),
    )


def extract_slots(pattern: Pattern) -> list[Slot]:
    """All across slots (row-major) followed by all down slots (column-major).

    Runs shorter than :data:`MIN_SLOT_LENGTH` are *not* filtered out here —
    :func:`validate_pattern` rejects patterns that contain any, so callers of
    a validated pattern never see one.
    """
    return _runs(pattern, ACROSS) + _runs(pattern, DOWN)


def crossings(slots: list[Slot]) -> list[list[tuple[int, int, int]]]:
    """For each slot, the ``(own_pos, other_slot_index, other_pos)`` triples.

    Two slots cross when they share a cell; ``own_pos``/``other_pos`` are the
    indexes of that shared cell within each slot.
    """
    cell_index: dict[tuple[int, int], list[tuple[int, int]]] = {}
    for slot_index, slot in enumerate(slots):
        for position, cell in enumerate(slot.cells):
            cell_index.setdefault(cell, []).append((slot_index, position))

    result: list[list[tuple[int, int, int]]] = [[] for _ in slots]
    for occupants in cell_index.values():
        for slot_index, position in occupants:
            for other_index, other_position in occupants:
                if other_index != slot_index:
                    result[slot_index].append((position, other_index, other_position))
    for entry in result:
        entry.sort()
    return result


def _connected(pattern: Pattern) -> bool:
    white = pattern.white_cells()
    if not white:
        return False
    remaining = set(white)
    start = white[0]
    stack = [start]
    remaining.discard(start)
    while stack:
        row, col = stack.pop()
        for neighbour in ((row - 1, col), (row + 1, col), (row, col - 1), (row, col + 1)):
            if neighbour in remaining:
                remaining.discard(neighbour)
                stack.append(neighbour)
    return not remaining


def validate_pattern(pattern: Pattern) -> None:
    """Raise :class:`PatternError` unless the pattern satisfies PLAN.md 3.2."""
    size = pattern.size
    if size < 3:
        raise PatternError(f"pattern {pattern.name!r}: size {size} is below the 3x3 minimum")

    for row, col in sorted(pattern.blocks):
        if not (0 <= row < size and 0 <= col < size):
            raise PatternError(
                f"pattern {pattern.name!r}: block ({row}, {col}) lies outside the {size}x{size} grid"
            )

    # Rule 1 — 180 degree rotational symmetry.
    for row, col in sorted(pattern.blocks):
        mirror = (size - 1 - row, size - 1 - col)
        if mirror not in pattern.blocks:
            raise PatternError(
                f"pattern {pattern.name!r}: rule 1 (symmetry) — block ({row}, {col}) "
                f"has no counterpart at {mirror}"
            )

    # Rule 4 — block budget (checked before the costlier rules).
    if len(pattern.blocks) > MAX_BLOCKS_5:
        raise PatternError(
            f"pattern {pattern.name!r}: rule 4 (block budget) — {len(pattern.blocks)} blocks "
            f"exceeds the maximum of {MAX_BLOCKS_5}"
        )

    # Rule 2 — every slot is at least MIN_SLOT_LENGTH long.
    for slot in extract_slots(pattern):
        if slot.length < MIN_SLOT_LENGTH:
            raise PatternError(
                f"pattern {pattern.name!r}: rule 2 (minimum slot length) — {slot.direction} "
                f"slot at ({slot.row}, {slot.col}) has length {slot.length}"
            )

    # Rule 3 — the white cells form one connected region.
    if not _connected(pattern):
        raise PatternError(
            f"pattern {pattern.name!r}: rule 3 (connectivity) — the white cells are not "
            f"a single connected region"
        )


def patterns_path(size: int, directory: Path | None = None) -> Path:
    base = directory if directory is not None else data_dir() / "patterns"
    return base / f"{size}.json"


def load_patterns(size: int = 5, directory: Path | None = None) -> list[Pattern]:
    """Load and validate every pattern for ``size``.

    Raises :class:`FileNotFoundError` if no pattern file exists for the size,
    and :class:`PatternError` if any pattern in the file is invalid.
    """
    path = patterns_path(size, directory)
    if not path.is_file():
        raise FileNotFoundError(f"no pattern file for size {size} at {path}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    declared = payload.get("size")
    if declared != size:
        raise PatternError(f"{path}: file declares size {declared!r} but was loaded as {size}")

    patterns: list[Pattern] = []
    seen: set[str] = set()
    for raw in payload.get("patterns", []):
        name = raw["name"]
        if name in seen:
            raise PatternError(f"{path}: duplicate pattern name {name!r}")
        seen.add(name)
        pattern = Pattern(
            name=name,
            size=size,
            blocks=frozenset((int(r), int(c)) for r, c in raw.get("blocks", [])),
        )
        validate_pattern(pattern)
        patterns.append(pattern)

    if not patterns:
        raise PatternError(f"{path}: contains no patterns")
    return patterns
