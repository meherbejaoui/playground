"""The fill engine: candidate indexing and backtracking search (PLAN.md 4).

Pure logic — no I/O, no globals, and every source of randomness is passed in
so a seed fully determines the result.
"""

from __future__ import annotations

from dataclasses import dataclass
from random import Random
from typing import Iterable, Sequence

from .patterns import Pattern, Slot, extract_slots
from .wordlist import Word

# Tuned against the shipped wordlist (PLAN.md 4.3 invites this): every
# bundled pattern fills well inside this budget, and the one layout that
# needs most of it (diagonal-2, six interlocking five-letter words) still
# finishes in about three seconds on the hardest seeds.
DEFAULT_MAX_BACKTRACKS = 250_000

# A slot's known letters, as a sorted tuple of (position, letter) pairs.
Constraint = tuple[tuple[int, str], ...]


class CandidateIndex:
    """Answers "which words fit this slot?" quickly enough to drive the search.

    Two lookup tables per PLAN.md 4.2: every word id grouped by length, and
    every word id grouped by (length, position, letter). A constrained slot's
    candidates are the intersection of one set per known letter.
    """

    def __init__(self, words: Sequence[Word]):
        self.words: tuple[Word, ...] = tuple(words)
        self._by_length: dict[int, frozenset[int]] = {}
        self._by_constraint: dict[tuple[int, int, str], frozenset[int]] = {}
        self._cache: dict[tuple[int, Constraint], tuple[int, ...]] = {}

        by_length: dict[int, set[int]] = {}
        by_constraint: dict[tuple[int, int, str], set[int]] = {}
        for word_id, word in enumerate(self.words):
            length = len(word.text)
            by_length.setdefault(length, set()).add(word_id)
            for position, letter in enumerate(word.text):
                by_constraint.setdefault((length, position, letter), set()).add(word_id)

        self._by_length = {k: frozenset(v) for k, v in by_length.items()}
        self._by_constraint = {k: frozenset(v) for k, v in by_constraint.items()}

    def lengths(self) -> list[int]:
        return sorted(self._by_length)

    def word(self, word_id: int) -> Word:
        return self.words[word_id]

    def text(self, word_id: int) -> str:
        return self.words[word_id].text

    def candidates_for(self, length: int, fixed: Constraint = ()) -> tuple[int, ...]:
        """Word ids of every entry of ``length`` matching the fixed letters.

        Always returned in ascending id order: callers that shuffle must start
        from a deterministic sequence (PLAN.md 4.3).
        """
        key = (length, fixed)
        cached = self._cache.get(key)
        if cached is not None:
            return cached

        if not fixed:
            result = tuple(sorted(self._by_length.get(length, frozenset())))
        else:
            sets = [
                self._by_constraint.get((length, position, letter), frozenset())
                for position, letter in fixed
            ]
            sets.sort(key=len)
            matching: frozenset[int] = sets[0]
            for other in sets[1:]:
                if not matching:
                    break
                matching = matching & other
            result = tuple(sorted(matching))

        self._cache[key] = result
        return result

    def count_candidates(self, length: int, fixed: Constraint = ()) -> int:
        return len(self.candidates_for(length, fixed))

    def order_candidates(self, word_ids: Iterable[int], rng: Random) -> list[int]:
        """Shuffle within descending score buckets (PLAN.md 4.3).

        High-scoring words are tried first so fills read well, while the
        shuffle inside each bucket keeps different seeds from producing the
        same puzzle.
        """
        buckets: dict[int, list[int]] = {}
        for word_id in sorted(word_ids):
            buckets.setdefault(self.words[word_id].score // 10, []).append(word_id)
        ordered: list[int] = []
        for bucket in sorted(buckets, reverse=True):
            group = buckets[bucket]
            rng.shuffle(group)
            ordered.extend(group)
        return ordered


@dataclass(frozen=True)
class FillResult:
    assignment: dict[int, int]  # slot index -> word id
    backtracks: int

    def words(self, index: CandidateIndex) -> dict[int, str]:
        return {slot: index.text(word_id) for slot, word_id in self.assignment.items()}


def _constraint(letters: dict[tuple[int, int], str], slot: Slot) -> Constraint:
    return tuple(
        (position, letters[cell])
        for position, cell in enumerate(slot.cells)
        if cell in letters
    )


def fill_slots(
    slots: Sequence[Slot],
    index: CandidateIndex,
    rng: Random,
    max_backtracks: int = DEFAULT_MAX_BACKTRACKS,
) -> FillResult | None:
    """Assign a distinct word to every slot, or return ``None``.

    Most-constrained-first with immediate backtracking on any empty domain;
    the search gives up once ``max_backtracks`` dead ends have been hit, which
    is what makes an unfillable pattern cheap to abandon (PLAN.md 4.4).
    """
    letters: dict[tuple[int, int], str] = {}
    assignment: dict[int, int] = {}
    used: set[int] = set()
    state = {"backtracks": 0}

    def choose_slot() -> tuple[int, tuple[int, ...]] | None:
        """The unassigned slot with the fewest candidates, and that shortlist."""
        best_slot = -1
        best: tuple[int, ...] = ()
        for slot_index, slot in enumerate(slots):
            if slot_index in assignment:
                continue
            candidates = tuple(
                word_id
                for word_id in index.candidates_for(slot.length, _constraint(letters, slot))
                if word_id not in used
            )
            if not candidates:
                return slot_index, ()
            if best_slot < 0 or len(candidates) < len(best):
                best_slot, best = slot_index, candidates
        if best_slot < 0:
            return None
        return best_slot, best

    def search() -> bool:
        if len(assignment) == len(slots):
            return True

        picked = choose_slot()
        if picked is None:
            return True
        slot_index, candidates = picked
        if not candidates:
            state["backtracks"] += 1
            return False

        slot = slots[slot_index]
        for word_id in index.order_candidates(candidates, rng):
            word = index.text(word_id)
            written = [
                cell for position, cell in enumerate(slot.cells) if cell not in letters
            ]
            for position, cell in enumerate(slot.cells):
                letters[cell] = word[position]
            assignment[slot_index] = word_id
            used.add(word_id)

            if search():
                return True

            del assignment[slot_index]
            used.discard(word_id)
            for cell in written:
                del letters[cell]

            state["backtracks"] += 1
            if state["backtracks"] >= max_backtracks:
                return False
        return False

    if search() and len(assignment) == len(slots):
        return FillResult(assignment=dict(assignment), backtracks=state["backtracks"])
    return None


def grid_from_assignment(
    pattern: Pattern,
    slots: Sequence[Slot],
    assignment: dict[int, int],
    index: CandidateIndex,
) -> tuple[str, ...]:
    """Render an assignment as solution rows, with ``#`` for blocks."""
    cells: dict[tuple[int, int], str] = {}
    for slot_index, word_id in assignment.items():
        word = index.text(word_id)
        for position, cell in enumerate(slots[slot_index].cells):
            cells[cell] = word[position]
    return tuple(
        "".join(
            "#" if pattern.is_block(row, col) else cells[(row, col)]
            for col in range(pattern.size)
        )
        for row in range(pattern.size)
    )


def fill_pattern(
    pattern: Pattern,
    index: CandidateIndex,
    rng: Random,
    max_backtracks: int = DEFAULT_MAX_BACKTRACKS,
) -> tuple[str, ...] | None:
    """Fill one pattern and return its solution grid, or ``None``."""
    slots = extract_slots(pattern)
    result = fill_slots(slots, index, rng, max_backtracks)
    if result is None:
        return None
    return grid_from_assignment(pattern, slots, result.assignment, index)


def fill_any_pattern(
    patterns: Sequence[Pattern],
    index: CandidateIndex,
    rng: Random,
    max_backtracks: int = DEFAULT_MAX_BACKTRACKS,
) -> tuple[Pattern, tuple[str, ...]] | None:
    """Try patterns in the order given, returning the first that fills.

    The caller shuffles the list; this is the fallback chain that lets a hard
    layout (the fully open grid) fail without failing the whole run.
    """
    for pattern in patterns:
        grid = fill_pattern(pattern, index, rng, max_backtracks)
        if grid is not None:
            return pattern, grid
    return None
