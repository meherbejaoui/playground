# Cellblock — a daily nonogram factory

Cellblock generates nonograms (picross / griddler puzzles) that are
**guaranteed solvable by pure logic — no guessing ever required** — and builds
a static website where anyone can solve them in the browser. It is the sister
project of Gridlock (`../gridlock/`): same philosophy (deterministic daily
puzzles, Python-stdlib generator, JSON contract, vanilla-JS player, zero
infrastructure), completely independent codebase.

```
$ python -m cellblock generate --seed 2026-08-19
Candidate 37 accepted: 10×10, density 52%, grade medium (7 passes)

        2  1  1        1
     3  1  2  2  5  2  4  1  3  2
  ┌──────────────────────────────┐
 …a 10×10 clue grid preview…

Wrote puzzles/2026-08-19-10.json

$ python -m cellblock build
Wrote site/ (1 daily puzzle, 12 gallery puzzles, index + player)
```

## Why this is worth building

- **The interesting problem is inverted from Gridlock's.** A crossword is hard
  to *fill*; a nonogram is trivial to create (any bitmap works) but hard to
  create *well*. A random picture usually produces a puzzle that stalls and
  forces guessing — the difference between a fair puzzle and a miserable one.
  Cellblock's core is a **line solver**: a dynamic-programming routine that
  computes every cell a perfect logician could deduce from one row or column,
  propagated to a fixpoint across the grid. Generation is then *rejection
  sampling*: produce candidate pictures, keep only the ones the solver fully
  cracks. Every shipped puzzle is certified no-guessing (and therefore has a
  unique solution) by construction.
- **The solver is the star, not glue code.** Line-solving nonograms is a
  classic constraint-propagation problem that is genuinely fun to implement
  and test — and far less trodden as a *project* than word games.
- **Two kinds of puzzles from one engine.** Seeded procedural dailies (same
  date → same puzzle for everyone, a free shared ritual), plus a curated
  gallery of hand-drawn pixel art whose reveal-the-picture ending is the
  payoff nonograms are loved for.
- **Everything is plain text.** Gallery art is ASCII files you can draw in
  any editor; the validator tells you immediately if your drawing makes a
  fair puzzle.

## Who it's for

- The same small groups Gridlock serves — a second daily puzzle for the same
  static site, with zero extra infrastructure.
- Pixel-artists who want to publish their art *as puzzles* and know they're
  fair before sharing.
- Developers who want a clean, tested reference implementation of nonogram
  line solving.

## What v1 delivers

- `cellblock generate` — deterministic daily 10×10 (and `--size 5`) puzzles,
  certified line-solvable, with a difficulty grade.
- A starter gallery of ~12 hand-drawn pixel-art puzzles, validated fair.
- `cellblock build` — static site: archive index (dailies + gallery) and a
  self-contained player page per puzzle.
- A polished player: fill and X-mark tools, drag painting, keyboard support,
  auto-dimming of satisfied clue lines, check/reveal, timer, saved progress,
  mobile layout, dark mode, and a reveal-the-picture completion moment.
- `cellblock validate-gallery` — proves every gallery image is line-solvable.
- A test suite locking down solver correctness, the no-guessing guarantee,
  and determinism.

Out of scope for v1: sizes above 15×15, color nonograms, hint systems beyond
check/reveal, multiplayer, and any solving techniques beyond single-line
deduction (see PLAN.md §9 — this bounds difficulty *by design*).

## Project map

- `PLAN.md` — architecture, the line-solver specification, data model,
  generation strategy, player spec, folder structure, and **assumptions &
  open questions** (flagged at the end).
- `TASKS.md` — 7 ordered milestones with per-task acceptance criteria.

Like its sister, this directory is fully self-contained and can be split into
its own repository with a single `git mv`.
