"""Tests for the static site builder (PLAN.md 5 `build` row)."""

from __future__ import annotations

import json
import re

import pytest

from gridlock.build import BuildError, build_site, load_puzzles
from gridlock.generate import generate_and_write, today_seed
from gridlock.puzzle import decode_answer
from gridlock.wordlist import load_wordlist


@pytest.fixture(scope="module")
def words():
    return load_wordlist()


def make_puzzles(tmp_path, seeds, words):
    puzzles_dir = tmp_path / "puzzles"
    for i, seed in enumerate(seeds):
        generate_and_write(
            seed, 5, out_dir=puzzles_dir, words=words, generated_at=f"2026-01-{i + 1:02d}T00:00:00Z"
        )
    return puzzles_dir


class TestLoadPuzzles:
    def test_orders_newest_first_by_generation_time(self, tmp_path, words):
        puzzles_dir = make_puzzles(tmp_path, ["one", "two", "three"], words)
        puzzles = load_puzzles(puzzles_dir)
        assert [p["id"] for p in puzzles] == ["three-5", "two-5", "one-5"]

    def test_missing_directory_raises(self, tmp_path):
        with pytest.raises(BuildError, match="no puzzles directory"):
            load_puzzles(tmp_path / "nope")


class TestBuildSite:
    def test_builds_index_and_one_page_per_puzzle(self, tmp_path, words):
        puzzles_dir = make_puzzles(tmp_path, ["alpha", "beta"], words)
        out_dir = tmp_path / "site"
        puzzles = build_site(puzzles_dir, out_dir, title="Gridlock")

        assert len(puzzles) == 2
        assert (out_dir / "index.html").is_file()
        assert (out_dir / ".gridlock-site").is_file()
        assert (out_dir / "p" / "beta-5.html").is_file()
        assert (out_dir / "p" / "alpha-5.html").is_file()

    def test_index_lists_both_newest_first(self, tmp_path, words):
        puzzles_dir = make_puzzles(tmp_path, ["alpha", "beta"], words)
        out_dir = tmp_path / "site"
        build_site(puzzles_dir, out_dir)

        index_text = (out_dir / "index.html").read_text(encoding="utf-8")
        beta_pos = index_text.index("beta-5")
        alpha_pos = index_text.index("alpha-5")
        assert beta_pos < alpha_pos, "the newer puzzle (beta) must be listed first"

    def test_today_label_tracks_real_seed_not_sort_position(self, tmp_path, words):
        # Regression test: the newest-by-generatedAt puzzle isn't
        # necessarily today's if `build` runs without a fresh `generate`
        # first. "Today" must attach to whichever puzzle's seed actually
        # matches today's UTC date, not to whatever sorts first.
        puzzles_dir = tmp_path / "puzzles"
        generate_and_write(
            today_seed(),
            5,
            out_dir=puzzles_dir,
            words=words,
            generated_at="2020-01-01T00:00:00Z",
        )
        generate_and_write(
            "not-today",
            5,
            out_dir=puzzles_dir,
            words=words,
            generated_at="2030-01-01T00:00:00Z",
        )
        out_dir = tmp_path / "site"
        build_site(puzzles_dir, out_dir)
        index_text = (out_dir / "index.html").read_text(encoding="utf-8")

        rows = re.findall(r"<li>.*?</li>", index_text, re.DOTALL)
        today_row = next(r for r in rows if f"{today_seed()}-5" in r)
        other_row = next(r for r in rows if "not-today-5" in r)

        assert "Today" in today_row
        assert "Today" not in other_row

    def test_puzzle_pages_carry_base64_but_never_plaintext_solutions(self, tmp_path, words):
        puzzles_dir = make_puzzles(tmp_path, ["secretcheck"], words)
        puzzles = load_puzzles(puzzles_dir)
        answers = [decode_answer(e["answer"]) for e in puzzles[0]["entries"]]

        out_dir = tmp_path / "site"
        build_site(puzzles_dir, out_dir)
        page_text = (out_dir / "p" / "secretcheck-5.html").read_text(encoding="utf-8")

        for answer in answers:
            assert answer not in page_text, f"plaintext answer {answer!r} leaked into the page"
        # But the base64 forms must be present so the player can decode them.
        for entry in puzzles[0]["entries"]:
            assert entry["answer"] in page_text

    def test_puzzle_page_grid_has_no_letters_only_blocks_and_dots(self, tmp_path, words):
        puzzles_dir = make_puzzles(tmp_path, ["gridcheck"], words)
        out_dir = tmp_path / "site"
        build_site(puzzles_dir, out_dir)
        page_text = (out_dir / "p" / "gridcheck-5.html").read_text(encoding="utf-8")

        match = re.search(r'"grid"\s*:\s*(\[[^\]]*\])', page_text)
        assert match, "could not find the inlined grid field"
        assert not re.search(r"[A-Z]", match.group(1))

    def test_script_tag_boundaries_are_escaped(self, tmp_path, words):
        # A clue containing a literal "</script>" must not be able to break
        # out of the puzzle-data <script> tag it's embedded in. Generate a
        # normal puzzle with the real wordlist, then tamper with one clue on
        # disk before building, so this test doesn't depend on a synthetic
        # wordlist being able to fill a grid.
        puzzles_dir = make_puzzles(tmp_path, ["scripttag"], words)
        puzzle_path = puzzles_dir / "scripttag-5.json"
        payload = json.loads(puzzle_path.read_text(encoding="utf-8"))
        payload["entries"][0]["clue"] = "Ends with a </script> tag"
        puzzle_path.write_text(json.dumps(payload), encoding="utf-8")

        out_dir = tmp_path / "site"
        build_site(puzzles_dir, out_dir)
        page_text = (out_dir / "p" / "scripttag-5.html").read_text(encoding="utf-8")

        assert "</script> tag" not in page_text
        assert "<\\/script> tag" in page_text


