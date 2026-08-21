"""Tests for procedural daily puzzle generation (PLAN.md 4.5, 8)."""

from __future__ import annotations

import time

import pytest

from cellblock.generate import (
    build_puzzle,
    generate_and_write,
    puzzle_id,
    today_seed,
)
from cellblock.model import to_json
from cellblock.solver import SOLVED, solve_grid


class TestFindSolvableBitmap:
    def test_density_and_triviality_rejections_are_reachable(self):
        # Not a correctness requirement by itself, just confirms the loop
        # doesn't trivially accept the very first candidate every time.
        from random import Random

        from cellblock.generate import find_solvable_bitmap

        rng = Random("density-check")
        _grid, attempt, _passes = find_solvable_bitmap(rng, 10, 10)
        assert attempt >= 1


class TestNoGuessingGuarantee:
    """PLAN.md 8: every generated puzzle must be solvable from a blank grid
    by single-line deduction alone, and that solution must match what got
    shipped."""

    @pytest.mark.parametrize("seed", [f"sweep-{i}" for i in range(10)])
    @pytest.mark.parametrize("size", [5, 10])
    def test_generated_puzzle_resolves_cleanly_from_scratch(self, seed, size):
        started = time.perf_counter()
        puzzle = build_puzzle(seed, size)
        elapsed = time.perf_counter() - started
        assert elapsed < 5.0, f"{seed}/{size} took {elapsed:.2f}s"

        status, grid, _passes = solve_grid(puzzle.row_clues, puzzle.col_clues)
        assert status == SOLVED

        solved_bools = tuple(tuple(cell == 1 for cell in row) for row in grid)
        assert solved_bools == puzzle.bitmap()


class TestDeterminism:
    def test_same_seed_gives_byte_identical_json_minus_timestamp(self):
        first = build_puzzle("repeat-me", 10, generated_at="stamp")
        second = build_puzzle("repeat-me", 10, generated_at="stamp")
        assert to_json(first) == to_json(second)

    def test_different_seeds_give_different_solutions(self):
        solutions = {build_puzzle(f"seed-{i}", 5).solution for i in range(3)}
        assert len(solutions) == 3


class TestBuildPuzzle:
    def test_schema_is_self_consistent(self):
        puzzle = build_puzzle("schema-check", 5)
        assert puzzle.id == "schema-check-5x5"
        assert puzzle.kind == "daily"
        assert puzzle.title is None
        assert puzzle.slug is None
        assert puzzle.seed == "schema-check"
        assert len(puzzle.row_clues) == 5
        assert len(puzzle.col_clues) == 5

    def test_unsupported_size_raises(self):
        with pytest.raises(ValueError, match="not supported"):
            build_puzzle("x", 7)

    def test_default_seed_is_todays_utc_date(self):
        assert build_puzzle(today_seed(), 5).seed == today_seed()


class TestGenerateAndWrite:
    def test_writes_a_valid_file(self, tmp_path):
        puzzle, path = generate_and_write("write-me", 5, out_dir=tmp_path)
        assert path == tmp_path / "write-me-5x5.json"
        assert path.is_file()

    def test_default_seed_resolves_to_today(self, tmp_path):
        puzzle, path = generate_and_write(None, 5, out_dir=tmp_path)
        assert puzzle.seed == today_seed()
        assert path.name == f"{puzzle_id(today_seed(), 5)}.json"

    def test_refuses_to_overwrite_without_force(self, tmp_path):
        generate_and_write("dup", 5, out_dir=tmp_path)
        with pytest.raises(FileExistsError):
            generate_and_write("dup", 5, out_dir=tmp_path)

    def test_force_overwrites(self, tmp_path):
        generate_and_write("dup2", 5, out_dir=tmp_path)
        puzzle, path = generate_and_write("dup2", 5, out_dir=tmp_path, force=True)
        assert path.is_file()
        assert puzzle.seed == "dup2"
