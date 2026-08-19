"""Tests for the candidate index and the backtracking fill engine."""

from __future__ import annotations

import itertools
import time
from random import Random

import pytest

from gridlock.fill import (
    CandidateIndex,
    fill_any_pattern,
    fill_pattern,
    fill_slots,
    grid_from_assignment,
)
from gridlock.patterns import Pattern, extract_slots, load_patterns
from gridlock.wordlist import Word, load_wordlist

TINY = [
    Word("CAT", 90, ("Pet",)),
    Word("CAR", 80, ("Ride",)),
    Word("CAB", 70, ("Taxi",)),
    Word("DOG", 60, ("Pooch",)),
    Word("DOT", 50, ("Point",)),
    Word("COT", 40, ("Small bed",)),
    Word("ROUTE", 30, ("Path",)),
    Word("ADOBE", 20, ("Brick",)),
]


@pytest.fixture(scope="module")
def tiny_index():
    return CandidateIndex(TINY)


def texts(index, ids):
    return sorted(index.text(word_id) for word_id in ids)


class TestCandidateIndex:
    def test_unconstrained_lookup_returns_every_word_of_that_length(self, tiny_index):
        assert texts(tiny_index, tiny_index.candidates_for(3)) == [
            "CAB",
            "CAR",
            "CAT",
            "COT",
            "DOG",
            "DOT",
        ]
        assert texts(tiny_index, tiny_index.candidates_for(5)) == ["ADOBE", "ROUTE"]

    def test_single_letter_constraint(self, tiny_index):
        assert texts(tiny_index, tiny_index.candidates_for(3, ((0, "C"),))) == [
            "CAB",
            "CAR",
            "CAT",
            "COT",
        ]
        assert texts(tiny_index, tiny_index.candidates_for(3, ((2, "T"),))) == [
            "CAT",
            "COT",
            "DOT",
        ]

    def test_multiple_constraints_intersect(self, tiny_index):
        assert texts(tiny_index, tiny_index.candidates_for(3, ((0, "C"), (1, "A")))) == [
            "CAB",
            "CAR",
            "CAT",
        ]
        assert texts(
            tiny_index, tiny_index.candidates_for(3, ((0, "C"), (1, "A"), (2, "T")))
        ) == ["CAT"]

    def test_impossible_constraints_return_nothing(self, tiny_index):
        assert tiny_index.candidates_for(3, ((0, "Z"),)) == ()
        assert tiny_index.candidates_for(3, ((0, "C"), (1, "O"), (2, "G"))) == ()
        assert tiny_index.candidates_for(4) == ()

    def test_results_are_sorted_for_determinism(self, tiny_index):
        result = tiny_index.candidates_for(3, ((0, "C"),))
        assert list(result) == sorted(result)

    def test_count_matches_the_candidate_list(self, tiny_index):
        for fixed in ((), ((0, "C"),), ((1, "O"),), ((0, "Z"),)):
            assert tiny_index.count_candidates(3, fixed) == len(
                tiny_index.candidates_for(3, fixed)
            )

    def test_ordering_prefers_high_scores(self, tiny_index):
        ids = tiny_index.candidates_for(3)
        ordered = tiny_index.order_candidates(ids, Random("x"))
        scores = [tiny_index.word(word_id).score for word_id in ordered]
        assert scores == sorted(scores, reverse=True)
        assert sorted(ordered) == sorted(ids)


# A 3x3 open grid: three across slots and three down slots, all length 3.
TOY_PATTERN = Pattern(name="toy-3", size=3, blocks=frozenset())

TOY_WORDS = [
    Word("BAT", 90, ("Club",)),
    Word("ORE", 80, ("Rock",)),
    Word("WED", 70, ("Marry",)),
    Word("BOW", 60, ("Bend",)),
    Word("ARE", 50, ("Exist",)),
    Word("TED", 40, ("Spread hay",)),
] + [
    Word(text, 30, ("Consonant heavy",))
    for text in ("SKY", "GYM", "FLY", "DRY", "SHY", "TRY", "PRY", "SPY", "WHY")
]


def brute_force_squares(words: list[Word]) -> list[tuple[str, str, str]]:
    """Every 3x3 square of six distinct words, found the dumb way."""
    lookup = {word.text for word in words}
    found = []
    for rows in itertools.permutations([w.text for w in words], 3):
        columns = tuple("".join(row[i] for row in rows) for i in range(3))
        if all(column in lookup for column in columns):
            if len(set(rows) | set(columns)) == 6:
                found.append(rows)
    return found


