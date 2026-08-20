# PLAN — Cellblock architecture & design

Written for an implementing agent working without further input. Decisions
are stated as decisions; genuinely open items live in **Assumptions & open
questions** (§9). Cellblock deliberately shares **no code** with its sister
project `../gridlock/` — only design philosophy — so either project can move
to its own repository untouched. Where the two plans agree (stack rationale,
static-site approach, testing philosophy), this document keeps the statement
short and does not cross-reference: this file must stand alone.

---

## 1. System overview

```
 data/gallery/*.txt  (hand-drawn pixel art, ASCII)
        │
        ▼
 ┌──────────────────────────────────────────┐
 │  GENERATOR (Python 3.11+, stdlib only)   │
 │  procedural candidates ──┐               │
 │  gallery bitmaps ────────┼→ clue derive  │
 │                          └→ LINE SOLVER  │  ← the heart: certifies
 │        accept only fully-deduced grids   │    "no guessing needed"
 └──────────────────────────────────────────┘
        │  puzzles/<id>.json
        ▼
 ┌──────────────────────────────────────────┐
 │  SITE BUILDER (Python)                   │
 │  inlines JSON+CSS+JS into per-puzzle     │
 │  pages + archive index                   │
 └──────────────────────────────────────────┘
        │  site/  (static, host anywhere)
        ▼
 ┌──────────────────────────────────────────┐
 │  PLAYER (vanilla JS, ES modules)         │
 │  player-core.js = pure logic             │
 │  player-ui.js   = DOM binding            │
 └──────────────────────────────────────────┘
```

The puzzle JSON is the contract; generator and player never know about each
other's internals.

## 2. Tech stack and why

Identical rationale to the sister project, restated for self-containment:

- **Generator/CLI: Python 3.11+, stdlib only** (`argparse`, `json`, `random`,
  `dataclasses`, `base64`, `pathlib`, `html`). `pytest` is the sole dev
  dependency. `pyproject.toml`, `src/` layout, `python -m cellblock`
  entrypoint, editable install via `pip install -e ".[dev]"`.
- **Player: vanilla HTML/CSS/JS ES modules**, no framework, no bundler, no
  runtime fetches. Pure logic lives in `player-core.js`, tested with
  `node --test` (Node 18+; zero npm installs).
- **Hosting: static files**; optional GitHub Pages automation is the final
  stretch milestone.

## 3. Data model

### 3.1 Bitmap convention (used everywhere)

A puzzle solution is a rows×cols boolean grid: `True` = filled cell. In
text form (gallery files, terminal rendering, tests) a filled cell is `#`
and an empty cell is `.`. Internally: `tuple[tuple[bool, ...], ...]`
(immutable, hashable).

### 3.2 Gallery files — `data/gallery/<slug>.txt`

Hand-drawn pixel art, one file per image:

```
; title: Sailboat
; author: cellblock starter set
....#.....
...##.....
..#.#.....
 …exactly rows lines of exactly cols characters, only # and . …
```

- Lines starting with `;` are metadata (`title:` required, free-form keys
  otherwise); all remaining lines are the bitmap and must be equal length.
- Allowed sizes: 5×5 to 15×15, square or rectangular.
- A gallery file **must** produce a line-solvable puzzle (§4) — enforced by
  `validate-gallery` and by a permanent test over every shipped file.
- The filename slug (lowercase, hyphens) becomes the puzzle id suffix.

### 3.3 Puzzle JSON — `puzzles/<id>.json`

`id` = `<seed>-<rows>x<cols>` for dailies (e.g. `2026-08-19-10x10`) or
`gallery-<slug>` for gallery puzzles.

```json
{
  "format": 1,
  "id": "2026-08-19-10x10",
  "kind": "daily",
  "title": null,
  "rows": 10,
  "cols": 10,
  "rowClues": [[3], [1, 1], [2, 4], []],
  "colClues": [[1, 2], [5]],
  "solution": "q83vEjRWeJA=",
  "difficulty": {"passes": 7, "grade": "medium"},
  "seed": "2026-08-19",
  "generatedAt": "2026-08-19T14:03:22Z"
}
```

- `rowClues`/`colClues`: standard nonogram run-lengths, top-to-bottom /
  left-to-right; an all-empty line is `[]` (renders as "0" in the player).
- `solution`: the bitmap packed row-major, each row padded to a whole number
  of bytes, MSB-first within a byte, then base64. (Casual spoiler protection
  only — same stance as the sister project: view-source shouldn't scream the
  answer; determined cheaters are not the threat model. Unlike the crossword,
  the clues alone mathematically determine the solution anyway — line
  solvability implies uniqueness — so the field exists purely for
  check/reveal in the player.)
- `kind`: `"daily"` (procedural, `title: null`, `seed` set) or `"gallery"`
  (`title` set, `seed: null`). Gallery JSON also carries `"slug"`.
