# TASKS — ordered build plan for Gridlock

Execute top to bottom. Every task is self-contained: files to touch and
acceptance criteria are stated so no clarifying questions should be needed —
where detail is missing here, PLAN.md §-references are authoritative.
**All paths are relative to the `gridlock/` project directory** (run pip,
pytest, and `python -m gridlock` from inside it), except `.github/workflows/`
in M7, which lives at the repo root. Commit
at least once per completed task with a message like `M2.3: wordlist
validator`. Run the whole test suite before every commit.

Definition of done for v1 = milestones M0–M6 complete and green.
M7 is optional (see PLAN.md §9 item 4).

---

## M0 — Scaffolding

### M0.1 Project skeleton
- **Create**: `pyproject.toml` (name `gridlock`, `requires-python >= 3.11`,
  no runtime deps, `[project.optional-dependencies] dev = ["pytest"]`,
  setuptools `src/` layout), `src/gridlock/__init__.py` (defines
  `__version__ = "0.1.0"`), `src/gridlock/__main__.py` (argparse skeleton
  with `generate`/`build`/`validate-words`/`show` subcommands that all print
  "not implemented" and exit 1), `.gitignore` (`site/`, `puzzles/`,
  `__pycache__/`, `.pytest_cache/`, `*.egg-info/`, `.venv/`).
- **Accept**: `pip install -e ".[dev]"` succeeds; `python -m gridlock
  generate` exits 1 with "not implemented"; `pytest` reports 0 tests, exit 0
  (add empty `tests/__init__.py` if needed for collection).

---

## M1 — Core structures: patterns, slots, puzzle model

### M1.1 Pattern loading & validation (`src/gridlock/patterns.py`)
- Load `data/patterns/<size>.json`; represent a pattern as a frozen dataclass
  (`name`, `size`, `blocks: frozenset[tuple[int,int]]`).
- Implement `validate_pattern(p)` enforcing PLAN §3.2 rules 1–4 (symmetry,
  no slots shorter than 3, single connected white region, ≤ 8 blocks),
  raising `PatternError` with a message naming the rule and pattern.
- Implement `extract_slots(p)` → list of `Slot(row, col, direction, length,
  cells)` and `crossings(slots)` → for each slot index, list of
  `(own_pos, other_slot_index, other_pos)` triples.
- **Create** `data/patterns/5.json` with 6 patterns per PLAN §3.2, including
  `"open"` (no blocks). Design the other 5 yourself; verify each against
  `validate_pattern` while writing them.
- **Tests** (`tests/test_patterns.py`): all bundled patterns validate;
  hand-built invalid patterns (asymmetric; 2-length slot; disconnected)
  each raise; slot extraction on a hand-drawn pattern matches a hand-computed
  expected list; crossings are symmetric.
- **Accept**: tests green.

### M1.2 Puzzle model, numbering, serialization (`src/gridlock/puzzle.py`)
- Dataclasses `Entry` and `Puzzle` mirroring PLAN §3.3. Implement standard
  numbering (`compute_numbers(grid)` → the `numbers` matrix), base64
  encode/decode helpers for answers, `to_json(puzzle)` /
  `from_json(text)` round-trip, and `strip_solution(puzzle_dict)` which
  replaces grid letters with `.` and is used only by build (PLAN §3.3).
- **Tests** (`tests/test_puzzle.py`): numbering matches an independent
  brute-force reference implemented inside the test file; round-trip
  equality; `strip_solution` leaves `#` and removes every A–Z from `grid`
  while `entries[].answer` stays base64.
- **Accept**: tests green.

### M1.3 Terminal rendering (`src/gridlock/render.py`)
- `render_grid(puzzle, solved=True)` → the boxed grid preview (letters, `█`
  for blocks); `render_clues(puzzle)` → numbered ACROSS/DOWN clue lists.
- Wire `python -m gridlock show <file>` to print both for an existing
  puzzle JSON.
- **Accept**: `show` on a hand-written fixture JSON (commit it as
  `tests/fixtures/sample-5.json`, built by hand to schema) prints grid +
  clues; snapshot-test the output string in `tests/test_puzzle.py`.

---

## M2 — Wordlist

### M2.1 Parser (`src/gridlock/wordlist.py`)
- Parse TSV per PLAN §3.1 into `Word(text, score, clues)` records; skip
  comments/blank lines; collect (not raise) structured errors with line
  numbers: bad charset, bad length, bad score, missing/empty clues, clue
  contains answer, duplicate word.
- **Tests** (`tests/test_wordlist.py`): a fixture TSV exercising every error
  type yields exactly the expected errors; a clean fixture parses fully.

