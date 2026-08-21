/**
 * DOM binding for the Gridlock player (PLAN.md 6, interaction spec items 1-6).
 *
 * All puzzle-solving logic lives in player-core.js; this module only reads
 * and writes the page. mountPlayer() is the single entry point.
 */
import { decodePuzzle, createInitialState, selectCell, moveCursor, nextSlot, typeLetter, backspace, checkCell, checkWord, checkAll, revealCell, revealWord, revealAll, clearAll, solvedWithoutHelp, serializeSave, restoreSave, currentSlot } from "./player-core.js";

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

function slotLabel(entry) {
  return `${entry.number}${entry.direction === "across" ? "A" : "D"}`;
}

function shellHtml(puzzle, title) {
  const acrossItems = puzzle.entries
    .filter((e) => e.direction === "across")
    .map(
      (e) =>
        `<li data-number="${e.number}" data-direction="across"><span class="gl-clue-number">${e.number}</span><span>${escapeHtml(e.clue)}</span></li>`
    )
    .join("");
  const downItems = puzzle.entries
    .filter((e) => e.direction === "down")
    .map(
      (e) =>
        `<li data-number="${e.number}" data-direction="down"><span class="gl-clue-number">${e.number}</span><span>${escapeHtml(e.clue)}</span></li>`
    )
    .join("");

  return `
    <nav class="gl-breadcrumb" aria-label="Breadcrumb">
      <a href="https://www.meherbejaoui.com/">meherbejaoui.com</a>
      <span aria-hidden="true">/</span>
      <a href="../../index.html">Puzzle Factories</a>
      <span aria-hidden="true">/</span>
      <a href="../index.html">Gridlock</a>
    </nav>
    <header class="gl-header">
      <h1 class="gl-title">${escapeHtml(title)}</h1>
      <div class="gl-timer" data-el="timer" aria-live="off">0:00</div>
    </header>
    <div class="gl-current-clue" data-el="current-clue" aria-live="polite">
      <span class="gl-current-clue-num" data-el="current-clue-num"></span>
      <span class="gl-current-clue-text" data-el="current-clue-text"></span>
    </div>
    <div class="gl-body">
      <div class="gl-grid-wrap">
        <div class="gl-grid" data-el="grid" role="grid" style="--size:${puzzle.size}"></div>
        <input class="gl-input" data-el="input" aria-hidden="true" autocomplete="off"
               autocapitalize="off" spellcheck="false" inputmode="text" maxlength="1">
        <div class="gl-toolbar">
          <details class="gl-menu">
            <summary>Check</summary>
            <div class="gl-menu-body">
              <button type="button" data-action="check-cell">This letter</button>
              <button type="button" data-action="check-word">This word</button>
              <button type="button" data-action="check-all">Whole puzzle</button>
            </div>
          </details>
          <details class="gl-menu">
            <summary>Reveal</summary>
            <div class="gl-menu-body">
              <button type="button" data-action="reveal-cell">This letter</button>
              <button type="button" data-action="reveal-word">This word</button>
              <button type="button" data-action="reveal-all">Whole puzzle</button>
            </div>
          </details>
          <button type="button" class="gl-btn" data-action="clear">Clear</button>
        </div>
      </div>
      <div class="gl-clues" data-el="clues">
        <div class="gl-clue-list" data-direction="across">
          <h2>Across</h2>
          <ol>${acrossItems}</ol>
        </div>
        <div class="gl-clue-list" data-direction="down">
          <h2>Down</h2>
          <ol>${downItems}</ol>
        </div>
      </div>
    </div>
    <div class="gl-completion" data-el="completion" hidden></div>
    <footer class="gl-footer">
      Built and maintained by <a href="https://www.meherbejaoui.com/">Meher Bejaoui</a>.
      <a href="https://github.com/meherbejaoui/puzzlefactory">Source on GitHub</a>.
    </footer>
  `;
}

function cellClasses(state, row, col) {
  const classes = ["gl-cell"];
  if (state.puzzle.blockMask[row][col]) {
    classes.push("gl-cell--block");
    return classes;
  }
  const key = `${row},${col}`;
  const slot = currentSlot(state);
  const inSlot = slot.cells.some(([r, c]) => r === row && c === col);
  const isCursor = state.cursor.row === row && state.cursor.col === col;
  if (inSlot) classes.push("gl-cell--slot");
  if (isCursor) classes.push("gl-cell--selected");
  if (state.wrong.has(key)) classes.push("gl-cell--wrong");
  if (state.revealed.has(key)) classes.push("gl-cell--revealed");
  return classes;
}

function renderGrid(gridEl, state) {
  const size = state.puzzle.size;
  let html = "";
  let index = 0;
  for (let row = 0; row < size; row++) {
    for (let col = 0; col < size; col++) {
      const classes = cellClasses(state, row, col);
      if (state.puzzle.blockMask[row][col]) {
        html += `<div class="${classes.join(" ")}" data-row="${row}" data-col="${col}"></div>`;
        continue;
      }
      const number = state.puzzle.numbers ? state.puzzle.numbers[row][col] : 0;
      const letter = state.cells[row][col];
      const display = letter === "." ? "" : letter;
      html += `<div class="${classes.join(" ")}" data-row="${row}" data-col="${col}" style="--cell-index:${index}">`;
      if (number > 0) html += `<span class="gl-cell-number">${number}</span>`;
      html += `${escapeHtml(display)}</div>`;
      index++;
    }
  }
  gridEl.innerHTML = html;
}