- `difficulty`: see §4.4.

### 3.4 Player save state — `localStorage`

Key `cellblock:<puzzleId>`:

```json
{"cells": "0..1x…", "elapsedSeconds": 148, "completed": false}
```

`cells` is a row-major string, one char per cell: `.` unknown, `1` filled,
`x` marked-empty. Exact encoding is implementer's choice if it round-trips;
this shape is a suggestion.

## 4. The solver (the heart of the project)

Module: `src/cellblock/solver.py`. Pure logic, no I/O, no randomness.

### 4.1 Cell states

`UNKNOWN`, `FILLED`, `EMPTY` (an `IntEnum` or module constants — cheap).

### 4.2 Line solver

`solve_line(clues: tuple[int, ...], line: tuple[state, ...]) →
tuple[state, ...] | None`

Given one row/column's clues and its current partial state, return the new
state with every **forced** cell applied, or `None` on contradiction (no
arrangement of the runs is consistent with the current partial state).

Algorithm (correct-and-simple beats clever; n ≤ 15 makes cost irrelevant):

- Memoized recursion `feasible(i, j)` = "runs j.. can be legally placed in
  cells i.. given the partial state", the standard DP: at each position
  either place an EMPTY (if cell isn't FILLED) and recurse `(i+1, j)`, or
  place run j starting at i (requires j's cells all non-EMPTY and the cell
  after the run non-FILLED / line-end) and recurse past it.
- To find forced cells, track for each cell whether it is FILLED in ≥1
  feasible completion and EMPTY in ≥1 feasible completion (accumulate during
  the DP, or run the DP twice per cell with the cell pinned — with n ≤ 15
  and ≤ 8 runs, even the naive O(n²) pinning approach is instantaneous;
  choose whichever is easier to get *provably right*). A cell feasible only
  one way becomes that state; feasible neither way → contradiction.
- Must handle: empty clue list (all cells forced EMPTY), clue sum + gaps
  exceeding line length (contradiction), already-complete lines (idempotent).

### 4.3 Grid propagation

`solve_grid(rowClues, colClues, grid=all-UNKNOWN) → (status, final_grid,
passes)` where `status ∈ {SOLVED, STUCK, CONTRADICTION}`.

Worklist algorithm: queue all rows and columns as dirty; pop a line, run
`solve_line`; if any cell changed, mark the crossing lines dirty; repeat
until the queue empties. `SOLVED` iff no UNKNOWN remains. `passes` = number
of `solve_line` calls that changed at least one cell (the difficulty raw
signal). **`SOLVED` ⟹ the puzzle is solvable by single-line deduction alone
and its solution is unique** — this is the certification the whole project
rests on.

### 4.4 Difficulty grade

Computed from a solve of the *empty* grid: `grade = "easy"` if
`passes ≤ rows+cols`, `"medium"` if `≤ 2·(rows+cols)`, else `"hard"`.
Stored in the JSON, shown in the archive index. Crude by design — flagged in
§9; thresholds live in one constant so tuning is a one-line change.

### 4.5 Procedural candidate generation

`src/cellblock/generate.py`, seeded by one `random.Random(seed_string)`:

1. Draw a candidate bitmap: independent fill probability 0.55, then one
   smoothing pass (a cell becomes FILLED iff ≥ 5 of its 9-neighborhood —
   itself plus 8 neighbors, out-of-bounds counting as EMPTY — are FILLED).
   Smoothing makes blobby, picture-ish shapes instead of static noise.
2. Reject fast, in this order: overall density outside 35–65%; more than 25%
   of lines trivial (a line is trivial if fully empty or fully filled);
   `solve_grid` on its clues ≠ `SOLVED`.
3. Accept the first survivor; record its 1-based candidate index in the log
   line. Try up to 1,000 candidates, then exit code 2 naming the seed
   (practically unreachable at 10×10 — the solvable fraction is high).

Determinism: same seed → same accepted puzzle, byte-identical JSON modulo
`generatedAt`. All randomness flows from the single RNG; never iterate a
set/dict where order affects output.

### 4.6 Gallery pipeline

`src/cellblock/gallery.py`: parse §3.2 files, derive clues, run
`solve_grid`; a file whose status isn't `SOLVED` is reported (by the
validator CLI) as unfair, with the stuck grid rendered so the artist can see
where deduction dies. Gallery puzzles get `difficulty` computed the same way.

## 5. CLI surface — `python -m cellblock …`

