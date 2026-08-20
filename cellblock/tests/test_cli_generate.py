"""Tests for the `generate` CLI wiring (PLAN.md 5, TASKS M4.1)."""

from __future__ import annotations

import json
import subprocess
import sys

from cellblock.generate import today_seed
from cellblock.model import from_json


def run_cli(args, cwd=None):
    return subprocess.run(
        [sys.executable, "-m", "cellblock", *args],
        capture_output=True,
        text=True,
        cwd=cwd,
    )


class TestGenerateCommand:
    def test_writes_a_schema_valid_file_and_prints_a_preview(self, tmp_path):
        result = run_cli(["generate", "--seed", "2026-08-19", "--out", str(tmp_path)])
        assert result.returncode == 0
        assert "Wrote" in result.stdout

        path = tmp_path / "2026-08-19-10x10.json"
        assert path.is_file()
        puzzle = from_json(path.read_text(encoding="utf-8"))
        assert puzzle.id == "2026-08-19-10x10"
        assert puzzle.rows == 10 and puzzle.cols == 10

        # Every entry's clue-derived answer matches the packed solution.
        from cellblock.model import derive_clues

        row_clues, col_clues = derive_clues(puzzle.bitmap())
        assert row_clues == puzzle.row_clues
        assert col_clues == puzzle.col_clues

    def test_quiet_suppresses_the_preview(self, tmp_path):
        result = run_cli(
            ["generate", "--seed", "quiet-check", "--out", str(tmp_path), "--quiet"]
        )
        assert result.returncode == 0
        assert "Wrote" in result.stdout
        assert "·" not in result.stdout  # no grid glyphs printed

    def test_default_seed_is_todays_utc_date(self, tmp_path):
        result = run_cli(["generate", "--out", str(tmp_path), "--quiet"])
        assert result.returncode == 0
        expected = tmp_path / f"{today_seed()}-10x10.json"
        assert expected.is_file()

    def test_refuses_to_overwrite_without_force(self, tmp_path):
        run_cli(["generate", "--seed", "dup", "--out", str(tmp_path), "--quiet"])
        second = run_cli(["generate", "--seed", "dup", "--out", str(tmp_path), "--quiet"])
        assert second.returncode == 1
        assert "already exists" in second.stderr

    def test_force_overwrites(self, tmp_path):
        run_cli(["generate", "--seed", "dup2", "--out", str(tmp_path), "--quiet"])
        result = run_cli(
            ["generate", "--seed", "dup2", "--out", str(tmp_path), "--quiet", "--force"]
        )
        assert result.returncode == 0

    def test_unsupported_size_is_rejected_by_argparse(self, tmp_path):
        result = run_cli(["generate", "--size", "12", "--out", str(tmp_path)])
        assert result.returncode == 2
        assert "invalid choice" in result.stderr

    def test_size_5_produces_a_5x5_puzzle(self, tmp_path):
        result = run_cli(
            ["generate", "--seed", "small", "--size", "5", "--out", str(tmp_path), "--quiet"]
        )
        assert result.returncode == 0
        puzzle = from_json((tmp_path / "small-5x5.json").read_text(encoding="utf-8"))
        assert (puzzle.rows, puzzle.cols) == (5, 5)