### M2.2 `validate-words` CLI
- Wire the subcommand: prints each error as `words.tsv:LINE: message`,
  summary line, exit 1 on errors / 0 clean.
- **Accept**: manual run on both fixtures behaves as specified; covered by a
  test invoking the module function (not a subprocess).

### M2.3 Author the wordlist (`data/words.tsv`) — largest single task
- Write **≥ 1,500 entries** meeting PLAN §3.1 (shape guidance: ~350×len-3,
  ~550×len-4, ~600×len-5; lengths 6–7 optional). Original clues only — do
  not copy published crossword clues. Mix definitional, fill-in-the-blank,
  and light-pun clues; ~2 clues for the most common words is a plus, 1 is
  fine. Keep everything family-friendly; broadly-known proper nouns allowed.
- Work in batches (e.g. 10 batches of 150), running `validate-words` after
  each batch so errors never accumulate.
- **Accept**: `python -m gridlock validate-words` exits 0 on the shipped
  file; a permanent test asserts this plus the ≥ 1,500 count and per-length
  minimums (≥ 250 threes, ≥ 400 fours, ≥ 450 fives).

---

## M3 — Fill engine

### M3.1 Candidate index (`src/gridlock/fill.py`)
- Build `by_length` and `by_constraint[(length, pos, letter)]` per PLAN §4.2.
  Include `candidates_for(slot, fixed_letters) -> list[word_id]` (sorted
  word-ids — determinism, PLAN §4.3) and a cheap `count_candidates`.
- **Tests**: on a tiny 8-word fixture list, hand-check candidate sets for
  several constraint combos, including the empty-constraint and
  no-candidates cases.

### M3.2 Backtracking search
- Implement PLAN §4.3 exactly: most-constrained-first, zero-candidate early
  backtrack, score-bucket seeded ordering, used-word set, `max_backtracks`
  budget (default 50,000), single `random.Random` passed in. Return
  `dict[slot_index, word_id]` or `None` (budget/exhausted).
- **Tests** (`tests/test_fill.py`): fills a hand-made 3×3-ish toy pattern
  from a 15-word fixture where exactly one solution exists — assert that
  solution; unsolvable fixture returns `None` quickly; determinism — same
  seed twice → identical assignment, two seeds → different (on the real
  wordlist + one real pattern).

### M3.3 Solvability sweep test
- Test per PLAN §8: 10 fixed seeds (`"sweep-0"`…`"sweep-9"`), each must fill
  via the pattern-fallback chain on the real wordlist, each < 5s. Mark it
  `@pytest.mark.slow` but keep it in the default run.
- **Accept**: sweep green. If any seed fails, fix by tuning wordlist gaps or
  budget — do not delete the test.

---

## M4 — Generation pipeline & CLI