class TestWipeGuard:
    def test_refuses_a_nonempty_directory_without_the_marker(self, tmp_path, words):
        puzzles_dir = make_puzzles(tmp_path, ["x"], words)
        out_dir = tmp_path / "site"
        out_dir.mkdir()
        (out_dir / "unrelated.txt").write_text("hello", encoding="utf-8")

        with pytest.raises(BuildError, match="refusing to overwrite"):
            build_site(puzzles_dir, out_dir)
        assert (out_dir / "unrelated.txt").is_file(), "must not have touched the directory"

    def test_rebuilds_a_directory_carrying_the_marker(self, tmp_path, words):
        puzzles_dir = make_puzzles(tmp_path, ["x"], words)
        out_dir = tmp_path / "site"
        build_site(puzzles_dir, out_dir)
        assert (out_dir / "p" / "x-5.html").is_file()

        # Rebuild after adding a second puzzle; the marker must let this through.
        generate_and_write("y", 5, out_dir=puzzles_dir, words=words, generated_at="2026-02-01T00:00:00Z")
        build_site(puzzles_dir, out_dir)
        assert (out_dir / "p" / "x-5.html").is_file()
        assert (out_dir / "p" / "y-5.html").is_file()

    def test_accepts_a_completely_empty_directory(self, tmp_path, words):
        puzzles_dir = make_puzzles(tmp_path, ["x"], words)
        out_dir = tmp_path / "site"
        out_dir.mkdir()
        build_site(puzzles_dir, out_dir)  # must not raise
        assert (out_dir / ".gridlock-site").is_file()


class TestIncrementalRebuild:
    def test_a_newly_added_puzzle_appears_after_rebuilding(self, tmp_path, words):
        puzzles_dir = make_puzzles(tmp_path, ["first", "second"], words)
        out_dir = tmp_path / "site"
        build_site(puzzles_dir, out_dir)
        assert not (out_dir / "p" / "third-5.html").exists()

        generate_and_write(
            "third", 5, out_dir=puzzles_dir, words=words, generated_at="2026-03-01T00:00:00Z"
        )
        build_site(puzzles_dir, out_dir)
        assert (out_dir / "p" / "third-5.html").is_file()
        index_text = (out_dir / "index.html").read_text(encoding="utf-8")
        assert "third-5" in index_text
