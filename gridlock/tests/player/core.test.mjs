import { test, describe } from "node:test";
import assert from "node:assert/strict";

import {
  decodePuzzle,
  createInitialState,
  selectCell,
  toggleDirection,
  moveCursor,
  nextSlot,
  typeLetter,
  backspace,
  checkCell,
  checkWord,
  checkAll,
  revealCell,
  revealWord,
  revealAll,
  isComplete,
  solvedWithoutHelp,
  serializeSave,
  restoreSave,
  currentSlot,
} from "../../web/player-core.js";

// A 3x3 open grid (no blocks), reused from the Python fill-engine tests:
// across BAT/ORE/WED, down BOW/ARE/TED.
function makeToyPuzzle() {
  return {
    id: "toy-3",
    size: 3,
    grid: ["...", "...", "..."],
    entries: [
      { number: 1, direction: "across", row: 0, col: 0, length: 3, answer: btoa("BAT"), clue: "Club" },
      { number: 1, direction: "down", row: 0, col: 0, length: 3, answer: btoa("BOW"), clue: "Bend" },
      { number: 2, direction: "down", row: 0, col: 1, length: 3, answer: btoa("ARE"), clue: "Exist" },
      { number: 3, direction: "down", row: 0, col: 2, length: 3, answer: btoa("TED"), clue: "Hay spreader" },
      { number: 4, direction: "across", row: 1, col: 0, length: 3, answer: btoa("ORE"), clue: "Rock" },
      { number: 5, direction: "across", row: 2, col: 0, length: 3, answer: btoa("WED"), clue: "Marry" },
    ],
  };
}

// The 5x5 fixture generated in tests/fixtures/sample-5.json:
//   #CHEF / CLONE / ROUTE / ASSET / BEER#
function makeBlockedPuzzle() {
  const words = {
    CHEF: "Kitchen boss",
    CLOSE: "Nearby",
    HOUSE: "Family dwelling",
    ENTER: "Go inside",
    FEET: "Ankle attachments",
    CLONE: "Exact copy",
    CRAB: "Sideways scuttler",
    ROUTE: "Path from A to B",
    ASSET: "Valuable holding",
    BEER: "Brewery product",
  };
  const entry = (number, direction, row, col, length, word) => ({
    number,
    direction,
    row,
    col,
    length,
    answer: btoa(word),
    clue: words[word],
  });
  return {
    id: "sample-fixture-5",
    size: 5,
    grid: ["#....", ".....", ".....", ".....", "....#"],
    entries: [
      entry(1, "across", 0, 1, 4, "CHEF"),
      entry(1, "down", 0, 1, 5, "CLOSE"),
      entry(2, "down", 0, 2, 5, "HOUSE"),
      entry(3, "down", 0, 3, 5, "ENTER"),
      entry(4, "down", 0, 4, 4, "FEET"),
      entry(5, "across", 1, 0, 5, "CLONE"),
      entry(5, "down", 1, 0, 4, "CRAB"),
      entry(6, "across", 2, 0, 5, "ROUTE"),
      entry(7, "across", 3, 0, 5, "ASSET"),
      entry(8, "across", 4, 0, 4, "BEER"),
    ],
  };
}

function typeWord(state, word) {
  let next = state;
  for (const letter of word) next = typeLetter(next, letter);
  return next;
}

describe("decodePuzzle", () => {
  test("decodes base64 answers and builds the solution grid", () => {
    const puzzle = decodePuzzle(makeToyPuzzle());
    assert.equal(puzzle.solution[0][0], "B");
    assert.equal(puzzle.solution[1][1], "R");
    assert.equal(puzzle.solution[2][2], "D");
  });

  test("accepts a JSON string as well as an object", () => {
    const puzzle = decodePuzzle(JSON.stringify(makeToyPuzzle()));
    assert.equal(puzzle.id, "toy-3");
  });

  test("builds a block mask from the grid's # characters", () => {
    const puzzle = decodePuzzle(makeBlockedPuzzle());
    assert.equal(puzzle.blockMask[0][0], true);
    assert.equal(puzzle.blockMask[4][4], true);
    assert.equal(puzzle.blockMask[0][1], false);
  });

  test("every white cell resolves both directions via cellSlots", () => {
    const puzzle = decodePuzzle(makeToyPuzzle());
    for (let row = 0; row < 3; row++) {
      for (let col = 0; col < 3; col++) {
        assert.notEqual(puzzle.cellSlots[row][col].across, null);
        assert.notEqual(puzzle.cellSlots[row][col].down, null);
      }
    }
  });
});

