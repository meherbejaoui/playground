# PLAN — Gridlock architecture & design

This document is the single source of truth for how Gridlock is built. It is
written for an implementing agent working without further input. Where a
judgment call was made, it is stated as a decision; genuinely open items are
collected in **Assumptions & open questions** at the bottom.

---

## 1. System overview

Gridlock is two loosely-coupled halves joined by a JSON file format:

```
 data/words.tsv          data/patterns/5.json
        │                        │
        ▼                        ▼
 ┌─────────────────────────────────────┐
 │  GENERATOR (Python, stdlib only)    │
 │  wordlist → index → fill → clues    │
 │  → number → serialize               │
 └─────────────────────────────────────┘
        │  puzzles/<id>.json  (one per puzzle, committed or ephemeral)
        ▼
 ┌─────────────────────────────────────┐
 │  SITE BUILDER (Python)              │
 │  copies web/ assets, inlines puzzle │
 │  JSON into per-puzzle pages, writes │
 │  archive index.html                 │
 └─────────────────────────────────────┘
        │  site/   (static, host anywhere)
        ▼
 ┌─────────────────────────────────────┐
 │  PLAYER (vanilla JS, ES modules)    │
 │  player-core.js = pure logic        │
 │  player-ui.js   = DOM binding       │
 └─────────────────────────────────────┘
```

The puzzle JSON is the contract. The generator never knows about the DOM; the
player never knows about the fill algorithm. Either half can be rewritten
without touching the other.

## 2. Tech stack and why

| Layer | Choice | Rationale |
|---|---|---|
| Generator & CLI | Python 3.11+, **stdlib only** at runtime | Zero install friction; `argparse`, `json`, `random`, `dataclasses`, `pathlib`, `html` cover everything. No dependency can rot. |
| Tests | `pytest` (only dev dependency) | Ubiquitous, better assertion output than `unittest`. |
| Player | Vanilla HTML/CSS/JS, ES modules | The player is one screen of well-defined interactions; a framework buys nothing and adds a build step. ES modules let logic live in an importable file testable by `node --test`. |
| Player logic tests | `node --test` (Node 18+ built-in runner) | No npm install at all — `player-core.js` is dependency-free pure functions. |
| Packaging | `pyproject.toml`, `src/` layout, `python -m gridlock` entrypoint | Standard; editable install via `pip install -e ".[dev]"`. |
| Hosting | Static files; optional GitHub Pages workflow | No server keeps scope honest. |

Deliberately avoided: SQLite (JSON files are the archive), any LLM/API for
clue generation (clues are curated data), any frontend tooling (bundlers,
TypeScript — the player is small enough that JSDoc type comments suffice).

## 3. Data model

### 3.1 Wordlist — `data/words.tsv`

Tab-separated, one entry per line, `#` comments and blank lines allowed:

```
WORD<TAB>score<TAB>clue 1|clue 2|clue 3
ALBUM<TAB>80<TAB>Photo book|Release with tracks
```

- `WORD`: uppercase A–Z only, length 3–7. No spaces, hyphens, or diacritics.
- `score`: integer 1–100. Higher = more common/desirable. The filler prefers
  high scores; the validator warns below 5% and above 60% share of any single
  length bucket only informationally (no hard limits).
- clues: 1+ clues separated by `|`. Clue selection is seeded-random among a
  word's clues. A clue must not contain its answer (case-insensitive
  substring) — the validator enforces this.
- Content bar: family-friendly, no slurs, no proper nouns requiring niche
  knowledge (broadly known ones like OSLO, ELVIS are fine — crossword
  tradition). Clues may be definitional, punny, or fill-in-the-blank
  (`"___ and crafts"`).
- Target size for v1: **≥ 1,500 entries**, weighted toward lengths 3–5
  (5×5 slots are only ever lengths 3, 4, 5). Recommended shape: ~350 threes,
  ~550 fours, ~600 fives; 6–7 letter words optional (future 7×7 use).

### 3.2 Block patterns — `data/patterns/5.json`

A pattern is the black-square layout of a grid. Bundled as data, not code:

```json
{
  "size": 5,
  "patterns": [
    {"name": "open", "blocks": []},
    {"name": "pinwheel-4", "blocks": [[0,4],[1,4],[3,0],[4,0]]},
    {"name": "corners-4", "blocks": [[0,0],[0,4],[4,0],[4,4]]}
  ]
}
```

