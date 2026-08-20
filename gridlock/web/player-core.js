/**
 * Pure puzzle-solving logic for the Gridlock player (PLAN.md 6).
 *
 * No DOM, no globals, no timers — every function takes a state object and
 * returns a new one. player-ui.js is the only module that touches the page;
 * this one is unit-testable with `node --test` alone.
 *
 * State shape:
 *   {
 *     puzzle,            // decoded puzzle, see decodePuzzle()
 *     cells,              // string[size]: '#' block, '.' empty, else a letter
 *     cursor: {row, col, direction},  // direction: 'across' | 'down'
 *     wrong,              // Set<"row,col"> of cells currently marked wrong
 *     revealed,           // Set<"row,col"> of cells the player revealed
 *     elapsedSeconds,
 *     completed,
 *   }
 */

const ACROSS = "across";
const DOWN = "down";

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

function entryCells(entry) {
  const cells = [];
  for (let i = 0; i < entry.length; i++) {
    cells.push(
      entry.direction === ACROSS ? [entry.row, entry.col + i] : [entry.row + i, entry.col]
    );
  }
  return cells;
}

function decodeBase64(text) {
  return atob(text);
}

/**
 * Parse a served puzzle payload (JSON string or already-parsed object) into
 * the denormalized shape the rest of this module works with: a block mask,
 * a fully decoded solution grid, per-cell slot lookups, and entries carrying
 * their own cell lists.
 */
export function decodePuzzle(raw) {
  const puzzle = typeof raw === "string" ? JSON.parse(raw) : raw;
  const size = puzzle.size;

  const blockMask = puzzle.grid.map((row) =>
    row.split("").map((char) => char === "#")
  );

  const entries = puzzle.entries.map((entry) => {
    const answer = decodeBase64(entry.answer);
    const decorated = {
      number: entry.number,
      direction: entry.direction,
      row: entry.row,
      col: entry.col,
      length: entry.length,
      clue: entry.clue,
      answer,
    };
    decorated.cells = entryCells(decorated);
    return decorated;
  });

  const solution = Array.from({ length: size }, () => Array(size).fill(null));
  const cellSlots = Array.from({ length: size }, () =>
    Array.from({ length: size }, () => ({ across: null, down: null }))
  );

  entries.forEach((entry, index) => {
    entry.cells.forEach(([row, col], position) => {
      solution[row][col] = entry.answer[position];
      cellSlots[row][col][entry.direction] = index;
    });
  });

  return { id: puzzle.id, size, blockMask, numbers: puzzle.numbers, solution, cellSlots, entries };
}

function isBlock(puzzle, row, col) {
  return puzzle.blockMask[row][col];
}

function allWhiteCells(puzzle) {
  const cells = [];
  for (let row = 0; row < puzzle.size; row++) {
    for (let col = 0; col < puzzle.size; col++) {
      if (!isBlock(puzzle, row, col)) cells.push([row, col]);
    }
  }
  return cells;
}

function defaultCursor(puzzle) {
  const first = puzzle.entries[0];
  return { row: first.row, col: first.col, direction: first.direction };
}

/** A fresh, empty solving state for a decoded puzzle. */
export function createInitialState(puzzle) {
  const cells = puzzle.blockMask.map((row) =>
    row.map((blocked) => (blocked ? "#" : ".")).join("")
  );
  return {
    puzzle,
    cells,
    cursor: defaultCursor(puzzle),
    wrong: new Set(),
    revealed: new Set(),
    elapsedSeconds: 0,
    completed: false,
  };
}

/** The entry (with its `.cells` list) that the cursor currently sits in. */
export function currentSlot(state) {
  const { row, col, direction } = state.cursor;
  const index = state.puzzle.cellSlots[row][col][direction];
  return state.puzzle.entries[index];
}

/** Flip across <-> down at the current cursor cell. */
export function toggleDirection(state) {
  return {
    ...state,
    cursor: { ...state.cursor, direction: state.cursor.direction === ACROSS ? DOWN : ACROSS },
  };
}

/**
 * Click-to-select (PLAN.md 6.1): selecting the already-selected cell toggles
 * direction; selecting a block is a no-op.
 */