describe("createInitialState", () => {
  test("cells start as . for white and # for block", () => {
    const state = createInitialState(decodePuzzle(makeBlockedPuzzle()));
    assert.equal(state.cells[0], "#....");
    assert.equal(state.cells[4], "....#");
  });

  test("cursor starts at the first entry", () => {
    const state = createInitialState(decodePuzzle(makeToyPuzzle()));
    assert.deepEqual(state.cursor, { row: 0, col: 0, direction: "across" });
  });
});

describe("selection and direction", () => {
  test("clicking a new cell selects it, keeping direction", () => {
    const state = createInitialState(decodePuzzle(makeToyPuzzle()));
    const next = selectCell(state, 1, 1);
    assert.deepEqual(next.cursor, { row: 1, col: 1, direction: "across" });
  });

  test("clicking the already-selected cell toggles direction", () => {
    const state = createInitialState(decodePuzzle(makeToyPuzzle()));
    const next = selectCell(state, 0, 0);
    assert.equal(next.cursor.direction, "down");
    assert.equal(next.cursor.row, 0);
    assert.equal(next.cursor.col, 0);
  });

  test("clicking a block cell is a no-op", () => {
    const state = createInitialState(decodePuzzle(makeBlockedPuzzle()));
    const next = selectCell(state, 0, 0);
    assert.deepEqual(next.cursor, state.cursor);
  });

  test("toggleDirection flips across <-> down", () => {
    const state = createInitialState(decodePuzzle(makeToyPuzzle()));
    assert.equal(toggleDirection(state).cursor.direction, "down");
    assert.equal(toggleDirection(toggleDirection(state)).cursor.direction, "across");
  });
});

describe("arrow-key movement", () => {
  test("moving along the current axis steps the cursor", () => {
    const state = createInitialState(decodePuzzle(makeToyPuzzle()));
    const next = moveCursor(state, "ArrowRight");
    assert.deepEqual(next.cursor, { row: 0, col: 1, direction: "across" });
  });

  test("an off-axis arrow only switches direction on the first press", () => {
    const state = createInitialState(decodePuzzle(makeToyPuzzle())); // direction: across
    const switched = moveCursor(state, "ArrowDown");
    assert.equal(switched.cursor.direction, "down");
    assert.equal(switched.cursor.row, 0, "first press must not move the cursor");
    assert.equal(switched.cursor.col, 0);

    const moved = moveCursor(switched, "ArrowDown");
    assert.equal(moved.cursor.row, 1, "second press, now on-axis, moves");
  });

  test("movement skips over a block to the next white cell", () => {
    const puzzle = decodePuzzle(makeBlockedPuzzle());
    let state = createInitialState(puzzle);
    state = { ...state, cursor: { row: 0, col: 1, direction: "across" } };
    const next = moveCursor(state, "ArrowLeft");
    // (0,0) is a block; the puzzle boundary is right past it, so the cursor
    // must not move onto the block, and there is nothing further left.
    assert.deepEqual(next.cursor, state.cursor);
  });

  test("movement stops (does not move) at the grid edge", () => {
    const state = createInitialState(decodePuzzle(makeToyPuzzle()));
    const next = moveCursor(state, "ArrowLeft");
    assert.deepEqual(next.cursor, state.cursor);
  });

  test("an unrecognized key is a no-op", () => {
    const state = createInitialState(decodePuzzle(makeToyPuzzle()));
    assert.deepEqual(moveCursor(state, "Escape"), state);
  });
});

