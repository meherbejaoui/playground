/**
 * Pure puzzle-solving logic for the Cellblock player (PLAN.md 6).
 *
 * No DOM, no globals, no timers — every function takes a state object and
 * returns a new one. player-ui.js is the only module that touches the page;
 * this one is unit-testable with `node --test` alone.
 *
 * State shape:
 *   {
 *     puzzle,            // decoded puzzle, see decodePuzzle()
 *     cells,              // string[rows]: '.' unknown, '1' filled, 'x' marked-empty
 *     cursor: {row, col},
 *     activeTool,         // 'fill' | 'mark' — which tool a plain click/tap applies
 *     wrong,              // Set<"row,col"> of cells currently marked wrong
 *     revealed,           // Set<"row,col"> of cells the player revealed
 *     elapsedSeconds,
 *     completed,
 *   }
 */

const FILL = "1";
const MARK = "x";
const UNKNOWN = ".";

function cellKey(row, col) {
  return `${row},${col}`;
}

function withKey(set, key) {
  const next = new Set(set);
  next.add(key);
  return next;
}

function withoutKey(set, key) {
  if (!set.has(key)) return set;
  const next = new Set(set);
  next.delete(key);
  return next;
}

function setCell(cells, row, col, char) {
  const line = cells[row];
  const nextLine = line.slice(0, col) + char + line.slice(col + 1);
  if (nextLine === line) return cells;
  const next = cells.slice();
  next[row] = nextLine;
  return next;
}

function allCells(puzzle) {
  const cells = [];
  for (let row = 0; row < puzzle.rows; row++) {
    for (let col = 0; col < puzzle.cols; col++) cells.push([row, col]);
  }
  return cells;
}

function decodeBase64ToBytes(base64) {
  const binary = atob(base64);
  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i);
  return bytes;
}

/**
 * Unpack a base64 solution into a boolean[rows][cols] grid. Must exactly
 * mirror the Python side's pack_solution (row-major, each row padded to a
 * whole number of bytes, MSB-first within a byte) — verified against the
 * shared known-answer vector in tests/fixtures/packing.json.
 */
export function unpackSolution(base64, rows, cols) {
  const bytesPerRow = Math.ceil(cols / 8);
  const data = decodeBase64ToBytes(base64);
  const grid = [];
  for (let r = 0; r < rows; r++) {
    const row = [];
    for (let c = 0; c < cols; c++) {
      const byteIndex = r * bytesPerRow + Math.floor(c / 8);
      const bitIndex = 7 - (c % 8);
      row.push(((data[byteIndex] >> bitIndex) & 1) === 1);
    }
    grid.push(row);
  }
  return grid;
}

/** Parse a served puzzle payload (JSON string or already-parsed object). */
export function decodePuzzle(raw) {
  const puzzle = typeof raw === "string" ? JSON.parse(raw) : raw;
  return {
    id: puzzle.id,
    kind: puzzle.kind,
    title: puzzle.title,
    rows: puzzle.rows,
    cols: puzzle.cols,
    rowClues: puzzle.rowClues,
    colClues: puzzle.colClues,
    solution: unpackSolution(puzzle.solution, puzzle.rows, puzzle.cols),
    difficulty: puzzle.difficulty,
  };
}

/** A fresh, empty solving state for a decoded puzzle. */
export function createInitialState(puzzle) {
  const cells = Array.from({ length: puzzle.rows }, () => UNKNOWN.repeat(puzzle.cols));
  return {
    puzzle,
    cells,
    cursor: { row: 0, col: 0 },
    activeTool: "fill",
    wrong: new Set(),
    revealed: new Set(),
    elapsedSeconds: 0,
    completed: false,
  };
}

function isComplete(state) {
  for (let row = 0; row < state.puzzle.rows; row++) {
    for (let col = 0; col < state.puzzle.cols; col++) {
      const filled = state.cells[row][col] === FILL;
      if (filled !== state.puzzle.solution[row][col]) return false;
    }
  }
  return true;
}

function withCompletion(state) {
  return { ...state, completed: isComplete(state) };
}

/** Switch which tool a plain click/tap applies. */
export function setActiveTool(state, tool) {
  return { ...state, activeTool: tool };
}

/**
 * Arrow-key cursor movement (PLAN.md 6.3). Nonogram grids have no blocks to
 * skip, so this is a simple clamp-at-the-edge move.
 */
export function moveCursor(state, key) {
  const deltas = {
    ArrowUp: [-1, 0],
    ArrowDown: [1, 0],
    ArrowLeft: [0, -1],
    ArrowRight: [0, 1],
  };
  const delta = deltas[key];
  if (!delta) return state;
  const row = Math.min(Math.max(state.cursor.row + delta[0], 0), state.puzzle.rows - 1);
  const col = Math.min(Math.max(state.cursor.col + delta[1], 0), state.puzzle.cols - 1);
  return { ...state, cursor: { row, col } };
}

/**
 * Click-to-toggle (PLAN.md 6.2): applying a tool to a cell that already
 * holds that tool's value clears it back to unknown; otherwise it overwrites
 * whatever was there (a fill can replace a mark and vice versa).
 */
export function applyTool(state, row, col, tool) {
  const key = cellKey(row, col);
  const toolChar = tool === "fill" ? FILL : MARK;
  const current = state.cells[row][col];
  const next = current === toolChar ? UNKNOWN : toolChar;
  const cells = setCell(state.cells, row, col, next);
  return withCompletion({
    ...state,
    cells,
    wrong: withoutKey(state.wrong, key),
    revealed: withoutKey(state.revealed, key),
  });
}

