"""Tests for terminal rendering (grid preview + stuck-solve diagnostics)."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from cellblock.model import derive_clues, from_json, parse_bitmap
from cellblock.render import render_bitmap, render_puzzle, render_stuck

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def sample_puzzle():
    return from_json((FIXTURES / "sample-5x5.json").read_text(encoding="utf-8"))


class TestRenderPuzzle:
    def test_solved_grid_shows_filled_and_empty_glyphs(self, sample_puzzle):
        output = render_puzzle(sample_puzzle)
        assert "#" in output
        assert "·" in output

    def test_header_names_the_puzzle_and_grade(self, sample_puzzle):
        output = render_puzzle(sample_puzzle)
        assert "sample-5x5" in output
        assert "easy" in output
        assert "5x5" in output

    def test_row_and_column_clues_are_all_present(self, sample_puzzle):
        output = render_puzzle(sample_puzzle)
        # Every row clue value appears somewhere in the rendered block.
        for run in sample_puzzle.row_clues:
            for n in run:
                assert str(n) in output

    def test_unsolved_variant_hides_the_solution(self, sample_puzzle):
        output = render_puzzle(sample_puzzle, solved=False)
        assert "#" not in output
        assert "?" in output

    def test_snapshot_matches_the_committed_fixture(self, sample_puzzle):
        output = render_puzzle(sample_puzzle)
        expected = (
            "sample-5x5  (5x5, easy)\n\n"
            "           1    \n"
            "         1 1 1  \n"
            "       3 1 1 1 3\n"
            "      ----------\n"
            "    3 | · # # # ·\n"
            "  1 1 | # · · · #\n"
            "1 1 1 | # · # · #\n"
            "  1 1 | # · · · #\n"
            "    3 | · # # # ·"
        )
        assert output == expected


class TestRenderBitmap:
    def test_matches_render_puzzle_for_an_equivalent_grid(self, sample_puzzle):
        grid = sample_puzzle.bitmap()
        row_clues, col_clues = derive_clues(grid)
        direct = render_bitmap(grid, row_clues, col_clues)
        via_puzzle = render_puzzle(sample_puzzle).split("\n\n", 1)[1]
        assert direct == via_puzzle


class TestRenderStuck:
    def test_unknown_cells_render_as_question_marks(self):
        grid = [[None, True], [False, None]]
        output = render_stuck(grid, ((1,), (1,)), ((1,), (1,)))
        assert "?" in output
        assert "#" in output
        assert "·" in output

    def test_fully_unknown_grid_is_all_question_marks(self):
        grid = [[None, None], [None, None]]
        output = render_stuck(grid, ((), ()), ((), ()))
        data_lines = output.splitlines()[-2:]
        assert "#" not in "\n".join(data_lines)
        assert "?" in "\n".join(data_lines)

    def test_does_not_import_the_solver_module(self):
        # render.py must stay usable before solver.py exists (M1 precedes
        # M2); a static check that it never imports cellblock.solver.
        import cellblock.render as render_module

        source = Path(render_module.__file__).read_text(encoding="utf-8")
        assert "import" not in "\n".join(
            line for line in source.splitlines() if "solver" in line
        )


class TestShowCommand:
    def test_prints_the_same_rendering_as_render_puzzle(self, sample_puzzle):
        result = subprocess.run(
            [sys.executable, "-m", "cellblock", "show", str(FIXTURES / "sample-5x5.json")],
            capture_output=True,
            text=True,
            check=True,
        )
        assert result.stdout.strip() == render_puzzle(sample_puzzle).strip()

    def test_missing_file_exits_nonzero(self):
        result = subprocess.run(
            [sys.executable, "-m", "cellblock", "show", str(FIXTURES / "nope.json")],
            capture_output=True,
            text=True,
        )
        assert result.returncode != 0
        assert "error" in result.stderr.lower()