export function selectCell(state, row, col) {
  if (isBlock(state.puzzle, row, col)) return state;
  if (state.cursor.row === row && state.cursor.col === col) {
    return toggleDirection(state);
  }
  return { ...state, cursor: { row, col, direction: state.cursor.direction } };
}

function findNextWhite(puzzle, row, col, deltaRow, deltaCol) {
  let r = row + deltaRow;
  let c = col + deltaCol;
  while (r >= 0 && r < puzzle.size && c >= 0 && c < puzzle.size) {
    if (!isBlock(puzzle, r, c)) return [r, c];
    r += deltaRow;
    c += deltaCol;
  }
  return null;
}

const ARROW_DELTAS = {
  ArrowUp: [-1, 0],
  ArrowDown: [1, 0],
  ArrowLeft: [0, -1],
  ArrowRight: [0, 1],
};

/**
 * Arrow-key navigation (PLAN.md 6.3): movement skips over blocks to the next
 * white cell; if the arrow's axis differs from the current direction, the
 * first press only switches direction and does not move.
 */
export function moveCursor(state, key) {
  const delta = ARROW_DELTAS[key];
  if (!delta) return state;

  const axis = key === "ArrowLeft" || key === "ArrowRight" ? ACROSS : DOWN;
  if (axis !== state.cursor.direction) {
    return { ...state, cursor: { ...state.cursor, direction: axis } };
  }

  const next = findNextWhite(state.puzzle, state.cursor.row, state.cursor.col, delta[0], delta[1]);
  if (!next) return state;
  return { ...state, cursor: { ...state.cursor, row: next[0], col: next[1] } };
}

/**
 * Tab / Shift-Tab (PLAN.md 6.3): jump to the next (delta=1) or previous
 * (delta=-1) slot's first empty cell, wrapping across <-> down. Because
 * `puzzle.entries` already interleaves across and down in reading order,
 * wrapping past either end naturally crosses directions.
 */
export function nextSlot(state, delta = 1) {
  const entries = state.puzzle.entries;
  const count = entries.length;
  const { row, col, direction } = state.cursor;
  const currentIndex = state.puzzle.cellSlots[row][col][direction];
  const targetIndex = ((currentIndex + delta) % count + count) % count;
  const target = entries[targetIndex];

  const firstEmpty = target.cells.find(([r, c]) => state.cells[r][c] === ".");
  const [targetRow, targetCol] = firstEmpty || target.cells[0];
  return { ...state, cursor: { row: targetRow, col: targetCol, direction: target.direction } };
}

function isComplete(state) {
  return allWhiteCells(state.puzzle).every(
    ([row, col]) => state.cells[row][col] === state.puzzle.solution[row][col]
  );
}

/** Whether the puzzle is complete and the player never used Reveal. */
export function solvedWithoutHelp(state) {
  return isComplete(state) && state.revealed.size === 0;
}

function withCompletion(state) {
  return { ...state, completed: isComplete(state) };
}

function advanceWithinSlot(slot, cells, row, col) {
  const index = slot.cells.findIndex(([r, c]) => r === row && c === col);
  for (let i = index + 1; i < slot.cells.length; i++) {
    const [r, c] = slot.cells[i];
    if (cells[r][c] === ".") return [r, c];
  }
  return slot.cells[slot.cells.length - 1];
}

/**
 * Type one letter into the current cell (PLAN.md 6.2): fills the cell,
 * clears any wrong/revealed marker on it (an edit invalidates both), then
 * advances to the next empty cell in the slot, stopping at the slot's last
 * cell if every remaining cell is already filled.
 */
export function typeLetter(state, letter) {
  const char = String(letter).toUpperCase();
  if (!/^[A-Z]$/.test(char)) return state;

  const { row, col } = state.cursor;
  if (isBlock(state.puzzle, row, col)) return state;

  const key = cellKey(row, col);
  const cells = setCell(state.cells, row, col, char);
  const slot = currentSlot(state);
  const [nextRow, nextCol] = advanceWithinSlot(slot, cells, row, col);

  return withCompletion({
    ...state,
    cells,
    wrong: withoutKey(state.wrong, key),
    revealed: withoutKey(state.revealed, key),
    cursor: { ...state.cursor, row: nextRow, col: nextCol },
  });
}