| Command | Behavior |
|---|---|
| `generate [--seed S] [--size N] [--out puzzles/] [--quiet] [--force]` | Seed defaults to today's UTC date `YYYY-MM-DD`. `--size` ∈ {5, 10, 15}, default 10 (square grids for dailies). Runs §4.5, writes `puzzles/<id>.json`, prints a terminal preview (clue-bordered grid, §M1.3) unless `--quiet`. Refuses to overwrite an existing id without `--force`. Exit 2 if no candidate accepted. |
| `import-gallery [--gallery data/gallery/] [--out puzzles/]` | Converts every valid gallery file to puzzle JSON (skipping unchanged existing outputs is not required — idempotent overwrite is fine for gallery kind). Exits 1 if any file is invalid or unfair, listing each. |
| `validate-gallery [--gallery data/gallery/]` | Checks every file per §3.2 + §4.6 without writing anything; per-file OK/FAIL lines with reasons; exit 1 on any failure. |
| `build [--puzzles puzzles/] [--out site/] [--title "Cellblock"]` | Static site: `site/p/<id>.html` per puzzle (self-contained: inlined CSS/JS/JSON) + `site/index.html` with two sections — "Daily" (reverse-chronological, newest labeled "Today") and "Gallery" (by title). Writes a `.cellblock-site` marker; refuses to wipe an `--out` that is non-empty and unmarked. All interpolation `html.escape`d; JSON inlined in `<script type="application/json">` with `</` escaped as `<\/`. |
| `show <puzzle.json>` | Terminal preview of an existing puzzle file (solution rendered, clues in margins). |

## 6. Player design

Two files, same split as the sister project so logic is testable without a
browser:

- **`web/player-core.js`** — pure functions, no DOM. Exports:
  `decodePuzzle(json)` (unpacks base64 solution → boolean grid),
  `applyTool(state, r, c, tool)` (tool ∈ fill/mark; cycle semantics below),
  `dragValue(state, r, c, tool)` (what a drag starting here paints),
  `moveCursor(state, key)`, `lineSatisfied(state, line)` (marks-vs-clues
  check treating UNKNOWN as blocking), `checkCells(state, scope)` /
  `reveal(state, scope)` (scope ∈ cell/all), `isComplete(state)` (every
  cell's filled-ness matches the solution; X-marks vs blanks both count as
  empty), `serializeSave` / `restoreSave`. State is a plain object; functions
  return new state.
- **`web/player-ui.js`** — DOM layer.

Interaction spec (acceptance contract for M5):

1. **Grid layout**: CSS grid; column clues rendered above, row clues to the
   left, right-aligned/bottom-aligned toward the grid; every 5th gridline
   heavier (standard nonogram visual anchor); an all-empty clue renders "0".
2. **Tools**: Fill and Mark (X). Desktop: left-click applies active tool,
   right-click always applies Mark (contextmenu suppressed on the grid).
   Clicking a cell that already has the tool's value clears it (toggle).
   **Drag painting**: pointer-down computes the paint value via `dragValue`
   (if the start cell is empty → paint the tool's value; if it already has
   the value → paint clear) and applies it to every cell dragged over,
   never flipping mid-drag. Touch: same, single-finger; a visible Fill/X
   toggle button is the tool switch on all form factors.
3. **Keyboard**: arrows move a visible cursor; Space applies Fill toggle,
   `X` applies Mark toggle; `Enter` = Space. A full keyboard-only solve must
   be possible.
4. **Clue feedback**: when `lineSatisfied`, that clue line dims. (Per-run
   strike-through is explicitly out of scope for v1 — flagged in §9.)
5. **Toolbar**: Check (menu: this cell / whole grid — wrong FILLED cells get
   a red slash cleared on edit; X-marks are never judged), Reveal (cell /
   all, confirm on all), Clear (confirm), timer (starts on first input,
   pauses on `visibilitychange`).
6. **Completion**: when `isComplete`, stop the timer, fade out X-marks and
   gridlines so the picture snaps into view, show elapsed time and — for
   gallery puzzles — the title (titles are hidden until completion;
   the index shows gallery entries by title, the puzzle page itself says
   "Gallery puzzle" pre-completion. Decided: the index spoiling the title is
   acceptable; the *picture* is the surprise, not the name).
7. **Persistence**: debounced save per §3.4; restore on load, including
   elapsed time and completed state.
8. **Layout/theme**: mobile-first (clues scale down but stay legible at
   375px width for a 10×10; 15×15 may require horizontal scroll of the grid
   container — acceptable); ≥ 700px centered comfortable sizing; dark mode
   via `prefers-color-scheme`; system font stack; no external requests.

## 7. Folder structure

All paths relative to the `cellblock/` project directory:

