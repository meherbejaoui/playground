import { test, describe } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

import {
  unpackSolution,
  decodePuzzle,
  createInitialState,
  setActiveTool,
  moveCursor,
  applyTool,
  dragValue,
  paintCell,
  lineSatisfied,
  checkCells,
  reveal,
  clearAll,
  isComplete,
  serializeSave,
  restoreSave,
} from "../../web/player-core.js";

const HERE = dirname(fileURLToPath(import.meta.url));
const FIXTURES = join(HERE, "..", "fixtures");

// A 3x3 X-pattern (# . # / . # . / # . #). base64 computed by the real
// Python pack_solution — see the commit introducing this file.
function makeToyPuzzle() {
  return {
    id: "toy-3x3",
    kind: "daily",
    title: null,
    rows: 3,
    cols: 3,
    rowClues: [[1, 1], [1], [1, 1]],
    colClues: [[1, 1], [1], [1, 1]],
    solution: "oECg",
    difficulty: { passes: 4, grade: "easy" },
    seed: "toy",
    generatedAt: "2026-01-01T00:00:00Z",
  };
}

function typeRow(state, row, chars) {
  let next = state;
  for (let col = 0; col < chars.length; col++) {
    const ch = chars[col];
    if (ch === "1") next = applyTool(next, row, col, "fill");
    else if (ch === "x") next = applyTool(next, row, col, "mark");
  }
  return next;
}

describe("unpackSolution / decodePuzzle against the shared known-answer vector", () => {
  const payload = JSON.parse(readFileSync(join(FIXTURES, "packing.json"), "utf8"));

  test("matches the Python-packed bitmap exactly", () => {
    const grid = unpackSolution(payload.base64, payload.rows, payload.cols);
    const expected = payload.bitmap.map((row) => [...row].map((ch) => ch === "#"));
    assert.deepEqual(grid, expected);
  });

  test("decodePuzzle wires unpackSolution through correctly", () => {
    const puzzle = decodePuzzle({
      id: "vector",
      kind: "daily",
      title: null,
      rows: payload.rows,
      cols: payload.cols,
      rowClues: [],
      colClues: [],
      solution: payload.base64,
      difficulty: { passes: 0, grade: "easy" },
    });
    assert.equal(puzzle.solution[0][0], true); // bitmap[0][0] is '#'
    assert.equal(puzzle.solution[1][0], false); // bitmap[1] is all dots
  });

  test("decodePuzzle accepts a JSON string too", () => {
    const raw = JSON.stringify({
      id: "vector-str",
      kind: "daily",
      rows: 3,
      cols: 3,
      rowClues: [[1, 1], [1], [1, 1]],
      colClues: [[1, 1], [1], [1, 1]],
      solution: "oECg",
      difficulty: { passes: 4, grade: "easy" },
    });
    assert.equal(decodePuzzle(raw).id, "vector-str");
  });
});

describe("createInitialState", () => {
  test("cells all start unknown", () => {
    const state = createInitialState(decodePuzzle(makeToyPuzzle()));
    assert.deepEqual(state.cells, ["...", "...", "..."]);
  });

  test("default cursor and tool", () => {
    const state = createInitialState(decodePuzzle(makeToyPuzzle()));
    assert.deepEqual(state.cursor, { row: 0, col: 0 });
    assert.equal(state.activeTool, "fill");
  });
});

describe("moveCursor", () => {
  test("moves within bounds", () => {
    const state = createInitialState(decodePuzzle(makeToyPuzzle()));
    const next = moveCursor(state, "ArrowRight");
    assert.deepEqual(next.cursor, { row: 0, col: 1 });
  });

  test("clamps at the grid edge instead of wrapping", () => {
    const state = createInitialState(decodePuzzle(makeToyPuzzle()));
    const next = moveCursor(state, "ArrowUp");
    assert.deepEqual(next.cursor, { row: 0, col: 0 });
  });

  test("an unrecognized key is a no-op", () => {
    const state = createInitialState(decodePuzzle(makeToyPuzzle()));
    assert.deepEqual(moveCursor(state, "Escape"), state);
  });
});

