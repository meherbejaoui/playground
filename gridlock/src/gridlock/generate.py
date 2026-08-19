"""Puzzle generation orchestration: seed -> pattern -> fill -> clues -> file.

This module wires together patterns.py, wordlist.py, fill.py and puzzle.py
into the `generate` CLI command (PLAN.md 4.4-4.5, 5).
"""

from __future__ import annotations

import datetime
from pathlib import Path
from random import Random

from .fill import CandidateIndex, fill_any_pattern
from .patterns import load_patterns
from .puzzle import Entry, Puzzle, compute_numbers, encode_answer, grid_entries, to_json
from .wordlist import Word, load_wordlist

SUPPORTED_SIZES = (5,)


class GenerationError(RuntimeError):
    """No bundled pattern could be filled for this seed."""


def today_seed() -> str:
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d")


def puzzle_id(seed: str, size: int) -> str:
    return f"{seed}-{size}"


def _now_iso() -> str:
    return (
        datetime.datetime.now(datetime.timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def _choose_clue(word: Word, rng: Random) -> str:
    if len(word.clues) == 1:
        return word.clues[0]
    return rng.choice(sorted(word.clues))


def _build_entries(
    grid: tuple[str, ...], words: list[Word], rng: Random
) -> tuple[Entry, ...]:
    by_text = {word.text: word for word in words}
    entries = []
    for number, direction, row, col, length, word_text in grid_entries(grid):
        source = by_text[word_text]
        entries.append(
            Entry(
                number=number,
                direction=direction,
                row=row,
                col=col,
                length=length,
                answer=encode_answer(word_text),
                clue=_choose_clue(source, rng),
            )
        )
    return tuple(entries)


def build_puzzle(
    seed: str,
    size: int,
    words: list[Word] | None = None,
    generated_at: str | None = None,
) -> Puzzle:
    """Generate one puzzle for ``seed``, trying patterns until one fills.

    Raises :class:`GenerationError` naming the seed if every bundled pattern
    fails within its backtrack budget (PLAN.md 4.4) — the CLI turns that into
    exit code 2.
    """
    if size not in SUPPORTED_SIZES:
        raise ValueError(
            f"size {size} is not supported in v1 (only {SUPPORTED_SIZES[0]} is available; "
            f"larger sizes are a stretch goal — see PLAN.md 9)"
        )

    rng = Random(seed)
    resolved_words = words if words is not None else load_wordlist()
    index = CandidateIndex(resolved_words)

    order = list(load_patterns(size))
    rng.shuffle(order)

    result = fill_any_pattern(order, index, rng)
    if result is None:
        raise GenerationError(
            f"no bundled pattern could be filled for seed {seed!r} within budget"
        )
    pattern, grid = result

    return Puzzle(
        id=puzzle_id(seed, size),
        size=size,
        seed=seed,
        pattern=pattern.name,
        generated_at=generated_at if generated_at is not None else _now_iso(),
        grid=grid,
        numbers=compute_numbers(grid),
        entries=_build_entries(grid, resolved_words, rng),
    )


def puzzle_path(seed: str, size: int, out_dir: str | Path = "puzzles") -> Path:
    return Path(out_dir) / f"{puzzle_id(seed, size)}.json"


def generate_and_write(
    seed: str | None,
    size: int,
    out_dir: str | Path = "puzzles",
    force: bool = False,
    words: list[Word] | None = None,
    generated_at: str | None = None,
) -> tuple[Puzzle, Path]:
    """Generate a puzzle and write it to ``out_dir``, returning (puzzle, path).

    Refuses to overwrite an existing file unless ``force`` is set.
    """
    resolved_seed = seed if seed is not None else today_seed()
    path = puzzle_path(resolved_seed, size, out_dir)
    if path.exists() and not force:
        raise FileExistsError(f"{path} already exists; pass --force to overwrite")

    puzzle = build_puzzle(resolved_seed, size, words=words, generated_at=generated_at)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(to_json(puzzle), encoding="utf-8")
    return puzzle, path
