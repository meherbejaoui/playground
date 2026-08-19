"""The puzzle model: numbering, entries, and the JSON contract (PLAN.md 3.3).

This module is the boundary between the generator and everything downstream.
Nothing here knows how a grid gets filled; it only describes a finished one.
"""

from __future__ import annotations

import base64
import json
from dataclasses import dataclass, replace
from typing import Any, Iterable

FORMAT_VERSION = 1
BLOCK = "#"
ACROSS = "across"
DOWN = "down"


class PuzzleError(ValueError):
    """A puzzle payload is structurally invalid."""


@dataclass(frozen=True)
class Entry:
    number: int
    direction: str
    row: int
    col: int
    length: int
    answer: str
    clue: str

    def cells(self) -> list[tuple[int, int]]:
        if self.direction == ACROSS:
            return [(self.row, self.col + i) for i in range(self.length)]
        return [(self.row + i, self.col) for i in range(self.length)]


@dataclass(frozen=True)
class Puzzle:
    id: str
    size: int
    seed: str
    pattern: str
    generated_at: str
    grid: tuple[str, ...]
    numbers: tuple[tuple[int, ...], ...]
    entries: tuple[Entry, ...]
    format: int = FORMAT_VERSION

    def is_block(self, row: int, col: int) -> bool:
        return self.grid[row][col] == BLOCK

    def entries_for(self, direction: str) -> list[Entry]:
        return [e for e in self.entries if e.direction == direction]


def encode_answer(word: str) -> str:
    """Base64 an answer for casual spoiler protection (PLAN.md 3.3)."""
    return base64.b64encode(word.encode("ascii")).decode("ascii")


def decode_answer(encoded: str) -> str:
    return base64.b64decode(encoded.encode("ascii")).decode("ascii")


def _is_white(grid: Iterable[str], row: int, col: int, size: int) -> bool:
    rows = list(grid)
    if not (0 <= row < size and 0 <= col < size):
        return False
    return rows[row][col] != BLOCK


def compute_numbers(grid: Iterable[str]) -> tuple[tuple[int, ...], ...]:
    """Standard crossword numbering.

    Scanning row-major, a white cell is numbered when it starts an across
    entry (nothing white to its left, something white to its right) or a down
    entry (nothing white above, something white below). Blocks are ``-1`` and
    unnumbered white cells are ``0``.
    """
    rows = list(grid)
    size = len(rows)
    if any(len(row) != size for row in rows):
        raise PuzzleError("grid must be square")

    numbers: list[list[int]] = []
    next_number = 1
    for row in range(size):
        line: list[int] = []
        for col in range(size):
            if not _is_white(rows, row, col, size):
                line.append(-1)
                continue
            starts_across = not _is_white(rows, row, col - 1, size) and _is_white(
                rows, row, col + 1, size
            )
            starts_down = not _is_white(rows, row - 1, col, size) and _is_white(
                rows, row + 1, col, size
            )
            if starts_across or starts_down:
                line.append(next_number)
                next_number += 1
            else:
                line.append(0)
        numbers.append(line)
    return tuple(tuple(line) for line in numbers)


def grid_entries(grid: Iterable[str]) -> list[tuple[int, str, int, int, int, str]]:
    """Every entry the grid contains, as ``(number, direction, row, col, length, word)``.

    Ordered by number, across before down at the same number — the order the
    clue lists are printed in.
    """
    rows = list(grid)
    size = len(rows)
    numbers = compute_numbers(rows)
    found: list[tuple[int, str, int, int, int, str]] = []

    for row in range(size):
        for col in range(size):
            number = numbers[row][col]
            if number <= 0:
                continue
            if not _is_white(rows, row, col - 1, size) and _is_white(rows, row, col + 1, size):
                length = 0
                while _is_white(rows, row, col + length, size):
                    length += 1
                word = rows[row][col : col + length]
                found.append((number, ACROSS, row, col, length, word))
            if not _is_white(rows, row - 1, col, size) and _is_white(rows, row + 1, col, size):
                length = 0
                while _is_white(rows, row + length, col, size):
                    length += 1
                word = "".join(rows[row + i][col] for i in range(length))
                found.append((number, DOWN, row, col, length, word))

    found.sort(key=lambda item: (item[0], 0 if item[1] == ACROSS else 1))
    return found


def to_dict(puzzle: Puzzle) -> dict[str, Any]:
    return {
        "format": puzzle.format,
        "id": puzzle.id,
        "size": puzzle.size,
        "seed": puzzle.seed,
        "pattern": puzzle.pattern,
        "generatedAt": puzzle.generated_at,
        "grid": list(puzzle.grid),
        "numbers": [list(row) for row in puzzle.numbers],
        "entries": [
            {
                "number": entry.number,
                "direction": entry.direction,
                "row": entry.row,
                "col": entry.col,
                "length": entry.length,
                "answer": entry.answer,
                "clue": entry.clue,
            }
            for entry in puzzle.entries
        ],
    }


def from_dict(payload: dict[str, Any]) -> Puzzle:
    try:
        entries = tuple(
            Entry(
                number=int(raw["number"]),
                direction=str(raw["direction"]),
                row=int(raw["row"]),
                col=int(raw["col"]),
                length=int(raw["length"]),
                answer=str(raw["answer"]),
                clue=str(raw["clue"]),
            )
            for raw in payload["entries"]
        )
        return Puzzle(
            format=int(payload.get("format", FORMAT_VERSION)),
            id=str(payload["id"]),
            size=int(payload["size"]),
            seed=str(payload["seed"]),
            pattern=str(payload["pattern"]),
            generated_at=str(payload["generatedAt"]),
            grid=tuple(str(row) for row in payload["grid"]),
            numbers=tuple(tuple(int(n) for n in row) for row in payload["numbers"]),
            entries=entries,
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


def strip_solution(payload: dict[str, Any]) -> dict[str, Any]:
    """Return a copy of a puzzle dict whose ``grid`` carries no letters.

    ``build`` serves this variant: the block layout survives as ``#``/``.``
    so the player can lay out the grid, while the answers remain only in the
    base64 ``entries[].answer`` fields.
    """
    stripped = dict(payload)
    stripped["grid"] = [
        "".join(BLOCK if char == BLOCK else "." for char in row) for row in payload["grid"]
    ]
    return stripped


def with_clues(puzzle: Puzzle, clues: dict[tuple[int, str], str]) -> Puzzle:
    """Return ``puzzle`` with each entry's clue replaced by ``clues[(number, direction)]``."""
    entries = tuple(
        replace(entry, clue=clues.get((entry.number, entry.direction), entry.clue))
        for entry in puzzle.entries
    )
    return replace(puzzle, entries=entries)