describe("applyTool (click-to-toggle)", () => {
  test("fill sets the cell, re-applying clears it", () => {
    let state = createInitialState(decodePuzzle(makeToyPuzzle()));
    state = applyTool(state, 0, 0, "fill");
    assert.equal(state.cells[0][0], "1");
    state = applyTool(state, 0, 0, "fill");
    assert.equal(state.cells[0][0], ".");
  });

  test("mark sets an x, re-applying clears it", () => {
    let state = createInitialState(decodePuzzle(makeToyPuzzle()));
    state = applyTool(state, 1, 1, "mark");
    assert.equal(state.cells[1][1], "x");
    state = applyTool(state, 1, 1, "mark");
    assert.equal(state.cells[1][1], ".");
  });

  test("fill overwrites an existing mark and vice versa", () => {
    let state = createInitialState(decodePuzzle(makeToyPuzzle()));
    state = applyTool(state, 0, 0, "mark");
    assert.equal(state.cells[0][0], "x");
    state = applyTool(state, 0, 0, "fill");
    assert.equal(state.cells[0][0], "1");
  });

  test("editing a cell clears its wrong and revealed markers", () => {
    let state = createInitialState(decodePuzzle(makeToyPuzzle()));
    state = applyTool(state, 0, 1, "fill"); // wrong: solution[0][1] is false
    state = { ...state, cursor: { row: 0, col: 1 } };
    state = checkCells(state, "cell");
    assert.ok(state.wrong.has("0,1"));
    state = applyTool(state, 0, 1, "fill"); // clear it
    assert.ok(!state.wrong.has("0,1"));
  });
});

describe("dragValue and paintCell (drag painting never flips mid-stroke)", () => {
  test("starting on an unknown cell paints the tool value", () => {
    const state = createInitialState(decodePuzzle(makeToyPuzzle()));
    assert.equal(dragValue(state, 0, 0, "fill"), "1");
  });

  test("starting on a cell already at the tool value paints clear", () => {
    let state = createInitialState(decodePuzzle(makeToyPuzzle()));
    state = applyTool(state, 0, 0, "fill");
    assert.equal(dragValue(state, 0, 0, "fill"), ".");
  });

  test("the paint value stays constant across every cell in the stroke", () => {
    let state = createInitialState(decodePuzzle(makeToyPuzzle()));
    const paint = dragValue(state, 0, 0, "fill"); // "1", computed once
    // Simulate dragging across a row that already has a mix of values;
    // paintCell must apply the SAME value everywhere, never re-toggling.
    state = applyTool(state, 0, 1, "fill"); // pre-fill a cell along the path
    for (let col = 0; col < 3; col++) {
      state = paintCell(state, 0, col, paint);
    }
    assert.equal(state.cells[0], "111");
  });

  test("paintCell also clears wrong/revealed on the touched cell", () => {
    let state = createInitialState(decodePuzzle(makeToyPuzzle()));
    state = applyTool(state, 0, 1, "fill");
    state = { ...state, cursor: { row: 0, col: 1 } };
    state = checkCells(state, "cell");
    assert.ok(state.wrong.has("0,1"));
    state = paintCell(state, 0, 1, ".");
    assert.ok(!state.wrong.has("0,1"));
  });
});

describe("lineSatisfied", () => {
  const clue = [1, 1];

  test("matches when filled runs are bounded by marks", () => {
    assert.equal(lineSatisfied(clue, ["1", "x", "1"]), true);
  });

  test("a run bounded only by the line's own edges is satisfied", () => {
    // clue [2] on a length-2 line: both ends of the run are grid edges,
    // no marks needed at all.
    assert.equal(lineSatisfied([2], ["1", "1"]), true);
  });

  test("an unknown cell touching a run blocks satisfaction", () => {
    assert.equal(lineSatisfied(clue, ["1", ".", "1"]), false);
  });

  test("wrong run pattern is not satisfied even with no unknowns", () => {
    assert.equal(lineSatisfied(clue, ["1", "1", "x"]), false); // [2] != [1,1]
  });

  test("an empty clue is satisfied by an all-unknown line", () => {
    assert.equal(lineSatisfied([], [".", ".", "."]), true);
  });

  test("an empty clue is violated by any filled cell", () => {
    assert.equal(lineSatisfied([], [".", "1", "."]), false);
  });
});

describe("checkCells", () => {
  test("marks a wrong filled cell", () => {
    let state = createInitialState(decodePuzzle(makeToyPuzzle()));
    state = applyTool(state, 0, 1, "fill"); // solution[0][1] is false
    state = { ...state, cursor: { row: 0, col: 1 } };
    state = checkCells(state, "cell");
    assert.ok(state.wrong.has("0,1"));
  });

  test("never marks a mark ('x') as wrong, even if it contradicts the solution", () => {
    let state = createInitialState(decodePuzzle(makeToyPuzzle()));
    state = applyTool(state, 0, 0, "mark"); // solution[0][0] is TRUE, marking it is "wrong" in spirit
    state = checkCells(state, "cell");
    assert.equal(state.wrong.size, 0);
  });

  test("scope 'all' checks every cell", () => {
    let state = createInitialState(decodePuzzle(makeToyPuzzle()));
    state = typeRow(state, 0, "1x1"); // (0,0)=1 correct, (0,1)=x, (0,2)=1 correct
    state = typeRow(state, 1, "111"); // all wrong except (1,1)
    state = checkCells(state, "all");
    assert.ok(state.wrong.has("1,0"));
    assert.ok(state.wrong.has("1,2"));
    assert.ok(!state.wrong.has("1,1"));
    assert.ok(!state.wrong.has("0,0"));
  });
});

