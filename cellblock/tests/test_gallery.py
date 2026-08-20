"""Tests for the gallery pipeline: parsing, fairness, import."""

from __future__ import annotations

from pathlib import Path

import pytest

from cellblock.gallery import (
    GalleryError,
    check_fairness,
    import_gallery,
    load_gallery_files,
    parse_gallery_file,
    slug_for,
    state_grid_to_bools,
    to_puzzle,
    validate_gallery,
)
from cellblock.model import from_json


def write(directory: Path, name: str, content: str) -> None:
    (directory / name).write_text(content, encoding="utf-8")


FAIR_5X5 = """; title: Plus Sign
..#..
..#..
#####
..#..
..#..
"""

# Two isolated cells on a diagonal within an otherwise empty 5x5: the
# classic unresolvable checkerboard swap, embedded so it also exercises the
# min-size boundary honestly (5x5, not the toy 2x2).
UNFAIR_5X5 = """; title: Ambiguous
.....
.#...
..#..
.....
.....
"""


class TestParseGalleryFile:
    def test_parses_title_and_bitmap(self):
        entry = parse_gallery_file(FAIR_5X5, "plus")
        assert entry.title == "Plus Sign"
        assert entry.slug == "plus"
        assert len(entry.bitmap) == 5
        assert entry.bitmap[2] == (True, True, True, True, True)

    def test_extra_metadata_is_preserved(self):
        text = "; title: X\n; author: someone\n#####\n#####\n#####\n#####\n#####\n"
        entry = parse_gallery_file(text, "x")
        assert entry.metadata["author"] == "someone"

    def test_missing_title_raises(self):
        text = "; author: nobody\n#####\n#####\n#####\n#####\n#####\n"
        with pytest.raises(GalleryError, match="title"):
            parse_gallery_file(text, "notitle")

    def test_ragged_rows_raise(self):
        text = "; title: Bad\n#####\n####\n#####\n#####\n#####\n"
        with pytest.raises(GalleryError):
            parse_gallery_file(text, "ragged")

    def test_invalid_characters_raise(self):
        text = "; title: Bad\n#####\n##x##\n#####\n#####\n#####\n"
        with pytest.raises(GalleryError):
            parse_gallery_file(text, "badchar")

    def test_too_small_size_raises(self):
        text = "; title: Tiny\n##\n##\n"
        with pytest.raises(GalleryError, match="outside the allowed range"):
            parse_gallery_file(text, "tiny")

    def test_too_large_size_raises(self):
        row = "#" * 16
        text = "; title: Huge\n" + "\n".join([row] * 16) + "\n"
        with pytest.raises(GalleryError, match="outside the allowed range"):
            parse_gallery_file(text, "huge")

    def test_blank_lines_between_metadata_and_bitmap_are_ignored(self):
        text = "; title: Spaced\n\n#####\n#####\n#####\n#####\n#####\n"
        entry = parse_gallery_file(text, "spaced")
        assert len(entry.bitmap) == 5


class TestFairness:
    def test_fair_image_is_certified(self):
        entry = parse_gallery_file(FAIR_5X5, "plus")
        is_fair, status, _grid = check_fairness(entry)
        assert is_fair
        assert status == "solved"

    def test_unfair_image_is_rejected_with_a_stuck_diagnostic(self):
        entry = parse_gallery_file(UNFAIR_5X5, "ambiguous")
        is_fair, status, grid = check_fairness(entry)
        assert not is_fair
        assert status == "stuck"
        bools = state_grid_to_bools(grid)
        assert any(cell is None for row in bools for cell in row)

    def test_to_puzzle_refuses_an_unfair_image(self):
        entry = parse_gallery_file(UNFAIR_5X5, "ambiguous")
        with pytest.raises(GalleryError, match="not line-solvable"):
            to_puzzle(entry, generated_at="x")

    def test_to_puzzle_on_a_fair_image_round_trips_the_bitmap(self):
        entry = parse_gallery_file(FAIR_5X5, "plus")
        puzzle = to_puzzle(entry, generated_at="2026-01-01T00:00:00Z")
        assert puzzle.kind == "gallery"
        assert puzzle.title == "Plus Sign"
        assert puzzle.slug == "plus"
        assert puzzle.seed is None
        assert puzzle.bitmap() == entry.bitmap


class TestSlugFor:
    def test_uses_the_filename_stem_lowercased(self, tmp_path):
        assert slug_for(tmp_path / "Sailboat.txt") == "sailboat"


class TestValidateGallery:
    def test_mixed_directory_reports_both(self, tmp_path):
        write(tmp_path, "plus.txt", FAIR_5X5)
        write(tmp_path, "ambiguous.txt", UNFAIR_5X5)
        results = {r.slug: r for r in validate_gallery(tmp_path)}
        assert results["plus"].ok
        assert not results["ambiguous"].ok
        assert results["ambiguous"].stuck_grid is not None

    def test_empty_directory_yields_no_results(self, tmp_path):
        assert validate_gallery(tmp_path) == []

    def test_malformed_file_is_reported_without_crashing(self, tmp_path):
        write(tmp_path, "broken.txt", "; author: no title here\n##\n##\n")
        results = validate_gallery(tmp_path)
        assert len(results) == 1
        assert not results[0].ok
        assert "title" in results[0].message


class TestImportGallery:
    def test_imports_every_fair_file(self, tmp_path):
        gallery_dir = tmp_path / "gallery"
        gallery_dir.mkdir()
        write(gallery_dir, "plus.txt", FAIR_5X5)

        out_dir = tmp_path / "puzzles"
        puzzles = import_gallery(gallery_dir, out_dir, generated_at="x")

        assert len(puzzles) == 1
        assert (out_dir / "gallery-plus.json").is_file()
        written = from_json((out_dir / "gallery-plus.json").read_text(encoding="utf-8"))
        assert written.title == "Plus Sign"

    def test_refuses_to_write_anything_if_any_file_is_unfair(self, tmp_path):
        gallery_dir = tmp_path / "gallery"
        gallery_dir.mkdir()
        write(gallery_dir, "plus.txt", FAIR_5X5)
        write(gallery_dir, "ambiguous.txt", UNFAIR_5X5)

        out_dir = tmp_path / "puzzles"
        with pytest.raises(GalleryError, match="ambiguous"):
            import_gallery(gallery_dir, out_dir, generated_at="x")
        assert not out_dir.exists() or list(out_dir.iterdir()) == []


class TestShippedGallery:
    """Keeps the curated starter set honest forever (TASKS M3.3)."""

    def test_has_at_least_ten_files(self):
        assert len(load_gallery_files()) >= 10

    def test_every_shipped_file_is_fair(self):
        results = validate_gallery()
        failures = [r for r in results if not r.ok]
        assert not failures, "\n".join(f"{r.slug}: {r.message}" for r in failures)

    def test_every_shipped_file_is_within_the_size_bounds(self):
        for path in load_gallery_files():
            entry = parse_gallery_file(path.read_text(encoding="utf-8"), slug_for(path))
            rows, cols = len(entry.bitmap), len(entry.bitmap[0])
            assert 5 <= rows <= 15
            assert 5 <= cols <= 15

    def test_every_shipped_file_has_a_title(self):
        for path in load_gallery_files():
            entry = parse_gallery_file(path.read_text(encoding="utf-8"), slug_for(path))
            assert entry.title
