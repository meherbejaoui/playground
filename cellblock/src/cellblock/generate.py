"""Procedural daily puzzle generation (PLAN.md 4.5) and its CLI orchestration.

The core loop draws candidate bitmaps and keeps only the first one the line
solver can fully certify from a blank grid — that certification is what
guarantees every shipped daily puzzle needs no guessing.
"""

from __future__ import annotations

import datetime
from pathlib import Path
from random import Random

from .model import Bitmap, DAILY, Difficulty, Puzzle, derive_clues, pack_solution
from .solver import SOLVED, grade, solve_grid

MAX_CANDIDATES = 1000
FILL_PROBABILITY = 0.55
SMOOTHING_THRESHOLD = 5  # of the 9-cell neighborhood (self + 8 neighbors)
MIN_DENSITY = 0.35
MAX_DENSITY = 0.65
MAX_TRIVIAL_LINE_FRACTION = 0.25

SUPPORTED_SIZES = (5, 10, 15)


class GenerationError(RuntimeError):
    """No candidate bitmap was certified solvable within the attempt budget."""


def today_seed() -> str:
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d")


def puzzle_id(seed: str, size: int) -> str:
    return f"{seed}-{size}x{size}"


def _now_iso() -> str:
    return (
        datetime.datetime.now(datetime.timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def _draw_candidate(rng: Random, rows: int, cols: int) -> Bitmap:
    """One noisy bitmap, then one smoothing pass (PLAN.md 4.5 step 1)."""
    raw = [[rng.random() < FILL_PROBABILITY for _ in range(cols)] for _ in range(rows)]

    smoothed: list[tuple[bool, ...]] = []
    for r in range(rows):
        row: list[bool] = []
        for c in range(cols):
            count = 0
            for dr in (-1, 0, 1):
                for dc in (-1, 0, 1):
                    rr, cc = r + dr, c + dc
                    if 0 <= rr < rows and 0 <= cc < cols and raw[rr][cc]:
                        count += 1
            row.append(count >= SMOOTHING_THRESHOLD)
        smoothed.append(tuple(row))
    return tuple(smoothed)


def _density(grid: Bitmap) -> float:
    total = sum(len(row) for row in grid)
    filled = sum(1 for row in grid for cell in row if cell)
    return filled / total if total else 0.0


def _trivial_line_fraction(grid: Bitmap, rows: int, cols: int) -> float:
    trivial = 0
    for row in grid:
        if all(row) or not any(row):
            trivial += 1
    for c in range(cols):
        column = [grid[r][c] for r in range(rows)]
        if all(column) or not any(column):
            trivial += 1
    return trivial / (rows + cols) if (rows + cols) else 0.0


def find_solvable_bitmap(rng: Random, rows: int, cols: int) -> tuple[Bitmap, int, int]:
    """The first candidate the line solver certifies, or raise :class:`GenerationError`.

    Returns ``(bitmap, attempt_number, passes)``. ``passes`` is the pass
    count from solving the *empty* grid — the same solve that certified it —
    which doubles as the raw difficulty signal (PLAN.md 4.4).
    """
    for attempt in range(1, MAX_CANDIDATES + 1):
        candidate = _draw_candidate(rng, rows, cols)

        density = _density(candidate)
        if not (MIN_DENSITY <= density <= MAX_DENSITY):
            continue
        if _trivial_line_fraction(candidate, rows, cols) > MAX_TRIVIAL_LINE_FRACTION:
            continue

        row_clues, col_clues = derive_clues(candidate)
        status, _grid, passes = solve_grid(row_clues, col_clues)
        if status == SOLVED:
            return candidate, attempt, passes

    raise GenerationError(
        f"no candidate certified solvable within {MAX_CANDIDATES} attempts"
    )


def build_puzzle(seed: str, size: int, generated_at: str | None = None) -> Puzzle:
    """Generate one certified-solvable daily puzzle for ``seed``."""
    if size not in SUPPORTED_SIZES:
        raise ValueError(
            f"size {size} is not supported (choose one of {SUPPORTED_SIZES})"
        )

    rng = Random(seed)
    grid, _attempt, passes = find_solvable_bitmap(rng, size, size)
    row_clues, col_clues = derive_clues(grid)

    return Puzzle(
        id=puzzle_id(seed, size),
        kind=DAILY,
        rows=size,
        cols=size,
        row_clues=row_clues,
        col_clues=col_clues,
        solution=pack_solution(grid),
        difficulty=Difficulty(passes=passes, grade=grade(passes, size, size)),
        generated_at=generated_at if generated_at is not None else _now_iso(),
        seed=seed,
    )


def puzzle_path(seed: str, size: int, out_dir: str | Path = "puzzles") -> Path:
    return Path(out_dir) / f"{puzzle_id(seed, size)}.json"


def generate_and_write(
    seed: str | None,
    size: int,
    out_dir: str | Path = "puzzles",
    force: bool = False,
    generated_at: str | None = None,
) -> tuple[Puzzle, Path]:
    """Generate a puzzle and write it to ``out_dir``, returning (puzzle, path).

    Refuses to overwrite an existing file unless ``force`` is set.
    """
    from .model import to_json

    resolved_seed = seed if seed is not None else today_seed()
    path = puzzle_path(resolved_seed, size, out_dir)
    if path.exists() and not force:
        raise FileExistsError(f"{path} already exists; pass --force to overwrite")

    puzzle = build_puzzle(resolved_seed, size, generated_at=generated_at)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(to_json(puzzle), encoding="utf-8")
    return puzzle, path
