# TASKS — ordered build plan for Cellblock

Execute top to bottom. Where detail is missing, PLAN.md §-references are
authoritative. **All paths are relative to the `cellblock/` project
directory** (run pip, pytest, and `python -m cellblock` from inside it),
except `.github/workflows/` in M7, which lives at the repo root. Commit at
least once per completed task (`M2.1: line solver`, …); run the full test
suite before every commit.

Definition of done for v1 = M0–M6 complete and green. M7 is optional.

---

## M0 — Scaffolding

### M0.1 Project skeleton
- **Create**: `pyproject.toml` (name `cellblock`, `requires-python >= 3.11`,
  no runtime deps, dev extra = pytest, setuptools `src/` layout),
  `src/cellblock/__init__.py` (`__version__ = "0.1.0"`),
  `src/cellblock/__main__.py` (argparse skeleton: `generate`,
  `import-gallery`, `validate-gallery`, `build`, `show` — all "not
  implemented", exit 1), `.gitignore` per PLAN §7.
- **Accept**: `pip install -e ".[dev]"` works; each subcommand exits 1;
  `pytest` collects 0 tests, exit 0.

---

## M1 — Model: bitmaps, clues, JSON, terminal rendering

### M1.1 Bitmap + clue derivation (`src/cellblock/model.py`)
- Bitmap type per PLAN §3.1; `parse_bitmap(text)` / `format_bitmap(grid)`
  for the `#`/`.` convention; `derive_clues(grid) → (rowClues, colClues)`
  (run-lengths; all-empty line → `[]`).
- **Tests** (`tests/test_model.py`): clue derivation on hand-made grids
  including all-empty and all-full lines; parse/format round-trip.

### M1.2 Bit-packing + puzzle JSON
- `pack_solution(grid) → base64 str` / `unpack_solution(b64, rows, cols)`
  per PLAN §3.3 (row-major, per-row byte padding, MSB-first). `Puzzle`
  dataclass with every §3.3 field; `to_json` / `from_json` round-trip.
- Write the **shared known-answer vector**: a fixed 7×13 bitmap and its
  exact base64 string, stored in `tests/fixtures/packing.json` — the JS
  decoder test (M5.1) must consume this same file.
- **Tests**: round-trips on 5×5, 10×10, 7×13; known-answer vector matches;
  JSON round-trip equality.

### M1.3 Terminal rendering (`src/cellblock/render.py`) + `show`
- `render_puzzle(puzzle, solved=True)`: grid with `#`/`·`, column clues
  stacked above, row clues left, heavier 5-cell rules approximated with
  spacing; `render_stuck(grid)` showing UNKNOWN as `?` (used by the gallery
  validator's diagnostics later).
- Wire `show <file>`; commit a hand-written schema-valid fixture
  `tests/fixtures/sample-5x5.json` and snapshot-test the rendering.
- **Accept**: `python -m cellblock show tests/fixtures/sample-5x5.json`
  prints a legible clued grid; snapshot test green.

---

## M2 — The solver (heart of the project; budget the most care here)

### M2.1 Line solver (`src/cellblock/solver.py`)
- Implement `solve_line` per PLAN §4.2 exactly (memoized feasibility DP;
  forced-cell extraction; `None` on contradiction). Handle empty clues,
  overfull clues, solved-line idempotence.
- **Tests** (`tests/test_solver.py`): the hand-verified table from PLAN §8
  bullet 1 (≥ 12 cases including the `[8]`-in-10 overlap classic), THEN the
  brute-force cross-check: ~200 seeded-random (length ≤ 10) cases where all
  2^n completions are enumerated and forced sets compared. Do not proceed to
  M2.2 until the cross-check passes — it is the project's correctness anchor.

### M2.2 Grid propagation + difficulty
- `solve_grid` worklist per PLAN §4.3 (status, final grid, passes);
  `grade(passes, rows, cols)` per PLAN §4.4 with thresholds in one constant.
- **Tests**: solvable fixture → SOLVED with the exact bitmap; a hand-built
  two-solution fixture (e.g. the classic 2×2 checkerboard ambiguity, clues
  `[1],[1]` / `[1],[1]`) → STUCK; contradiction fixture → CONTRADICTION;
  grade thresholds boundary-tested.

---

## M3 — Generation sources

### M3.1 Procedural candidates (`src/cellblock/generate.py`)
- Candidate loop per PLAN §4.5: fill p=0.55, one smoothing pass (≥ 5 of
  9-neighborhood, out-of-bounds = EMPTY), rejection order (density 35–65% →
  trivial-lines ≤ 25% → SOLVED), 1,000-candidate budget, single RNG,
  exit-2 path.
- **Tests** (`tests/test_generate.py`): the no-guessing sweep from PLAN §8
  (10 seeds × sizes {5, 10}: emitted clues re-solve from scratch to the
  decoded solution); determinism (same seed → identical minus
  `generatedAt`); 3 seeds → 3 distinct solutions.

### M3.2 Gallery pipeline (`src/cellblock/gallery.py`)
- Parse/validate PLAN §3.2 (metadata, rectangularity, charset, size bounds,
  required title) and fairness via `solve_grid`; produce gallery `Puzzle`s.
  Wire `validate-gallery` (per-file OK/FAIL + stuck-grid diagnostic via
  `render_stuck`) and `import-gallery` per PLAN §5.
- **Tests** (`tests/test_gallery.py`): each malformed fixture fails with the
  right message; a fair fixture imports; an unfair-but-well-formed fixture
  is rejected with the stuck diagnostic.

### M3.3 Author the starter gallery (`data/gallery/`)
- Draw **~12 original ASCII pixel arts** (sizes 8×8–12×12, recognizable
  everyday subjects — e.g. sailboat, cat face, mug, key, tree, umbrella,
  fish, house, heart, moon, mushroom, glasses). Draw → `validate-gallery` →
  rework any FAIL (add/remove pixels to break ambiguity) → repeat.
- **Accept**: `validate-gallery` exits 0 on the shipped set; permanent test
  asserts every shipped file is fair and the set has ≥ 10 files.

---

## M4 — Generate CLI

### M4.1 Wire `generate`
- Full PLAN §5 row: UTC-date default seed, `--size {5,10,15}` (default 10),
  preview print, `--quiet`, `--force` overwrite guard, exit codes.
- **Tests**: end-to-end into `tmp_path` — file schema-valid (field types +
  clues match the decoded solution), overwrite refused without `--force`,
  `--size 12` rejected by argparse choices.
- **Accept**: `python -m cellblock generate --seed 2026-08-19` prints a
  clued preview and writes a valid file.

---

## M5 — Browser player

### M5.1 Pure logic (`web/player-core.js`)
- Every export in PLAN §6 bullet 1, implementing the semantics of §6 items
  2–6 as pure logic (tool toggling, `dragValue` start-cell rule, cursor
  movement, `lineSatisfied`, check never judging X-marks, `isComplete`
  treating X and blank as equal).
- **Tests** (`tests/player/core.test.mjs`, `node --test`): decode the shared
  known-answer vector from `tests/fixtures/packing.json` (M1.2); every
  behavior listed in PLAN §8 last bullet; ≥ 25 assertions, ≥ 10 cases.

### M5.2 UI (`web/player-ui.js`, `web/player.css`, `web/page.html`)
- Implement PLAN §6 items 1–8 completely, including right-click Mark with
  suppressed context menu, drag painting via pointer events (set
  `touch-action: none` on the grid), the Fill/X toggle button, keyboard-only
  solvability, clue dimming, toolbar with confirms, timer +
  `visibilitychange`, debounced `cellblock:<id>` saves, the completion
  picture-reveal (fade X-marks/gridlines, show title for gallery kind),
  responsive + dark mode, placeholders per PLAN §7.
- **Accept**: manual checklist against a generated 10×10 AND a gallery
  puzzle: every numbered PLAN §6 interaction verified; usable at 375px; no
  console errors. Record checklist results in the commit message body.

---

## M6 — Static site builder

### M6.1 `build.py`
- Per PLAN §5 `build` row: per-puzzle self-contained pages; index with
  "Daily" (reverse-chron, newest = "Today", shows difficulty grade) and
  "Gallery" (by title, shows grade) sections; `.cellblock-site`
  marker + wipe-guard; escaping rules as specified.
- **Tests** (`tests/test_build.py`): build 2 dailies + 2 gallery puzzles
  into `tmp_path`; both index sections correct and ordered; pages carry
  base64 but no `#`/`.` bitmap dumps of solutions; wipe-guard refuses an
  unmarked non-empty dir; incremental rebuild picks up a new puzzle.
- **Accept**: `generate` × 3 seeds + `import-gallery` → `build` → open
  `site/index.html`, solve one daily and one gallery puzzle end to end.
  v1 complete.

---

## M7 — OPTIONAL stretch: automation (read PLAN §9 items 6–7 first)

### M7.1 CI (repo root: `.github/workflows/cellblock-ci.yml`)
- On push/PR filtered to `paths: ["cellblock/**"]`, with
  `defaults.run.working-directory: cellblock`: Python 3.11 + Node 18/20,
  `pip install -e ".[dev]"`, `pytest`, `node --test tests/player/`.

### M7.2 Daily Pages deploy (repo root: `.github/workflows/cellblock-daily.yml`)
- Cron + manual dispatch: generate today's puzzle, commit `puzzles/<id>.json`
  back (un-gitignore `puzzles/` in this task), build, deploy.
- **Monorepo caveat (binding)**: GitHub serves ONE Pages site per repo. If
  the sister project's deploy also exists here, implement the combined
  artifact instead — a root `index.html` linking to `gridlock/` and
  `cellblock/` subdirectories, each project's built `site/` copied under its
  name — in a single shared deploy workflow rather than two competing ones.
- **Accept**: workflows lint clean; README documents the one manual step
  (enable Pages: Settings → Pages → GitHub Actions source).

---

## Dependencies at a glance

M0 → M1 → M2 → M3 → M4 → M6 linear; M3.2/M3.3 need M2; M5.1 needs only
M1.2's schema + packing vector (can start after M1); M5.2 needs M5.1;
M6 needs M4 + M3.2 + M5.2; M7 needs M6.