function renderClues(cluesEl, state) {
  const slot = currentSlot(state);
  cluesEl.querySelectorAll("li[data-number]").forEach((li) => {
    const active =
      Number(li.dataset.number) === slot.number && li.dataset.direction === slot.direction;
    li.classList.toggle("gl-clue--active", active);
  });
}

function renderCurrentClue(els, state) {
  const slot = currentSlot(state);
  els.currentClueNum.textContent = slotLabel(slot);
  els.currentClueText.textContent = slot.clue;
}

function renderTimer(els, state) {
  els.timer.textContent = formatTime(state.elapsedSeconds);
}

function queryElements(root) {
  const byEl = (name) => root.querySelector(`[data-el="${name}"]`);
  return {
    grid: byEl("grid"),
    input: byEl("input"),
    clues: byEl("clues"),
    currentClueNum: byEl("current-clue-num"),
    currentClueText: byEl("current-clue-text"),
    timer: byEl("timer"),
    completion: byEl("completion"),
  };
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
  const title = options.title || (typeof document !== "undefined" && document.title) || puzzle.id;
  const saveKey = `gridlock:${puzzle.id}`;

  root.classList.add("gridlock-player");
  root.innerHTML = shellHtml(puzzle, title);
  const els = queryElements(root);

  let state = loadSave(puzzle, saveKey) || createInitialState(puzzle);
  let saveTimer = null;
  let tickHandle = null;

  function render() {
    renderGrid(els.grid, state);
    renderClues(els.clues, state);
    renderCurrentClue(els, state);
    renderTimer(els, state);
  }

  function scheduleSave() {
    if (saveTimer) window.clearTimeout(saveTimer);
    saveTimer = window.setTimeout(() => persistSave(saveKey, state), SAVE_DEBOUNCE_MS);
  }

  function onCompleted() {
    root.classList.add("gl-solved");
    els.completion.hidden = false;
    els.completion.textContent = solvedWithoutHelp(state)
      ? `Solved without help in ${formatTime(state.elapsedSeconds)}!`
      : `Solved in ${formatTime(state.elapsedSeconds)}.`;
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
      renderTimer(els, state);
      scheduleSave();
    }, 1000);
  }

  els.grid.addEventListener("click", (event) => {
    const cell = event.target.closest(".gl-cell");
    if (!cell || cell.classList.contains("gl-cell--block")) return;
    setState(selectCell(state, Number(cell.dataset.row), Number(cell.dataset.col)));
    els.input.focus();
  });

  els.clues.addEventListener("click", (event) => {
    const li = event.target.closest("li[data-number]");
    if (!li) return;
    const number = Number(li.dataset.number);
    const direction = li.dataset.direction;
    const entry = puzzle.entries.find((e) => e.number === number && e.direction === direction);
    if (!entry) return;
    const firstEmpty = entry.cells.find(([r, c]) => state.cells[r][c] === ".");
    const [row, col] = firstEmpty || entry.cells[0];
    setState({ ...state, cursor: { row, col, direction } });
    els.input.focus();
  });

  els.input.addEventListener("keydown", (event) => {
    const key = event.key;
    if (key === "Backspace") {
      event.preventDefault();
      setState(backspace(state));
      ensureTicking();
    } else if (key === "Tab") {
      event.preventDefault();
      setState(nextSlot(state, event.shiftKey ? -1 : 1));
    } else if (key.startsWith("Arrow")) {
      event.preventDefault();
      setState(moveCursor(state, key));
    } else if (/^[a-zA-Z]$/.test(key)) {
      event.preventDefault();
      setState(typeLetter(state, key));
      ensureTicking();
    }
  });

  root.addEventListener("click", (event) => {
    const button = event.target.closest("[data-action]");
    if (!button) return;
    const menu = button.closest(".gl-menu");
    const action = button.dataset.action;

    switch (action) {
      case "check-cell":
        setState(checkCell(state));
        break;
      case "check-word":
        setState(checkWord(state));
        break;
      case "check-all":
        setState(checkAll(state));
        break;
      case "reveal-cell":
        setState(revealCell(state));
        break;
      case "reveal-word":
        setState(revealWord(state));
        break;
      case "reveal-all":
        if (window.confirm("Reveal the entire puzzle? This can't be undone.")) {
          setState(revealAll(state));
        }
        break;
      case "clear":
        if (window.confirm("Clear all your answers?")) {
          setState(clearAll(state));
        }
        break;
      default:
        return;
    }
    if (menu) menu.open = false;
    els.input.focus();
  });

  document.addEventListener("visibilitychange", () => {
    if (!document.hidden) ensureTicking();
  });

  render();
  if (state.completed) onCompleted();
}
