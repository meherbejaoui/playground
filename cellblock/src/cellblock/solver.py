"""The line solver and grid propagation (PLAN.md 4). Pure logic, no I/O.

This is the certification engine the whole project rests on: a puzzle is
only ever shipped if :func:`solve_grid` reaches ``SOLVED`` from a blank
grid, meaning single-line deduction alone — no guessing — recovers the
unique solution.
"""

from __future__ import annotations

from collections import deque
from enum import IntEnum
from functools import lru_cache
from typing import Sequence

SOLVED = "solved"
STUCK = "stuck"
CONTRADICTION = "contradiction"

GRADE_EASY = "easy"
GRADE_MEDIUM = "medium"
GRADE_HARD = "hard"


class State(IntEnum):
    UNKNOWN = 0
    FILLED = 1
    EMPTY = -1


Line = tuple[State, ...]
Grid = tuple[tuple[State, ...], ...]


def _feasible(clues: tuple[int, ...], line: Line) -> bool:
    """Is there any legal placement of ``clues`` consistent with ``line``?"""
    n = len(line)
    k = len(clues)

    @lru_cache(maxsize=None)
    def go(i: int, j: int) -> bool:
        if j == k:
            return not any(line[p] == State.FILLED for p in range(i, n))
        if i >= n:
            return False

        # Option A: cell i is empty (skip it) — allowed unless it's fixed FILLED.
        if line[i] != State.FILLED and go(i + 1, j):
            return True

        # Option B: run j starts exactly at i.
        length = clues[j]
        end = i + length
        if end <= n and not any(line[p] == State.EMPTY for p in range(i, end)):
            if end == n or line[end] != State.FILLED:
                next_start = end + 1 if end < n else end
                if go(next_start, j + 1):
                    return True
        return False

    return go(0, 0)


def solve_line(clues: Sequence[int], line: Line) -> Line | None:
    """Every cell forced by ``clues`` given the partial state ``line``.

    Returns the updated line (unchanged where nothing new was forced), or
    ``None`` if no arrangement of the runs is consistent with ``line`` at
    all (a contradiction).
    """
    clue_tuple = tuple(clues)
    if not _feasible(clue_tuple, line):
        return None

    forced = list(line)
    for i, cell in enumerate(line):
        if cell != State.UNKNOWN:
            continue

        pinned_filled = line[:i] + (State.FILLED,) + line[i + 1 :]
        pinned_empty = line[:i] + (State.EMPTY,) + line[i + 1 :]
        filled_possible = _feasible(clue_tuple, pinned_filled)
        empty_possible = _feasible(clue_tuple, pinned_empty)

        if filled_possible and not empty_possible:
            forced[i] = State.FILLED
        elif empty_possible and not filled_possible:
            forced[i] = State.EMPTY
        # else: both possible (stays UNKNOWN), or — unreachable, given the
        # overall line is feasible — neither possible.

    return tuple(forced)


def _freeze(cells: list[list[State]]) -> Grid:
    return tuple(tuple(row) for row in cells)


def solve_grid(
    row_clues: Sequence[Sequence[int]],
    col_clues: Sequence[Sequence[int]],
    grid: Grid | None = None,
) -> tuple[str, Grid, int]:
    """Propagate :func:`solve_line` across every row and column to a fixpoint.

    Returns ``(status, final_grid, passes)`` where ``status`` is one of
    :data:`SOLVED`, :data:`STUCK`, or :data:`CONTRADICTION`, and ``passes``
    counts the ``solve_line`` calls that changed at least one cell — the raw
    difficulty signal (PLAN.md 4.4).
    """
    rows = len(row_clues)
    cols = len(col_clues)
    cells: list[list[State]] = (
        [[State.UNKNOWN] * cols for _ in range(rows)]
        if grid is None
        else [list(row) for row in grid]
    )

    queue: deque[tuple[str, int]] = deque()
    queued: set[tuple[str, int]] = set()
    for r in range(rows):
        queue.append(("row", r))
        queued.add(("row", r))
    for c in range(cols):
        queue.append(("col", c))
        queued.add(("col", c))

    passes = 0

    def enqueue(key: tuple[str, int]) -> None:
        if key not in queued:
            queue.append(key)
            queued.add(key)

    while queue:
        kind, index = queue.popleft()
        queued.discard((kind, index))

        if kind == "row":
            r = index
            line = tuple(cells[r])
            result = solve_line(row_clues[r], line)
            if result is None:
                return CONTRADICTION, _freeze(cells), passes
            if result != line:
                passes += 1
                for c in range(cols):
                    if result[c] != cells[r][c]:
                        cells[r][c] = result[c]
                        enqueue(("col", c))
        else:
            c = index
            line = tuple(cells[r][c] for r in range(rows))
            result = solve_line(col_clues[c], line)
            if result is None:
                return CONTRADICTION, _freeze(cells), passes
            if result != line:
                passes += 1
                for r in range(rows):
                    if result[r] != cells[r][c]:
                        cells[r][c] = result[r]
                        enqueue(("row", r))

    status = SOLVED if all(cell != State.UNKNOWN for row in cells for cell in row) else STUCK
    return status, _freeze(cells), passes


def grade(passes: int, rows: int, cols: int) -> str:
    """Crude difficulty label from a solve of the empty grid (PLAN.md 4.4)."""
    threshold = rows + cols
    if passes <= threshold:
        return GRADE_EASY
    if passes <= 2 * threshold:
        return GRADE_MEDIUM
    return GRADE_HARD
