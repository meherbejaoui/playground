# Puzzle Factories — Gridlock & Cellblock

Two sister projects that each turn one command into a daily browser puzzle,
with zero servers, zero accounts, and zero paid APIs. Same design philosophy,
completely independent codebases.

| | [`gridlock/`](gridlock/) | [`cellblock/`](cellblock/) |
|---|---|---|
| Puzzle | Mini crossword (5×5, NYT-Mini style) | Nonogram / picross (10×10 daily + pixel-art gallery) |
| The hard problem | *Filling* the grid: constraint-satisfaction backtracking over a curated wordlist | *Certifying* the grid: a line-solver proves every puzzle is solvable by pure logic, no guessing |
| Curated data | ~1,500-word clued wordlist (TSV) | ~12 hand-drawn ASCII pixel arts |
| Status | Planned — see `gridlock/TASKS.md` | Planned — see `cellblock/TASKS.md` |

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

## Monorepo notes

- **Splitting later is a first-class option.** Moving either project to its
  own repository is a single `git mv` (plus relocating its workflow files if
  the optional M7 automation milestone was built). Nothing else references
  across the boundary.
- **Workflows** (optional M7 in each project) live at the repo root under
  `.github/workflows/<project>-*.yml`, path-filtered per project.
- **One GitHub Pages site per repo**: if both projects' daily-deploy
  milestones are enabled while they still share this repo, they must publish
  a single combined artifact (root index linking `gridlock/` and
  `cellblock/` subdirectories) — both TASKS files spell this out in M7.

## Suggested build order

Either project stands alone. If building both: **Gridlock first** (its plan
predates and calibrated the shared conventions), then Cellblock — by then the
generator/builder/player rhythm is familiar and only the solver is new.