class TestBacktrackingSearch:
    def test_toy_grid_has_exactly_one_square_and_its_transpose(self):
        # A 3x3 open grid is transpose-symmetric, so any solution's mirror is
        # also a solution; the fixture admits precisely that one pair.
        squares = brute_force_squares(TOY_WORDS)
        assert sorted(squares) == [("BAT", "ORE", "WED"), ("BOW", "ARE", "TED")]

    def test_fill_finds_one_of_the_valid_squares(self):
        index = CandidateIndex(TOY_WORDS)
        grid = fill_pattern(TOY_PATTERN, index, Random("toy"))
        assert grid is not None
        assert tuple(grid) in {("BAT", "ORE", "WED"), ("BOW", "ARE", "TED")}

    def test_fill_never_repeats_a_word(self):
        index = CandidateIndex(TOY_WORDS)
        slots = extract_slots(TOY_PATTERN)
        for seed in range(5):
            result = fill_slots(slots, index, Random(seed))
            assert result is not None
            used = list(result.assignment.values())
            assert len(used) == len(set(used)) == len(slots)

    def test_unfillable_wordlist_returns_none_quickly(self):
        words = [Word(t, 50, ("x",)) for t in ("SKY", "GYM", "FLY", "DRY", "SHY")]
        index = CandidateIndex(words)
        started = time.perf_counter()
        assert fill_pattern(TOY_PATTERN, index, Random("nope")) is None
        assert time.perf_counter() - started < 2.0

    def test_budget_is_respected(self):
        words = [Word(t, 50, ("x",)) for t in ("SKY", "GYM", "FLY", "DRY", "SHY")]
        index = CandidateIndex(words)
        assert fill_pattern(TOY_PATTERN, index, Random("nope"), max_backtracks=5) is None

    def test_grid_matches_the_assignment(self):
        index = CandidateIndex(TOY_WORDS)
        slots = extract_slots(TOY_PATTERN)
        result = fill_slots(slots, index, Random("grid"))
        assert result is not None
        grid = grid_from_assignment(TOY_PATTERN, slots, result.assignment, index)
        for slot_index, word_id in result.assignment.items():
            slot = slots[slot_index]
            spelled = "".join(grid[row][col] for row, col in slot.cells)
            assert spelled == index.text(word_id)


@pytest.fixture(scope="module")
def real_index():
    return CandidateIndex(load_wordlist())


@pytest.fixture(scope="module")
def real_patterns():
    return load_patterns(5)


class TestDeterminism:
    def test_same_seed_gives_the_same_fill(self, real_index, real_patterns):
        pattern = next(p for p in real_patterns if p.name == "corners-4")
        first = fill_pattern(pattern, real_index, Random("repeat-me"))
        second = fill_pattern(pattern, real_index, Random("repeat-me"))
        assert first is not None
        assert first == second

    def test_different_seeds_give_different_fills(self, real_index, real_patterns):
        pattern = next(p for p in real_patterns if p.name == "corners-4")
        grids = {
            fill_pattern(pattern, real_index, Random(f"seed-{i}")) for i in range(3)
        }
        assert len(grids) == 3

    def test_fill_respects_blocks_and_only_uses_listed_words(
        self, real_index, real_patterns
    ):
        vocabulary = {word.text for word in real_index.words}
        for pattern in real_patterns:
            grid = fill_pattern(pattern, real_index, Random("audit"))
            assert grid is not None, pattern.name
            for row in range(pattern.size):
                for col in range(pattern.size):
                    if pattern.is_block(row, col):
                        assert grid[row][col] == "#"
                    else:
                        assert grid[row][col].isupper()
            spelled = [
                "".join(grid[r][c] for r, c in slot.cells)
                for slot in extract_slots(pattern)
            ]
            assert all(word in vocabulary for word in spelled)
            assert len(spelled) == len(set(spelled))


class TestSolvabilitySweep:
    """PLAN.md 8: every seed must fill via the pattern-fallback chain."""

    @pytest.mark.slow
    @pytest.mark.parametrize("seed", [f"sweep-{i}" for i in range(10)])
    def test_seed_fills_within_the_time_budget(self, seed, real_index, real_patterns):
        rng = Random(seed)
        order = list(real_patterns)
        rng.shuffle(order)
        started = time.perf_counter()
        result = fill_any_pattern(order, real_index, rng)
        elapsed = time.perf_counter() - started
        assert result is not None, f"{seed} filled no pattern"
        assert elapsed < 5.0, f"{seed} took {elapsed:.1f}s"

    @pytest.mark.slow
    def test_every_bundled_pattern_is_fillable_on_its_own(self, real_index, real_patterns):
        # A pattern nothing can fill is dead weight in the fallback chain.
        for pattern in real_patterns:
            filled = any(
                fill_pattern(pattern, real_index, Random(f"{pattern.name}-{i}"))
                is not None
                for i in range(3)
            )
            assert filled, f"{pattern.name} never fills"