### M4.1 `generate.py` orchestration
- Per PLAN §4.4–4.5 and §5: seed default = UTC `YYYY-MM-DD`; RNG seeded once;
  shuffle patterns; first fill wins; assign clues (seeded choice among the
  word's clues); build `Puzzle`; write `puzzles/<id>.json`; print preview via
  `render.py` (respect `--quiet`); `--force` overwrite guard; exit 2 with
  seed-naming message if all patterns fail.
- **Tests** (`tests/test_generate.py`): end-to-end into `tmp_path` — file
  exists, schema-valid (validate every field type + grid/entries consistency:
  each entry's answer matches the grid letters at its cells), determinism
  (two runs, same seed → identical minus `generatedAt`), overwrite refused
  without `--force`, `--size 7` rejected with the stretch-goal message.
- **Accept**: `python -m gridlock generate --seed 2026-08-19` produces a
  playable-looking preview and a valid file.

---

## M5 — Browser player

### M5.1 Pure logic (`web/player-core.js`)
- Implement every export in PLAN §6 bullet 1 against the puzzle JSON format
  (input = solution-stripped puzzle + base64 answers). State shape:
  `{puzzle, cells, cursor:{row,col,direction}, marks, elapsedSeconds,
  completed}` — refine as needed but keep functions pure.
- Encode the interaction semantics of PLAN §6 items 1–3 (advance-to-next-
  empty, backspace rules, arrow first-press direction switch, tab slot
  cycling with wrap) as logic, not DOM behavior.
- **Tests** (`tests/player/core.test.mjs`, `node --test`): cursor movement
  across blocks and edges; typing/advance/backspace sequences on a fixture
  puzzle; check/reveal on right, wrong, and empty cells; `isComplete` only
  when every white cell matches; save round-trip. Minimum 25 assertions
  across ≥ 10 test cases.

### M5.2 UI (`web/player-ui.js`, `web/player.css`, `web/page.html`)
- Implement PLAN §6 items 1–6 fully: grid via CSS grid; clue lists; mobile
  current-clue bar; toolbar (Check/Reveal menus, Clear with confirm, timer);
  `visibilitychange` pause; debounced localStorage saves keyed
  `gridlock:<id>` (PLAN §3.4); completion wave + time display; responsive
  breakpoint at 700px; `prefers-color-scheme` dark mode; system fonts;
  `page.html` uses `%%TITLE%%`, `%%PUZZLE_JSON%%`, `%%CSS%%`, `%%CORE_JS%%`,
  `%%UI_JS%%` placeholders (build inlines everything → self-contained page).
- No dependencies, no fetches at runtime (puzzle JSON is inlined).
- **Accept**: manual checklist executed against a locally generated puzzle
  (open the built page — M6.1 can be developed in parallel to view it, or
  temporarily hand-inline): every numbered interaction in PLAN §6 works;
  keyboard-only solve possible; page usable at 375px width; no console
  errors. Record the checklist results in the commit message body.

---

## M6 — Static site builder

### M6.1 `build.py`
- Per PLAN §5 `build` row: read all `puzzles/*.json`, strip solutions
  (M1.2 helper), inline into `page.html` placeholders, write
  `site/p/<id>.html`; write `site/index.html` (reverse-chron list, newest
  labeled "Today", shows each puzzle's id/date and completion-agnostic —
  index has no JS requirement); write `.gridlock-site` marker; wipe-guard
  per PLAN §5 (empty dir or marker present, else refuse with exit 1).
- Escape all interpolated text with `html.escape`; JSON inlined inside a
  `<script type="application/json">` tag (escape `</` as `<\/`).
- **Tests** (`tests/test_build.py`): build 2 generated puzzles into
  `tmp_path`; index lists both, newest first; puzzle pages contain base64
  answers but none of the plaintext solution words; wipe-guard refuses a
  dir containing an unrelated file; rebuild after adding a third puzzle
  picks it up.
- **Accept**: `generate` × 3 seeds → `build` → open `site/index.html` in a
  browser and solve one puzzle end to end. v1 complete.

---

## M7 — OPTIONAL stretch: daily automation (see PLAN §9 item 4 before starting)

### M7.1 CI workflow (repo root: `.github/workflows/gridlock-ci.yml`)
- On push/PR **filtered to `paths: ["gridlock/**"]`**, with
  `defaults.run.working-directory: gridlock` (this repo hosts a sister
  project; keep workflows per-project so a future repo split is trivial):
  set up Python 3.11 + Node 18/20, `pip install -e ".[dev]"`, run `pytest`
  and `node --test tests/player/*.test.mjs` (the explicit glob, not a bare
  directory — see the PLAN.md 7 note on this).

### M7.2 Daily Pages deploy
- **Resolved (binding), superseding the "deploy `site/` directly" option
  below**: this repo hosts both sister projects, and GitHub serves ONE Pages
  site per repo, so there is exactly one deploy workflow for both:
  `.github/workflows/daily-deploy.yml` (repo root, not `gridlock-daily.yml`
  — that per-project name was retired once Cellblock's M7 landed).
  It generates *and commits* both projects' daily puzzles in the same run
  (`gridlock/puzzles/<id>.json` and `cellblock/puzzles/<id>.json` — both
  gitignore entries were removed so the archives accumulate), builds both
  `site/` directories, then assembles ONE combined artifact: the root
  `index.html` landing page plus each project's `site/` copied under
  `gridlock/` and `cellblock/`. Never split this back into two independent
  deploy jobs — they would silently clobber each other's Pages deployment.
  Cron `10 0 * * *` + manual dispatch; the commit step is guarded against
  no-op days (`--force` never used; Cellblock's gallery import is also
  guarded — see `cellblock/TASKS.md` M7.2 — so it doesn't churn out a
  spurious commit every day from nothing but a changed timestamp).
- **Accept**: workflow files lint clean (`actionlint`); root README gains a
  short "enable Pages" section documenting the one manual step (Settings →
  Pages → GitHub Actions source). Verified end-to-end with Playwright:
  landing page → Gridlock card → puzzle loads; landing page → Cellblock
  card → puzzle loads; zero console errors.
- *(Original plan, if this project ever splits out of the monorepo:*
  *a standalone `gridlock-daily.yml` deploying `site/` directly with*
  *`actions/deploy-pages` — straightforward to recreate from this file's*
  *git history if needed.)*

---

## Task-order dependencies at a glance

M0 → M1 → M2 → M3 → M4 → M6 depend linearly; M5.1 needs only M1.2's schema
(can start after M1), M5.2 needs M5.1; M6 needs M4 + M5.2; M7 needs M6.