describe("typing and advancing", () => {
  test("typing fills the cell and advances to the next empty one", () => {
    const state = createInitialState(decodePuzzle(makeToyPuzzle()));
    const next = typeLetter(state, "B");
    assert.equal(next.cells[0][0], "B");
    assert.deepEqual(next.cursor, { row: 0, col: 1, direction: "across" });
  });

  test("typing a full slot stops at the last cell once filled", () => {
    let state = createInitialState(decodePuzzle(makeToyPuzzle()));
    state = typeWord(state, "BAT");
    assert.equal(state.cells[0], "BAT");
    assert.deepEqual(state.cursor, { row: 0, col: 2, direction: "across" });
  });

  test("typing skips over already-filled cells", () => {
    let state = createInitialState(decodePuzzle(makeToyPuzzle()));
    state = typeLetter(state, "B");
    state = { ...state, cursor: { row: 0, col: 2, direction: "across" } };
    state = typeLetter(state, "T"); // fills the last cell, leaving col 1 empty
    state = { ...state, cursor: { row: 0, col: 0, direction: "across" } };
    state = typeLetter(state, "B"); // re-typing col 0 should advance to col 1, not col 2
    assert.deepEqual(state.cursor, { row: 0, col: 1, direction: "across" });
  });

  test("lowercase and non-letter input is normalized or ignored", () => {
    const state = createInitialState(decodePuzzle(makeToyPuzzle()));
    const lower = typeLetter(state, "b");
    assert.equal(lower.cells[0][0], "B");
    const digit = typeLetter(state, "5");
    assert.deepEqual(digit, state);
  });

  test("editing a cell clears its wrong and revealed markers", () => {
    let state = createInitialState(decodePuzzle(makeToyPuzzle()));
    state = typeLetter(state, "Z"); // wrong letter for (0,0); cursor advances to (0,1)
    state = { ...state, cursor: { row: 0, col: 0, direction: "across" } };
    state = checkCell(state);
    assert.ok(state.wrong.has("0,0"));
    state = typeLetter(state, "B");
    assert.ok(!state.wrong.has("0,0"));
  });
});

describe("backspace", () => {
  test("clears a filled cell without moving", () => {
    let state = createInitialState(decodePuzzle(makeToyPuzzle()));
    state = typeLetter(state, "B"); // cursor now at (0,1)
    state = { ...state, cursor: { row: 0, col: 0, direction: "across" } };
    state = backspace(state);
    assert.equal(state.cells[0][0], ".");
    assert.deepEqual(state.cursor, { row: 0, col: 0, direction: "across" });
  });

  test("on an empty cell, steps back and clears the previous cell", () => {
    let state = createInitialState(decodePuzzle(makeToyPuzzle()));
    state = typeLetter(state, "B"); // (0,0) filled, cursor at (0,1)
    state = backspace(state); // (0,1) already empty -> step back, clear (0,0)
    assert.equal(state.cells[0][0], ".");
    assert.deepEqual(state.cursor, { row: 0, col: 0, direction: "across" });
  });

  test("backspace at the very start of a slot is a no-op", () => {
    const state = createInitialState(decodePuzzle(makeToyPuzzle()));
    assert.deepEqual(backspace(state), state);
  });
});