```
cellblock/
├── README.md / PLAN.md / TASKS.md
├── pyproject.toml            # no runtime deps; [dev] = pytest
├── .gitignore                # site/, puzzles/, __pycache__/, .pytest_cache/
├── data/gallery/             # ~12 shipped .txt pixel arts (§3.2)
├── src/cellblock/
│   ├── __init__.py           # __version__
│   ├── __main__.py           # argparse dispatch only
│   ├── model.py              # bitmap type, clue derivation, bit-packing,
│   │                         #   puzzle dataclass, JSON (de)serialize
│   ├── solver.py             # line solver + grid propagation + difficulty
│   ├── generate.py           # seeded candidate loop (§4.5)
│   ├── gallery.py            # gallery parse/validate/import (§3.2, §4.6)
│   ├── render.py             # terminal previews (clue margins, stuck grids)
│   └── build.py              # static site assembly (f-string templates)
├── web/
│   ├── player-core.js        # pure logic (ES module, JSDoc-typed)
│   ├── player-ui.js / player.css
│   └── page.html             # %%TITLE%% %%PUZZLE_JSON%% %%CSS%%
│                             #   %%CORE_JS%% %%UI_JS%% placeholders
├── tests/
│   ├── test_model.py  test_solver.py  test_generate.py
│   ├── test_gallery.py  test_build.py
│   └── player/core.test.mjs  # node --test
├── puzzles/                  # generated (gitignored)
└── site/                     # generated (gitignored)
```

## 8. Testing strategy

- **Line solver** (the most-tested code in the project): hand-verified
  tables of (clues, partial line) → expected forced cells, covering empty
  clues, full line, single run with slack, multiple runs, contradiction,
  idempotence on solved lines, and the classic "overlap" deductions (e.g.
  clue `[8]` on length 10 forces cells 2–7). Plus a brute-force
  cross-check: for every line of length ≤ 10 over ~200 random (clues,
  partial) cases, enumerate all 2^n completions directly and compare forced
  sets with the DP — this test is the correctness anchor.
- **Grid solver**: known-solvable fixtures solve to the right bitmap;
  a known-ambiguous fixture (two solutions) returns STUCK; contradiction
  fixture returns CONTRADICTION; passes counter sane.
- **No-guessing guarantee**: for 10 fixed seeds × sizes {5, 10}, `generate`
  succeeds and re-running `solve_grid` on the emitted clues from scratch
  returns SOLVED with a bitmap equal to the decoded `solution` field.
- **Determinism**: same seed twice → identical JSON minus `generatedAt`;
  three different seeds → three different solutions.
- **Bit-packing**: round-trip on ragged sizes (5×5, 10×10, 7×13), plus a
  fixed known-answer vector so the JS decoder can share it.
- **Gallery**: every shipped file parses, validates, and is line-solvable
  (permanent honesty test); malformed fixtures (ragged rows, bad chars,
  missing title, unfair image) each fail with the right message.
- **Build**: index sections/order correct; puzzle pages contain the base64
  solution but not obvious plaintext bitmaps; wipe-guard behavior.
- **Player core** (`node --test`): decode against the shared known-answer
  vector; tool/drag semantics per §6.2 (start-cell rules, no mid-drag flip);
  `lineSatisfied` cases; check/reveal; `isComplete` with X vs blank
  equivalence; save round-trip. Minimum 25 assertions across ≥ 10 cases.

## 9. Assumptions & open questions

Defaults apply if you say nothing.

1. **ASSUMPTION — single-line deduction defines "fair".** Advanced human
   techniques (multi-line reasoning, contradiction probing) are neither
   required nor modeled; anything the line solver can't finish is rejected.
   This caps maximum difficulty — a feature for a daily casual puzzle, but a
   real ceiling. *Alternative if rejected: add a bounded 1-cell
   trial-and-contradiction layer and a "hard" tier — post-v1.*
2. **ASSUMPTION — the starter gallery is agent-drawn** (~12 original ASCII
   pixel arts: recognizable everyday objects — boat, cat, cup, key, tree…).
   No copyrighted sprites, no imported art. Unfair drawings get reworked
   until they validate.
3. **ASSUMPTION — difficulty grading is crude** (§4.4 pass-count
   thresholds). Good enough to label an archive; not a research project.
4. **DECIDED — spoiler stance matches the sister project**: base64 solution
   in the JSON, gallery titles visible in the index but not on the puzzle
   page pre-completion (§6.6).
5. **OPEN — 15×15 dailies** are supported by the flag but the default stays
   10×10; 15×15 procedural blobs are solvable but visually noisy. Revisit
   with a better texture generator post-v1.
6. **RESOLVED — M7 automation.** Both projects deploy from this repo, so
   the one-Pages-site-per-repo caveat is live, not hypothetical: a single
   `.github/workflows/daily-deploy.yml` at the repo root builds, commits,
   and combines both projects' output under one artifact (root landing page
   + a subdirectory per project) — see TASKS M7.2 for the exact shape.
7. **ASSUMPTION — monorepo layout is temporary-friendly**: no shared code,
   no cross-directory imports, per-project *CI* workflows (the deploy
   workflow is the one deliberate exception — see item 6), so a future
   split is one `git mv` plus recreating a standalone deploy workflow.
