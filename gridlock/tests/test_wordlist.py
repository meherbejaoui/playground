"""Tests for wordlist parsing and the validate-words linter."""

from __future__ import annotations

import io
from pathlib import Path

import pytest

from gridlock.wordlist import (
    Word,
    WordlistError,
    length_warnings,
    load_wordlist,
    parse_wordlist,
    read_wordlist,
    validate_words,
)

FIXTURES = Path(__file__).parent / "fixtures"
CLEAN = FIXTURES / "words-clean.tsv"
BROKEN = FIXTURES / "words-broken.tsv"


class TestCleanParsing:
    def test_parses_every_entry_with_no_issues(self):
        words, issues = read_wordlist(CLEAN)
        assert issues == []
        assert [w.text for w in words] == ["CAT", "OPAL", "ROUTE", "ADOBE", "EYE"]

    def test_scores_and_multiple_clues_survive(self):
        words, _ = read_wordlist(CLEAN)
        by_text = {w.text: w for w in words}
        assert by_text["CAT"].score == 90
        assert by_text["CAT"].clues == ("Purring pet", "Mouse chaser")
        assert by_text["OPAL"].clues == ("Iridescent gem",)

    def test_comments_and_blank_lines_are_skipped(self):
        words, issues = parse_wordlist("# note\n\n   \nCAT\t50\tPet\n")
        assert issues == []
        assert words == [Word("CAT", 50, ("Pet",))]

    def test_load_wordlist_returns_words_for_a_clean_file(self):
        assert len(load_wordlist(CLEAN)) == 5


@pytest.fixture(scope="module")
def issues():
    _words, found = read_wordlist(BROKEN)
    return {issue.line: issue.message for issue in found}


class TestIssueReporting:

    def test_reports_exactly_the_expected_lines(self, issues):
        assert sorted(issues) == [4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14]

    @pytest.mark.parametrize(
        "line,fragment",
        [
            (4, "uppercase A-Z"),
            (5, "uppercase A-Z"),
            (6, "length 2"),
            (7, "length 8"),
            (8, "not an integer"),
            (9, "outside the allowed range"),
            (10, "outside the allowed range"),
            (11, "3 tab-separated fields"),
            (12, "gives away the answer"),
            (13, "duplicate word"),
            (14, "at least one clue"),
        ],
    )
    def test_each_error_type_is_described(self, issues, line, fragment):
        assert fragment in issues[line]

    def test_valid_lines_still_parse_alongside_broken_ones(self):
        words, _ = read_wordlist(BROKEN)
        assert [w.text for w in words] == ["CAT"]

    def test_load_wordlist_refuses_a_file_with_errors(self):
        with pytest.raises(WordlistError, match="problem"):
            load_wordlist(BROKEN)

    def test_missing_file_raises(self):
        with pytest.raises(FileNotFoundError):
            read_wordlist(FIXTURES / "no-such-file.tsv")


class TestValidateWordsCommand:
    def test_clean_file_exits_zero_and_summarises(self):
        out = io.StringIO()
        assert validate_words(CLEAN, out=out) == 0
        text = out.getvalue()
        assert "5 entries OK" in text
        assert "3:2" in text  # two three-letter words

    def test_broken_file_exits_one_and_lists_every_problem(self):
        out = io.StringIO()
        assert validate_words(BROKEN, out=out) == 1
        text = out.getvalue()
        assert f"{BROKEN}:4:" in text
        assert text.count(f"{BROKEN}:") == 11
        assert "11 problem(s)" in text

    def test_missing_file_exits_one(self):
        out = io.StringIO()
        assert validate_words(FIXTURES / "nope.tsv", out=out) == 1
        assert "not found" in out.getvalue()


class TestLengthWarnings:
    def test_flags_a_dominating_bucket(self):
        words = [Word("A" * 3, 50, ("x",))] * 9 + [Word("BBBB", 50, ("x",))]
        notes = length_warnings(words)
        assert any("dominates" in note for note in notes)

    def test_flags_a_thin_bucket(self):
        words = [Word(f"{i:04d}", 50, ("x",)) for i in range(30)] + [Word("AAA", 50, ("x",))]
        notes = length_warnings(words)
        assert any("thin bucket" in note for note in notes)

    def test_balanced_list_produces_no_notes(self):
        words = [Word("AAA", 50, ("x",))] * 5 + [Word("BBBB", 50, ("x",))] * 5
        assert length_warnings(words) == []


@pytest.fixture(scope="module")
def shipped():
    return load_wordlist()


class TestShippedWordlist:
    """Keeps the curated data honest forever (TASKS M2.3)."""

    def test_lints_clean(self):
        out = io.StringIO()
        assert validate_words(out=out) == 0, out.getvalue()

    def test_has_at_least_fifteen_hundred_entries(self, shipped):
        assert len(shipped) >= 1500

    @pytest.mark.parametrize("length,minimum", [(3, 250), (4, 400), (5, 450)])
    def test_per_length_minimums(self, shipped, length, minimum):
        assert sum(1 for word in shipped if len(word) == length) >= minimum

    def test_every_entry_is_usable_by_the_filler(self, shipped):
        for word in shipped:
            assert word.text.isupper() and word.text.isalpha()
            assert 1 <= word.score <= 100
            assert word.clues and all(clue.strip() for clue in word.clues)

    def test_words_are_unique(self, shipped):
        texts = [word.text for word in shipped]
        assert len(texts) == len(set(texts))