/**
 * Backspace (PLAN.md 6.2): clears the current cell if it holds a letter and
 * stays put; if the current cell is already empty, steps back one cell
 * within the slot and clears that one instead.
 */
export function backspace(state) {
  const { row, col } = state.cursor;
  if (isBlock(state.puzzle, row, col)) return state;

  const key = cellKey(row, col);
  if (state.cells[row][col] !== ".") {
    return withCompletion({
      ...state,
      cells: setCell(state.cells, row, col, "."),
      wrong: withoutKey(state.wrong, key),
      revealed: withoutKey(state.revealed, key),
    });
  }

  const slot = currentSlot(state);
  const index = slot.cells.findIndex(([r, c]) => r === row && c === col);
  if (index <= 0) return state;

  const [prevRow, prevCol] = slot.cells[index - 1];
  const prevKey = cellKey(prevRow, prevCol);
  return withCompletion({
    ...state,
    cells: setCell(state.cells, prevRow, prevCol, "."),
    wrong: withoutKey(state.wrong, prevKey),
    revealed: withoutKey(state.revealed, prevKey),
    cursor: { ...state.cursor, row: prevRow, col: prevCol },
  });
}

function checkCells(state, cells) {
  let wrong = state.wrong;
  for (const [row, col] of cells) {
    const key = cellKey(row, col);
    const letter = state.cells[row][col];
    if (letter !== "." && letter !== "#") {
      wrong = letter !== state.puzzle.solution[row][col] ? withKey(wrong, key) : withoutKey(wrong, key);
    } else {
      wrong = withoutKey(wrong, key);
    }
  }
  return { ...state, wrong };
}

/** Mark the current cell wrong iff it is filled and incorrect. */
export function checkCell(state) {
  return checkCells(state, [[state.cursor.row, state.cursor.col]]);
}

/** Mark every filled-and-incorrect cell in the current slot. */
export function checkWord(state) {
  return checkCells(state, currentSlot(state).cells);
}

/** Mark every filled-and-incorrect cell in the whole grid. */
export function checkAll(state) {
  return checkCells(state, allWhiteCells(state.puzzle));
}

function revealCells(state, cells) {
  let gridCells = state.cells;
  let wrong = state.wrong;
  let revealed = state.revealed;
  for (const [row, col] of cells) {
    const key = cellKey(row, col);
    gridCells = setCell(gridCells, row, col, state.puzzle.solution[row][col]);
    wrong = withoutKey(wrong, key);
    revealed = withKey(revealed, key);
  }
  return withCompletion({ ...state, cells: gridCells, wrong, revealed });
}

/** Fill in the correct letter for the current cell and mark it revealed. */
export function revealCell(state) {
  return revealCells(state, [[state.cursor.row, state.cursor.col]]);
}

/** Fill in the correct letters for the current slot and mark them revealed. */
export function revealWord(state) {
  return revealCells(state, currentSlot(state).cells);
}

/** Fill in the entire solution and mark every cell revealed. */
export function revealAll(state) {
  return revealCells(state, allWhiteCells(state.puzzle));
}

/** Erase every entered letter and its wrong/revealed marks; keeps the timer running. */
export function clearAll(state) {
  const cells = state.puzzle.blockMask.map((row) =>
    row.map((blocked) => (blocked ? "#" : ".")).join("")
  );
  return withCompletion({ ...state, cells, wrong: new Set(), revealed: new Set() });
}

export { isComplete };

/** Serialize the parts of state worth persisting (PLAN.md 3.4). */
export function serializeSave(state) {
  return {
    cells: state.cells.slice(),
    wrong: Array.from(state.wrong).sort(),
    revealed: Array.from(state.revealed).sort(),
    elapsedSeconds: state.elapsedSeconds,
    completed: state.completed,
  };
}

/** Rebuild a state from a decoded puzzle plus a previously serialized save. */
export function restoreSave(puzzle, saved) {
  return {
    puzzle,
    cells: saved.cells.slice(),
    cursor: defaultCursor(puzzle),
    wrong: new Set(saved.wrong || []),
    revealed: new Set(saved.revealed || []),
    elapsedSeconds: saved.elapsedSeconds || 0,
    completed: !!saved.completed,
  };
}