Rules every pattern must satisfy (enforced by a validator function and a
test, not by trust):

1. 180° rotational symmetry (crossword convention).
2. Every white cell is **checked** — belongs to both an across and a down slot
   of length ≥ 3 — OR the pattern explicitly allows length-3 minimum slots;
   concretely: no slot of length 1 or 2 exists in either direction.
3. All white cells form a single connected region (4-connectivity).
4. At most 8 blocks on a 5×5.

Ship **6 patterns** for size 5, including the fully open one (hardest to
fill — the filler falls back to the next pattern if it can't fill in budget,
see §4.4). Choosing which 6: implementer's discretion within the rules above;
variety of slot-length mixes is the goal.

### 3.3 Puzzle JSON — `puzzles/<id>.json`

`id` = `<seed>-<size>`, e.g. `2026-08-19-5`. Schema (versioned):

```json
{
  "format": 1,
  "id": "2026-08-19-5",
  "size": 5,
  "seed": "2026-08-19",
  "pattern": "pinwheel-4",
  "generatedAt": "2026-08-19T14:03:22Z",
  "grid": ["SCRAP", "HOAX#", "ALBUM", "#ONCE", "MAGMA"],
  "numbers": [[1,2,3,4,5],[6,0,0,0,-1],[7,0,0,0,8],[-1,9,0,0,0],[10,0,0,0,0]],
  "entries": [
    {"number": 1, "direction": "across", "row": 0, "col": 0,
     "length": 5, "answer": "U0NSQVA=", "clue": "Bits for the recycling bin"}
  ]
}
```

- `grid`: row strings of the **solution**; `#` = block. Canonical source of
  truth for cell layout.
- `numbers`: per-cell clue numbers; `0` = unnumbered white cell, `-1` = block.
  Derivable from `grid`, but precomputed so the player stays dumb.
