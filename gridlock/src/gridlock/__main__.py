"""Command-line entrypoint: ``python -m gridlock <subcommand>``.

This module does argparse dispatch only; every subcommand delegates to a
module that holds the actual logic.
"""

from __future__ import annotations

import argparse
import sys


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

    print(f"{args.command}: not implemented", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
