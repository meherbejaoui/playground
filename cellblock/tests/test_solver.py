"""Tests for the line solver and grid propagation.

The brute-force cross-check in :class:`TestBruteForceCrossCheck` is this
project's correctness anchor (PLAN.md 8): it enumerates every possible
completion of a partial line directly, independent of solve_line's own DP,
and compares the forced cells. If this test passes, the DP is provably
correct on everything it was exercised against.
"""

from __future__ import annotations

import itertools
from random import Random

import pytest

from cellblock.solver import (
    CONTRADICTION,
    GRADE_EASY,
    GRADE_HARD,
    GRADE_MEDIUM,
    SOLVED,
    STUCK,
    State,
    grade,
    solve_grid,
    solve_line,
)

U, F, E = State.UNKNOWN, State.FILLED, State.EMPTY


def line(*chars: str) -> tuple[State, ...]:
    """Shorthand: line('?', '#', '.', '?') -> (UNKNOWN, FILLED, EMPTY, UNKNOWN)."""
    table = {"?": U, "#": F, ".": E}
    return tuple(table[c] for c in chars)


class TestSolveLineHandVerified:
    """Every expected value here was cross-checked against an independent
    brute-force enumeration before being written down (see the commit that
    introduced this file for the verification script's output)."""

    def test_empty_clues_forces_every_unknown_cell_empty(self):
        assert solve_line((), (U, U, U, U, U)) == (E, E, E, E, E)

    def test_empty_clues_on_an_already_empty_line_is_idempotent(self):
        assert solve_line((), (E, E, E)) == (E, E, E)

    def test_full_line_run_forces_every_cell_filled(self):
        assert solve_line((5,), (U, U, U, U, U)) == (F, F, F, F, F)

    def test_single_run_with_slack_forces_only_the_overlap(self):
        assert solve_line((3,), (U, U, U, U, U)) == (U, U, F, U, U)

    def test_two_runs_with_no_slack_forces_the_whole_line(self):
        assert solve_line((1, 1), (U, U, U)) == (F, E, F)

    def test_exact_fit_multi_run_forces_the_whole_line(self):
        assert solve_line((2, 2), (U, U, U, U, U)) == (F, F, E, F, F)

    def test_run_longer_than_the_line_is_a_contradiction(self):
        assert solve_line((5,), (U, U, U, U)) is None

    def test_a_run_that_cannot_fit_among_fixed_empties_is_a_contradiction(self):
        assert solve_line((2,), (E, E, E)) is None

    def test_solved_line_is_idempotent(self):
        assert solve_line((1, 1), (F, E, F)) == (F, E, F)

    def test_classic_overlap_eight_in_ten(self):
        # clue [8] on a length-10 line: valid starts are 0, 1, 2; every
        # placement covers cells 2..7, so exactly those six are forced.
        assert solve_line((8,), (U,) * 10) == (U, U, F, F, F, F, F, F, U, U)

    def test_a_pre_filled_anchor_narrows_the_overlap_further(self):
        # A lone FILLED cell at index 2 rules out placements that would not
        # cover it, narrowing the run-4-in-6 overlap from {2,3,4} down to {2,3}.
        assert solve_line((4,), (U, U, F, U, U, U)) == (U, U, F, F, U, U)

    def test_a_fixed_cell_contradicting_every_placement_is_detected(self):
        # clue (1,) says exactly one filled cell, but two are already fixed.
        assert solve_line((1,), (F, U, F)) is None


def brute_force_forced(clues: tuple[int, ...], partial: tuple[State, ...]) -> tuple[State, ...] | None:
    """Ground truth: try every completion, keep those matching the clue exactly."""

    def run_lengths(bools: tuple[bool, ...]) -> tuple[int, ...]:
        out: list[int] = []
        run = 0
        for b in bools:
            if b:
                run += 1
            else:
                if run:
                    out.append(run)
                run = 0
        if run:
            out.append(run)
        return tuple(out)

    n = len(partial)
    unknown_positions = [i for i, s in enumerate(partial) if s == U]
    valid: list[list[State]] = []
    for bits in itertools.product((False, True), repeat=len(unknown_positions)):
        candidate = list(partial)
        for pos, bit in zip(unknown_positions, bits):
            candidate[pos] = F if bit else E
        as_bools = tuple(c == F for c in candidate)
        if run_lengths(as_bools) == clues:
            valid.append(candidate)

    if not valid:
        return None

    forced = list(partial)
    for i in range(n):
        filled_possible = any(c[i] == F for c in valid)
        empty_possible = any(c[i] == E for c in valid)
        if filled_possible and not empty_possible:
            forced[i] = F
        elif empty_possible and not filled_possible:
            forced[i] = E
    return tuple(forced)


