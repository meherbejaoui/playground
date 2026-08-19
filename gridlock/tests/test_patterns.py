"""Tests for pattern loading, validation, slot extraction and crossings."""

from __future__ import annotations

import pytest

from gridlock.patterns import (
    ACROSS,
    DOWN,
    Pattern,
    PatternError,
    Slot,
    crossings,
    extract_slots,
    load_patterns,
    validate_pattern,
)


def make(name: str, blocks, size: int = 5) -> Pattern:
    return Pattern(name=name, size=size, blocks=frozenset(blocks))


class TestBundledPatterns:
    def test_all_bundled_patterns_load_and_validate(self):
        patterns = load_patterns(5)
        assert len(patterns) == 6
        for pattern in patterns:
            validate_pattern(pattern)  # must not raise

    def test_bundled_names_are_unique(self):
        names = [p.name for p in load_patterns(5)]
        assert len(names) == len(set(names))

    def test_no_bundled_pattern_is_the_fully_open_grid(self):
        # PLAN.md 3.2 originally shipped the blockless grid. Measurement
        # showed it never fills from a curated wordlist (a 5x5 double word
        # square needs a far larger dictionary), so it was replaced rather
        # than left to burn the fallback chain's time budget on every run.
        assert all(p.blocks for p in load_patterns(5))

    def test_bundled_patterns_offer_a_variety_of_slot_length_mixes(self):
        signatures = {
            tuple(sorted(s.length for s in extract_slots(p))) for p in load_patterns(5)
        }
        assert len(signatures) >= 4

    def test_missing_size_raises_file_not_found(self):
        with pytest.raises(FileNotFoundError):
            load_patterns(9)


class TestValidation:
    def test_asymmetric_pattern_is_rejected(self):
        pattern = make("asymmetric", [(0, 0)])
        with pytest.raises(PatternError, match="rule 1"):
            validate_pattern(pattern)

    def test_short_slot_is_rejected(self):
        # Blocking the middle of the top and bottom rows leaves length-2 runs.
        pattern = make("short-slot", [(0, 2), (4, 2)])
        with pytest.raises(PatternError, match="rule 2"):
            validate_pattern(pattern)

    def test_length_one_slot_is_rejected(self):
        pattern = make("pinched", [(1, 1), (3, 3)])
        with pytest.raises(PatternError, match="rule 2"):
            validate_pattern(pattern)

    def test_disconnected_white_region_is_rejected(self):
        # A fully blocked centre column on a 7x7 keeps symmetry, the block
        # budget and the minimum slot length, but splits the grid in two.
        pattern = make("split", [(r, 3) for r in range(7)], size=7)
        with pytest.raises(PatternError, match="rule 3"):
            validate_pattern(pattern)

    def test_block_budget_is_enforced(self):
        blocks = [(0, 0), (0, 1), (0, 2), (0, 3), (4, 1), (4, 2), (4, 3), (4, 4), (2, 2)]
        # Symmetric set of 10 blocks (each pairs with its 180-degree mirror).
        pattern = make("too-many", blocks + [(0, 4), (4, 0)])
        with pytest.raises(PatternError, match="rule 4"):
            validate_pattern(pattern)

    def test_out_of_range_block_is_rejected(self):
        pattern = make("oob", [(0, 5), (4, -1)])
        with pytest.raises(PatternError, match="outside"):
            validate_pattern(pattern)


class TestSlots:
    def test_extract_slots_matches_hand_computed_layout(self):
        pattern = make("corners-4", [(0, 0), (0, 4), (4, 0), (4, 4)])
        expected = [
            Slot(0, 1, ACROSS, 3, ((0, 1), (0, 2), (0, 3))),
            Slot(1, 0, ACROSS, 5, ((1, 0), (1, 1), (1, 2), (1, 3), (1, 4))),
            Slot(2, 0, ACROSS, 5, ((2, 0), (2, 1), (2, 2), (2, 3), (2, 4))),
            Slot(3, 0, ACROSS, 5, ((3, 0), (3, 1), (3, 2), (3, 3), (3, 4))),
            Slot(4, 1, ACROSS, 3, ((4, 1), (4, 2), (4, 3))),
            Slot(1, 0, DOWN, 3, ((1, 0), (2, 0), (3, 0))),
            Slot(0, 1, DOWN, 5, ((0, 1), (1, 1), (2, 1), (3, 1), (4, 1))),
            Slot(0, 2, DOWN, 5, ((0, 2), (1, 2), (2, 2), (3, 2), (4, 2))),
            Slot(0, 3, DOWN, 5, ((0, 3), (1, 3), (2, 3), (3, 3), (4, 3))),
            Slot(1, 4, DOWN, 3, ((1, 4), (2, 4), (3, 4))),
        ]
        assert extract_slots(pattern) == expected

    def test_every_white_cell_belongs_to_exactly_one_slot_per_direction(self):
        for pattern in load_patterns(5):
            slots = extract_slots(pattern)
            for direction in (ACROSS, DOWN):
                covered = [
                    cell for slot in slots if slot.direction == direction for cell in slot.cells
                ]
                assert sorted(covered) == sorted(pattern.white_cells())
                assert len(covered) == len(set(covered))


class TestCrossings:
    def test_crossings_are_symmetric(self):
        for pattern in load_patterns(5):
            slots = extract_slots(pattern)
            cross = crossings(slots)
            for index, entries in enumerate(cross):
                for own_pos, other_index, other_pos in entries:
                    assert (other_pos, index, own_pos) in cross[other_index]

    def test_crossings_only_link_opposite_directions_and_share_a_cell(self):
        pattern = make("pinwheel-4", [(0, 4), (1, 4), (3, 0), (4, 0)])
        slots = extract_slots(pattern)
        for index, entries in enumerate(crossings(slots)):
            for own_pos, other_index, other_pos in entries:
                assert slots[index].direction != slots[other_index].direction
                assert slots[index].cells[own_pos] == slots[other_index].cells[other_pos]

    def test_open_grid_every_slot_crosses_all_five_of_the_other_direction(self):
        pattern = make("open", [])
        cross = crossings(extract_slots(pattern))
        assert [len(entries) for entries in cross] == [5] * 10
