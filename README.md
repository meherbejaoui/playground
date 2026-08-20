# Puzzle Factories — Gridlock & Cellblock

Two sister projects that each turn one command into a daily browser puzzle,
with zero servers, zero accounts, and zero paid APIs. Same design philosophy,
completely independent codebases, deployed together as one small site.

| | [`gridlock/`](gridlock/) | [`cellblock/`](cellblock/) |
|---|---|---|
| Puzzle | Mini crossword (5×5, NYT-Mini style) | Nonogram / picross (10×10 daily + pixel-art gallery) |
| The hard problem | *Filling* the grid: constraint-satisfaction backtracking over a curated wordlist | *Certifying* the grid: a line-solver proves every puzzle is solvable by pure logic, no guessing |
| Curated data | 2,564-word clued wordlist (TSV) | 12 hand-drawn ASCII pixel arts |
| Status | v1 + optional M7 automation complete — see `gridlock/TASKS.md` | v1 + optional M7 automation complete — see `cellblock/TASKS.md` |

Shared architecture, implemented twice on purpose:

```
curated plain-text data → Python-stdlib generator (deterministic, seeded by
today's date) → puzzle JSON → static site builder → vanilla-JS player page
```

Each project directory is fully self-contained (own `pyproject.toml`, `src/`,
`data/`, `web/`, `tests/`; **no shared code, no cross-directory imports**) and
carries its own `README.md` (pitch), `PLAN.md` (architecture, data model,
algorithms, flagged assumptions & open questions), and `TASKS.md` (ordered
milestones with acceptance criteria for the implementing agent).

## The live site

[`index.html`](index.html) at the repo root is a small landing page with two
cards linking to `/gridlock/` and `/cellblock/`. It's what
`.github/workflows/daily-deploy.yml` publishes as the GitHub Pages root once
Pages is enabled (`Settings → Pages → Build and deployment → Source: GitHub
Actions` — the one manual step no workflow can do for you). Each project's
own README documents what that workflow does for it specifically.

## Monorepo notes

- **One GitHub Pages site per repo, one shared deploy workflow.** Both
  projects publish from this repo, and GitHub only serves one Pages site per
  repo — so there is exactly one deploy workflow
  (`.github/workflows/daily-deploy.yml`), not two competing ones. It
  generates and commits both projects' daily puzzles, builds both sites, and
  assembles them under the root landing page in a single artifact. CI stays
  split (`gridlock-ci.yml`, `cellblock-ci.yml`) since test runs don't share
  that one-per-repo constraint — only the Pages deploy does.
- **Splitting later is still a first-class option.** Moving either project
  to its own repository is a single `git mv`; nothing in `src/`, `web/`, or
  `tests/` references across the project boundary. The one piece that isn't
  a plain copy is the deploy workflow — pulled apart, each project would get
  back the simple standalone version (generate → commit → build → deploy its
  own `site/` directly) that `daily-deploy.yml` currently does jointly; each
  project's `TASKS.md` M7.2 keeps a note on what that looked like.

## Repo layout

```
.
├── index.html                        # landing page (see "The live site")
├── .github/workflows/
│   ├── gridlock-ci.yml               # Gridlock tests, per-project
│   ├── cellblock-ci.yml              # Cellblock tests, per-project
│   └── daily-deploy.yml              # shared: both projects, one Pages site
├── gridlock/                         # self-contained, see gridlock/README.md
└── cellblock/                        # self-contained, see cellblock/README.md
```
