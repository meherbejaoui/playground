"""Tests for bitmaps, clue derivation, bit-packing, and puzzle JSON."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from cellblock.model import (
    BitmapError,
    Difficulty,
    Puzzle,
    PuzzleError,
    derive_clues,
    format_bitmap,
    from_json,
    pack_solution,
    parse_bitmap,
    to_json,
    unpack_solution,
)

FIXTURES = Path(__file__).parent / "fixtures"


def grid_from(rows: list[str]):
    return parse_bitmap("\n".join(rows))


class TestParseFormat:
    def test_round_trips(self):
        text = "#.#\n.#.\n###"
        assert format_bitmap(parse_bitmap(text)) == text

    def test_hash_and_dot_map_to_true_false(self):
        grid = grid_from(["#.", ".#"])
        assert grid == ((True, False), (False, True))

    def test_ragged_rows_raise(self):
        with pytest.raises(BitmapError, match="ragged"):
            parse_bitmap("##\n#")

    def test_invalid_character_raises(self):
        with pytest.raises(BitmapError, match="not"):
            parse_bitmap("#x\n..")

    def test_empty_text_raises(self):
        with pytest.raises(BitmapError):
            parse_bitmap("")


class TestDeriveClues:
    def test_all_empty_line_has_no_clue(self):
        grid = grid_from(["...", "...", "..."])
        row_clues, col_clues = derive_clues(grid)
        assert row_clues == ((), (), ())
        assert col_clues == ((), (), ())

    def test_all_full_line_is_one_run(self):
        grid = grid_from(["###", "###", "###"])
        row_clues, col_clues = derive_clues(grid)
        assert row_clues == ((3,), (3,), (3,))
        assert col_clues == ((3,), (3,), (3,))

    def test_multiple_runs_per_line(self):
        grid = grid_from(
            [
                "#.#.#",
                "##..#",
                ".....",
                "#####",
                "#.###",
            ]
        )
        row_clues, col_clues = derive_clues(grid)
        assert row_clues == ((1, 1, 1), (2, 1), (), (5,), (1, 3))
        # Columns, read top-to-bottom: c0=#,#,.,#,# -> (2,2); c1=.,#,.,#,. -> (1,1);
        # c2=#,.,.,#,# -> (1,2); c3=.,.,.,#,# -> (2,); c4=#,#,.,#,# -> (2,2)
        assert col_clues == ((2, 2), (1, 1), (1, 2), (2,), (2, 2))

    def test_single_cell_grid(self):
        assert derive_clues(grid_from(["#"])) == (((1,),), ((1,),))
        assert derive_clues(grid_from(["."])) == (((),), ((),))


class TestPacking:
    @pytest.mark.parametrize("rows,cols", [(5, 5), (10, 10), (7, 13), (1, 1), (3, 16)])
    def test_round_trips_on_various_sizes(self, rows, cols):
        # A deterministic, non-trivial pattern so every bit position is exercised.
        grid = tuple(
            tuple((r * 7 + c * 3) % 5 == 0 for c in range(cols)) for r in range(rows)
        )
        encoded = pack_solution(grid)
        assert unpack_solution(encoded, rows, cols) == grid

    def test_all_empty_and_all_filled(self):
        empty = tuple(tuple(False for _ in range(6)) for _ in range(4))
        full = tuple(tuple(True for _ in range(6)) for _ in range(4))
        assert unpack_solution(pack_solution(empty), 4, 6) == empty
        assert unpack_solution(pack_solution(full), 4, 6) == full

    def test_bits_are_msb_first_within_a_byte(self):
        # A single row of 8 cells, only the first (leftmost) cell filled,
        # must pack to the single byte 0b10000000 = base64 "gA==".
        grid = ((True, False, False, False, False, False, False, False),)
        assert pack_solution(grid) == "gA=="

    def test_wrong_length_payload_raises(self):
        with pytest.raises(BitmapError):
            unpack_solution("AA==", 5, 5)

    def test_known_answer_vector_matches_the_shared_fixture(self):
        payload = json.loads((FIXTURES / "packing.json").read_text(encoding="utf-8"))
        grid = grid_from(payload["bitmap"])
        assert len(grid) == payload["rows"]
        assert len(grid[0]) == payload["cols"]
        assert pack_solution(grid) == payload["base64"]
        assert unpack_solution(payload["base64"], payload["rows"], payload["cols"]) == grid


def sample_puzzle() -> Puzzle:
    grid = grid_from(["#.#", ".#.", "###"])
    row_clues, col_clues = derive_clues(grid)
    return Puzzle(
        id="test-3x3",
        kind="daily",
        rows=3,
        cols=3,
        row_clues=row_clues,
        col_clues=col_clues,
        solution=pack_solution(grid),
        difficulty=Difficulty(passes=4, grade="easy"),
        generated_at="2026-08-19T00:00:00Z",
        seed="test",
    )


class TestPuzzleSerialization:
    def test_json_round_trip_is_lossless(self):
        puzzle = sample_puzzle()
        assert from_json(to_json(puzzle)) == puzzle

    def test_json_stable_across_serializations(self):
        puzzle = sample_puzzle()
        assert to_json(puzzle) == to_json(from_json(to_json(puzzle)))

    def test_payload_carries_every_documented_field(self):
        payload = json.loads(to_json(sample_puzzle()))
        assert set(payload) == {
            "format",
            "id",
            "kind",
            "title",
            "rows",
            "cols",
            "rowClues",
            "colClues",
            "solution",
            "difficulty",
            "seed",
            "generatedAt",
            "slug",
        }
        assert payload["format"] == 1
        assert payload["title"] is None
        assert payload["slug"] is None

    def test_gallery_puzzle_carries_title_and_slug(self):
        puzzle = Puzzle(
            id="gallery-cat",
            kind="gallery",
            rows=3,
            cols=3,
            row_clues=((1,), (1,), (1,)),
            col_clues=((1,), (1,), (1,)),
            solution=pack_solution(grid_from(["#..", ".#.", "..#"])),
            difficulty=Difficulty(passes=3, grade="easy"),
            generated_at="2026-08-19T00:00:00Z",
            title="Cat",
            slug="cat",
        )
        payload = json.loads(to_json(puzzle))
        assert payload["title"] == "Cat"
        assert payload["slug"] == "cat"
        assert payload["seed"] is None

    def test_bitmap_helper_decodes_the_solution(self):
        puzzle = sample_puzzle()
        assert puzzle.bitmap() == grid_from(["#.#", ".#.", "###"])

    def test_malformed_payloads_raise(self):
        with pytest.raises(PuzzleError):
            from_json("{not json")
        with pytest.raises(PuzzleError):
            from_json("[]")
        with pytest.raises(PuzzleError):
            from_json('{"id": "x"}')
