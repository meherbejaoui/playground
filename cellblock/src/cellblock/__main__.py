"""Command-line entrypoint: ``python -m cellblock <subcommand>``.

This module does argparse dispatch only; every subcommand delegates to a
module that holds the actual logic.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="cellblock",
        description="Generate certified-solvable nonograms and build a static site to play them.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    gen = sub.add_parser("generate", help="generate a daily puzzle for a seed (default: today)")
    gen.add_argument("--seed", help="seed string; defaults to today's UTC date (YYYY-MM-DD)")
    gen.add_argument("--size", type=int, choices=(5, 10, 15), default=10, help="grid size (square)")
    gen.add_argument("--out", default="puzzles", help="output directory for puzzle JSON")
    gen.add_argument("--quiet", action="store_true", help="suppress the terminal preview")
    gen.add_argument("--force", action="store_true", help="overwrite an existing puzzle file")

    imp = sub.add_parser("import-gallery", help="convert gallery art into puzzle JSON")
    imp.add_argument("--gallery", default="data/gallery", help="directory of gallery .txt files")
    imp.add_argument("--out", default="puzzles", help="output directory for puzzle JSON")

    val = sub.add_parser("validate-gallery", help="check that every gallery file is fair")
    val.add_argument("--gallery", default="data/gallery", help="directory of gallery .txt files")

    bld = sub.add_parser("build", help="assemble the static site from generated puzzles")
    bld.add_argument("--puzzles", default="puzzles", help="directory of puzzle JSON files")
    bld.add_argument("--out", default="site", help="output directory for the site")
    bld.add_argument("--title", default="Cellblock", help="site title")

    show = sub.add_parser("show", help="print an existing puzzle file in the terminal")
    show.add_argument("puzzle", help="path to a puzzle JSON file")

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    if args.command == "generate":
        return _run_generate(args)

    if args.command == "show":
        return _run_show(args)

    if args.command == "validate-gallery":
        return _run_validate_gallery(args)

    if args.command == "import-gallery":
        return _run_import_gallery(args)

    if args.command == "build":
        return _run_build(args)

    print(f"{args.command}: not implemented", file=sys.stderr)
    return 1


def _run_generate(args: argparse.Namespace) -> int:
    from .generate import GenerationError, generate_and_write
    from .render import render_puzzle

    try:
        puzzle, path = generate_and_write(
            seed=args.seed, size=args.size, out_dir=args.out, force=args.force
        )
    except FileExistsError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    except GenerationError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    if not args.quiet:
        print(render_puzzle(puzzle))
        print()
    print(f"Wrote {path}")
    return 0


def _run_build(args: argparse.Namespace) -> int:
    from .build import BuildError, build_site

    try:
        daily, gallery = build_site(puzzles_dir=args.puzzles, out_dir=args.out, title=args.title)
    except BuildError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    print(f"Wrote {args.out} ({len(daily)} daily, {len(gallery)} gallery, index + player)")
    return 0


def _run_validate_gallery(args: argparse.Namespace) -> int:
    from .gallery import state_grid_to_bools, validate_gallery
    from .render import render_stuck

    results = validate_gallery(args.gallery)
    if not results:
        print(f"no gallery files found in {args.gallery}", file=sys.stderr)
        return 1

    failed = 0
    for result in results:
        if result.ok:
            print(f"OK   {result.slug}")
        else:
            failed += 1
            print(f"FAIL {result.slug}: {result.message}", file=sys.stderr)
            if result.stuck_grid is not None:
                bools = state_grid_to_bools(result.stuck_grid)
                print(
                    render_stuck(bools, result.row_clues, result.col_clues),
                    file=sys.stderr,
                )

    print(f"\n{len(results) - failed}/{len(results)} gallery file(s) OK")
    return 1 if failed else 0


def _run_import_gallery(args: argparse.Namespace) -> int:
    from .gallery import GalleryError, import_gallery

    try:
        puzzles = import_gallery(args.gallery, args.out)
    except GalleryError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    print(f"Wrote {len(puzzles)} gallery puzzle(s) to {args.out}")
    return 0


def _run_show(args: argparse.Namespace) -> int:
    from .model import PuzzleError, from_json
    from .render import render_puzzle

    try:
        text = Path(args.puzzle).read_text(encoding="utf-8")
        puzzle = from_json(text)
    except (OSError, PuzzleError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    print(render_puzzle(puzzle))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
