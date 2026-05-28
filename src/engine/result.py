"""Game result detection: checkmate, stalemate, and king capture."""

from __future__ import annotations

from src.engine.board import BLACK, GameState
from src.engine.hostage import get_drop_moves, get_exchange_options
from src.engine.moves import get_legal_board_moves, is_in_check


def _has_any_legal_action(state: GameState) -> bool:
    """Check if the active player has any legal action (move, drop, or exchange with drop)."""
    # Check normal board moves
    if get_legal_board_moves(state):
        return True

    # Check drop moves from airfield
    if get_drop_moves(state):
        return True

    # Check exchange options (which now strictly verify valid drop squares exist)
    return bool(get_exchange_options(state))


def check_game_result(state: GameState) -> str | None:
    """Determine the game result for the current position.

    Returns:
        None if the game is ongoing.
        'White wins by checkmate' / 'Black wins by checkmate'
        'Draw by stalemate'
        'White wins - Black king missing' / 'Black wins - White king missing'
    """
    colour = state.active

    # Check if either king is missing (shouldn't happen with proper rules, but defensive)
    white_king_exists = any("K" in row for row in state.board)
    black_king_exists = any("k" in row for row in state.board)

    if not white_king_exists:
        return "Black wins - White king captured"
    if not black_king_exists:
        return "White wins - Black king captured"

    # Check if the active player has any legal actions
    if not _has_any_legal_action(state):
        if is_in_check(state, colour):
            # Checkmate
            winner = "White" if colour == BLACK else "Black"
            return f"{winner} wins by checkmate"
        else:
            return "Draw by stalemate"

    return None
