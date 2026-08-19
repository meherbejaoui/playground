"""Terminal rendering of a puzzle: the grid preview and the clue lists."""

from __future__ import annotations

from .puzzle import ACROSS, DOWN, Puzzle, decode_answer

CELL_WIDTH = 4
BLOCK_FILL = "█" * CELL_WIDTH  # full block, one per column of the cell


def _rule(left: str, middle: str, right: str, size: int) -> str:
    return left + middle.join(["─" * CELL_WIDTH] * size) + right


def render_grid(puzzle: Puzzle, solved: bool = True) -> str:
    """A boxed grid preview: clue numbers on top of each cell, letters below.

    With ``solved=False`` the letters are blanked, which is what a "here is
    the puzzle, go solve it" preview wants.
    """
    size = puzzle.size
    lines = [_rule("┌", "┬", "┐", size)]
    for row in range(size):
        number_cells: list[str] = []
        letter_cells: list[str] = []
        for col in range(size):
            if puzzle.is_block(row, col):
                number_cells.append(BLOCK_FILL)
                letter_cells.append(BLOCK_FILL)
                continue
            number = puzzle.numbers[row][col]
            number_cells.append(f"{number:<{CELL_WIDTH}}" if number > 0 else " " * CELL_WIDTH)
            letter = puzzle.grid[row][col] if solved else " "
            letter_cells.append(f" {letter}".ljust(CELL_WIDTH))
        lines.append("│" + "│".join(number_cells) + "│")
        lines.append("│" + "│".join(letter_cells) + "│")
        divider = (
            _rule("├", "┼", "┤", size)
            if row < size - 1
            else _rule("└", "┴", "┘", size)
        )
        lines.append(divider)
    return "\n".join(lines)


def render_clues(puzzle: Puzzle) -> str:
    """Numbered ACROSS and DOWN clue lists."""
    sections: list[str] = []
    for direction, heading in ((ACROSS, "ACROSS"), (DOWN, "DOWN")):
        entries = sorted(puzzle.entries_for(direction), key=lambda e: e.number)
        width = max((len(str(e.number)) for e in entries), default=1)
        body = "\n".join(f"  {entry.number:>{width}}. {entry.clue}" for entry in entries)
        sections.append(f"{heading}\n{body}" if body else heading)
    return "\n\n".join(sections)


def render_answers(puzzle: Puzzle) -> str:
    """Clue lists with their answers — for debugging a generated fill."""
    sections: list[str] = []
    for direction, heading in ((ACROSS, "ACROSS"), (DOWN, "DOWN")):
        entries = sorted(puzzle.entries_for(direction), key=lambda e: e.number)
        width = max((len(str(e.number)) for e in entries), default=1)
        body = "\n".join(
            f"  {entry.number:>{width}}. {decode_answer(entry.answer)} — {entry.clue}"
            for entry in entries
        )
        sections.append(f"{heading}\n{body}" if body else heading)
    return "\n\n".join(sections)


def render_puzzle(puzzle: Puzzle, solved: bool = True) -> str:
    """The full terminal preview: header, grid, then clues."""
    header = f"{puzzle.id}  (pattern: {puzzle.pattern}, seed: {puzzle.seed})"
    return "\n\n".join([header, render_grid(puzzle, solved=solved), render_clues(puzzle)])
