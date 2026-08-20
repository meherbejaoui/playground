"""Gallery pipeline: parsing, fairness validation, and import (PLAN.md 3.2, 4.6).

A gallery file is hand-drawn pixel art. It only ships if the line solver can
certify it from a blank grid — the same guarantee procedural dailies get.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .model import (
    MAX_SIZE,
    MIN_SIZE,
    GALLERY,
    Bitmap,
    BitmapError,
    Clues,
    Difficulty,
    Puzzle,
    _bitmap_from_rows,
    derive_clues,
    pack_solution,
)
from .solver import SOLVED, Grid, State, grade, solve_grid

METADATA_PREFIX = ";"
TITLE_KEY = "title"


class GalleryError(ValueError):
    """A gallery file is malformed or unfair."""


@dataclass(frozen=True)
class GalleryEntry:
    slug: str
    title: str
    metadata: dict[str, str]
    bitmap: Bitmap


def _parse_metadata_line(line: str) -> tuple[str, str] | None:
    body = line[len(METADATA_PREFIX) :].strip()
    if ":" not in body:
        return None
    key, _, value = body.partition(":")
    return key.strip().lower(), value.strip()


def parse_gallery_file(text: str, slug: str) -> GalleryEntry:
    """Parse one gallery ``.txt`` file's contents (PLAN.md 3.2).

    Raises :class:`GalleryError` for missing metadata, ragged rows, bad
    characters, or an out-of-range size. Never checks fairness — that is
    :func:`solve_grid`'s job, run separately so callers can report which
    check failed.
    """
    metadata: dict[str, str] = {}
    bitmap_rows: list[str] = []

    for line in text.splitlines():
        if not line.strip():
            continue
        if line.lstrip().startswith(METADATA_PREFIX):
            parsed = _parse_metadata_line(line.lstrip())
            if parsed is not None:
                key, value = parsed
                metadata[key] = value
            continue
        bitmap_rows.append(line)

    if TITLE_KEY not in metadata or not metadata[TITLE_KEY]:
        raise GalleryError(f"{slug}: missing required '; title:' metadata line")

    try:
        bitmap = _bitmap_from_rows(bitmap_rows)
    except BitmapError as exc:
        raise GalleryError(f"{slug}: {exc}") from exc

    rows = len(bitmap)
    cols = len(bitmap[0])
    if not (MIN_SIZE <= rows <= MAX_SIZE and MIN_SIZE <= cols <= MAX_SIZE):
        raise GalleryError(
            f"{slug}: size {rows}x{cols} is outside the allowed range "
            f"{MIN_SIZE}x{MIN_SIZE}-{MAX_SIZE}x{MAX_SIZE}"
        )

    return GalleryEntry(slug=slug, title=metadata[TITLE_KEY], metadata=metadata, bitmap=bitmap)


def state_grid_to_bools(grid: Grid) -> list[list[bool | None]]:
    """Convert a solver ``Grid`` to render.py's ``bool | None`` convention."""
    return [
        [True if cell == State.FILLED else False if cell == State.EMPTY else None for cell in row]
        for row in grid
    ]


def slug_for(path: Path) -> str:
    return path.stem.lower()


def gallery_dir_default() -> Path:
    return Path(__file__).resolve().parents[2] / "data" / "gallery"


def load_gallery_files(gallery_dir: str | Path | None = None) -> list[Path]:
    directory = Path(gallery_dir) if gallery_dir is not None else gallery_dir_default()
    if not directory.is_dir():
        return []
    return sorted(directory.glob("*.txt"))


def check_fairness(entry: GalleryEntry) -> tuple[bool, str, Grid]:
    """Is ``entry`` line-solvable from a blank grid?

    Returns ``(is_fair, status, stuck_grid)``: ``stuck_grid`` is the partial
    solve result (only meaningful when not fair), useful for diagnostics.
    """
    row_clues, col_clues = derive_clues(entry.bitmap)
    status, grid, _passes = solve_grid(row_clues, col_clues)
    return status == SOLVED, status, grid


def to_puzzle(entry: GalleryEntry, generated_at: str) -> Puzzle:
    """Build a gallery :class:`Puzzle`. Caller must have already checked fairness."""
    row_clues, col_clues = derive_clues(entry.bitmap)
    status, _grid, passes = solve_grid(row_clues, col_clues)
    if status != SOLVED:
        raise GalleryError(f"{entry.slug}: not line-solvable ({status})")

    rows = len(entry.bitmap)
    cols = len(entry.bitmap[0])
    return Puzzle(
        id=f"gallery-{entry.slug}",
        kind=GALLERY,
        rows=rows,
        cols=cols,
        row_clues=row_clues,
        col_clues=col_clues,
        solution=pack_solution(entry.bitmap),
        difficulty=Difficulty(passes=passes, grade=grade(passes, rows, cols)),
        generated_at=generated_at,
        title=entry.title,
        slug=entry.slug,
    )


@dataclass(frozen=True)
class ValidationResult:
    slug: str
    ok: bool
    message: str
    stuck_grid: Grid | None = None
    row_clues: Clues | None = None
    col_clues: Clues | None = None


def validate_gallery(gallery_dir: str | Path | None = None) -> list[ValidationResult]:
    """Check every gallery file: parses, is well-formed, and is line-solvable."""
    results: list[ValidationResult] = []
    for path in load_gallery_files(gallery_dir):
        slug = slug_for(path)
        try:
            entry = parse_gallery_file(path.read_text(encoding="utf-8"), slug)
        except GalleryError as exc:
            results.append(ValidationResult(slug=slug, ok=False, message=str(exc)))
            continue

        is_fair, status, grid = check_fairness(entry)
        if is_fair:
            results.append(ValidationResult(slug=slug, ok=True, message="OK"))
        else:
            row_clues, col_clues = derive_clues(entry.bitmap)
            results.append(
                ValidationResult(
                    slug=slug,
                    ok=False,
                    message=f"not line-solvable ({status})",
                    stuck_grid=grid,
                    row_clues=row_clues,
                    col_clues=col_clues,
                )
            )
    return results


def import_gallery(
    gallery_dir: str | Path | None = None,
    out_dir: str | Path = "puzzles",
    generated_at: str | None = None,
) -> list[Puzzle]:
    """Convert every valid, fair gallery file into puzzle JSON.

    Raises :class:`GalleryError` listing every failure if any file is
    invalid or unfair; writes nothing in that case.
    """
    import datetime

    from .model import to_json

    stamp = generated_at or (
        datetime.datetime.now(datetime.timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )

    results = validate_gallery(gallery_dir)
    failures = [r for r in results if not r.ok]
    if failures:
        details = "\n".join(f"  {r.slug}: {r.message}" for r in failures)
        raise GalleryError(f"{len(failures)} gallery file(s) failed validation:\n{details}")

    puzzles: list[Puzzle] = []
    out_path = Path(out_dir)
    out_path.mkdir(parents=True, exist_ok=True)
    for path in load_gallery_files(gallery_dir):
        slug = slug_for(path)
        entry = parse_gallery_file(path.read_text(encoding="utf-8"), slug)
        puzzle = to_puzzle(entry, stamp)
        (out_path / f"{puzzle.id}.json").write_text(to_json(puzzle), encoding="utf-8")
        puzzles.append(puzzle)
    return puzzles
