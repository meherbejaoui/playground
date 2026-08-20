/**
 * DOM binding for the Cellblock player (PLAN.md 6, interaction spec items 1-8).
 *
 * All puzzle-solving logic lives in player-core.js; this module only reads
 * and writes the page. mountPlayer() is the single entry point.
 */
import { decodePuzzle, createInitialState, setActiveTool, moveCursor, applyTool, dragValue, paintCell, lineSatisfied, checkCells, reveal, clearAll, isComplete, serializeSave, restoreSave } from "./player-core.js";

const SAVE_DEBOUNCE_MS = 400;

function escapeHtml(text) {
  return String(text)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function formatTime(totalSeconds) {
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;
  return `${minutes}:${String(seconds).padStart(2, "0")}`;
}

function formatClue(run) {
  return run.length ? run.join(" ") : "0";
}

function shellHtml(puzzle) {
  return `
    <header class="cb-header">
      <h1 class="cb-title" data-el="title"></h1>
      <div class="cb-timer" data-el="timer" aria-live="off">0:00</div>
    </header>
    <div class="cb-body">
      <div class="cb-grid-scroll">
        <div class="cb-grid-area" data-el="grid" tabindex="-1"
             style="grid-template-columns: auto repeat(${puzzle.cols}, 1fr); grid-template-rows: auto repeat(${puzzle.rows}, 1fr);"></div>
      </div>
      <div class="cb-toolbar">
        <div class="cb-tool-group">
          <button type="button" class="cb-tool" data-action="tool-fill">Fill</button>
          <button type="button" class="cb-tool" data-action="tool-mark">&#10007;</button>
        </div>
        <details class="cb-menu">
          <summary>Check</summary>
          <div class="cb-menu-body">
            <button type="button" data-action="check-cell">This cell</button>
            <button type="button" data-action="check-all">Whole grid</button>
          </div>
        </details>
        <details class="cb-menu">
          <summary>Reveal</summary>
          <div class="cb-menu-body">
            <button type="button" data-action="reveal-cell">This cell</button>
            <button type="button" data-action="reveal-all">Whole grid</button>
          </div>
        </details>
        <button type="button" class="cb-btn" data-action="clear">Clear</button>
      </div>
    </div>
    <div class="cb-completion" data-el="completion" hidden></div>
  `;
}

function queryElements(root) {
  const byEl = (name) => root.querySelector(`[data-el="${name}"]`);
  return {
    title: byEl("title"),
    timer: byEl("timer"),
    grid: byEl("grid"),
    completion: byEl("completion"),
  };
}

function displayTitle(state, siteTitle) {
  if (state.puzzle.kind === "gallery") {
    return state.completed ? state.puzzle.title : "Gallery puzzle";
  }
  return siteTitle || state.puzzle.id;
}

function lineFromCells(cells, kind, index, rows, cols) {
  if (kind === "row") return cells[index].split("");
  const column = [];
  for (let r = 0; r < rows; r++) column.push(cells[r][index]);
  return column;
}

function renderGrid(gridEl, state) {
  const { rows, cols } = state.puzzle;
  const rowSatisfied = [];
  const colSatisfied = [];
  for (let r = 0; r < rows; r++) {
    rowSatisfied.push(lineSatisfied(state.puzzle.rowClues[r], lineFromCells(state.cells, "row", r, rows, cols)));
  }
  for (let c = 0; c < cols; c++) {
    colSatisfied.push(lineSatisfied(state.puzzle.colClues[c], lineFromCells(state.cells, "col", c, rows, cols)));
  }

  let html = '<div class="cb-corner"></div>';

  for (let c = 0; c < cols; c++) {
    const numbers = state.puzzle.colClues[c].length
      ? state.puzzle.colClues[c].map((n) => `<span>${n}</span>`).join("")
      : "<span>0</span>";
    const cls = colSatisfied[c] ? "cb-col-clue cb-clue--satisfied" : "cb-col-clue";
    html += `<div class="${cls}">${numbers}</div>`;
  }

  for (let r = 0; r < rows; r++) {
    const numbers = state.puzzle.rowClues[r].length
      ? state.puzzle.rowClues[r].map((n) => `<span>${n}</span>`).join("")
      : "<span>0</span>";
    const rowCls = rowSatisfied[r] ? "cb-row-clue cb-clue--satisfied" : "cb-row-clue";
    html += `<div class="${rowCls}">${numbers}</div>`;

    for (let c = 0; c < cols; c++) {
      const classes = ["cb-cell"];
      const value = state.cells[r][c];
      if (value === "1") classes.push("cb-cell--filled");
      if (value === "x") classes.push("cb-cell--mark");
      const key = `${r},${c}`;
      if (state.wrong.has(key)) classes.push("cb-cell--wrong");
      if (state.revealed.has(key)) classes.push("cb-cell--revealed");
      if (state.cursor.row === r && state.cursor.col === c) classes.push("cb-cell--selected");
      if ((c + 1) % 5 === 0 && c + 1 !== cols) classes.push("cb-cell--heavy-right");
      if ((r + 1) % 5 === 0 && r + 1 !== rows) classes.push("cb-cell--heavy-bottom");
      html += `<div class="${classes.join(" ")}" data-row="${r}" data-col="${c}"></div>`;
    }
  }

  gridEl.innerHTML = html;
}

function loadSave(puzzle, key) {
  try {
    const raw = window.localStorage.getItem(key);
    if (!raw) return null;
    return restoreSave(puzzle, JSON.parse(raw));
  } catch {
    return null;
  }
}

function persistSave(key, state) {
  try {
    window.localStorage.setItem(key, JSON.stringify(serializeSave(state)));
  } catch {
    /* storage unavailable or full: progress simply won't persist */
  }
}

/**
 * Mount an interactive player into `root` for the given served puzzle
 * payload (JSON string or parsed object, per decodePuzzle()).
 */
export function mountPlayer(root, rawPuzzle, options = {}) {
  const puzzle = decodePuzzle(rawPuzzle);
  const siteTitle = options.title || (typeof document !== "undefined" && document.title) || "";
  const saveKey = `cellblock:${puzzle.id}`;

  root.classList.add("cellblock-player");
  root.innerHTML = shellHtml(puzzle);
  const els = queryElements(root);

  let state = loadSave(puzzle, saveKey) || createInitialState(puzzle);
  let saveTimer = null;
  let tickHandle = null;
  let dragValueInProgress = null;
  let lastPaintedKey = null;

  function render() {
    els.title.textContent = displayTitle(state, siteTitle);
    renderGrid(els.grid, state);
    els.timer.textContent = formatTime(state.elapsedSeconds);
  }

  function scheduleSave() {
    if (saveTimer) window.clearTimeout(saveTimer);
    saveTimer = window.setTimeout(() => persistSave(saveKey, state), SAVE_DEBOUNCE_MS);
  }

  function onCompleted() {
    root.classList.add("cb-solved");
    els.completion.hidden = false;
    const label = state.puzzle.kind === "gallery" ? ` "${state.puzzle.title}"` : "";
    els.completion.textContent = `Solved${label} in ${formatTime(state.elapsedSeconds)}.`;
  }

  function setState(next) {
    const wasComplete = state.completed;
    state = next;
    render();
    scheduleSave();
    if (!wasComplete && state.completed) onCompleted();
  }

  function ensureTicking() {
    if (tickHandle || state.completed) return;
    tickHandle = window.setInterval(() => {
      if (document.hidden || state.completed) return;
      state = { ...state, elapsedSeconds: state.elapsedSeconds + 1 };
      els.timer.textContent = formatTime(state.elapsedSeconds);
      scheduleSave();
    }, 1000);
  }

  function cellAtPoint(x, y) {
    const el = document.elementFromPoint(x, y);
    const cell = el && el.closest ? el.closest(".cb-cell") : null;
    return cell && els.grid.contains(cell) ? cell : null;
  }

  function cellCoords(cell) {
    return [Number(cell.dataset.row), Number(cell.dataset.col)];
  }

  els.grid.addEventListener("contextmenu", (event) => event.preventDefault());

  els.grid.addEventListener("pointerdown", (event) => {
    const cell = event.target.closest(".cb-cell");
    if (!cell) return;
    event.preventDefault();
    // preventDefault() above also suppresses the browser's normal
    // click-elsewhere focus shift, so a previously-focused toolbar button
    // (Fill/Mark/Check/Reveal) would otherwise keep swallowing keyboard
    // input via the button/summary/a guard below. Claim focus on the grid
    // itself so keyboard control reliably resumes after any grid interaction.
    els.grid.focus({ preventScroll: true });
    const [row, col] = cellCoords(cell);
    const tool = event.button === 2 ? "mark" : state.activeTool;
    dragValueInProgress = dragValue(state, row, col, tool);
    lastPaintedKey = `${row},${col}`;
    setState({ ...paintCell(state, row, col, dragValueInProgress), cursor: { row, col } });
    ensureTicking();
  });

  els.grid.addEventListener("pointermove", (event) => {
    if (dragValueInProgress === null) return;
    const cell = cellAtPoint(event.clientX, event.clientY);
    if (!cell) return;
    const [row, col] = cellCoords(cell);
    const key = `${row},${col}`;
    if (key === lastPaintedKey) return;
    lastPaintedKey = key;
    setState({ ...paintCell(state, row, col, dragValueInProgress), cursor: { row, col } });
  });

  function endDrag() {
    dragValueInProgress = null;
    lastPaintedKey = null;
  }
  window.addEventListener("pointerup", endDrag);
  window.addEventListener("pointercancel", endDrag);

  document.addEventListener("keydown", (event) => {
    if (event.target && event.target.closest && event.target.closest("button, summary, a")) {
      return;
    }
    const key = event.key;
    if (key.startsWith("Arrow")) {
      event.preventDefault();
      setState(moveCursor(state, key));
    } else if (key === " " || key === "Spacebar" || key === "Enter") {
      event.preventDefault();
      setState(applyTool(state, state.cursor.row, state.cursor.col, "fill"));
      ensureTicking();
    } else if (key.toLowerCase() === "x") {
      event.preventDefault();
      setState(applyTool(state, state.cursor.row, state.cursor.col, "mark"));
      ensureTicking();
    }
  });

  root.addEventListener("click", (event) => {
    const button = event.target.closest("[data-action]");
    if (!button) return;
    const menu = button.closest(".cb-menu");
    const action = button.dataset.action;

    switch (action) {
      case "tool-fill":
        setState(setActiveTool(state, "fill"));
        break;
      case "tool-mark":
        setState(setActiveTool(state, "mark"));
        break;
      case "check-cell":
        setState(checkCells(state, "cell"));
        break;
      case "check-all":
        setState(checkCells(state, "all"));
        break;
      case "reveal-cell":
        setState(reveal(state, "cell"));
        break;
      case "reveal-all":
        if (window.confirm("Reveal the entire picture? This can't be undone.")) {
          setState(reveal(state, "all"));
        }
        break;
      case "clear":
        if (window.confirm("Clear all your fills and marks?")) {
          setState(clearAll(state));
        }
        break;
      default:
        return;
    }
    if (menu) menu.open = false;
    updateToolButtons();
  });

  function updateToolButtons() {
    root.querySelectorAll(".cb-tool").forEach((button) => {
      const isFill = button.dataset.action === "tool-fill";
      const active = (isFill && state.activeTool === "fill") || (!isFill && state.activeTool === "mark");
      button.classList.toggle("cb-tool--active", active);
    });
  }

  document.addEventListener("visibilitychange", () => {
    if (!document.hidden) ensureTicking();
  });

  render();
  updateToolButtons();
  if (state.completed) onCompleted();
}
