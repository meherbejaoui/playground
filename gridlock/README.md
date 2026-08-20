# Gridlock — a daily mini-crossword factory

Gridlock is a self-contained crossword machine. One command generates a fresh,
solvable 5×5 mini crossword (NYT-Mini style); another command builds a static
website where you — or anyone you send the link to — can solve it in the
browser with full keyboard navigation, check/reveal, a timer, and saved
progress. No server, no accounts, no APIs, no build step for the frontend.

```
$ python -m gridlock generate --seed 2026-08-19
Filled pattern "pinwheel-4" in 0.31s (2,141 backtracks)

  S C R A P
  H O A X #
  A L B U M
  # O N C E
  M A G M A

Wrote puzzles/2026-08-19-5.json

$ python -m gridlock build
Wrote site/ (1 puzzle, index + player)
```

Open `site/index.html` and play.

## Why this is worth building

- **Daily puzzles are one of the most-loved genres of software** (Wordle, the
  NYT Mini, Connections), yet almost nobody self-hosts one, because the hard
  part — generating a *good, solvable, fully-interlocked* grid — is
  algorithmically non-trivial. Gridlock packages that hard part into a small,
  legible codebase.
- **Deterministic by date.** The seed defaults to today's date, so everyone
  running the same version gets the same "today's puzzle" — a shared daily
  ritual you can host on GitHub Pages for your team, family, or group chat,
  for free, forever.
- **The core is a real algorithm, not glue code.** Grid filling is constraint
  satisfaction with backtracking, a most-constrained-first heuristic, and a
  precomputed letter-position index. It's the kind of engine that's satisfying
  to build, test, and tune.
- **Everything is inspectable plain text.** Puzzles are JSON, the wordlist is
  a TSV you can edit with any editor, and the player is one HTML file with
  vanilla JS. Want a themed puzzle for a birthday? Add ten themed words to the
  wordlist and generate with a custom seed.

## Who it's for

- People who want a private daily crossword for a small group (Slack channel,
  family, classroom) without depending on a puzzle site.
- Anyone who wants to hand-craft themed puzzles (weddings, onboarding docs,
  newsletters) without learning professional construction software.
- Developers who want a clean reference implementation of crossword filling.

## What v1 delivers

- `gridlock generate` — deterministic 5×5 puzzle generation from a bundled,
  curated wordlist and a set of symmetric block patterns; outputs puzzle JSON
  and a terminal preview.
- `gridlock build` — assembles a static site: an archive index plus one
  self-contained player page per puzzle.
- A polished browser player: click/arrow/tab navigation, across–down toggle,
  check letter/word/puzzle, reveal, timer, progress saved in `localStorage`,
  mobile-friendly layout, dark mode.
- `gridlock validate-words` — lints the wordlist so contributions stay clean.
- A test suite proving generation is solvable, deterministic, and fast.

Out of scope for v1 (deliberately): multiplayer, accounts, puzzle difficulty
ratings, sizes beyond 5×5 (7×7 is a flagged stretch goal), and any
LLM-generated clues — clues live in the curated wordlist.

## Directions considered and rejected

An RSS-to-"daily front page" generator (useful but mostly plumbing), a git
history time-lapse visualizer (pretty but low utility), and a typing trainer
fed by your own diffs (fun, thin core). The crossword factory won because it
combines a meaty algorithm, a genuinely delightful artifact, and a scope that
lands in a few focused sessions.

## Project map

Gridlock lives in the `gridlock/` directory of a two-project repo (its sister
is Cellblock, a nonogram factory — see the root `README.md`). The directory is
fully self-contained — own `pyproject.toml`, sources, data, tests; no imports
from outside it — so it can be split into its own repository with a single
`git mv` at any time.

- `PLAN.md` — architecture, data model, algorithm design, stack rationale,
  folder structure, and **assumptions & open questions** (flagged at the end).
- `TASKS.md` — ordered, self-sufficient task breakdown for the implementing
  agent: 7 milestones, each task with files-to-touch and acceptance criteria.

## Tech stack (details in PLAN.md)

- Generator/CLI: **Python 3.11+, stdlib only** (pytest as the sole dev
  dependency).
- Player: **vanilla HTML/CSS/JS (ES modules)** — no framework, no bundler.
- Hosting: any static host; an optional GitHub Actions + Pages workflow ships
  as the final stretch milestone.

## Daily automation (optional, M7)

Two workflows live at the repo root under `.github/workflows/`:

- **`gridlock-ci.yml`** — runs `pytest` and the player-core `node --test`
  suite on every push/PR touching `gridlock/`.
- **`gridlock-daily.yml`** — on a daily cron (and via manual dispatch),
  generates today's puzzle if it doesn't already exist, commits it to
  `gridlock/puzzles/` (which is *not* gitignored — the archive is meant to
  accumulate in the repo), rebuilds the site, and deploys it to GitHub
  Pages.

**The one manual step this repo can't do for you:** GitHub Pages needs to be
enabled once, from the web UI — `Settings → Pages → Build and deployment →
Source: GitHub Actions`. Nothing else is required; the workflow handles
generation, the git commit, the build, and the deploy on its own from then
on. Skip both workflow files entirely (or just `gridlock-daily.yml`) if you
don't want the repo to self-update.
