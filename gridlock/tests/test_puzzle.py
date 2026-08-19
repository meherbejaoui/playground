"""Tests for numbering, entry extraction, serialization and solution stripping."""

from __future__ import annotations

import json

import pytest

from gridlock.patterns import extract_slots, load_patterns
from gridlock.puzzle import (
    ACROSS,
    DOWN,
    Entry,
    Puzzle,
    PuzzleError,
    compute_numbers,
    decode_answer,
    encode_answer,
    from_json,
    grid_entries,
    strip_solution,
    to_dict,
    to_json,
    with_clues,
)


def reference_numbers(grid: list[str]) -> list[list[int]]:
    """An independent numbering implementation, written differently on purpose.

    It collects the start cell of every maximal white run of length >= 2 in
    both directions, then numbers those cells in reading order. The
    production code decides cell-by-cell instead.
    """
    size = len(grid)
    starts: set[tuple[int, int]] = set()

    for row in range(size):
        run: list[tuple[int, int]] = []
        for col in range(size + 1):
            white = col < size and grid[row][col] != "#"
            if white:
                run.append((row, col))
            else:
                if len(run) >= 2:
                    starts.add(run[0])
                run = []

    for col in range(size):
        run = []
        for row in range(size + 1):
            white = row < size and grid[row][col] != "#"
            if white:
                run.append((row, col))
            else:
                if len(run) >= 2:
                    starts.add(run[0])
                run = []

    numbers = [[-1 if grid[r][c] == "#" else 0 for c in range(size)] for r in range(size)]
    counter = 1
    for row in range(size):
        for col in range(size):
            if (row, col) in starts:
                numbers[row][col] = counter
                counter += 1
    return numbers


GRIDS = [
    ["SCALE", "HOARD", "ADOBE", "REVEL", "PLANT"],
    ["#CAT#", "ROUTE", "ADOBE", "BLEND", "#EYE#"],
    ["ABCD#", "EFGHI", "JKLMN", "OPQRS", "#TUVW"],
    ["##ABC", "#DEFG", "HIJKL", "MNOP#", "QRS##"],
]


class TestNumbering:
    @pytest.mark.parametrize("grid", GRIDS)
    def test_matches_independent_reference(self, grid):
        assert [list(row) for row in compute_numbers(grid)] == reference_numbers(grid)

    def test_matches_reference_for_every_bundled_pattern(self):
        for pattern in load_patterns(5):
            grid = [
                "".join("#" if pattern.is_block(r, c) else "A" for c in range(5))
                for r in range(5)
            ]
            assert [list(row) for row in compute_numbers(grid)] == reference_numbers(grid)

    def test_blocks_are_minus_one_and_plain_cells_are_zero(self):
        numbers = compute_numbers(["#CAT#", "ROUTE", "ADOBE", "BLEND", "#EYE#"])
        assert numbers[0][0] == -1
        assert numbers[0][4] == -1
        assert numbers[2][2] == 0

    def test_non_square_grid_is_rejected(self):
        with pytest.raises(PuzzleError, match="square"):
            compute_numbers(["ABC", "DE"])


class TestGridEntries:
    def test_entries_of_a_blocked_grid(self):
        entries = grid_entries(["#CAT#", "ROUTE", "ADOBE", "BLEND", "#EYE#"])
        assert entries == [
            (1, ACROSS, 0, 1, 3, "CAT"),
            (1, DOWN, 0, 1, 5, "CODLE"),
            (2, DOWN, 0, 2, 5, "AUOEY"),
            (3, DOWN, 0, 3, 5, "TTBNE"),
            (4, ACROSS, 1, 0, 5, "ROUTE"),
            (4, DOWN, 1, 0, 3, "RAB"),
            (5, DOWN, 1, 4, 3, "EED"),
            (6, ACROSS, 2, 0, 5, "ADOBE"),
            (7, ACROSS, 3, 0, 5, "BLEND"),
            (8, ACROSS, 4, 1, 3, "EYE"),
        ]

    def test_entry_words_match_the_grid_for_every_pattern(self):
        for pattern in load_patterns(5):
            grid = [
                "".join(
                    "#" if pattern.is_block(r, c) else chr(ord("A") + (r * 5 + c) % 26)
                    for c in range(5)
                )
                for r in range(5)
            ]
            slots = extract_slots(pattern)
            entries = grid_entries(grid)
            assert len(entries) == len(slots)
            for _number, direction, row, col, length, word in entries:
                cells = (
                    [(row, col + i) for i in range(length)]
                    if direction == ACROSS
                    else [(row + i, col) for i in range(length)]
                )
                assert word == "".join(grid[r][c] for r, c in cells)


