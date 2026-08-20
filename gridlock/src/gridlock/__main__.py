"""Command-line entrypoint: ``python -m gridlock <subcommand>``.

This module does argparse dispatch only; every subcommand delegates to a
module that holds the actual logic.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="gridlock",
        description="Generate daily mini crosswords and build a static site to play them.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    gen = sub.add_parser("generate", help="generate a puzzle for a seed (default: today)")
    gen.add_argument("--seed", help="seed string; defaults to today's UTC date (YYYY-MM-DD)")
    gen.add_argument("--size", type=int, default=5, help="grid size (only 5 is supported in v1)")
    gen.add_argument("--out", default="puzzles", help="output directory for puzzle JSON")
    gen.add_argument("--quiet", action="store_true", help="suppress the terminal preview")
    gen.add_argument("--force", action="store_true", help="overwrite an existing puzzle file")

    bld = sub.add_parser("build", help="assemble the static site from generated puzzles")
    bld.add_argument("--puzzles", default="puzzles", help="directory of puzzle JSON files")
    bld.add_argument("--out", default="site", help="output directory for the site")
    bld.add_argument("--title", default="Gridlock", help="site title")

    val = sub.add_parser("validate-words", help="lint the wordlist")
    val.add_argument("--words", default="data/words.tsv", help="path to the wordlist TSV")

    show = sub.add_parser("show", help="print an existing puzzle file in the terminal")
    show.add_argument("puzzle", help="path to a puzzle JSON file")

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    if args.command == "validate-words":
        from .wordlist import validate_words

        return validate_words(args.words)

    if args.command == "generate":
        return _run_generate(args)

    if args.command == "build":
        return _run_build(args)

    if args.command == "show":
        return _run_show(args)

    print(f"{args.command}: not implemented", file=sys.stderr)
    return 1


def _run_generate(args: argparse.Namespace) -> int:
    from .generate import GenerationError, SUPPORTED_SIZES, generate_and_write
    from .render import render_puzzle

    if args.size not in SUPPORTED_SIZES:
        print(
            f"error: --size {args.size} is not supported in v1 (only "
            f"{SUPPORTED_SIZES[0]} is available; larger sizes are a stretch "
            f"goal — see PLAN.md 9)",
            file=sys.stderr,
        )
        return 1

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
        puzzles = build_site(puzzles_dir=args.puzzles, out_dir=args.out, title=args.title)
    except BuildError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    print(f"Wrote {args.out} ({len(puzzles)} puzzle(s), index + player)")
    return 0


def _run_show(args: argparse.Namespace) -> int:
    from .puzzle import PuzzleError, from_json
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
