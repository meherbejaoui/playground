"""Tests for the generate CLI orchestration (PLAN.md 4.4-4.5, 5)."""

from __future__ import annotations

import json

import pytest

from gridlock.generate import (
    GenerationError,
    build_puzzle,
    generate_and_write,
    puzzle_id,
    today_seed,
)
from gridlock.puzzle import decode_answer, to_json
from gridlock.wordlist import load_wordlist


@pytest.fixture(scope="module")
def words():
    return load_wordlist()


class TestBuildPuzzle:
    def test_schema_is_valid_and_self_consistent(self, words):
        puzzle = build_puzzle("schema-check", 5, words=words)
        payload = json.loads(to_json(puzzle))
        assert payload["format"] == 1
        assert payload["id"] == "schema-check-5"
        assert payload["size"] == 5
        assert len(payload["grid"]) == 5
        assert all(len(row) == 5 for row in payload["grid"])

        for entry in puzzle.entries:
            cells = entry.cells()
            spelled = "".join(puzzle.grid[r][c] for r, c in cells)
            assert spelled == decode_answer(entry.answer)
            assert entry.clue

    def test_default_seed_is_todays_utc_date(self):
        assert build_puzzle(today_seed(), 5).seed == today_seed()

    def test_unsupported_size_raises_before_touching_the_filler(self, words):
        with pytest.raises(ValueError, match="not supported"):
            build_puzzle("x", 7, words=words)

    def test_determinism_same_seed_twice(self, words):
        first = build_puzzle("repeat", 5, words=words, generated_at="stamp")
        second = build_puzzle("repeat", 5, words=words, generated_at="stamp")
        assert first == second

    def test_different_seeds_differ(self, words):
        grids = {build_puzzle(f"seed-{i}", 5, words=words).grid for i in range(3)}
        assert len(grids) == 3

    def test_unfillable_wordlist_raises_generation_error(self):
        from gridlock.wordlist import Word

        tiny = [Word("SKY", 50, ("x",)), Word("GYM", 50, ("x",))]
        with pytest.raises(GenerationError, match="no-fit"):
            build_puzzle("no-fit", 5, words=tiny)


class TestGenerateAndWrite:
    def test_writes_a_valid_file(self, tmp_path, words):
        puzzle, path = generate_and_write("write-me", 5, out_dir=tmp_path, words=words)
        assert path == tmp_path / "write-me-5.json"
        assert path.is_file()
        payload = json.loads(path.read_text(encoding="utf-8"))
        assert payload["id"] == puzzle.id

    def test_default_seed_resolves_to_today(self, tmp_path, words):
        puzzle, path = generate_and_write(None, 5, out_dir=tmp_path, words=words)
        assert puzzle.seed == today_seed()
        assert path.name == f"{puzzle_id(today_seed(), 5)}.json"

    def test_refuses_to_overwrite_without_force(self, tmp_path, words):
        generate_and_write("dup", 5, out_dir=tmp_path, words=words)
        with pytest.raises(FileExistsError):
            generate_and_write("dup", 5, out_dir=tmp_path, words=words)

    def test_force_overwrites(self, tmp_path, words):
        generate_and_write("dup2", 5, out_dir=tmp_path, words=words)
        puzzle, path = generate_and_write(
            "dup2", 5, out_dir=tmp_path, force=True, words=words
        )
        assert path.is_file()
        assert puzzle.seed == "dup2"

    def test_two_runs_same_seed_are_identical_minus_timestamp(self, tmp_path, words):
        _puzzle, path_a = generate_and_write(
            "stable", 5, out_dir=tmp_path / "a", words=words
        )
        _puzzle, path_b = generate_and_write(
            "stable", 5, out_dir=tmp_path / "b", words=words
        )
        payload_a = json.loads(path_a.read_text(encoding="utf-8"))
        payload_b = json.loads(path_b.read_text(encoding="utf-8"))
        payload_a.pop("generatedAt")
        payload_b.pop("generatedAt")
        assert payload_a == payload_b

    def test_seed_with_path_separator_is_rejected(self, tmp_path, words):
        # Regression test: a seed becomes a single filesystem path
        # component via puzzle_id(); one containing "/" would otherwise
        # let generate_and_write escape out_dir (e.g.
        # --seed "../../../etc/evil" writing outside puzzles/).
        with pytest.raises(GenerationError, match="path separator"):
            generate_and_write("../escape", 5, out_dir=tmp_path, words=words)
        assert not (tmp_path.parent / "escape-5.json").exists()
        assert list(tmp_path.glob("**/*.json")) == []

    def test_seed_with_backslash_is_rejected(self, tmp_path, words):
        with pytest.raises(GenerationError, match="path separator"):
            generate_and_write("back\\slash", 5, out_dir=tmp_path, words=words)

    def test_empty_seed_is_rejected(self, tmp_path, words):
        with pytest.raises(GenerationError, match="non-empty"):
            generate_and_write("", 5, out_dir=tmp_path, words=words)
