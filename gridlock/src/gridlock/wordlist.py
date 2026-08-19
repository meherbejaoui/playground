"""The wordlist: parsing and linting ``data/words.tsv`` (PLAN.md 3.1).

Errors are collected rather than raised so ``validate-words`` can report
every problem in one pass; :func:`load_wordlist` is the strict entry point
used by the generator.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from .patterns import data_dir

MIN_LENGTH = 3
MAX_LENGTH = 7
MIN_SCORE = 1
MAX_SCORE = 100
CLUE_SEPARATOR = "|"


class WordlistError(ValueError):
    """The wordlist could not be loaded because it contains errors."""


@dataclass(frozen=True)
class Word:
    text: str
    score: int
    clues: tuple[str, ...]

    def __len__(self) -> int:
        return len(self.text)


@dataclass(frozen=True)
class Issue:
    line: int
    message: str

    def format(self, source: str) -> str:
        return f"{source}:{self.line}: {self.message}"


def wordlist_path(path: str | Path | None = None) -> Path:
    if path is not None:
        return Path(path)
    return data_dir() / "words.tsv"


def parse_wordlist(text: str) -> tuple[list[Word], list[Issue]]:
    """Parse TSV content into words plus the issues found along the way."""
    words: list[Word] = []
    issues: list[Issue] = []
    first_seen: dict[str, int] = {}

    for line_number, raw_line in enumerate(text.splitlines(), start=1):
        line = raw_line.rstrip("\n")
        if not line.strip() or line.lstrip().startswith("#"):
            continue

        fields = line.split("\t")
        if len(fields) != 3:
            issues.append(
                Issue(
                    line_number,
                    f"expected 3 tab-separated fields (WORD, score, clues), found {len(fields)}",
                )
            )
            continue

        raw_word, raw_score, raw_clues = fields
        word = raw_word.strip()
        problems_before = len(issues)

        if not word:
            issues.append(Issue(line_number, "word is empty"))
        elif not word.isascii() or not word.isalpha() or not word.isupper():
            issues.append(
                Issue(line_number, f"word {word!r} must be uppercase A-Z with no other characters")
            )
        elif not MIN_LENGTH <= len(word) <= MAX_LENGTH:
            issues.append(
                Issue(
                    line_number,
                    f"word {word!r} has length {len(word)}; allowed range is "
                    f"{MIN_LENGTH}-{MAX_LENGTH}",
                )
            )

        score = 0
        try:
            score = int(raw_score.strip())
        except ValueError:
            issues.append(Issue(line_number, f"score {raw_score.strip()!r} is not an integer"))
        else:
            if not MIN_SCORE <= score <= MAX_SCORE:
                issues.append(
                    Issue(
                        line_number,
                        f"score {score} is outside the allowed range {MIN_SCORE}-{MAX_SCORE}",
                    )
                )

        clues = tuple(clue.strip() for clue in raw_clues.split(CLUE_SEPARATOR) if clue.strip())
        if not clues:
            issues.append(Issue(line_number, "at least one clue is required"))
        elif word:
            for clue in clues:
                if word.lower() in clue.lower():
                    issues.append(
                        Issue(line_number, f"clue {clue!r} gives away the answer {word!r}")
                    )

        if word:
            if word in first_seen:
                issues.append(
                    Issue(line_number, f"duplicate word {word!r} (first seen on line {first_seen[word]})")
                )
            else:
                first_seen[word] = line_number

        if len(issues) == problems_before:
            words.append(Word(text=word, score=score, clues=clues))

    return words, issues


def length_warnings(words: list[Word]) -> list[str]:
    """Informational notes about the shape of the list (PLAN.md 3.1).

    Never errors — an unbalanced list still generates puzzles, it just
    generates less varied ones.
    """
    if not words:
        return []
    counts = Counter(len(word) for word in words)
    total = len(words)
    notes: list[str] = []
    for length in sorted(counts):
        share = counts[length] / total
        if share < 0.05:
            notes.append(
                f"length {length}: {counts[length]} words ({share:.1%}) — a thin bucket, "
                f"fills may be repetitive"
            )
        elif share > 0.60:
            notes.append(
                f"length {length}: {counts[length]} words ({share:.1%}) — dominates the list"
            )
    return notes


def read_wordlist(path: str | Path | None = None) -> tuple[list[Word], list[Issue]]:
    resolved = wordlist_path(path)
    if not resolved.is_file():
        raise FileNotFoundError(f"wordlist not found: {resolved}")
    return parse_wordlist(resolved.read_text(encoding="utf-8"))


def validate_words(path: str | Path | None = None, out=None) -> int:
    """Lint a wordlist and report to ``out``; the return value is the exit code."""
    import sys

    stream = out if out is not None else sys.stdout
    resolved = wordlist_path(path)
    try:
        words, issues = read_wordlist(resolved)
    except FileNotFoundError as exc:
        print(exc, file=stream)
        return 1

    source = str(resolved)
    for issue in issues:
        print(issue.format(source), file=stream)

    counts = Counter(len(word) for word in words)
    shape = ", ".join(f"{length}:{counts[length]}" for length in sorted(counts))
    if issues:
        print(f"\n{len(issues)} problem(s) in {len(words) + len(issues)} entries", file=stream)
        return 1

    print(f"{source}: {len(words)} entries OK ({shape})", file=stream)
    for note in length_warnings(words):
        print(f"  note: {note}", file=stream)
    return 0


def load_wordlist(path: str | Path | None = None) -> list[Word]:
    """Load a wordlist, refusing to proceed if it has any errors."""
    words, issues = read_wordlist(path)
    if issues:
        source = wordlist_path(path)
        preview = "\n".join(issue.format(str(source)) for issue in issues[:5])
        raise WordlistError(
            f"{source}: {len(issues)} problem(s) found; run `python -m gridlock "
            f"validate-words` for the full list\n{preview}"
        )
    return words
