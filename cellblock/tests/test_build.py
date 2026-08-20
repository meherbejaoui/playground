"""Tests for the static site builder (PLAN.md 5 `build` row)."""

from __future__ import annotations

import json
import re

import pytest

from cellblock.build import BuildError, build_site, load_puzzles
from cellblock.gallery import import_gallery
from cellblock.generate import generate_and_write


def make_dailies(tmp_path, seeds_sizes):
    puzzles_dir = tmp_path / "puzzles"
    for i, (seed, size) in enumerate(seeds_sizes):
        generate_and_write(
            seed, size, out_dir=puzzles_dir, generated_at=f"2026-01-{i + 1:02d}T00:00:00Z"
        )
    return puzzles_dir


GALLERY_A = """; title: Zebra
#####
#####
#####
#####
#####
"""

GALLERY_B = """; title: Apple
#####
#####
#####
#####
#####
"""


def add_gallery(puzzles_dir, tmp_path, entries):
    gallery_dir = tmp_path / "gallery_src"
    gallery_dir.mkdir(exist_ok=True)
    for name, content in entries.items():
        (gallery_dir / f"{name}.txt").write_text(content, encoding="utf-8")
    import_gallery(gallery_dir, puzzles_dir, generated_at="2026-01-01T00:00:00Z")


class TestLoadPuzzles:
    def test_splits_daily_and_gallery_and_orders_each(self, tmp_path):
        puzzles_dir = make_dailies(tmp_path, [("one", 5), ("two", 5), ("three", 5)])
        add_gallery(puzzles_dir, tmp_path, {"zebra": GALLERY_A, "apple": GALLERY_B})

        daily, gallery = load_puzzles(puzzles_dir)
        assert [p["id"] for p in daily] == ["three-5x5", "two-5x5", "one-5x5"]
        assert [p["title"] for p in gallery] == ["Apple", "Zebra"]

    def test_missing_directory_raises(self, tmp_path):
        with pytest.raises(BuildError, match="no puzzles directory"):
            load_puzzles(tmp_path / "nope")


class TestBuildSite:
    def test_builds_index_and_one_page_per_puzzle(self, tmp_path):
        puzzles_dir = make_dailies(tmp_path, [("alpha", 5), ("beta", 5)])
        add_gallery(puzzles_dir, tmp_path, {"zebra": GALLERY_A})
        out_dir = tmp_path / "site"

        daily, gallery = build_site(puzzles_dir, out_dir, title="Cellblock")

        assert len(daily) == 2
        assert len(gallery) == 1
        assert (out_dir / "index.html").is_file()
        assert (out_dir / ".cellblock-site").is_file()
        assert (out_dir / "p" / "beta-5x5.html").is_file()
        assert (out_dir / "p" / "gallery-zebra.html").is_file()

    def test_index_has_both_sections_correctly_ordered(self, tmp_path):
        puzzles_dir = make_dailies(tmp_path, [("alpha", 5), ("beta", 5)])
        add_gallery(puzzles_dir, tmp_path, {"zebra": GALLERY_A, "apple": GALLERY_B})
        out_dir = tmp_path / "site"
        build_site(puzzles_dir, out_dir)

        index_text = (out_dir / "index.html").read_text(encoding="utf-8")
        assert "Daily" in index_text and "Gallery" in index_text
        beta_pos = index_text.index("beta-5x5")
        alpha_pos = index_text.index("alpha-5x5")
        assert beta_pos < alpha_pos, "newer daily (beta) must be listed first"
        apple_pos = index_text.index("Apple")
        zebra_pos = index_text.index("Zebra")
        assert apple_pos < zebra_pos, "gallery entries must be alphabetical by title"
        assert "Today" in index_text

    def test_gallery_title_appears_on_the_index_but_not_the_page(self, tmp_path):
        puzzles_dir = tmp_path / "puzzles"
        puzzles_dir.mkdir()
        add_gallery(puzzles_dir, tmp_path, {"zebra": GALLERY_A})
        out_dir = tmp_path / "site"
        build_site(puzzles_dir, out_dir)

        index_text = (out_dir / "index.html").read_text(encoding="utf-8")
        assert "Zebra" in index_text

        page_text = (out_dir / "p" / "gallery-zebra.html").read_text(encoding="utf-8")
        assert "Gallery puzzle" in page_text
        # The title still has to be present *somewhere* for the player's own
        # completion logic to read from the embedded JSON, just not in the
        # human-visible <title> tag or any pre-rendered heading text.
        assert '"title": "Zebra"' in page_text

    def test_puzzle_pages_carry_no_bitmap_dumps(self, tmp_path):
        puzzles_dir = make_dailies(tmp_path, [("bitmapcheck", 5)])
        out_dir = tmp_path / "site"
        build_site(puzzles_dir, out_dir)
        page_text = (out_dir / "p" / "bitmapcheck-5x5.html").read_text(encoding="utf-8")

        match = re.search(r'"solution"\s*:\s*"([^"]*)"', page_text)
        assert match, "could not find the inlined solution field"
        # Only ever base64 characters, never the literal '#'/'.' bitmap form.
        assert re.fullmatch(r"[A-Za-z0-9+/=]*", match.group(1))

    def test_script_tag_boundaries_are_escaped(self, tmp_path):
        puzzles_dir = tmp_path / "puzzles"
        puzzles_dir.mkdir()
        add_gallery(puzzles_dir, tmp_path, {"zebra": GALLERY_A})
        puzzle_path = puzzles_dir / "gallery-zebra.json"
        payload = json.loads(puzzle_path.read_text(encoding="utf-8"))
        payload["title"] = "Ends with a </script> tag"
        puzzle_path.write_text(json.dumps(payload), encoding="utf-8")

        out_dir = tmp_path / "site"
        build_site(puzzles_dir, out_dir)
        page_text = (out_dir / "p" / "gallery-zebra.html").read_text(encoding="utf-8")
        assert "</script> tag" not in page_text
        assert "<\\/script> tag" in page_text