describe("tab slot cycling", () => {
  test("Tab jumps to the next slot's first empty cell", () => {
    const state = createInitialState(decodePuzzle(makeToyPuzzle()));
    const next = nextSlot(state, 1);
    assert.deepEqual(next.cursor, { row: 0, col: 0, direction: "down" });
  });

  test("Shift+Tab jumps to the previous slot", () => {
    const state = createInitialState(decodePuzzle(makeToyPuzzle()));
    const next = nextSlot(state, -1);
    // Entries in order: 1-across, 1-down, 2-down, 3-down, 4-across, 5-across.
    // From the first (1-across), the previous one wraps to the last: 5-across.
    assert.deepEqual(next.cursor, { row: 2, col: 0, direction: "across" });
  });

  test("Tab wraps from the last slot back to the first, crossing directions", () => {
    const state = createInitialState(decodePuzzle(makeToyPuzzle()));
    const atLast = { ...state, cursor: { row: 2, col: 0, direction: "across" } }; // 5-across
    const wrapped = nextSlot(atLast, 1);
    assert.deepEqual(wrapped.cursor, { row: 0, col: 0, direction: "across" });
  });

  test("Tab skips to the first empty cell, not just the slot start", () => {
    let state = createInitialState(decodePuzzle(makeToyPuzzle()));
    state = typeLetter(state, "B"); // fills (0,0), cursor moves to (0,1)
    // Jump to slot 1 (down, starting at 0,0) — its first cell is filled,
    // so the first *empty* cell in it is (1,0).
    const toDown = nextSlot({ ...state, cursor: { row: 0, col: 0, direction: "across" } }, 1);
    assert.deepEqual(toDown.cursor, { row: 1, col: 0, direction: "down" });
  });
});

describe("check", () => {
  test("checkCell marks a wrong letter and leaves a correct one unmarked", () => {
    let state = createInitialState(decodePuzzle(makeToyPuzzle()));
    state = typeLetter(state, "Z"); // cursor advances to (0,1); check (0,0) explicitly
    state = { ...state, cursor: { row: 0, col: 0, direction: "across" } };
    state = checkCell(state);
    assert.ok(state.wrong.has("0,0"));

    let correctState = createInitialState(decodePuzzle(makeToyPuzzle()));
    correctState = typeLetter(correctState, "B");
    correctState = { ...correctState, cursor: { row: 0, col: 0, direction: "across" } };
    correctState = checkCell(correctState);
    assert.ok(!correctState.wrong.has("0,0"));
  });

  test("checkCell on an empty cell marks nothing", () => {
    const state = createInitialState(decodePuzzle(makeToyPuzzle()));
    assert.equal(checkCell(state).wrong.size, 0);
  });

  test("checkWord marks every wrong letter in the slot", () => {
    let state = createInitialState(decodePuzzle(makeToyPuzzle()));
    state = typeWord(state, "ZZZ");
    state = checkWord(state);
    assert.equal(state.wrong.size, 3);
  });

  test("checkAll marks wrong letters across the whole grid", () => {
    let state = createInitialState(decodePuzzle(makeToyPuzzle()));
    state = typeWord(state, "ZAT"); // (0,0) wrong, (0,1)/(0,2) correct for BAT
    state = checkAll(state);
    assert.ok(state.wrong.has("0,0"));
    assert.equal(state.wrong.size, 1);
  });
});

describe("reveal", () => {
  test("revealCell fills the correct letter and marks it revealed", () => {
    let state = createInitialState(decodePuzzle(makeToyPuzzle()));
    state = revealCell(state);
    assert.equal(state.cells[0][0], "B");
    assert.ok(state.revealed.has("0,0"));
  });

  test("revealWord fills the whole current slot", () => {
    let state = createInitialState(decodePuzzle(makeToyPuzzle()));
    state = revealWord(state);
    assert.equal(state.cells[0], "BAT");
    assert.equal(state.revealed.size, 3);
  });

  test("revealAll solves the puzzle and marks completed", () => {
    let state = createInitialState(decodePuzzle(makeToyPuzzle()));
    state = revealAll(state);
    assert.equal(state.cells.join(""), "BATOREWED");
    assert.equal(state.completed, true);
  });

  test("revealing a cell clears any wrong marker on it", () => {
    let state = createInitialState(decodePuzzle(makeToyPuzzle()));
    state = typeLetter(state, "Z"); // cursor advances to (0,1)
    state = { ...state, cursor: { row: 0, col: 0, direction: "across" } };
    state = checkCell(state);
    assert.ok(state.wrong.has("0,0"));
    state = revealCell(state);
    assert.ok(!state.wrong.has("0,0"));
  });
});