def sample_puzzle() -> Puzzle:
    grid = ("#CAT#", "ROUTE", "ADOBE", "BLEND", "#EYE#")
    numbers = compute_numbers(grid)
    entries = tuple(
        Entry(
            number=number,
            direction=direction,
            row=row,
            col=col,
            length=length,
            answer=encode_answer(word),
            clue=f"clue for {word}",
        )
        for number, direction, row, col, length, word in grid_entries(grid)
    )
    return Puzzle(
        id="test-5",
        size=5,
        seed="test",
        pattern="corners-4",
        generated_at="2026-08-19T00:00:00Z",
        grid=grid,
        numbers=numbers,
        entries=entries,
    )


class TestSerialization:
    def test_answers_round_trip_through_base64(self):
        for word in ("CAT", "ROUTE", "A", "ZZZZZ"):
            assert decode_answer(encode_answer(word)) == word

    def test_json_round_trip_is_lossless(self):
        puzzle = sample_puzzle()
        assert from_json(to_json(puzzle)) == puzzle

    def test_json_is_stable_across_serializations(self):
        puzzle = sample_puzzle()
        assert to_json(puzzle) == to_json(from_json(to_json(puzzle)))

    def test_payload_carries_every_documented_field(self):
        payload = json.loads(to_json(sample_puzzle()))
        assert set(payload) == {
            "format",
            "id",
            "size",
            "seed",
            "pattern",
            "generatedAt",
            "grid",
            "numbers",
            "entries",
        }
        assert payload["format"] == 1
        assert set(payload["entries"][0]) == {
            "number",
            "direction",
            "row",
            "col",
            "length",
            "answer",
            "clue",
        }

    def test_malformed_payloads_raise(self):
        with pytest.raises(PuzzleError):
            from_json("{not json")
        with pytest.raises(PuzzleError):
            from_json("[]")
        with pytest.raises(PuzzleError):
            from_json('{"id": "x"}')


class TestStripSolution:
    def test_grid_keeps_blocks_but_loses_every_letter(self):
        payload = to_dict(sample_puzzle())
        stripped = strip_solution(payload)
        assert stripped["grid"] == ["#...#", ".....", ".....", ".....", "#...#"]
        for row in stripped["grid"]:
            assert not any(char.isalpha() for char in row)

    def test_answers_survive_as_base64_and_the_original_is_untouched(self):
        payload = to_dict(sample_puzzle())
        stripped = strip_solution(payload)
        assert stripped["entries"] == payload["entries"]
        assert decode_answer(stripped["entries"][0]["answer"]) == "CAT"
        assert payload["grid"][0] == "#CAT#"

    def test_stripped_payload_still_parses_as_a_puzzle(self):
        stripped = strip_solution(to_dict(sample_puzzle()))
        puzzle = from_json(json.dumps(stripped))
        assert puzzle.grid[0] == "#...#"


class TestWithClues:
    def test_replaces_clues_by_number_and_direction(self):
        puzzle = sample_puzzle()
        updated = with_clues(puzzle, {(1, ACROSS): "Feline"})
        across_one = next(
            e for e in updated.entries if e.number == 1 and e.direction == ACROSS
        )
        assert across_one.clue == "Feline"
        assert updated.entries[1].clue == puzzle.entries[1].clue