class TestWipeGuard:
    def test_refuses_a_nonempty_directory_without_the_marker(self, tmp_path):
        puzzles_dir = make_dailies(tmp_path, [("x", 5)])
        out_dir = tmp_path / "site"
        out_dir.mkdir()
        (out_dir / "unrelated.txt").write_text("hello", encoding="utf-8")

        with pytest.raises(BuildError, match="refusing to overwrite"):
            build_site(puzzles_dir, out_dir)
        assert (out_dir / "unrelated.txt").is_file()

    def test_rebuilds_a_directory_carrying_the_marker(self, tmp_path):
        puzzles_dir = make_dailies(tmp_path, [("x", 5)])
        out_dir = tmp_path / "site"
        build_site(puzzles_dir, out_dir)
        assert (out_dir / "p" / "x-5x5.html").is_file()

        generate_and_write("y", 5, out_dir=puzzles_dir, generated_at="2026-02-01T00:00:00Z")
        build_site(puzzles_dir, out_dir)
        assert (out_dir / "p" / "x-5x5.html").is_file()
        assert (out_dir / "p" / "y-5x5.html").is_file()

    def test_accepts_a_completely_empty_directory(self, tmp_path):
        puzzles_dir = make_dailies(tmp_path, [("x", 5)])
        out_dir = tmp_path / "site"
        out_dir.mkdir()
        build_site(puzzles_dir, out_dir)
        assert (out_dir / ".cellblock-site").is_file()


class TestIncrementalRebuild:
    def test_a_newly_added_puzzle_appears_after_rebuilding(self, tmp_path):
        puzzles_dir = make_dailies(tmp_path, [("first", 5), ("second", 5)])
        out_dir = tmp_path / "site"
        build_site(puzzles_dir, out_dir)
        assert not (out_dir / "p" / "third-5x5.html").exists()

        generate_and_write("third", 5, out_dir=puzzles_dir, generated_at="2026-03-01T00:00:00Z")
        build_site(puzzles_dir, out_dir)
        assert (out_dir / "p" / "third-5x5.html").is_file()
        index_text = (out_dir / "index.html").read_text(encoding="utf-8")
        assert "third-5x5" in index_text