/**
 * The value a drag stroke starting at (row, col) should paint (PLAN.md
 * 6.2): computed once from the start cell, then applied verbatim to every
 * cell the stroke crosses via paintCell — a drag never flips mid-stroke.
 */
export function dragValue(state, row, col, tool) {
  const toolChar = tool === "fill" ? FILL : MARK;
  const current = state.cells[row][col];
  return current === toolChar ? UNKNOWN : toolChar;
}

/**
 * Set one cell to a precomputed value (the drag-painting primitive; unlike
 * applyTool, this never toggles — it just applies whatever dragValue decided
 * for the whole stroke).
 */
export function paintCell(state, row, col, value) {
  const key = cellKey(row, col);
  const cells = setCell(state.cells, row, col, value);
  return withCompletion({
    ...state,
    cells,
    wrong: withoutKey(state.wrong, key),
    revealed: withoutKey(state.revealed, key),
  });
}

/**
 * Does the current fill/mark pattern in `line` exactly satisfy `clues`
 * (PLAN.md 6.4)? Unknown cells "block" certainty: a run of filled cells
 * touching an unknown cell (rather than a mark or the line's edge) has an
 * unconfirmed length, so the line cannot yet be considered satisfied. An
 * all-unknown line against an empty clue is vacuously satisfied — there is
 * nothing left to do.
 */
export function lineSatisfied(clues, line) {
  const n = line.length;
  const runs = [];
  let i = 0;
  while (i < n) {
    if (line[i] === FILL) {
      let j = i;
      while (j < n && line[j] === FILL) j++;
      const leftBlocked = i > 0 && line[i - 1] === UNKNOWN;
      const rightBlocked = j < n && line[j] === UNKNOWN;
      if (leftBlocked || rightBlocked) return false;
      runs.push(j - i);
      i = j;
    } else {
      i++;
    }
  }
  if (runs.length !== clues.length) return false;
  return runs.every((run, index) => run === clues[index]);
}

function scopeCells(state, scope) {
  return scope === "all" ? allCells(state.puzzle) : [[state.cursor.row, state.cursor.col]];
}

/**
 * Mark filled-and-wrong cells in `scope` ('cell' | 'all'). X-marks are
 * never judged (PLAN.md 6.5) — only a committed fill can be "wrong".
 */
export function checkCells(state, scope) {
  let wrong = state.wrong;
  for (const [row, col] of scopeCells(state, scope)) {
    const key = cellKey(row, col);
    const filled = state.cells[row][col] === FILL;
    if (filled) {
      wrong = state.puzzle.solution[row][col] ? withoutKey(wrong, key) : withKey(wrong, key);
    } else {
      wrong = withoutKey(wrong, key);
    }
  }
  return { ...state, wrong };
}

/**
 * Fill in the correct value for `scope` ('cell' | 'all') and mark it
 * revealed. A solution-empty cell is revealed as an explicit mark ('x')
 * rather than left unknown, so a full reveal leaves nothing ambiguous.
 */
export function reveal(state, scope) {
  let cells = state.cells;
  let wrong = state.wrong;
  let revealed = state.revealed;
  for (const [row, col] of scopeCells(state, scope)) {
    const key = cellKey(row, col);
    const value = state.puzzle.solution[row][col] ? FILL : MARK;
    cells = setCell(cells, row, col, value);
    wrong = withoutKey(wrong, key);
    revealed = withKey(revealed, key);
  }
  return withCompletion({ ...state, cells, wrong, revealed });
}

/** Erase every fill/mark and their wrong/revealed flags; keeps the timer running. */
export function clearAll(state) {
  const cells = Array.from({ length: state.puzzle.rows }, () =>
    UNKNOWN.repeat(state.puzzle.cols)
  );
  return withCompletion({ ...state, cells, wrong: new Set(), revealed: new Set() });
}

export { isComplete };

/**
 * Serialize the parts of state worth persisting (PLAN.md 3.4). `cells` is
 * flattened to one row-major string, matching the schema there exactly;
 * `wrong`/`revealed` are a deliberate addition beyond the minimal suggested
 * shape so a checked-wrong or revealed cell survives a reload too.
 */
export function serializeSave(state) {
  return {
    cells: state.cells.join(""),
    wrong: Array.from(state.wrong).sort(),
    revealed: Array.from(state.revealed).sort(),
    elapsedSeconds: state.elapsedSeconds,
    completed: state.completed,
  };
}

/** Rebuild a state from a decoded puzzle plus a previously serialized save. */
export function restoreSave(puzzle, saved) {
  const flat = typeof saved.cells === "string" ? saved.cells : UNKNOWN.repeat(puzzle.rows * puzzle.cols);
  const cells = [];
  for (let row = 0; row < puzzle.rows; row++) {
    cells.push(flat.slice(row * puzzle.cols, (row + 1) * puzzle.cols));
  }
  return {
    puzzle,
    cells,
    cursor: { row: 0, col: 0 },
    activeTool: "fill",
    wrong: new Set(saved.wrong || []),
    revealed: new Set(saved.revealed || []),
    elapsedSeconds: saved.elapsedSeconds || 0,
    completed: !!saved.completed,
  };
}