- `entries[].answer`: **base64-encoded** solution word. This is casual
  spoiler protection only (view-source shouldn't scream the answers), not
  security — decided, not open. The player decodes at load. Note `grid` also
  contains the solution; therefore `build` strips `grid` down to a
  block-mask (`"....."` / `"#"` form, letters replaced with `.`) in the copy
  it inlines into HTML pages, while `puzzles/*.json` on disk keeps the full
  solution as the archival record.
- Standard numbering: scan row-major; a white cell gets a number if it starts
  an across slot (no white cell to its left, ≥1 to its right… length ≥ 3 by
  pattern rules) or starts a down slot analogously.

### 3.4 Player save state — `localStorage`

Key `gridlock:<puzzleId>`, value:

```json
{"cells": ["SC?A?", "H....", …], "elapsedSeconds": 148,
 "completed": false, "checkedWrong": 3}
```

`?` = user-entered-and-checked-wrong marker cleared on edit; `.` = empty.
Exact cell encoding is implementer's choice as long as it round-trips; this
shape is a suggestion.

## 4. The fill engine (the heart of the project)

Module: `src/gridlock/fill.py`. Pure logic, no I/O.

### 4.1 Slot extraction

From a pattern, extract **slots**: maximal horizontal/vertical runs of white
cells, each with `(row, col, direction, length)` and the list of cells it
covers. Build the **crossing map**: for each slot, which other slots share
which of its cells.

### 4.2 Candidate index

From the wordlist build, per length, an index
`by_constraint[(length, position, letter)] → set of word ids`, plus
`by_length[length] → list of word ids sorted by descending score`. Candidate
lookup for a partially-constrained slot = set intersection over its fixed
letters (or the full length list if unconstrained). This makes candidate
counting cheap enough to drive the heuristic.

### 4.3 Backtracking search

```
state: assignment slot → word, grid of fixed letters
loop:
  if all slots assigned → success
  pick unassigned slot with FEWEST candidates (most-constrained-first);
    if any slot has 0 candidates → backtrack immediately
  order that slot's candidates by: seeded-shuffle within descending
    score buckets (bucket = score // 10), so high-quality words are
    preferred but runs vary by seed
  for each candidate not already used in this puzzle:
    place; recurse; unplace on failure
  all candidates failed → backtrack
```

- **No duplicate words** in one puzzle (track a used-set).
- **Determinism**: all randomness flows from one `random.Random(seed_string)`
  instance created per generation run; iteration over sets must never leak
  into ordering (always sort word-id collections before shuffling). A test
  locks this down.
- **Budget**: a backtrack counter; abort a pattern after `max_backtracks`
  (default 50,000 — tune if tests show 5×5 needs less/more).

### 4.4 Pattern selection & retry

`generate` seeds the RNG, shuffles the pattern list, and tries patterns in
order until one fills within budget. With ≥1,500 words, blocked 5×5 patterns
fill in well under a second; the open pattern may fail on some seeds — that's
what the fallback is for. If **all** patterns fail (should be nearly
impossible), exit code 2 with a clear message naming the seed.

### 4.5 Clue assignment

After fill: for each slot, look up the word's clues, pick one with the run's
RNG. Two slots with… duplicates are already impossible (used-set), so no
cross-entry clue collision handling is needed.

## 5. CLI surface — `python -m gridlock …`

| Command | Behavior |
|---|---|
| `generate [--seed S] [--size 5] [--out puzzles/] [--quiet]` | Seed defaults to today's UTC date `YYYY-MM-DD`. Prints terminal preview (solution grid + numbered clue list) unless `--quiet`. Writes `puzzles/<id>.json`. Refuses to overwrite an existing id unless `--force`. Exit 0 on success. |
| `build [--puzzles puzzles/] [--out site/] [--title "Gridlock"]` | Renders `site/`: one `p/<id>.html` per puzzle (self-contained: inlined CSS/JS/puzzle-JSON with solution-stripped grid) + `index.html` archive (reverse-chronological list, latest puzzle linked prominently as "Today"). Idempotent; `--out` is wiped and rebuilt each run (safety: refuse to wipe a directory that doesn't look generated — require it to be empty or contain a `.gridlock-site` marker file that `build` writes). |
| `validate-words [--words data/words.tsv]` | Lints wordlist per §3.1; prints all violations with line numbers; exit 1 if any errors. |
| `show <puzzle.json>` | Re-renders the terminal preview of an existing puzzle file (handy for debugging). |

`--size` accepts only 5 in v1 (validated with a clear "7 is a stretch goal"
error message); the flag exists so the interface doesn't change later.

## 6. Player design

Two files so logic is testable without a browser:

- **`web/player-core.js`** — pure functions, no DOM, no globals. Exports:
  `decodePuzzle(json)`, cursor model (`moveCursor(state, key)` handling
  arrows/tab/backspace/letter semantics), `toggleDirection`, `nextSlot`,
  `checkCell/checkWord/checkAll`, `revealCell/revealWord/revealAll`,
  `isComplete(state)`, `serializeSave(state)` / `restoreSave(...)`. State is
  a plain object; every function returns a new state or a mutation-free
  answer. Tested with `node --test`.
- **`web/player-ui.js`** — renders the grid as a CSS-grid of cells, binds
  keyboard + click + touch, renders clue lists and the mobile current-clue
  bar, owns the timer (starts on first input, pauses when tab hidden via
  `visibilitychange`), persists saves (debounced), and shows the completion
  state.

Interaction spec (this is the acceptance contract for M5):

1. Click a cell → select it; click the selected cell again → toggle
   across/down. Selected cell + its slot are visually highlighted; the active
   clue is highlighted in the clue list and shown in the top bar.
2. Typing A–Z fills the cell and advances to the next empty cell in the slot
   (skipping filled ones; stops at slot end). Backspace clears the current
   cell, or moves back one and clears if already empty.
3. Arrows move the cursor spatially (skipping blocks); if the arrow axis
   differs from the current direction, the FIRST press only switches
   direction (NYT behavior). Tab / Shift-Tab jump to the next/previous slot's
   first empty cell, wrapping across ↔ down.
4. Toolbar: Check (menu: letter / word / puzzle), Reveal (same menu, with a
   confirm on "puzzle"), Clear, and the timer. Checked-wrong cells get a red
   slash that clears when the cell is edited; revealed cells are marked and
   excluded from the "solved without help" flourish.
5. On completion (all cells correct): stop timer, small CSS-only celebration
   (grid cells cascade a color wave), show elapsed time, persist
   `completed: true`.
6. Layout: mobile-first single column (grid, current-clue bar, then clue
   lists); ≥ 700px two-column (grid left, clues right). Dark mode via
   `prefers-color-scheme`. No external fonts — system font stack.

## 7. Folder structure

```
.
├── README.md / PLAN.md / TASKS.md
├── pyproject.toml            # project meta; [dev] extra = pytest
├── .gitignore                # site/, puzzles/, __pycache__, .pytest_cache
├── data/
│   ├── words.tsv             # curated wordlist (§3.1)
│   └── patterns/5.json       # block patterns (§3.2)
├── src/gridlock/
│   ├── __init__.py
│   ├── __main__.py           # argparse dispatch only
│   ├── wordlist.py           # parse/validate TSV → Word records
│   ├── patterns.py           # load patterns, validate rules, extract slots
│   ├── fill.py               # candidate index + backtracking engine
│   ├── puzzle.py             # dataclasses, numbering, JSON (de)serialize
│   ├── generate.py           # orchestrates seed→pattern→fill→clues→file
│   ├── render.py             # terminal preview rendering
│   └── build.py              # static site assembly (uses html.escape;
│                             #   templates as Python f-string functions —
│                             #   no template engine)
├── web/
│   ├── player-core.js        # pure logic (ES module, JSDoc-typed)
│   ├── player-ui.js          # DOM layer
│   ├── player.css
│   └── page.html             # skeleton with %%PLACEHOLDERS%% build.py fills
├── tests/
│   ├── test_wordlist.py  test_patterns.py  test_fill.py
│   ├── test_puzzle.py    test_generate.py  test_build.py
│   └── player/core.test.mjs  # run with: node --test tests/player/
├── puzzles/                  # generated (gitignored)
└── site/                     # generated (gitignored)
```

## 8. Testing strategy

- **Determinism**: same seed → byte-identical puzzle JSON (minus
  `generatedAt`, which the test normalizes). Two different seeds → different
  puzzles (statistically; assert on 3 seed pairs).
- **Solvability sweep**: for 10 fixed seeds × all bundled patterns
  (skipping expected-fail combos is NOT allowed — instead assert: every seed
  fills on *some* pattern via the fallback chain, and total generate time
  < 5s per puzzle on CI-class hardware).
- **Fill correctness**: filled grid respects pattern blocks; every slot's
  word is in the wordlist; no duplicate words; numbering matches a
  brute-force reference implementation written independently in the test.
- **Wordlist**: `validate-words` passes on the shipped `data/words.tsv`
  (this test keeps the curated data honest forever).
- **Build**: output HTML contains no plaintext answers (assert the literal
  solution words absent), contains the base64 forms, index lists all
  puzzles, `.gridlock-site` marker logic works.
- **Player core**: `node --test` covering cursor movement edge cases
  (block skipping, slot wrap, backspace-at-start), check/reveal semantics,
  completion detection, save round-trip.
- CI (stretch milestone): GitHub Actions running `pytest` + `node --test`.

## 9. Assumptions & open questions

Decisions below were made to keep momentum; only revisit if you (the human)
disagree. **Defaults apply if you say nothing.**

1. **ASSUMPTION — Wordlist is agent-authored.** The implementing agent writes
   `data/words.tsv` (~1,500 entries with original clues) rather than
   importing a third-party crossword dictionary, avoiding all licensing
   questions. Clue quality bar: NYT-Monday-ish, definitional or lightly
   punny. *Alternative if rejected: wire in a user-supplied TSV path.*
2. **ASSUMPTION — Spoiler handling is casual.** Answers are base64 in served
   HTML and the solution grid is stripped to a block-mask (§3.3). Anyone who
   opens devtools *and* decodes base64 can cheat; that's accepted for v1.
3. **ASSUMPTION — "Daily" means seed = UTC date.** No timezone setting in
   v1; a `--seed` override exists for custom/themed puzzles.
4. **OPEN — GitHub Pages automation (M7)** ships as a workflow file that
   generates today's puzzle, rebuilds the site, and deploys to Pages on a
   daily cron. It's written but inert until Pages is enabled in repo
   settings — the one manual step v1 can't do for you. Skip M7 entirely if
   you don't want the repo to self-update.
5. **OPEN — 7×7 grids** are structurally supported by the data model
   (patterns file per size, `--size` flag) but not shipped: they need a
   larger wordlist and tuning. Flagged as post-v1.
6. **ASSUMPTION — English only.** The A–Z constraint is load-bearing in the
   index and player; i18n is out of scope.
