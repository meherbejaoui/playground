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

    if args.command == "show":
        return _run_show(args)

    print(f"{args.command}: not implemented", file=sys.stderr)
    return 1


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