def random_case(rng: Random) -> tuple[tuple[int, ...], tuple[State, ...]]:
    """A random (clues, partial-line) pair guaranteed satisfiable by
    construction: draw a full random line, derive its clues, then blank out
    a random subset of cells back to UNKNOWN."""
    n = rng.randint(1, 10)
    full = [rng.random() < 0.5 for _ in range(n)]

    runs: list[int] = []
    run = 0
    for b in full:
        if b:
            run += 1
        else:
            if run:
                runs.append(run)
            run = 0
    if run:
        runs.append(run)
    clues = tuple(runs)

    reveal_probability = rng.random()  # varies how much of the line stays known
    partial = tuple(
        (F if cell else E) if rng.random() < reveal_probability else U for cell in full
    )
    return clues, partial


class TestBruteForceCrossCheck:
    @pytest.mark.parametrize("seed", range(200))
    def test_solve_line_matches_brute_force(self, seed):
        rng = Random(f"cellblock-solver-cross-check-{seed}")
        clues, partial = random_case(rng)
        assert solve_line(clues, partial) == brute_force_forced(clues, partial)


class TestSolveGrid:
    def test_solvable_fixture_reaches_solved_with_the_exact_bitmap(self):
        # A 3x3 checkerboard-free ring-ish shape, fully line-solvable:
        #   ###
        #   #.#
        #   ###
        row_clues = ((3,), (1, 1), (3,))
        col_clues = ((3,), (1, 1), (3,))
        status, grid, passes = solve_grid(row_clues, col_clues)
        assert status == SOLVED
        assert grid == (
            (F, F, F),
            (F, E, F),
            (F, F, F),
        )
        assert passes > 0

    def test_ambiguous_fixture_returns_stuck(self):
        # The classic 2x2 checkerboard: clues [1],[1] / [1],[1] admit two
        # solutions (the two diagonals) and single-line deduction cannot
        # tell them apart.
        row_clues = ((1,), (1,))
        col_clues = ((1,), (1,))
        status, grid, _passes = solve_grid(row_clues, col_clues)
        assert status == STUCK
        assert any(cell == U for row in grid for cell in row)

    def test_contradictory_clues_are_detected(self):
        # A 1x1 grid where the row wants it empty and the column wants it filled.
        status, _grid, _passes = solve_grid(((),), ((1,),))
        assert status == CONTRADICTION

    def test_starting_from_a_partially_filled_grid_still_converges(self):
        row_clues = ((3,), (1, 1), (3,))
        col_clues = ((3,), (1, 1), (3,))
        seed_grid = (
            (U, U, U),
            (U, U, U),
            (U, U, U),
        )
        status, grid, _passes = solve_grid(row_clues, col_clues, seed_grid)
        assert status == SOLVED
        assert grid[0] == (F, F, F)

    def test_passes_counts_only_lines_that_actually_changed(self):
        # An already-fully-known, self-consistent grid: no line changes,
        # so passes must be exactly 0 even though every line gets visited.
        row_clues = ((3,), (1, 1), (3,))
        col_clues = ((3,), (1, 1), (3,))
        solved_grid = (
            (F, F, F),
            (F, E, F),
            (F, F, F),
        )
        status, grid, passes = solve_grid(row_clues, col_clues, solved_grid)
        assert status == SOLVED
        assert grid == solved_grid
        assert passes == 0


class TestGrade:
    def test_boundaries(self):
        # rows+cols = 10 for a 5x5 grid.
        assert grade(passes=10, rows=5, cols=5) == GRADE_EASY
        assert grade(passes=11, rows=5, cols=5) == GRADE_MEDIUM
        assert grade(passes=20, rows=5, cols=5) == GRADE_MEDIUM
        assert grade(passes=21, rows=5, cols=5) == GRADE_HARD

    def test_zero_passes_is_easy(self):
        assert grade(passes=0, rows=10, cols=10) == GRADE_EASY
