"""Tests for the `generate` CLI's error handling (PLAN.md 5)."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

REAL_DATA_DIR = Path(__file__).resolve().parents[1] / "data"


def run_cli(args, env=None):
    return subprocess.run(
        [sys.executable, "-m", "gridlock", *args],
        capture_output=True,
        text=True,
        env=env,
    )


class TestGenerateCommandErrorHandling:
    def test_malformed_pattern_file_produces_a_clean_error_not_a_traceback(self, tmp_path):
        # Regression test: load_patterns() can raise a raw KeyError (e.g. a
        # pattern entry missing "name") or a PatternError (e.g. a symmetry
        # violation) for a malformed patterns/<size>.json. The CLI must turn
        # that into a clean "error: ..." message and exit code, not an
        # uncaught traceback.
        fake_data = tmp_path / "fakedata"
        (fake_data / "patterns").mkdir(parents=True)
        shutil.copy(REAL_DATA_DIR / "words.tsv", fake_data / "words.tsv")
        (fake_data / "patterns" / "5.json").write_text(
            json.dumps({"size": 5, "patterns": [{"blocks": [[0, 0]]}]}),  # missing "name"
            encoding="utf-8",
        )

        env = {**os.environ, "GRIDLOCK_DATA_DIR": str(fake_data)}
        result = run_cli(
            ["generate", "--seed", "x", "--out", str(tmp_path / "out"), "--quiet"], env=env
        )

        assert result.returncode == 2
        assert "Traceback" not in result.stderr
        assert "error:" in result.stderr

    def test_missing_pattern_directory_produces_a_clean_error_not_a_traceback(self, tmp_path):
        fake_data = tmp_path / "emptydata"
        fake_data.mkdir()
        shutil.copy(REAL_DATA_DIR / "words.tsv", fake_data / "words.tsv")
        # No patterns/ subdirectory at all -> load_patterns raises
        # FileNotFoundError, previously also uncaught by the CLI.

        env = {**os.environ, "GRIDLOCK_DATA_DIR": str(fake_data)}
        result = run_cli(
            ["generate", "--seed", "x", "--out", str(tmp_path / "out"), "--quiet"], env=env
        )

        assert result.returncode == 2
        assert "Traceback" not in result.stderr
        assert "error:" in result.stderr