describe("reveal", () => {
  test("reveal cell fills the correct value and marks it revealed", () => {
    let state = createInitialState(decodePuzzle(makeToyPuzzle()));
    state = reveal(state, "cell");
    assert.equal(state.cells[0][0], "1");
    assert.ok(state.revealed.has("0,0"));
  });

  test("reveal cell on a solution-empty cell writes an explicit mark", () => {
    let state = createInitialState(decodePuzzle(makeToyPuzzle()));
    state = { ...state, cursor: { row: 0, col: 1 } };
    state = reveal(state, "cell");
    assert.equal(state.cells[0][1], "x");
  });

  test("reveal all solves the puzzle and marks completed", () => {
    let state = createInitialState(decodePuzzle(makeToyPuzzle()));
    state = reveal(state, "all");
    assert.equal(state.cells.join(""), "1x1x1x1x1");
    assert.equal(state.completed, true);
  });

  test("revealing clears any wrong marker on that cell", () => {
    let state = createInitialState(decodePuzzle(makeToyPuzzle()));
    state = applyTool(state, 0, 1, "fill");
    state = { ...state, cursor: { row: 0, col: 1 } };
    state = checkCells(state, "cell");
    assert.ok(state.wrong.has("0,1"));
    state = reveal(state, "cell");
    assert.ok(!state.wrong.has("0,1"));
  });
});

describe("clearAll", () => {
  test("erases every cell and mark but keeps elapsed time", () => {
    let state = createInitialState(decodePuzzle(makeToyPuzzle()));
    state = typeRow(state, 0, "1x1");
    state = checkCells(state, "all");
    state = { ...state, elapsedSeconds: 42 };
    state = clearAll(state);
    assert.equal(state.cells.join(""), ".........");
    assert.equal(state.wrong.size, 0);
    assert.equal(state.elapsedSeconds, 42);
    assert.equal(state.completed, false);
  });
});

describe("isComplete: X-marks and blanks are equivalent as 'not filled'", () => {
  test("false while any filled cell is wrong or missing", () => {
    const state = createInitialState(decodePuzzle(makeToyPuzzle()));
    assert.equal(isComplete(state), false);
  });

  test("true once every filled cell matches, regardless of mark-vs-blank elsewhere", () => {
    let state = createInitialState(decodePuzzle(makeToyPuzzle()));
    state = typeRow(state, 0, "1.1"); // leave (0,1) blank rather than marked
    state = typeRow(state, 1, ".1."); // leave both empties blank
    state = typeRow(state, 2, "1x1"); // mark the one empty cell here instead
    assert.equal(isComplete(state), true);
  });

  test("applyTool keeps state.completed in sync", () => {
    let state = createInitialState(decodePuzzle(makeToyPuzzle()));
    state = typeRow(state, 0, "1.1");
    state = typeRow(state, 1, ".1.");
    state = typeRow(state, 2, "1.1");
    assert.equal(state.completed, true);
  });
});

describe("save round trip", () => {
  test("serialize then restore reproduces cells, marks, and progress", () => {
    const puzzle = decodePuzzle(makeToyPuzzle());
    let state = createInitialState(puzzle);
    state = typeRow(state, 0, "1x1");
    state = checkCells(state, "all");
    state = { ...state, elapsedSeconds: 77 };

    const saved = serializeSave(state);
    assert.equal(saved.cells, "1x1......");
    const restored = restoreSave(puzzle, saved);

    assert.deepEqual(restored.cells, state.cells);
    assert.deepEqual(Array.from(restored.wrong).sort(), Array.from(state.wrong).sort());
    assert.equal(restored.elapsedSeconds, 77);
    assert.equal(restored.completed, state.completed);
  });

  test("restoring with no saved cells yields an all-unknown grid", () => {
    const puzzle = decodePuzzle(makeToyPuzzle());
    const restored = restoreSave(puzzle, {});
    assert.deepEqual(restored.cells, ["...", "...", "..."]);
    assert.equal(restored.elapsedSeconds, 0);
    assert.equal(restored.completed, false);
  });

  test("a fully revealed save round-trips as complete", () => {
    const puzzle = decodePuzzle(makeToyPuzzle());
    let state = createInitialState(puzzle);
    state = reveal(state, "all");
    const restored = restoreSave(puzzle, serializeSave(state));
    assert.equal(isComplete(restored), true);
    assert.equal(restored.completed, true);
  });
});

describe("setActiveTool", () => {
  test("switches the active tool", () => {
    const state = createInitialState(decodePuzzle(makeToyPuzzle()));
    assert.equal(setActiveTool(state, "mark").activeTool, "mark");
  });
});