describe("isComplete / solvedWithoutHelp", () => {
  test("false while any white cell is wrong or empty", () => {
    let state = createInitialState(decodePuzzle(makeToyPuzzle()));
    assert.equal(isComplete(state), false);
    state = typeWord(state, "BAT");
    assert.equal(isComplete(state), false); // down slots still empty
  });

  test("true only once every white cell matches the solution", () => {
    // Across BAT fills row 0; the three down slots (BOW/ARE/TED) share that
    // row, so only rows 1-2 of each down slot remain to be typed.
    let state = createInitialState(decodePuzzle(makeToyPuzzle()));
    state = typeWord(state, "BAT");
    state = { ...state, cursor: { row: 1, col: 0, direction: "down" } };
    state = typeWord(state, "OW");
    state = { ...state, cursor: { row: 1, col: 1, direction: "down" } };
    state = typeWord(state, "RE");
    state = { ...state, cursor: { row: 1, col: 2, direction: "down" } };
    state = typeWord(state, "ED");
    assert.equal(isComplete(state), true);
    assert.equal(state.completed, true, "typeLetter keeps state.completed in sync");
  });

  test("solvedWithoutHelp is false once anything was revealed", () => {
    let state = createInitialState(decodePuzzle(makeToyPuzzle()));
    state = revealAll(state);
    assert.equal(isComplete(state), true);
    assert.equal(solvedWithoutHelp(state), false);
  });
});

describe("save round trip", () => {
  test("serialize then restore reproduces cells, marks, and progress", () => {
    const puzzle = decodePuzzle(makeToyPuzzle());
    let state = createInitialState(puzzle);
    state = typeWord(state, "ZAT"); // one wrong letter
    state = checkWord(state);
    state = { ...state, elapsedSeconds: 42 };

    const saved = serializeSave(state);
    const restored = restoreSave(puzzle, saved);

    assert.deepEqual(restored.cells, state.cells);
    assert.deepEqual(Array.from(restored.wrong).sort(), Array.from(state.wrong).sort());
    assert.deepEqual(restored.revealed, state.revealed);
    assert.equal(restored.elapsedSeconds, 42);
    assert.equal(restored.completed, state.completed);
  });

  test("restoring with no saved marks yields empty sets", () => {
    const puzzle = decodePuzzle(makeToyPuzzle());
    const restored = restoreSave(puzzle, { cells: ["...", "...", "..."] });
    assert.equal(restored.wrong.size, 0);
    assert.equal(restored.revealed.size, 0);
    assert.equal(restored.elapsedSeconds, 0);
    assert.equal(restored.completed, false);
  });

  test("a completed, fully revealed save round-trips as complete", () => {
    const puzzle = decodePuzzle(makeToyPuzzle());
    let state = createInitialState(puzzle);
    state = revealAll(state);
    const restored = restoreSave(puzzle, serializeSave(state));
    assert.equal(isComplete(restored), true);
    assert.equal(restored.completed, true);
  });
});

describe("integration on the blocked 5x5 fixture", () => {
  test("currentSlot resolves correctly around a block", () => {
    const puzzle = decodePuzzle(makeBlockedPuzzle());
    const state = { ...createInitialState(puzzle), cursor: { row: 0, col: 1, direction: "across" } };
    const slot = currentSlot(state);
    assert.equal(slot.answer, "CHEF");
  });

  test("solving the whole grid across all entries completes the puzzle", () => {
    const puzzle = decodePuzzle(makeBlockedPuzzle());
    let state = createInitialState(puzzle);
    for (const [word, row, col, direction] of [
      ["CHEF", 0, 1, "across"],
      ["CLONE", 1, 0, "across"],
      ["ROUTE", 2, 0, "across"],
      ["ASSET", 3, 0, "across"],
      ["BEER", 4, 0, "across"],
    ]) {
      state = { ...state, cursor: { row, col, direction } };
      state = typeWord(state, word);
    }
    assert.equal(isComplete(state), true);
  });
});
